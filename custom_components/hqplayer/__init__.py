"""The HQPlayer integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .api import HQPlayerClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import HQPlayerDataUpdateCoordinator

type HQPlayerConfigEntry = ConfigEntry[HQPlayerDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HQPlayerConfigEntry) -> bool:
    """Set up HQPlayer from a config entry."""
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
