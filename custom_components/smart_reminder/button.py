"""Complete and default-snooze reminder buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SmartReminderEntity, async_setup_dynamic_entities
from .manager import ReminderManager
from .model import minutes_to_duration


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamic reminder buttons."""
    async_setup_dynamic_entities(
        hass,
        entry,
        async_add_entities,
        lambda manager, config_entry, reminder_id: CompleteReminderButton(
            manager, config_entry, reminder_id
        ),
    )
    async_setup_dynamic_entities(
        hass,
        entry,
        async_add_entities,
        lambda manager, config_entry, reminder_id: SnoozeReminderButton(
            manager, config_entry, reminder_id
        ),
    )


class CompleteReminderButton(SmartReminderEntity, ButtonEntity):
    """Complete a reminder."""

    _attr_icon = "mdi:check-circle-outline"

    def __init__(
        self, manager: ReminderManager, entry: ConfigEntry, reminder_id: str
    ) -> None:
        super().__init__(manager, entry, reminder_id, "complete")

    def refresh_metadata(self) -> None:
        self._attr_name = f"{self.reminder.name} complete"

    async def async_press(self) -> None:
        """Complete the reminder."""
        await self.manager.async_complete(self.reminder_id)


class SnoozeReminderButton(SmartReminderEntity, ButtonEntity):
    """Snooze a reminder by its configured default."""

    _attr_icon = "mdi:bell-sleep-outline"

    def __init__(
        self, manager: ReminderManager, entry: ConfigEntry, reminder_id: str
    ) -> None:
        super().__init__(manager, entry, reminder_id, "snooze")

    def refresh_metadata(self) -> None:
        self._attr_name = f"{self.reminder.name} snooze"

    async def async_press(self) -> None:
        """Snooze using default_snooze_minutes."""
        await self.manager.async_snooze(
            self.reminder_id,
            minutes_to_duration(self.reminder.default_snooze_minutes),
        )
