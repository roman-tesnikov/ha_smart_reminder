"""Tests for reminder validation and schedule calculations."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_reminder.const import ReminderStatus, ReminderType
from custom_components.smart_reminder.model import (
    Reminder,
    ReminderValidationError,
    minutes_to_duration,
    next_cron_occurrence,
    parse_duration,
)

MOSCOW = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def reminder_payload(**overrides: object) -> dict[str, object]:
    """Return a valid one-time reminder payload."""
    payload: dict[str, object] = {
        "id": "water_cactus",
        "name": "Water the cactus",
        "enabled": True,
        "reminder_type": "once",
        "scheduled_at": "2026-07-13T10:00",
        "ignore_dnd": False,
        "repeat_interval_minutes": 15,
        "default_snooze_minutes": 90,
        "first_text": "Water the cactus",
        "repeat_text": "The cactus is still waiting",
        "completed_text": "Thank you",
        "recipient_ids": ["123", "family"],
    }
    payload.update(overrides)
    return payload


def test_one_time_payload_uses_home_assistant_timezone() -> None:
    """Naive UI datetimes are interpreted in the HA timezone."""
    reminder = Reminder.from_payload(reminder_payload(), now=NOW, local_tz=MOSCOW)

    assert reminder.reminder_type is ReminderType.ONCE
    assert reminder.status is ReminderStatus.SCHEDULED
    assert reminder.next_trigger == datetime(2026, 7, 13, 7, 0, tzinfo=UTC)
    assert reminder.recipient_ids == ["123", "family"]


def test_cron_schedule_respects_timezone() -> None:
    """Cron is evaluated as wall-clock time in the HA timezone."""
    next_run = next_cron_occurrence("0 10 * * 1", NOW, MOSCOW)

    assert next_run == datetime(2026, 7, 13, 7, 0, tzinfo=UTC)


def test_extended_cron_supports_every_second_week() -> None:
    """The extension covers a cadence standard crontab cannot represent."""
    expression = "@every 2w 0 10 * * 1"
    anchor = next_cron_occurrence(expression, NOW, MOSCOW)

    next_run = next_cron_occurrence(
        expression,
        datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        MOSCOW,
        anchor,
    )

    assert anchor == datetime(2026, 7, 13, 7, 0, tzinfo=UTC)
    assert next_run == datetime(2026, 7, 27, 7, 0, tzinfo=UTC)


def test_extended_cron_accepts_explicit_anchor_date() -> None:
    """A user-selected anchor controls the phase of a multi-week schedule."""
    reminder = Reminder.from_payload(
        reminder_payload(
            reminder_type="cron",
            cron="@every 2w 0 10 * * 1",
            cron_anchor="2026-07-27",
        ),
        now=NOW,
        local_tz=MOSCOW,
    )

    assert reminder.cron_anchor == datetime(2026, 7, 26, 21, 0, tzinfo=UTC)
    assert reminder.next_trigger == datetime(2026, 7, 27, 7, 0, tzinfo=UTC)


def test_standard_cron_rejects_anchor_date() -> None:
    """An anchor has no defined meaning without the @every Nw extension."""
    with pytest.raises(ReminderValidationError, match="@every Nw"):
        Reminder.from_payload(
            reminder_payload(
                reminder_type="cron",
                cron="0 10 * * 1",
                cron_anchor="2026-07-27",
            ),
            now=NOW,
            local_tz=MOSCOW,
        )


def test_anchor_date_must_match_base_cron() -> None:
    """A Tuesday cannot anchor a schedule whose base cron only runs on Mondays."""
    with pytest.raises(ReminderValidationError, match="cron_anchor"):
        Reminder.from_payload(
            reminder_payload(
                reminder_type="cron",
                cron="@every 2w 0 10 * * 1",
                cron_anchor="2026-07-28",
            ),
            now=NOW,
            local_tz=MOSCOW,
        )


def test_storage_round_trip_preserves_runtime_state() -> None:
    """Persistent state survives a complete serialize/restore cycle."""
    reminder = Reminder.from_payload(reminder_payload(), now=NOW, local_tz=MOSCOW)
    reminder.status = ReminderStatus.ACTIVE
    reminder.next_trigger = NOW + timedelta(minutes=15)
    reminder.last_triggered_at = NOW
    reminder.repeat_count = 3

    restored = Reminder.from_storage(reminder.to_dict(), now=NOW, local_tz=MOSCOW)

    assert restored.status is ReminderStatus.ACTIVE
    assert restored.next_trigger == reminder.next_trigger
    assert restored.last_triggered_at == NOW
    assert restored.repeat_count == 3


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        ("15m", timedelta(minutes=15)),
        ("1h30m", timedelta(minutes=90)),
        ("2d3h5m", timedelta(days=2, hours=3, minutes=5)),
    ],
)
def test_duration_parser(duration: str, expected: timedelta) -> None:
    assert parse_duration(duration) == expected


@pytest.mark.parametrize("duration", ["", "0m", "1:30", "30", "-5m", "1h 5m"])
def test_duration_parser_rejects_invalid_values(duration: str) -> None:
    with pytest.raises(ReminderValidationError):
        parse_duration(duration)


def test_minutes_are_formatted_for_telegram_callback() -> None:
    assert minutes_to_duration(15) == "15m"
    assert minutes_to_duration(90) == "1h30m"
    assert minutes_to_duration(1440) == "1d"


def test_invalid_id_is_rejected() -> None:
    with pytest.raises(ReminderValidationError, match="id must"):
        Reminder.from_payload(
            reminder_payload(id="contains spaces"), now=NOW, local_tz=MOSCOW
        )


def test_after_completion_requires_positive_delay() -> None:
    with pytest.raises(ReminderValidationError, match="delay_minutes"):
        Reminder.from_payload(
            reminder_payload(reminder_type="after_completion", delay_minutes=0),
            now=NOW,
            local_tz=MOSCOW,
        )
