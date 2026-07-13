"""Tests for scheduler lifecycle policies with lightweight HA fakes."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_reminder import manager as manager_module
from custom_components.smart_reminder.const import (
    EVENT_COMPLETED,
    EVENT_REPEATED,
    EVENT_SNOOZED,
    EVENT_TRIGGERED,
    ReminderStatus,
)
from custom_components.smart_reminder.manager import ReminderManager
from custom_components.smart_reminder.model import Reminder

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class FakeBus:
    """Collect fired HA events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def async_fire(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((event_type, data))


class FakeHass:
    """Minimal HomeAssistant surface used by manager transitions."""

    def __init__(self) -> None:
        self.bus = FakeBus()


class FakeStore:
    """Collect persisted payloads."""

    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    async def async_save(self, data: dict[str, Any]) -> None:
        self.saved.append(data)


def reminder_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "test_reminder",
        "name": "Test reminder",
        "enabled": True,
        "reminder_type": "once",
        "scheduled_at": "2026-07-13T14:59:00+03:00",
        "ignore_dnd": True,
        "repeat_interval_minutes": 15,
        "default_snooze_minutes": 30,
        "first_text": "First text",
        "repeat_text": "Repeat text",
        "completed_text": "Completed text",
        "recipient_ids": ["123"],
    }
    payload.update(overrides)
    return payload


def lifecycle_manager(reminder: Reminder) -> ReminderManager:
    manager = ReminderManager.__new__(ReminderManager)
    manager.hass = FakeHass()
    manager.reminders = {reminder.id: reminder}
    manager.time_zone = ZoneInfo("Europe/Moscow")
    manager._dnd_start = time(23)
    manager._dnd_end = time(10)
    manager._store = FakeStore()
    manager._lock = asyncio.Lock()
    manager._started = True
    manager._stopped = False
    manager._cancel_timer = None
    manager._arm_timer = lambda: None
    manager._notify_updated = lambda: None
    return manager


def manager_with_dnd(start: time, end: time) -> ReminderManager:
    """Create a minimal manager for testing the pure DnD calculation."""
    manager = ReminderManager.__new__(ReminderManager)
    manager.time_zone = ZoneInfo("Europe/Moscow")
    manager._dnd_start = start
    manager._dnd_end = end
    return manager


def test_overnight_dnd_moves_to_end_of_quiet_period() -> None:
    manager = manager_with_dnd(time(23), time(10))

    # 21:00 UTC is midnight in Moscow on the following date.
    result = manager._dnd_end_for(datetime(2026, 7, 13, 21, tzinfo=UTC))

    assert result == datetime(2026, 7, 14, 7, tzinfo=UTC)


def test_moment_outside_dnd_is_not_moved() -> None:
    manager = manager_with_dnd(time(23), time(10))

    assert manager._dnd_end_for(datetime(2026, 7, 13, 12, tzinfo=UTC)) is None


def test_equal_dnd_bounds_disable_quiet_period() -> None:
    manager = manager_with_dnd(time(10), time(10))

    assert manager._dnd_end_for(datetime(2026, 7, 13, 7, tzinfo=UTC)) is None


def test_due_reminder_becomes_active_and_fires_first_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_process_due())

    assert reminder.status is ReminderStatus.ACTIVE
    assert reminder.next_trigger == NOW + timedelta(minutes=15)
    assert manager.hass.bus.events[0][0] == EVENT_TRIGGERED
    assert manager.hass.bus.events[0][1]["text"] == "First text"
    assert manager._store.saved[-1]["reminders"][0]["status"] == "active"


def test_snoozed_wakeup_uses_repeat_event_and_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    reminder.status = ReminderStatus.SNOOZED
    reminder.next_trigger = NOW - timedelta(minutes=1)
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_process_due())

    assert manager.hass.bus.events[0][0] == EVENT_REPEATED
    assert manager.hass.bus.events[0][1]["text"] == "Repeat text"
    assert reminder.repeat_count == 1


def test_snooze_persists_new_time_and_fires_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_snooze(reminder.id, "1h30m"))

    assert reminder.status is ReminderStatus.SNOOZED
    assert reminder.next_trigger == NOW + timedelta(minutes=90)
    assert manager.hass.bus.events[0][0] == EVENT_SNOOZED
    assert manager.hass.bus.events[0][1]["duration"] == "1h30m"


def test_updating_cron_anchor_recalculates_next_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing only the anchor must not preserve the previous runtime schedule."""
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    zone = ZoneInfo("Europe/Moscow")
    payload = reminder_payload(
        reminder_type="cron",
        cron="@every 2w 0 10 * * 1",
    )
    reminder = Reminder.from_payload(payload, now=NOW, local_tz=zone)
    manager = lifecycle_manager(reminder)

    updated_payload = {**payload, "cron_anchor": "2026-07-27"}
    updated = asyncio.run(manager.async_update(reminder.id, updated_payload))

    assert updated.cron_anchor == datetime(2026, 7, 26, 21, 0, tzinfo=UTC)
    assert updated.next_trigger == datetime(2026, 7, 27, 7, 0, tzinfo=UTC)


def test_completing_once_deletes_reminder_after_persisting_event_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    reminder.status = ReminderStatus.ACTIVE
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_complete(reminder.id))

    assert reminder.id not in manager.reminders
    assert manager.hass.bus.events[0][0] == EVENT_COMPLETED
    assert manager.hass.bus.events[0][1]["text"] == "Completed text"
    assert manager._store.saved[-1]["reminders"] == []


def test_completing_after_completion_schedules_from_actual_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(reminder_type="after_completion", delay_minutes=1440),
        now=NOW - timedelta(days=1),
        local_tz=ZoneInfo("UTC"),
    )
    reminder.status = ReminderStatus.ACTIVE
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_complete(reminder.id))

    assert reminder.status is ReminderStatus.SCHEDULED
    assert reminder.next_trigger == NOW + timedelta(days=1)
    assert reminder.id in manager.reminders
