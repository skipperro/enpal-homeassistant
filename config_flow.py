"""Config flow for IP check integration."""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from influxdb_client import InfluxDBClient

from .const import DOMAIN

big_int = vol.All(vol.Coerce(int), vol.Range(min=300))

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
            {
                vol.Required('enpal_host_ip', default='192.168.178.'): cv.string,
                vol.Required('enpal_host_port', default=8086): cv.positive_int,
                vol.Required('enpal_token', default=''): cv.string,
            }
        )

def validate_ipv4(s: str):
    # IPv4 address is a string of 4 numbers separated by dots
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True

async def get_health(ip: str, port: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'http://{ip}:{port}/health') as response:
            return await response.json()

async def check_for_influx(ip: str, port: int):
    resp = await get_health(ip, port)
    if resp['status'] == 'pass':
        return True
    return False

def check_token(ip: str, port: int, token: str) -> bool:
    query = 'from(bucket: "solar") \
      |> range(start: -2m) \
      |> aggregateWindow(every: 2m, fn: last, createEmpty: false) \
      |> yield(name: "last")'
    try:
        with InfluxDBClient(url=f'http://{ip}:{port}', token=token, org='enpal') as client:
            tables = client.query_api().query(query)
            return len(tables) > 0
    except Exception:
        return False

    if tables:
        if len(tables) > 10:
            return True
    return False


class CustomFlow(config_entries.ConfigFlow, domain=DOMAIN):
    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            self.data = user_input
            if not validate_ipv4(self.data['enpal_host_ip']):
                errors['base'] = 'invalid_ip'
            if self.data['enpal_host_port'] < 300:
                errors['base'] = 'port_too_low'
            if self.data['enpal_host_port'] > 65535:
                errors['base'] = 'port_too_high'
            if not self.data['enpal_token']:
                errors['base'] = 'token_empty'

            if not errors:
                influx_found = await self.hass.async_add_executor_job(
                    check_for_influx,
                    self.data['enpal_host_ip'],
                    self.data['enpal_host_port'],
                )
                if not influx_found:
                    errors['base'] = 'db_not_found'

            if not errors:
                token_valid = await self.hass.async_add_executor_job(
                    check_token,
                    self.data['enpal_host_ip'],
                    self.data['enpal_host_port'],
                    self.data['enpal_token'],
                )
                if not token_valid:
                    errors['base'] = 'token_invalid'

            if not errors:
                return self.async_create_entry(title="Enpal", data=self.data)

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        errors: Dict[str, str] = {}
        if user_input is not None:
            self.data = user_input
            if not validate_ipv4(self.data['enpal_host_ip']):
                errors['base'] = 'invalid_ip'
            if self.data['enpal_host_port'] < 300:
                errors['base'] = 'port_too_low'
            if self.data['enpal_host_port'] > 65535:
                errors['base'] = 'port_too_high'
            if not self.data['enpal_token']:
                errors['base'] = 'token_empty'

            if not errors:
                if not await check_for_influx(self.data['enpal_host_ip'], self.data['enpal_host_port']):
                    errors['base'] = 'db_not_found'
            if not errors:
                if not check_token(self.data['enpal_host_ip'], self.data['enpal_host_port'], self.data['enpal_token']):
                    errors['base'] = 'token_invalid'

            if not errors:
                return self.async_create_entry(title="Enpal", data={'enpal_host_ip': self.data['enpal_host_ip'], 'enpal_host_port': self.data['enpal_host_port'], 'enpal_token': self.data['enpal_token']})

        default_ip = ''
        if 'enpal_host_ip' in self.config_entry.data:
            default_ip = self.config_entry.data['enpal_host_ip']
        if 'enpal_host_ip' in self.config_entry.options:
            default_ip = self.config_entry.options['enpal_host_ip']

        default_port = 8086
        if 'enpal_host_port' in self.config_entry.data:
            default_port = self.config_entry.data['enpal_host_port']
        if 'enpal_host_port' in self.config_entry.options:
            default_port = self.config_entry.options['enpal_host_port']

        default_token = ''
        if 'enpal_token' in self.config_entry.data:
            default_token = self.config_entry.data['enpal_token']
        if 'enpal_token' in self.config_entry.options:
            default_token = self.config_entry.options['enpal_token']

        OPTIONS_SCHEMA = vol.Schema(
            {
                vol.Required('enpal_host_ip', default=default_ip): cv.string,
                vol.Required('enpal_host_port', default=default_port): cv.positive_int,
                vol.Required('enpal_token', default=default_token): cv.string,
            }
        )
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA, errors=errors)
