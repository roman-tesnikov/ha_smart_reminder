"""Shared entity support for Smart Reminder."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, SIGNAL_REMINDERS_UPDATED
from .manager import ReminderManager
from .model import Reminder


class SmartReminderEntity(Entity):
    """Base for an entity backed by one reminder."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: ReminderManager,
        entry: ConfigEntry,
        reminder_id: str,
        suffix: str,
    ) -> None:
        self.manager = manager
        self.reminder_id = reminder_id
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{reminder_id}_{suffix}"

    @property
    def reminder(self) -> Reminder:
        """Return current reminder data."""
        return self.manager.get(self.reminder_id)

    @property
    def available(self) -> bool:
        """Return whether the reminder still exists."""
        return self.reminder_id in self.manager.reminders

    @property
    def device_info(self) -> DeviceInfo:
        """Group reminder entities under one virtual device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=NAME,
            manufacturer="Smart Reminder",
            model="Local reminder scheduler",
            entry_type=DeviceEntryType.SERVICE,
        )

    def refresh_metadata(self) -> None:
        """Refresh metadata derived from editable reminder fields."""


def async_setup_dynamic_entities[EntityT: SmartReminderEntity](
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[ReminderManager, ConfigEntry, str], EntityT],
) -> None:
    """Keep a platform synchronized with reminders created and removed at runtime."""
    manager: ReminderManager = entry.runtime_data
    entities: dict[str, EntityT] = {}

    @callback
    def _sync_entities() -> None:
        current_ids = set(manager.reminders)
        for removed_id in set(entities) - current_ids:
            entity = entities.pop(removed_id)
            hass.async_create_task(entity.async_remove(force_remove=True))

        new_entities: list[EntityT] = []
        for reminder_id in current_ids - set(entities):
            entity = factory(manager, entry, reminder_id)
            entity.refresh_metadata()
            entities[reminder_id] = entity
            new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

        for reminder_id in current_ids & set(entities):
            entity = entities[reminder_id]
            entity.refresh_metadata()
            if entity.hass is not None:
                entity.async_write_ha_state()

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_REMINDERS_UPDATED, _sync_entities)
    )
    _sync_entities()
