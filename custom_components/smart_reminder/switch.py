"""Reminder enabled switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SmartReminderEntity, async_setup_dynamic_entities
from .manager import ReminderManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamic enable switches."""
    async_setup_dynamic_entities(
        hass,
        entry,
        async_add_entities,
        lambda manager, config_entry, reminder_id: SmartReminderSwitch(
            manager, config_entry, reminder_id
        ),
    )


class SmartReminderSwitch(SmartReminderEntity, SwitchEntity):
    """Enable or disable one reminder."""

    _attr_icon = "mdi:bell-cog-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, manager: ReminderManager, entry: ConfigEntry, reminder_id: str
    ) -> None:
        super().__init__(manager, entry, reminder_id, "enabled")

    def refresh_metadata(self) -> None:
        self._attr_name = f"{self.reminder.name} enabled"

    @property
    def is_on(self) -> bool:
        """Return whether the reminder is enabled."""
        return self.reminder.enabled

    async def async_turn_on(self, **_kwargs: object) -> None:
        """Enable the reminder."""
        await self.manager.async_set_enabled(self.reminder_id, True)

    async def async_turn_off(self, **_kwargs: object) -> None:
        """Disable the reminder."""
        await self.manager.async_set_enabled(self.reminder_id, False)
