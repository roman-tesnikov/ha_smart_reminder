"""WebSocket API used by the Smart Reminder management panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .manager import (
    ReminderAlreadyExistsError,
    ReminderNotFoundError,
)
from .model import ReminderValidationError
from .services import get_manager

ERR_INVALID_REMINDER = "invalid_reminder"
ERR_NOT_FOUND = "reminder_not_found"
ERR_ALREADY_EXISTS = "reminder_already_exists"


def _send_domain_error(
    connection: websocket_api.ActiveConnection, msg_id: int, err: Exception
) -> None:
    if isinstance(err, ReminderNotFoundError):
        code = ERR_NOT_FOUND
    elif isinstance(err, ReminderAlreadyExistsError):
        code = ERR_ALREADY_EXISTS
    else:
        code = ERR_INVALID_REMINDER
    connection.send_error(msg_id, code, str(err))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list"})
@websocket_api.require_admin
@callback
def websocket_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return reminders and integration-wide settings."""
    manager = get_manager(hass)
    connection.send_result(
        msg["id"],
        {
            "reminders": manager.list_serialized(),
            "settings": {
                "dnd_start": manager.dnd_start,
                "dnd_end": manager.dnd_end,
                "timezone": hass.config.time_zone,
            },
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/create",
        vol.Required("reminder"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a fully configured reminder."""
    try:
        reminder = await get_manager(hass).async_create(msg["reminder"])
    except (ReminderValidationError, ReminderAlreadyExistsError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"reminder": reminder.to_dict()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update",
        vol.Required("reminder_id"): str,
        vol.Required("reminder"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update a reminder."""
    try:
        reminder = await get_manager(hass).async_update(
            msg["reminder_id"], msg["reminder"]
        )
    except (ReminderValidationError, ReminderNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"reminder": reminder.to_dict()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete",
        vol.Required("reminder_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a reminder."""
    try:
        await get_manager(hass).async_delete(msg["reminder_id"])
    except (ReminderValidationError, ReminderNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/snooze",
        vol.Required("reminder_id"): str,
        vol.Required("duration"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_snooze(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Snooze a reminder."""
    try:
        reminder = await get_manager(hass).async_snooze(
            msg["reminder_id"], msg["duration"]
        )
    except (ReminderValidationError, ReminderNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"reminder": reminder.to_dict()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/complete",
        vol.Required("reminder_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_complete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Complete a reminder."""
    try:
        reminder = await get_manager(hass).async_complete(msg["reminder_id"])
    except (ReminderValidationError, ReminderNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"reminder": reminder.to_dict()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_enabled",
        vol.Required("reminder_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_set_enabled(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Enable or disable a reminder."""
    try:
        await get_manager(hass).async_set_enabled(msg["reminder_id"], msg["enabled"])
    except (ReminderValidationError, ReminderNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all management WebSocket commands once."""
    for command in (
        websocket_list,
        websocket_create,
        websocket_update,
        websocket_delete,
        websocket_snooze,
        websocket_complete,
        websocket_set_enabled,
    ):
        websocket_api.async_register_command(hass, command)
