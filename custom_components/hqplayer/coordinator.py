"""DataUpdateCoordinator for HQPlayer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
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

    async def async_execute_command(
        self,
        action: Awaitable[None],
        verify: Callable[[HQPlayerState], bool] | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Execute a command and poll every 500ms until status matches (or timeout)."""
        self._busy_count += 1
        self.async_update_listeners()
        try:
            async with self._cmd_lock:
                await action
                loop = asyncio.get_running_loop()
                deadline = loop.time() + timeout
                while True:
                    await asyncio.sleep(0.5)
                    await self.async_request_refresh()
                    if verify is None or (
                        self.data is not None and verify(self.data)
                    ):
                        break
                    if loop.time() >= deadline:
                        break
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
