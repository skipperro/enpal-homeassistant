"""Config Flow for Enpal HTML‑scraper integration.

Home Assistant uses a *Config Flow* to collect user input at setup time and to
validate that the integration can connect.  This file therefore:

1. Prompts the user for the inverter’s **IP address**.
2. Performs a *live* fetch of ``/deviceMessages`` to verify the host is
   reachable.
3. Creates a Config Entry storing the IP so that :pyfunc:`sensor.async_setup_entry`
   can spin up the sensors.

The flow has only one step (`async_step_user`).  Re‑authentication support is
included for completeness, but in the current design it simply re‑runs the same
reachability test.
"""
from __future__ import annotations

import aiohttp
import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

# Import DOMAIN from our package’s const – falls back to a dummy when testing
try:
    from custom_components.enpal.const import DOMAIN
except ModuleNotFoundError:  # Stand‑alone lint/test run
    DOMAIN = "enpal"


_LOGGER = logging.getLogger(__name__)  # Re‑use sensor.py's logger name space


class EnpalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single‑step configuration flow collecting just the inverter’s IP."""

    VERSION = 2
    MINOR_VERSION = 0

    # ---------------------------------------------------------------------
    # Step 1 – shown when the user chooses “Add Integration → Enpal”
    # ---------------------------------------------------------------------
    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial form – request IP and validate reachability."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip: str = user_input[CONF_HOST]

            if await self._async_can_connect(ip):
                # Success – create Config Entry and finish the flow
                return self.async_create_entry(title=ip, data={"enpal_host_ip": ip})

            errors["base"] = "cannot_connect"

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # Helper – actually perform the reachability test
    # ------------------------------------------------------------------
    async def _async_can_connect(self, ip: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{ip}/deviceMessages", timeout=10) as resp:
                    return resp.status == 200
        except Exception as exc:  # noqa: BLE001 – network errors, timeouts, etc.
            _LOGGER.warning("Enpal config‑flow: cannot connect to %s – %s", ip, exc)
            return False

    # ------------------------------------------------------------------
    # Re‑auth support – called if HA detects credentials changed (not used
    # today but keeps the skeleton ready for future token‑based auth).
    # ------------------------------------------------------------------
    async def async_step_reauth(self, user_input: dict | None = None):
        """Handle re‑authentication – identical to the user step for now."""
        return await self.async_step_user(user_input)

    # ------------------------------------------------------------------
    # Home Assistant may call this to display the title in the UI before the
    # flow fully finishes (e.g. in the integrations list).
    # ------------------------------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):  # noqa: D401 – HA callback
        """No options flow for this integration."""
        return None