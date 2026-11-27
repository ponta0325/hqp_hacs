"""Sensor entities for HQPlayer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HQPlayerConfigEntry
from .api import HQPlayerState
from .coordinator import HQPlayerDataUpdateCoordinator
from .entity import HQPlayerEntity


@dataclass(frozen=True, kw_only=True)
class HQPlayerSensorDescription(SensorEntityDescription):
    """Describes an HQPlayer sensor entity."""

    value_fn: Callable[[HQPlayerState], str | None]


def _format_sample_rate(value: str | None) -> str | None:
    """Format sample rate in Hz to kHz or MHz."""
    if value is None or value == "":
        return None
    try:
        hz = int(float(value))
    except ValueError:
        return value
    if hz >= 1_000_000:
        return f"{hz / 1_000_000:.6f}".rstrip("0").rstrip(".") + " MHz"
    if hz >= 1_000:
        return f"{hz / 1_000:.3f}".rstrip("0").rstrip(".") + " kHz"
    return f"{hz} Hz"


SENSOR_DESCRIPTIONS: tuple[HQPlayerSensorDescription, ...] = (
    HQPlayerSensorDescription(
        key="playback_state",
        name="Playback State",
        icon="mdi:play-pause",
        value_fn=lambda s: s.state,
    ),
    HQPlayerSensorDescription(
        key="input_sample_rate",
        name="Input Sample Rate",
        icon="mdi:audio-input-stereo-minijack",
        value_fn=lambda s: _format_sample_rate(s.input_sample_rate),
    ),
    HQPlayerSensorDescription(
        key="output_sample_rate",
        name="Output Sample Rate",
        icon="mdi:speaker",
        value_fn=lambda s: _format_sample_rate(s.output_sample_rate),
    ),
    HQPlayerSensorDescription(
        key="input_format",
        name="Input Format",
        icon="mdi:file-music",
        value_fn=lambda s: s.input_format,
    ),
    HQPlayerSensorDescription(
        key="input_bits",
        name="Input Bit Depth",
        icon="mdi:sine-wave",
        value_fn=lambda s: s.input_bits,
    ),
    HQPlayerSensorDescription(
        key="output_format",
        name="Output Format",
        icon="mdi:file-music-outline",
        value_fn=lambda s: s.output_format,
    ),
    HQPlayerSensorDescription(
        key="output_bits",
        name="Output Bit Depth",
        icon="mdi:sine-wave",
        value_fn=lambda s: s.output_bits,
    ),
    HQPlayerSensorDescription(
        key="apod",
        name="Apodization Count",
        icon="mdi:waveform",
        value_fn=lambda s: s.apod,
    ),
    HQPlayerSensorDescription(
        key="clips",
        name="Clips Count",
        icon="mdi:alert-circle-outline",
        value_fn=lambda s: s.clips,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HQPlayerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HQPlayer sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        HQPlayerSensor(coordinator, entry.entry_id, description)
        for description in SENSOR_DESCRIPTIONS
    )


class HQPlayerSensor(HQPlayerEntity, SensorEntity):
    """Representation of an HQPlayer sensor entity."""

    entity_description: HQPlayerSensorDescription

    def __init__(
        self,
        coordinator: HQPlayerDataUpdateCoordinator,
        entry_id: str,
        description: HQPlayerSensorDescription,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
