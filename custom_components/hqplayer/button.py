"""Button entity for manual HQPlayer refresh."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HQPlayerConfigEntry
from .coordinator import HQPlayerDataUpdateCoordinator
from .entity import HQPlayerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HQPlayerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HQPlayer button entities."""
    coordinator = entry.runtime_data
    async_add_entities([HQPlayerRefreshButton(coordinator, entry.entry_id)])


class HQPlayerRefreshButton(HQPlayerEntity, ButtonEntity):
    """Button to manually refresh HQPlayer state and dynamic lists."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: HQPlayerDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator, entry_id, "refresh")

    @property
    def available(self) -> bool:
        """Return False while a command and state refresh are in progress."""
        return super().available and not self.coordinator.busy

    async def async_press(self) -> None:
        """Trigger a manual coordinator refresh."""
        await self.coordinator.async_request_refresh()
