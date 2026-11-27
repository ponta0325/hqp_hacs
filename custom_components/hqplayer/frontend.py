"""Frontend registration for HQPlayer dashboard strategy."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/hqplayer_files"
JS_FILENAME = "hqplayer-dashboard.js"


class HQPlayerFrontendRegistration:
    """Register static path and Lovelace resource for HQPlayer dashboard strategy."""

    def __init__(self, hass: HomeAssistant, domain: str) -> None:
        """Initialize registration helper."""
        self.hass = hass
        integration = hass.data.get("integrations", {}).get(domain)
        self._version = getattr(integration, "version", "0.1.0")

    async def async_register(self) -> None:
        """Register static path and Lovelace resource."""
        www_dir = Path(__file__).parent / "www"
        js_file = www_dir / JS_FILENAME
        if not await self.hass.async_add_executor_job(js_file.is_file):
            _LOGGER.error("HQPlayer dashboard JS not found at %s", js_file)
            return

        if not self.hass.data.setdefault("hqplayer_frontend", {}).get("static_registered"):
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(www_dir), cache_headers=False)]
            )
            self.hass.data["hqplayer_frontend"]["static_registered"] = True

        await self._async_register_resource()

    def _get_storage_mode_resources(self):
        """Return Lovelace resources collection if running in storage mode."""
        lovelace_data = self.hass.data.get(LOVELACE_DATA)
        if lovelace_data is None:
            return None
        mode = (
            lovelace_data.resource_mode
            if hasattr(lovelace_data, "resource_mode")
            else getattr(lovelace_data, "mode", None)
        )
        return lovelace_data.resources if mode == "storage" else None

    async def _async_register_resource(self) -> None:
        """Register JS module in Lovelace storage resources (or fallback extra_js_url)."""
        js_url = f"{URL_BASE}/{JS_FILENAME}?v={self._version}"
        resources = self._get_storage_mode_resources()
        if resources is None:
            add_extra_js_url(self.hass, js_url)
            _LOGGER.debug("Registered HQPlayer extra JS URL (YAML mode): %s", js_url)
            return

        # Fix for Home Assistant 2026.x lazy-load issue (#165773)
        if hasattr(resources, "loaded") and not resources.loaded:
            await resources.async_load()
            resources.loaded = True

        base_url = f"{URL_BASE}/{JS_FILENAME}"
        matched = [
            res
            for res in resources.async_items()
            if res.get("url", "").startswith((base_url, f"/hqplayer/{JS_FILENAME}"))
        ]
        if not matched:
            await resources.async_create_item({"res_type": "module", "url": js_url})
            _LOGGER.info("Created HQPlayer Lovelace resource: %s", js_url)
        else:
            for res in matched:
                if res.get("url") != js_url:
                    await resources.async_update_item(
                        res["id"], {"res_type": "module", "url": js_url}
                    )
                    _LOGGER.info("Updated HQPlayer Lovelace resource: %s", js_url)

    async def async_unregister(self) -> None:
        """Remove Lovelace resource when last integration entry is unloaded."""
        resources = self._get_storage_mode_resources()
        if resources is None:
            return

        if hasattr(resources, "loaded") and not resources.loaded:
            await resources.async_load()
            resources.loaded = True

        base_url = f"{URL_BASE}/{JS_FILENAME}"
        for res in list(resources.async_items()):
            if res.get("url", "").startswith((base_url, f"/hqplayer/{JS_FILENAME}")):
                await resources.async_delete_item(res["id"])
