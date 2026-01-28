"""Config flow for IP check integration."""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

big_int = vol.All(vol.Coerce(int), vol.Range(min=300))

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
            {
                vol.Required('enpal_host_ip', default='192.168.178'): cv.string,
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

async def get_health(ip: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'http://{ip}/health') as response:
            return await response.json()

async def validate_device_messages(ip: str) -> bool:
    """Check if the /deviceMessages endpoint contains the word 'power'."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://{ip}/deviceMessages', timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    return "power" in html.lower()
    except Exception as e:
        _LOGGER.error(f"Error validating /deviceMessages for IP {ip}: {e}")
    return False

class CustomFlow(config_entries.ConfigFlow, domain=DOMAIN):
    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            self.data = user_input
            ip = self.data['enpal_host_ip']

            if not validate_ipv4(ip):
                errors['base'] = 'invalid_ip'
            elif not await validate_device_messages(ip):
                errors['base'] = 'invalid_device_messages'

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
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        errors: Dict[str, str] = {}
        if user_input is not None:
            self.data = user_input
            ip = self.data['enpal_host_ip']

            if not validate_ipv4(ip):
                errors['base'] = 'invalid_ip'
            elif not await validate_device_messages(ip):
                errors['base'] = 'invalid_device_messages'

            if not errors:
                return self.async_create_entry(title="Enpal", data={'enpal_host_ip': ip})

        default_ip = ''
        if 'enpal_host_ip' in self._config_entry.data:
            default_ip = self._config_entry.data['enpal_host_ip']
        if 'enpal_host_ip' in self._config_entry.options:
            default_ip = self._config_entry.options['enpal_host_ip']

        OPTIONS_SCHEMA = vol.Schema(
            {
                vol.Required('enpal_host_ip', default=default_ip): cv.string,
            }
        )
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA, errors=errors)

