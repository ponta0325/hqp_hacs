"""The HQPlayer integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import HQPlayerClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import HQPlayerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

STATIC_URL_PATH = "/hqplayer_files"
DASHBOARD_JS_FILE = "hqplayer-dashboard.js"
DASHBOARD_JS_VERSION = "0.1.19"

type HQPlayerConfigEntry = ConfigEntry[HQPlayerDataUpdateCoordinator]


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register static frontend files and dashboard strategy JS."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("frontend_registered"):
        return

    www_dir = Path(__file__).parent / "www"
    js_file = www_dir / DASHBOARD_JS_FILE
    if not await hass.async_add_executor_job(js_file.is_file):
        _LOGGER.error("HQPlayer dashboard JS not found at %s", js_file)
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(www_dir), False)]
    )
    js_url = f"{STATIC_URL_PATH}/{DASHBOARD_JS_FILE}?v={DASHBOARD_JS_VERSION}"
    add_extra_js_url(hass, js_url)
    domain_data["frontend_registered"] = True
    _LOGGER.debug("Registered HQPlayer dashboard JS at %s", js_url)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the HQPlayer integration component."""
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HQPlayerConfigEntry) -> bool:
    """Set up HQPlayer from a config entry."""
    await _async_register_frontend(hass)

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    client = HQPlayerClient(host=host, port=port)
    coordinator = HQPlayerDataUpdateCoordinator(hass, client, scan_interval)

    await coordinator.async_config_entry_first_refresh()
    coordinator.start_subscription()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: HQPlayerConfigEntry
) -> None:
    """Reload integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HQPlayerConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.stop_subscription()
        await entry.runtime_data.client.disconnect()
    return unload_ok
