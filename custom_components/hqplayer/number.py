"""Number entity for HQPlayer volume control."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfSoundPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HQPlayerConfigEntry
from .const import MAX_VOLUME_DB, MIN_VOLUME_DB, VOLUME_STEP_DB
from .coordinator import HQPlayerDataUpdateCoordinator
from .entity import HQPlayerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HQPlayerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HQPlayer number entities."""
    coordinator = entry.runtime_data
    async_add_entities([HQPlayerVolumeNumber(coordinator, entry.entry_id)])


class HQPlayerVolumeNumber(HQPlayerEntity, NumberEntity):
    """Representation of HQPlayer Volume (dB)."""

    _attr_name = "Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = MIN_VOLUME_DB
    _attr_native_max_value = MAX_VOLUME_DB
    _attr_native_step = VOLUME_STEP_DB
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: HQPlayerDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the volume number entity."""
        super().__init__(coordinator, entry_id, "volume")

    @property
    def available(self) -> bool:
        """Return True if volume control is enabled on HQPlayer."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.volume_enabled
        )

    @property
    def native_min_value(self) -> float:
        """Return dynamic minimum volume in dB."""
        if (
            self.coordinator.data is not None
            and self.coordinator.data.volume_min is not None
        ):
            return self.coordinator.data.volume_min
        return MIN_VOLUME_DB

    @property
    def native_max_value(self) -> float:
        """Return dynamic maximum volume in dB."""
        if (
            self.coordinator.data is not None
            and self.coordinator.data.volume_max is not None
        ):
            return self.coordinator.data.volume_max
        return MAX_VOLUME_DB

    @property
    def native_value(self) -> float | None:
        """Return the current volume in dB."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.volume

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume in dB."""
        await self.coordinator.async_execute_command(
            self.coordinator.client.set_volume(value),
            verify=lambda s: s.volume is not None and abs(s.volume - value) < 0.2,
        )
