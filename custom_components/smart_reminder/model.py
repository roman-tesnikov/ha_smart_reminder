"""Reminder data model and validation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import Any

from croniter import CroniterBadCronError, croniter

from .const import ReminderStatus, ReminderType

REMINDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DURATION_PATTERN = re.compile(
    r"^(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?$",
    re.IGNORECASE,
)
CRON_WEEK_INTERVAL_PATTERN = re.compile(
    r"^@every\s+(?P<weeks>[1-9]\d*)w\s+(?P<cron>.+)$", re.IGNORECASE
)


class ReminderValidationError(ValueError):
    """Raised when reminder data is invalid."""


def utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize a datetime in UTC."""
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def parse_datetime(value: Any, local_tz: tzinfo, field_name: str) -> datetime:
    """Parse a datetime and normalize it to UTC."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as err:
            raise ReminderValidationError(
                f"{field_name} must be a valid ISO 8601 datetime"
            ) from err
    else:
        raise ReminderValidationError(f"{field_name} must be a datetime")

    if result.tzinfo is None:
        result = result.replace(tzinfo=local_tz)
    return result.astimezone(UTC)


def parse_optional_datetime(
    value: Any, local_tz: tzinfo, field_name: str
) -> datetime | None:
    """Parse an optional datetime."""
    if value in (None, ""):
        return None
    return parse_datetime(value, local_tz, field_name)


def parse_cron_anchor(value: Any, local_tz: tzinfo) -> datetime | None:
    """Parse an optional cron anchor and normalize it to a local calendar date."""
    parsed = parse_optional_datetime(value, local_tz, "cron_anchor")
    if parsed is None:
        return None
    local_day = parsed.astimezone(local_tz).date()
    return datetime.combine(local_day, time.min, tzinfo=local_tz).astimezone(UTC)


def validate_reminder_id(value: Any) -> str:
    """Validate a reminder identifier suitable for actions and entity IDs."""
    if not isinstance(value, str) or not REMINDER_ID_PATTERN.fullmatch(value.strip()):
        raise ReminderValidationError(
            "id must be 1-64 characters and contain only letters, numbers, "
            "'.', '_' or '-'"
        )
    return value.strip()


def parse_duration(value: str) -> timedelta:
    """Parse a compact duration such as 1h30m."""
    if not isinstance(value, str):
        raise ReminderValidationError("duration must be a string such as 1h30m")
    match = DURATION_PATTERN.fullmatch(value.strip())
    if match is None or not any(match.groupdict().values()):
        raise ReminderValidationError(
            "duration must use the format 2d3h15m (at least one unit is required)"
        )
    duration = timedelta(
        days=int(match.group("days") or 0),
        hours=int(match.group("hours") or 0),
        minutes=int(match.group("minutes") or 0),
    )
    if duration <= timedelta(0):
        raise ReminderValidationError("duration must be greater than zero")
    return duration


def minutes_to_duration(minutes: int) -> str:
    """Format minutes as a compact duration for bot callback commands."""
    days, remainder = divmod(minutes, 24 * 60)
    hours, mins = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return "".join(parts)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReminderValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ReminderValidationError(f"{key} must be a string")
    return value.strip()


def _boolean(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ReminderValidationError(f"{key} must be a boolean")
    return value


def _positive_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReminderValidationError(f"{key} must be a positive integer")
    return value


def _recipient_ids(payload: dict[str, Any]) -> list[str]:
    values = payload.get("recipient_ids", [])
    if values is None:
        return []
    if not isinstance(values, list):
        raise ReminderValidationError("recipient_ids must be a list of strings")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ReminderValidationError(
                "recipient_ids must contain only non-empty strings"
            )
        normalized = value.strip()
        if normalized not in result:
            result.append(normalized)
    return result


def next_cron_occurrence(
    expression: str,
    after: datetime,
    local_tz: tzinfo,
    anchor: datetime | None = None,
) -> datetime:
    """Return the next cron occurrence, respecting HA timezone and week intervals."""
    expression = expression.strip()
    week_match = CRON_WEEK_INTERVAL_PATTERN.fullmatch(expression)
    week_interval = int(week_match.group("weeks")) if week_match else 1
    cron_expression = week_match.group("cron") if week_match else expression
    if len(cron_expression.split()) != 5:
        raise ReminderValidationError("cron must contain exactly 5 fields")
    try:
        anchor_date = None
        if week_match and anchor is not None:
            anchor_date = anchor.astimezone(local_tz).date()
            anchor_start = datetime.combine(
                anchor_date, time.min, tzinfo=local_tz
            ) - timedelta(microseconds=1)
            first_on_anchor = croniter(cron_expression, anchor_start).get_next(datetime)
            if first_on_anchor.date() != anchor_date:
                raise ReminderValidationError(
                    "cron_anchor must be a date matched by the cron expression"
                )

        iterator = croniter(cron_expression, after.astimezone(local_tz))
        result = iterator.get_next(datetime)
        if week_match and anchor_date is not None:
            interval_days = week_interval * 7
            for _ in range(10000):
                if (
                    result.date() >= anchor_date
                    and (result.date() - anchor_date).days % interval_days == 0
                ):
                    break
                result = iterator.get_next(datetime)
            else:
                raise ReminderValidationError(
                    "cron week interval did not produce an occurrence"
                )
    except ReminderValidationError:
        raise
    except (CroniterBadCronError, ValueError, KeyError) as err:
        raise ReminderValidationError("cron is not a valid crontab expression") from err
    if result.tzinfo is None:
        result = result.replace(tzinfo=local_tz)
    return result.astimezone(UTC)


@dataclass(slots=True)
class Reminder:
    """Persistent configuration and runtime state of one reminder."""

    id: str
    name: str
    enabled: bool
    reminder_type: ReminderType
    ignore_dnd: bool
    repeat_interval_minutes: int
    default_snooze_minutes: int
    first_text: str
    repeat_text: str
    snoozed_text: str
    completed_text: str
    recipient_ids: list[str]
    scheduled_at: datetime | None = None
    cron: str | None = None
    cron_anchor: datetime | None = None
    delay_minutes: int | None = None
    status: ReminderStatus = ReminderStatus.SCHEDULED
    next_trigger: datetime | None = None
    last_triggered_at: datetime | None = None
    last_completed_at: datetime | None = None
    repeat_count: int = 0

    @property
    def schedule_signature(self) -> tuple[Any, ...]:
        """Return values which determine the next scheduled occurrence."""
        return (
            self.reminder_type,
            self.scheduled_at,
            self.cron,
            self.cron_anchor,
            self.delay_minutes,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the reminder for storage and the WebSocket API."""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "reminder_type": self.reminder_type.value,
            "scheduled_at": datetime_to_iso(self.scheduled_at),
            "cron": self.cron,
            "cron_anchor": datetime_to_iso(self.cron_anchor),
            "delay_minutes": self.delay_minutes,
            "ignore_dnd": self.ignore_dnd,
            "repeat_interval_minutes": self.repeat_interval_minutes,
            "default_snooze_minutes": self.default_snooze_minutes,
            "first_text": self.first_text,
            "repeat_text": self.repeat_text,
            "snoozed_text": self.snoozed_text,
            "completed_text": self.completed_text,
            "recipient_ids": list(self.recipient_ids),
            "status": self.status.value,
            "next_trigger": datetime_to_iso(self.next_trigger),
            "last_triggered_at": datetime_to_iso(self.last_triggered_at),
            "last_completed_at": datetime_to_iso(self.last_completed_at),
            "repeat_count": self.repeat_count,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        now: datetime,
        local_tz: tzinfo,
    ) -> Reminder:
        """Build and validate a reminder from user input."""
        try:
            reminder_type = ReminderType(payload.get("reminder_type"))
        except (TypeError, ValueError) as err:
            raise ReminderValidationError(
                "reminder_type must be once, cron or after_completion"
            ) from err

        scheduled_at: datetime | None = None
        cron: str | None = None
        cron_anchor: datetime | None = None
        delay_minutes: int | None = None
        if reminder_type is ReminderType.CRON:
            cron = _required_string(payload, "cron")
            week_match = CRON_WEEK_INTERVAL_PATTERN.fullmatch(cron)
            requested_anchor = parse_cron_anchor(payload.get("cron_anchor"), local_tz)
            if week_match is None:
                if requested_anchor is not None:
                    raise ReminderValidationError(
                        "cron_anchor can only be used with an @every Nw schedule"
                    )
                next_trigger = next_cron_occurrence(cron, now, local_tz)
            else:
                cron_anchor = requested_anchor
                if cron_anchor is None:
                    first_trigger = next_cron_occurrence(cron, now, local_tz)
                    cron_anchor = parse_cron_anchor(first_trigger, local_tz)
                next_trigger = next_cron_occurrence(cron, now, local_tz, cron_anchor)
        else:
            scheduled_at = parse_datetime(
                payload.get("scheduled_at"), local_tz, "scheduled_at"
            )
            next_trigger = scheduled_at
            if reminder_type is ReminderType.AFTER_COMPLETION:
                delay_minutes = _positive_int(payload, "delay_minutes", 1440)

        return cls(
            id=validate_reminder_id(payload.get("id")),
            name=_required_string(payload, "name"),
            enabled=_boolean(payload, "enabled", True),
            reminder_type=reminder_type,
            scheduled_at=scheduled_at,
            cron=cron,
            cron_anchor=cron_anchor,
            delay_minutes=delay_minutes,
            ignore_dnd=_boolean(payload, "ignore_dnd", False),
            repeat_interval_minutes=_positive_int(
                payload, "repeat_interval_minutes", 15
            ),
            default_snooze_minutes=_positive_int(payload, "default_snooze_minutes", 30),
            first_text=_required_string(payload, "first_text"),
            repeat_text=_optional_string(payload, "repeat_text"),
            snoozed_text=_optional_string(payload, "snoozed_text"),
            completed_text=_optional_string(payload, "completed_text"),
            recipient_ids=_recipient_ids(payload),
            next_trigger=next_trigger,
        )

    @classmethod
    def from_storage(
        cls, payload: dict[str, Any], *, now: datetime, local_tz: tzinfo
    ) -> Reminder:
        """Restore a reminder, validating both configuration and runtime data."""
        reminder = cls.from_payload(payload, now=now, local_tz=local_tz)
        reminder.cron_anchor = parse_cron_anchor(payload.get("cron_anchor"), local_tz)
        if (
            reminder.reminder_type is ReminderType.CRON
            and CRON_WEEK_INTERVAL_PATTERN.fullmatch(reminder.cron or "")
            and reminder.cron_anchor is None
        ):
            reminder.cron_anchor = parse_cron_anchor(
                payload.get("next_trigger"), local_tz
            ) or parse_cron_anchor(reminder.next_trigger, local_tz)
        try:
            reminder.status = ReminderStatus(
                payload.get("status", ReminderStatus.SCHEDULED)
            )
        except ValueError as err:
            raise ReminderValidationError("stored status is invalid") from err

        reminder.next_trigger = parse_optional_datetime(
            payload.get("next_trigger"), local_tz, "next_trigger"
        )
        if reminder.next_trigger is None:
            reminder.status = ReminderStatus.SCHEDULED
            if reminder.reminder_type is ReminderType.CRON:
                reminder.next_trigger = next_cron_occurrence(
                    reminder.cron or "", now, local_tz, reminder.cron_anchor
                )
            else:
                reminder.next_trigger = reminder.scheduled_at
        reminder.last_triggered_at = parse_optional_datetime(
            payload.get("last_triggered_at"), local_tz, "last_triggered_at"
        )
        reminder.last_completed_at = parse_optional_datetime(
            payload.get("last_completed_at"), local_tz, "last_completed_at"
        )
        repeat_count = payload.get("repeat_count", 0)
        if isinstance(repeat_count, bool) or not isinstance(repeat_count, int):
            raise ReminderValidationError("stored repeat_count is invalid")
        reminder.repeat_count = max(0, repeat_count)
        return reminder
