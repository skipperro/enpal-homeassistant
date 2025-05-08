"""Enpal Home‑Assistant Integration – **HTML‑scraping** edition
----------------------------------------------------------------
This version replaces the original InfluxDB approach.  It fetches
``http://<IP>/deviceMessages`` from an Enpal Box, parses
**every** row in the resulting HTML tables and exposes them as Home‑Assistant
`sensor` entities.

Highlights
~~~~~~~~~~
* **One network request per polling interval** – a shared `_EnpalData` helper
  caches the last response. The cache Time‑To‑Live is always **½ of `SCAN_INTERVAL`**
* **Testable without Home Assistant** – just run python3 sensor.py [IP]
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import timedelta
from time import monotonic
from typing import Dict, Tuple, Optional

import aiohttp
from bs4 import BeautifulSoup  # Add to manifest.json → "beautifulsoup4==4.12.3"

# Home‑Assistant imports are only present when running inside HA.  We guard
# them so the file can still be executed stand‑alone for testing.
try:
    from homeassistant import config_entries
    from homeassistant.components.sensor import SensorEntity
    from homeassistant.const import CONF_HOST
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_registry import (
        async_entries_for_config_entry,
        async_get,
    )

    # Domain constant provided by ``custom_components.enpal.const``
    from custom_components.enpal.const import DOMAIN
except ModuleNotFoundError:  # Stand‑alone mode (no Home Assistant environment)
    HomeAssistant = object  # type: ignore[misc,assignment]
    config_entries = SensorEntity = async_entries_for_config_entry = async_get = CONF_HOST = DOMAIN = None  # type: ignore

__all__ = [
    "SCAN_INTERVAL",
    "async_scrape_enpal",
    "scrape_enpal",
    # HA classes are exported only when inside HA
]

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)
VERSION = "0.4.0"

_UNIT_MAP: Dict[str, Tuple[Optional[str], str]] = {
    "W": ("power", "mdi:flash"),
    "kW": ("power", "mdi:flash"),
    "Wh": ("energy", "mdi:lightning-bolt"),
    "kWh": ("energy", "mdi:lightning-bolt"),
    "V": ("voltage", "mdi:flash"),
    "A": ("current", "mdi:current-ac"),
    "Hz": ("frequency", "mdi:sine-wave"),
    "%": ("battery", "mdi:battery"),
    "°C": ("temperature", "mdi:thermometer"),
    "Minutes": (None, "mdi:timer-sand"),
}

# ---------------------------------------------------------------------------
# Regular expressions for value parsing
# ---------------------------------------------------------------------------
_NUMBER_WITH_UNIT = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([^\d\s]+)?.*$")
_NUMBER_IN_PAREN = re.compile(r"\(([-+]?\d+(?:\.\d+)?)\)\s*$")


def _parse_value(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a table‑cell string into ``(value, unit)``.

    Supported formats
    -----------------
    1. *Trailing* number in parentheses – the whole value is taken from the last
       parenthetical group and returned **without** a unit.  Examples::

           "On‑grid mode (200)"   → ("On‑grid mode (200)", None)
           "Health (99)"          → ("Health (99)", None)

    2. Number followed by an optional unit abbreviation.  Examples::

           "18.52kWh"   → ("18.52", "kWh")
           "2366.35 W"  → ("2366.35", "W")

    3. Non-numeric values (e.g., serial numbers). Examples::

           "SerialNumber: HV1110112411" → ("SerialNumber: HV1110112411", None)
    """

    # Case 1 – (123) at the end of the string
    paren_match = _NUMBER_IN_PAREN.search(text)
    if paren_match:
        # Return the full text if no unit is present
        return text, None

    # Case 2 – generic "number[ unit]" pattern
    unit_match = _NUMBER_WITH_UNIT.match(text)
    if unit_match:
        numeric_str, unit_str = unit_match.groups()
        return numeric_str, (unit_str or None)

    # Case 3 – fallback for non-numeric values
    if text.strip():
        return text, None

    # Fallback – nothing recognised
    return None, None


# ---------------------------------------------------------------------------
# Pure HTML → dict parser (usable outside Home Assistant)
# ---------------------------------------------------------------------------

def _parse_device_messages_html(html: str) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """Return ``{row_name: (value, unit)}`` from raw ``/deviceMessages`` HTML."""
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        if not tbody:
            continue
        for tr in tbody.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            name = tds[0].get_text(strip=True)
            raw_value = tds[1].get_text(strip=True)
            value, unit = _parse_value(raw_value)

            # Convert Wh to kWh if applicable
            if unit == "Wh" and value is not None:
                try:
                    value = str(float(value) / 1000)
                    unit = "kWh"
                except ValueError:
                    pass

            # Skip empty values
            if value is None:
                continue

            data[name] = (value, unit)

    return data


async def async_scrape_enpal(ip: str) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """**Async** helper – download and parse ``/deviceMessages`` from *ip*."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{ip}/deviceMessages", timeout=15) as resp:
            html = await resp.text()
    return _parse_device_messages_html(html)


def scrape_enpal(ip: str) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """**Sync** wrapper around :pyfunc:`async_scrape_enpal` for quick CLI tests."""
    return asyncio.run(async_scrape_enpal(ip))


# ---------------------------------------------------------------------------
# Home‑Assistant specific implementation
# ---------------------------------------------------------------------------

class _EnpalData:
    """Shared fetch‑and‑cache manager.  One instance per Config Entry."""

    def __init__(self, hass: HomeAssistant, ip: str) -> None:
        self._hass = hass
        self._ip = ip
        self._cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        self._last_fetch: float = 0.0  # monotonic time
        self._ttl = int(SCAN_INTERVAL.total_seconds() / 2)  # half interval
        self._lock = asyncio.Lock()

    @property
    def data(self) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        return self._cache

    # ---------------------------------------------------------------------
    # Home Assistant calls `async_update` on **every** entity, but we only
    # hit the Enpal Box once because of the TTL + lock.
    # ---------------------------------------------------------------------
    async def async_update(self) -> None:
        """Fetch new data if the cache expired."""
        now = monotonic()
        if self._cache and now - self._last_fetch < self._ttl:
            return  # fresh

        async with self._lock:
            # Another coroutine may already have refreshed the cache while we
            # were waiting for the lock – check again.
            now = monotonic()
            if self._cache and now - self._last_fetch < self._ttl:
                return

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://{self._ip}/deviceMessages", timeout=15
                    ) as resp:
                        html = await resp.text()
            except Exception as exc:
                _LOGGER.warning("Enpal fetch failed: %s", exc)
                return

            self._cache = _parse_device_messages_html(html)
            self._last_fetch = monotonic()


# ---------------------------------------------------------------------------
# Skip the Home‑Assistant parts when running this file directly for testing.
# ---------------------------------------------------------------------------
if HomeAssistant is not object:

    async def async_setup_entry(hass: HomeAssistant, entry: "config_entries.ConfigEntry", async_add_entities):
        """Called by Home Assistant when the Config Entry is added / reloaded.

        It builds the list of `EnpalSensor` entities **once**, based on the rows
        currently present in the HTML.  When `/deviceMessages` adds new rows
        you need to reload the integration (or restart HA) to pick them up –
        matching the behaviour of the original InfluxDB version.
        """
        ip: str = entry.data["enpal_host_ip"]

        fetcher = _EnpalData(hass, ip)
        # Prime the cache so we know which sensors exist before registering
        await fetcher.async_update()

        sensors = []
        for row_name, (_, unit) in fetcher.data.items():
            device_class, default_icon = _UNIT_MAP.get(unit, (None, "mdi:gauge"))
            sensors.append(
                EnpalSensor(row_name, unit, device_class, default_icon, fetcher)
            )

        # Clean up any entities that may have disappeared (renamed rows, etc.)
        registry = async_get(hass)
        for entity_entry in async_entries_for_config_entry(registry, entry.entry_id):
            registry.async_remove(entity_entry.entity_id)

        async_add_entities(sensors, update_before_add=True)


    class EnpalSensor(SensorEntity):
        """Home‑Assistant entity matching a single row from `/deviceMessages`."""

        _attr_state_class = "measurement"

        def __init__(
            self,
            row_name: str,
            unit: Optional[str],
            device_class: Optional[str],
            icon: str,
            fetcher: _EnpalData,
        ) -> None:
            self._row_name = row_name
            self._unit = unit
            self._fetcher = fetcher

            # Derive a safe unique_id and entity_id suffix
            slug = re.sub(r"[^a-z0-9_]+", "_", row_name.strip().lower())
            self._attr_unique_id = f"enpal_{slug}"
            self._attr_name = f"Enpal {row_name}"
            self._attr_icon = icon
            self._attr_device_class = device_class
            self._attr_native_unit_of_measurement = unit

        async def async_update(self) -> None:
            """Home Assistant schedules this approximately every SCAN_INTERVAL."""
            await self._fetcher.async_update()
            value, unit = self._fetcher.data.get(self._row_name, (None, self._unit))

            # Determine if the value should be a float or remain a string
            if unit and value is not None:
                try:
                    self._attr_native_value = float(value)
                except ValueError:
                    self._attr_native_value = value
            else:
                self._attr_native_value = value


# ---------------------------------------------------------------------------
# Optional command‑line interface
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # Run "python sensor.py <ip>" for a quick test
    if len(sys.argv) != 2:
        print("Usage: python sensor.py <inverter-ip>")
        sys.exit(1)

    ip_arg = sys.argv[1]
    results = scrape_enpal(ip_arg)
    for key, (val, unit) in sorted(results.items()):
        print(f"{key:40s} : {val} {unit or ''}")
