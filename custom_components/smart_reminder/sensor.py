"""Reminder status sensor entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ReminderStatus
from .entity import SmartReminderEntity, async_setup_dynamic_entities
from .manager import ReminderManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamic status sensors."""
    async_setup_dynamic_entities(
        hass,
        entry,
        async_add_entities,
        lambda manager, config_entry, reminder_id: SmartReminderSensor(
            manager, config_entry, reminder_id
        ),
    )


class SmartReminderSensor(SmartReminderEntity, SensorEntity):
    """Expose the lifecycle state and configuration of one reminder."""

    def __init__(
        self, manager: ReminderManager, entry: ConfigEntry, reminder_id: str
    ) -> None:
        super().__init__(manager, entry, reminder_id, "status")

    def refresh_metadata(self) -> None:
        self._attr_name = f"{self.reminder.name} status"

    @property
    def native_value(self) -> str:
        """Return scheduled, active or snoozed."""
        return self.reminder.status.value

    @property
    def icon(self) -> str:
        """Return a state-specific icon."""
        return {
            ReminderStatus.SCHEDULED: "mdi:calendar-clock",
            ReminderStatus.ACTIVE: "mdi:bell-ring",
            ReminderStatus.SNOOZED: "mdi:bell-sleep",
        }[self.reminder.status]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful automation attributes without duplicating internal fields."""
        reminder = self.reminder
        return {
            "reminder_id": reminder.id,
            "reminder_type": reminder.reminder_type.value,
            "enabled": reminder.enabled,
            "next_trigger": reminder.next_trigger.isoformat()
            if reminder.next_trigger
            else None,
            "cron_anchor": reminder.cron_anchor.isoformat()
            if reminder.cron_anchor
            else None,
            "last_triggered_at": reminder.last_triggered_at.isoformat()
            if reminder.last_triggered_at
            else None,
            "recipient_ids": list(reminder.recipient_ids),
            "repeat_count": reminder.repeat_count,
            "ignore_dnd": reminder.ignore_dnd,
            "repeat_interval_minutes": reminder.repeat_interval_minutes,
            "default_snooze_minutes": reminder.default_snooze_minutes,
        }
