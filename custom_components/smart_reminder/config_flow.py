"""UI configuration for Smart Reminder."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DND_END,
    CONF_DND_START,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    DOMAIN,
    NAME,
)


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DND_START,
                default=defaults.get(CONF_DND_START, DEFAULT_DND_START),
            ): selector.TimeSelector(),
            vol.Required(
                CONF_DND_END,
                default=defaults.get(CONF_DND_END, DEFAULT_DND_END),
            ): selector.TimeSelector(),
        }
    )


class SmartReminderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single Smart Reminder config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle setup from Settings > Integrations."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the integration options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Edit global DnD settings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit quiet hours."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_settings_schema(defaults)
        )
