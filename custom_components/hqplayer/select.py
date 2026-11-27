"""Select entities for HQPlayer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HQPlayerConfigEntry
from .api import HQPlayerClient, HQPlayerState
from .const import CONF_ALLOWED_FILTERS, CONF_ALLOWED_SHAPERS
from .coordinator import HQPlayerDataUpdateCoordinator
from .entity import HQPlayerEntity


@dataclass(frozen=True, kw_only=True)
class HQPlayerSelectDescription(SelectEntityDescription):
    """Describes an HQPlayer select entity."""

    options_fn: Callable[[HQPlayerState], list[str]]
    current_fn: Callable[[HQPlayerState], str | None]
    select_fn: Callable[[HQPlayerClient, str], Awaitable[None]]


SELECT_DESCRIPTIONS: tuple[HQPlayerSelectDescription, ...] = (
    HQPlayerSelectDescription(
        key="filter_1x",
        name="Filter 1x",
        icon="mdi:sine-wave",
        options_fn=lambda s: s.filters_1x,
        current_fn=lambda s: s.filter_1x,
        select_fn=lambda c, v: c.set_filter_1x(v),
    ),
    HQPlayerSelectDescription(
        key="filter_nx",
        name="Filter Nx",
        icon="mdi:sine-wave",
        options_fn=lambda s: s.filters_nx,
        current_fn=lambda s: s.filter_nx,
        select_fn=lambda c, v: c.set_filter_nx(v),
    ),
    HQPlayerSelectDescription(
        key="shaper",
        name="Shaper / Modulator",
        icon="mdi:waveform",
        options_fn=lambda s: s.shapers,
        current_fn=lambda s: s.shaper,
        select_fn=lambda c, v: c.set_shaper(v),
    ),
    HQPlayerSelectDescription(
        key="output_mode",
        name="Output Mode",
        icon="mdi:audio-video",
        options_fn=lambda s: s.output_modes,
        current_fn=lambda s: s.output_mode,
        select_fn=lambda c, v: c.set_output_mode(v),
    ),
    HQPlayerSelectDescription(
        key="sample_rate",
        name="Sample Rate",
        icon="mdi:speedometer",
        options_fn=lambda s: s.sample_rates,
        current_fn=lambda s: s.sample_rate,
        select_fn=lambda c, v: c.set_sample_rate(v),
    ),
    HQPlayerSelectDescription(
        key="matrix_profile",
        name="Matrix Profile",
        icon="mdi:matrix",
        options_fn=lambda s: s.matrix_profiles,
        current_fn=lambda s: s.matrix_profile,
        select_fn=lambda c, v: c.set_matrix_profile(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HQPlayerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HQPlayer select entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        HQPlayerSelect(coordinator, entry.entry_id, description)
        for description in SELECT_DESCRIPTIONS
    )


class HQPlayerSelect(HQPlayerEntity, SelectEntity):
    """Representation of an HQPlayer dynamic select entity."""

    entity_description: HQPlayerSelectDescription

    def __init__(
        self,
        coordinator: HQPlayerDataUpdateCoordinator,
        entry_id: str,
        description: HQPlayerSelectDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def options(self) -> list[str]:
        """Return dynamic list of available options."""
        if self.coordinator.data is None:
            return []
        opts = self.entity_description.options_fn(self.coordinator.data)
        if self.entity_description.key in ("filter_1x", "filter_nx"):
            allowed = self.coordinator.config_entry.options.get(
                CONF_ALLOWED_FILTERS, []
            )
            if allowed:
                current = self.entity_description.current_fn(self.coordinator.data)
                return [o for o in opts if o in allowed or o == current]
        elif self.entity_description.key == "shaper":
            allowed = self.coordinator.config_entry.options.get(
                CONF_ALLOWED_SHAPERS, []
            )
            if allowed:
                current = self.entity_description.current_fn(self.coordinator.data)
                return [o for o in opts if o in allowed or o == current]
        return opts

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        if self.coordinator.data is None:
            return None
        current = self.entity_description.current_fn(self.coordinator.data)
        if current is not None and current in self.options:
            return current
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.select_fn(self.coordinator.client, option)
        await self.coordinator.async_request_refresh()
