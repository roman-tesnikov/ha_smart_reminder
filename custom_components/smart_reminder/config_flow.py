"""UI configuration for Smart Reminder."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALREADY_COMPLETED_ERROR_TEXT,
    CONF_ALREADY_SNOOZED_ERROR_TEXT,
    CONF_DND_END,
    CONF_DND_START,
    DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
    DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    DOMAIN,
    NAME,
)


def _normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional text fields and restore safe defaults for blanks."""
    normalized = dict(settings)
    for key, default in (
        (CONF_ALREADY_SNOOZED_ERROR_TEXT, DEFAULT_ALREADY_SNOOZED_ERROR_TEXT),
        (CONF_ALREADY_COMPLETED_ERROR_TEXT, DEFAULT_ALREADY_COMPLETED_ERROR_TEXT),
    ):
        value = normalized.get(key)
        normalized[key] = value.strip() if isinstance(value, str) else default
        if not normalized[key]:
            normalized[key] = default
    return normalized


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    defaults = _normalize_settings(defaults)
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
            vol.Required(
                CONF_ALREADY_SNOOZED_ERROR_TEXT,
                default=defaults[CONF_ALREADY_SNOOZED_ERROR_TEXT],
            ): selector.TextSelector(),
            vol.Required(
                CONF_ALREADY_COMPLETED_ERROR_TEXT,
                default=defaults[CONF_ALREADY_COMPLETED_ERROR_TEXT],
            ): selector.TextSelector(),
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
            user_input = _normalize_settings(user_input)
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the integration options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Edit global DnD settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit quiet hours."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data=_normalize_settings(user_input)
            )
        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_settings_schema(defaults)
        )
