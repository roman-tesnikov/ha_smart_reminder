"""Home Assistant action registration for Smart Reminder."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_AT,
    ATTR_DEFAULT_SNOOZE_MINUTES,
    ATTR_DURATION,
    ATTR_IGNORE_DND,
    ATTR_NAME,
    ATTR_RECIPIENT_IDS,
    ATTR_REMINDER_ID,
    ATTR_REPEAT_INTERVAL_MINUTES,
    ATTR_TEXT,
    DOMAIN,
    SERVICE_COMPLETE,
    SERVICE_CREATE,
    SERVICE_SNOOZE,
    ReminderType,
)
from .manager import ReminderManager
from .model import ReminderValidationError, parse_duration, validate_reminder_id


def _id_validator(value: Any) -> str:
    try:
        return validate_reminder_id(value)
    except ReminderValidationError as err:
        raise vol.Invalid(str(err)) from err


def _duration_validator(value: Any) -> str:
    value = cv.string(value)
    try:
        parse_duration(value)
    except ReminderValidationError as err:
        raise vol.Invalid(str(err)) from err
    return value


CREATE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_REMINDER_ID): _id_validator,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Required(ATTR_AT): cv.datetime,
        vol.Required(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_RECIPIENT_IDS, default=[]): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(ATTR_IGNORE_DND, default=False): cv.boolean,
        vol.Optional(ATTR_REPEAT_INTERVAL_MINUTES, default=15): cv.positive_int,
        vol.Optional(ATTR_DEFAULT_SNOOZE_MINUTES, default=30): cv.positive_int,
    }
)

SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_REMINDER_ID): _id_validator,
        vol.Required(ATTR_DURATION): _duration_validator,
    }
)

COMPLETE_SCHEMA = vol.Schema({vol.Required(ATTR_REMINDER_ID): _id_validator})


def get_manager(hass: HomeAssistant) -> ReminderManager:
    """Return the only configured manager."""
    managers = hass.data.get(DOMAIN, {})
    if not managers:
        raise ServiceValidationError(
            "Smart Reminder is not configured. Add the integration first."
        )
    return next(iter(managers.values()))


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration actions once from async_setup."""

    async def _create(call: ServiceCall) -> ServiceResponse | None:
        text = call.data[ATTR_TEXT].strip()
        if not text:
            raise ServiceValidationError("text must not be empty")
        reminder_id = call.data.get(ATTR_REMINDER_ID) or f"reminder_{uuid4().hex[:10]}"
        name = call.data.get(ATTR_NAME, "").strip() or text
        at: datetime = call.data[ATTR_AT]
        payload = {
            "id": reminder_id,
            "name": name,
            "enabled": True,
            "reminder_type": ReminderType.ONCE.value,
            "scheduled_at": at,
            "ignore_dnd": call.data[ATTR_IGNORE_DND],
            "repeat_interval_minutes": call.data[ATTR_REPEAT_INTERVAL_MINUTES],
            "default_snooze_minutes": call.data[ATTR_DEFAULT_SNOOZE_MINUTES],
            "first_text": text,
            "repeat_text": "",
            "snoozed_text": "",
            "completed_text": "",
            "recipient_ids": call.data[ATTR_RECIPIENT_IDS],
        }
        try:
            reminder = await get_manager(hass).async_create(payload)
        except (ReminderValidationError, ValueError) as err:
            raise ServiceValidationError(str(err)) from err
        if call.return_response:
            return {"reminder_id": reminder.id, "reminder": reminder.to_dict()}
        return None

    async def _snooze(call: ServiceCall) -> None:
        try:
            await get_manager(hass).async_snooze(
                call.data[ATTR_REMINDER_ID], call.data[ATTR_DURATION]
            )
        except (ReminderValidationError, ValueError) as err:
            raise ServiceValidationError(str(err)) from err

    async def _complete(call: ServiceCall) -> None:
        try:
            await get_manager(hass).async_complete(call.data[ATTR_REMINDER_ID])
        except (ReminderValidationError, ValueError) as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE,
        _create,
        schema=CREATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _snooze, schema=SNOOZE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE, _complete, schema=COMPLETE_SCHEMA
    )
