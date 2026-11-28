"""DataUpdateCoordinator for HQPlayer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging
import xml.etree.ElementTree as ET

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
        self._stop_event = asyncio.Event()
        self._sub_task: asyncio.Task[None] | None = None

    def start_subscription(self) -> None:
        """Start background <Status subscribe="1"/> listener for live metrics."""
        if self._sub_task is not None and not self._sub_task.done():
            return
        self._stop_event.clear()
        self._sub_task = self.hass.async_create_background_task(
            self.client.subscribe_status(self._handle_status_push, self._stop_event),
            name=f"{DOMAIN}_status_subscription",
        )

    async def stop_subscription(self) -> None:
        """Stop background <Status subscribe="1"/> listener."""
        self._stop_event.set()
        if self._sub_task is not None:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass
            self._sub_task = None

    async def _handle_status_push(self, status_el: ET.Element) -> None:
        """Update playback metrics (apod, clips, I/O rates) on <Status> push."""
        if self.data is None:
            return
        updated = self.client.apply_status_metrics(status_el, self.data)
        self.async_set_updated_data(updated)

    @property
    def busy(self) -> bool:
        """Return True while a command and post-command refresh are in progress."""
        return self._busy_count > 0

    async def async_execute_command(
        self,
        action: Awaitable[None],
        verify: Callable[[HQPlayerState], bool] | None = None,
        timeout: float = 10.0,
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
