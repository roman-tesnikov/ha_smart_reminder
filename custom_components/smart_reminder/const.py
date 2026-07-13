"""Constants for the Smart Reminder integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "smart_reminder"
NAME: Final = "Smart Reminder"
VERSION: Final = "1.0.0"

PLATFORMS: Final = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]

CONF_DND_START: Final = "dnd_start"
CONF_DND_END: Final = "dnd_end"
DEFAULT_DND_START: Final = "23:00:00"
DEFAULT_DND_END: Final = "10:00:00"

PANEL_URL_PATH: Final = "smart-reminders"
PANEL_WEB_COMPONENT: Final = "smart-reminder-panel"
PANEL_STATIC_URL: Final = "/smart_reminder_static"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.reminders"

SIGNAL_REMINDERS_UPDATED: Final = f"{DOMAIN}_reminders_updated"

EVENT_TRIGGERED: Final = f"{DOMAIN}_triggered"
EVENT_REPEATED: Final = f"{DOMAIN}_repeated"
EVENT_SNOOZED: Final = f"{DOMAIN}_snoozed"
EVENT_COMPLETED: Final = f"{DOMAIN}_completed"

SERVICE_CREATE: Final = "create"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_COMPLETE: Final = "complete"

ATTR_REMINDER_ID: Final = "reminder_id"
ATTR_NAME: Final = "name"
ATTR_AT: Final = "at"
ATTR_TEXT: Final = "text"
ATTR_RECIPIENT_IDS: Final = "recipient_ids"
ATTR_IGNORE_DND: Final = "ignore_dnd"
ATTR_REPEAT_INTERVAL_MINUTES: Final = "repeat_interval_minutes"
ATTR_DEFAULT_SNOOZE_MINUTES: Final = "default_snooze_minutes"
ATTR_DURATION: Final = "duration"


class ReminderType(StrEnum):
    """Supported reminder schedules."""

    ONCE = "once"
    CRON = "cron"
    AFTER_COMPLETION = "after_completion"


class ReminderStatus(StrEnum):
    """Runtime reminder states."""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    SNOOZED = "snoozed"
