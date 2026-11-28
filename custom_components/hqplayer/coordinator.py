"""DataUpdateCoordinator for HQPlayer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HQPlayerClient, HQPlayerConnectionError, HQPlayerState
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HQPlayerDataUpdateCoordinator(DataUpdateCoordinator[HQPlayerState]):
    """Coordinator that polls HQPlayer Control API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HQPlayerClient,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._busy_count = 0
        self._cmd_lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        """Return True while a command and post-command refresh are in progress."""
        return self._busy_count > 0

    async def async_execute_command(self, action: Awaitable[None]) -> None:
        """Execute a command, wait 500ms, refresh status, then re-enable controls."""
        self._busy_count += 1
        self.async_update_listeners()
        try:
            async with self._cmd_lock:
                await action
                await asyncio.sleep(0.5)
                await self.async_request_refresh()
        finally:
            self._busy_count -= 1
            self.async_update_listeners()

    async def _async_update_data(self) -> HQPlayerState:
        """Fetch latest state from HQPlayer (full on first/mode-change, light otherwise)."""
        try:
            return await self.client.fetch_light_state(self.data)
        except HQPlayerConnectionError as err:
            self.client.invalidate_options_cache()
            raise UpdateFailed(f"Error communicating with HQPlayer: {err}") from err
