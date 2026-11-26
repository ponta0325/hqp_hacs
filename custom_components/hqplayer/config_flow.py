"""Config flow for HQPlayer integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import HQPlayerClient, HQPlayerConnectionError
from .const import (
    CONF_ALLOWED_FILTERS,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=2, max=3600)
        ),
    }
)


class HQPlayerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HQPlayer."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HQPlayerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = HQPlayerClient(host=host, port=port)
            try:
                await client.connect()
                await client.get_status()
            except HQPlayerConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during HQPlayer config flow")
                errors["base"] = "unknown"
            finally:
                await client.disconnect()

            if not errors:
                return self.async_create_entry(
                    title=f"HQPlayer ({host}:{port})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class HQPlayerOptionsFlow(OptionsFlow):
    """Handle HQPlayer options (checkbox filter list)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator = getattr(self.config_entry, "runtime_data", None)
        all_filters: list[str] = (
            list(coordinator.data.filters_1x)
            if coordinator is not None and coordinator.data is not None
            else []
        )
        current_allowed: list[str] = list(
            self.config_entry.options.get(CONF_ALLOWED_FILTERS, [])
        )
        # Keep any previously saved items in options so HA selector stays valid
        options = list(dict.fromkeys([*all_filters, *current_allowed]))

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ALLOWED_FILTERS,
                    default=current_allowed,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
