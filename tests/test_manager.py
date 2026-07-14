"""Tests for scheduler lifecycle policies with lightweight HA fakes."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_reminder import manager as manager_module
from custom_components.smart_reminder.const import (
    DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
    DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
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
        "snoozed_text": "Snoozed text",
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
    manager._already_snoozed_error_text = "Custom already snoozed error"
    manager._already_completed_error_text = "Custom already completed error"
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


def test_missing_error_text_options_use_defaults() -> None:
    manager = manager_with_dnd(time(23), time(10))

    manager._apply_options({})

    assert manager._already_snoozed_error_text == DEFAULT_ALREADY_SNOOZED_ERROR_TEXT
    assert manager._already_completed_error_text == DEFAULT_ALREADY_COMPLETED_ERROR_TEXT


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


def test_snoozed_wakeup_uses_repeat_event_and_snoozed_text(
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
    assert manager.hass.bus.events[0][1]["text"] == "Snoozed text"
    assert reminder.repeat_count == 1


@pytest.mark.parametrize(
    ("snoozed_text", "repeat_text", "expected"),
    [
        ("", "Repeat text", "Repeat text"),
        ("", "", "First text"),
    ],
)
def test_snoozed_text_falls_back_to_repeat_then_first_text(
    monkeypatch: pytest.MonkeyPatch,
    snoozed_text: str,
    repeat_text: str,
    expected: str,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(snoozed_text=snoozed_text, repeat_text=repeat_text),
        now=NOW - timedelta(days=1),
        local_tz=ZoneInfo("UTC"),
    )
    reminder.status = ReminderStatus.SNOOZED
    reminder.next_trigger = NOW - timedelta(minutes=1)
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_process_due())

    assert manager.hass.bus.events[0][1]["text"] == expected


def test_normal_repeat_does_not_use_snoozed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    reminder.status = ReminderStatus.ACTIVE
    reminder.next_trigger = NOW - timedelta(minutes=1)
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_process_due())

    assert manager.hass.bus.events[0][0] == EVENT_REPEATED
    assert manager.hass.bus.events[0][1]["text"] == "Repeat text"


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
    assert manager.hass.bus.events[0][1]["text"] == "Snoozed text"
    assert manager.hass.bus.events[0][1]["duration"] == "1h30m"
    assert (
        manager.hass.bus.events[0][1]["next_trigger"]
        == (NOW + timedelta(minutes=90)).isoformat()
    )
    assert manager.hass.bus.events[0][1]["action_succeeded"] is True
    assert manager.hass.bus.events[0][1]["reason"] is None


def test_snoozed_reminder_fires_repeated_event_when_delay_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": NOW}
    monkeypatch.setattr(manager_module, "utcnow", lambda: clock["now"])
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_snooze(reminder.id, "30m"))
    clock["now"] = NOW + timedelta(minutes=30)
    asyncio.run(manager.async_process_due())

    assert [event_type for event_type, _data in manager.hass.bus.events] == [
        EVENT_SNOOZED,
        EVENT_REPEATED,
    ]
    assert manager.hass.bus.events[-1][1]["text"] == "Snoozed text"
    assert reminder.status is ReminderStatus.ACTIVE


def test_repeated_snooze_does_not_move_next_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(), now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_snooze(reminder.id, "30m"))
    first_next_trigger = reminder.next_trigger
    asyncio.run(manager.async_snooze(reminder.id, "2h"))

    assert reminder.status is ReminderStatus.SNOOZED
    assert reminder.next_trigger == first_next_trigger
    assert len(manager._store.saved) == 1
    event_type, event_data = manager.hass.bus.events[-1]
    assert event_type == EVENT_SNOOZED
    assert event_data["text"] == "Custom already snoozed error"
    assert event_data["next_trigger"] == first_next_trigger.isoformat()
    assert event_data["snoozed_until"] == first_next_trigger.isoformat()
    assert event_data["scheduled_for"] is None
    assert event_data["action_succeeded"] is False
    assert event_data["reason"] == "already_snoozed"


def test_snooze_with_empty_snoozed_text_still_fires_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automations can substitute their own confirmation when text is empty."""
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(snoozed_text=""),
        now=NOW - timedelta(days=1),
        local_tz=ZoneInfo("UTC"),
    )
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_snooze(reminder.id, "30m"))

    assert len(manager.hass.bus.events) == 1
    event_type, event_data = manager.hass.bus.events[0]
    assert event_type == EVENT_SNOOZED
    assert event_data["text"] == ""
    assert event_data["duration"] == "30m"


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


def test_updating_next_trigger_preserves_schedule_and_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    payload = reminder_payload(
        reminder_type="after_completion",
        delay_minutes=1440,
    )
    reminder = Reminder.from_payload(
        payload, now=NOW - timedelta(days=1), local_tz=ZoneInfo("UTC")
    )
    reminder.status = ReminderStatus.SNOOZED
    reminder.repeat_count = 2
    original_scheduled_at = reminder.scheduled_at
    manager = lifecycle_manager(reminder)

    updated = asyncio.run(
        manager.async_update(
            reminder.id,
            {**payload, "next_trigger": "2026-07-20T21:12:00+03:00"},
        )
    )

    assert updated.scheduled_at == original_scheduled_at
    assert updated.status is ReminderStatus.SNOOZED
    assert updated.repeat_count == 2
    assert updated.next_trigger == datetime(2026, 7, 20, 18, 12, tzinfo=UTC)


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
    assert len(manager.hass.bus.events) == 1
    assert manager.hass.bus.events[0][0] == EVENT_COMPLETED
    assert manager.hass.bus.events[0][1]["text"] == "Completed text"
    assert manager.hass.bus.events[0][1]["reminder_id"] == reminder.id
    assert manager.hass.bus.events[0][1]["next_trigger"] is None
    assert manager.hass.bus.events[0][1]["action_succeeded"] is True
    assert manager.hass.bus.events[0][1]["reason"] is None
    assert manager._store.saved[-1]["reminders"] == []


def test_completing_once_with_empty_text_still_fires_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty completion message must not suppress the lifecycle event."""
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(completed_text=""),
        now=NOW - timedelta(days=1),
        local_tz=ZoneInfo("UTC"),
    )
    reminder.status = ReminderStatus.ACTIVE
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_complete(reminder.id))

    assert len(manager.hass.bus.events) == 1
    event_type, event_data = manager.hass.bus.events[0]
    assert event_type == EVENT_COMPLETED
    assert event_data["reminder_id"] == reminder.id
    assert event_data["text"] == ""
    assert reminder.id not in manager.reminders


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
    assert (
        manager.hass.bus.events[0][1]["next_trigger"]
        == (NOW + timedelta(days=1)).isoformat()
    )


def test_repeated_completion_does_not_schedule_again(
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
    first_next_trigger = reminder.next_trigger
    first_completed_at = reminder.last_completed_at
    asyncio.run(manager.async_complete(reminder.id))

    assert reminder.status is ReminderStatus.SCHEDULED
    assert reminder.next_trigger == first_next_trigger
    assert reminder.last_completed_at == first_completed_at
    assert len(manager._store.saved) == 1
    event_type, event_data = manager.hass.bus.events[-1]
    assert event_type == EVENT_COMPLETED
    assert event_data["text"] == "Custom already completed error"
    assert event_data["next_trigger"] == first_next_trigger.isoformat()
    assert event_data["action_succeeded"] is False
    assert event_data["reason"] == "already_completed"


def test_repeated_completion_is_rejected_even_if_next_trigger_is_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delayed scheduler callback must not make the old button valid again."""
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(reminder_type="after_completion", delay_minutes=1440),
        now=NOW - timedelta(days=2),
        local_tz=ZoneInfo("UTC"),
    )
    reminder.status = ReminderStatus.SCHEDULED
    reminder.last_completed_at = NOW - timedelta(days=1)
    reminder.next_trigger = NOW - timedelta(minutes=1)
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_complete(reminder.id))

    assert reminder.next_trigger == NOW - timedelta(minutes=1)
    assert manager._store.saved == []
    assert manager.hass.bus.events[-1][1]["reason"] == "already_completed"


def test_fresh_scheduled_reminder_can_be_completed_before_first_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_module, "utcnow", lambda: NOW)
    reminder = Reminder.from_payload(
        reminder_payload(reminder_type="after_completion", delay_minutes=1440),
        now=NOW,
        local_tz=ZoneInfo("UTC"),
    )
    assert reminder.last_completed_at is None
    manager = lifecycle_manager(reminder)

    asyncio.run(manager.async_complete(reminder.id))

    assert reminder.last_completed_at == NOW
    assert reminder.next_trigger == NOW + timedelta(days=1)
    assert manager.hass.bus.events[-1][1]["action_succeeded"] is True
