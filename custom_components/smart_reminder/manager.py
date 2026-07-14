"""Persistent reminder manager and scheduler."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALREADY_COMPLETED_ERROR_TEXT,
    CONF_ALREADY_SNOOZED_ERROR_TEXT,
    CONF_DND_END,
    CONF_DND_START,
    DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
    DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    EVENT_COMPLETED,
    EVENT_REPEATED,
    EVENT_SNOOZED,
    EVENT_TRIGGERED,
    SIGNAL_REMINDERS_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    ReminderStatus,
    ReminderType,
)
from .model import (
    Reminder,
    ReminderValidationError,
    datetime_to_iso,
    minutes_to_duration,
    next_cron_occurrence,
    parse_datetime,
    parse_duration,
    utcnow,
    validate_reminder_id,
)

_LOGGER = logging.getLogger(__name__)


class ReminderNotFoundError(HomeAssistantError):
    """Raised when a reminder does not exist."""


class ReminderAlreadyExistsError(HomeAssistantError):
    """Raised when a reminder ID already exists."""


def _parse_clock(value: Any, default: str) -> time:
    """Parse a config-flow time value."""
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        value = default
    try:
        return time.fromisoformat(value)
    except ValueError:
        return time.fromisoformat(default)


def _local_datetime(day: date, clock: time, zone: tzinfo) -> datetime:
    """Combine a date and a wall clock time in a timezone."""
    return datetime.combine(day, clock).replace(tzinfo=zone)


class ReminderManager:
    """Own reminder state, persistence, scheduling and events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.entry = entry
        self.reminders: dict[str, Reminder] = {}
        self.time_zone = dt_util.get_time_zone(hass.config.time_zone) or UTC
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._lock = asyncio.Lock()
        self._cancel_timer: Callable[[], None] | None = None
        self._cancel_start_listener: Callable[[], None] | None = None
        self._started = False
        self._stopped = False
        self._apply_options({**entry.data, **entry.options})

    @property
    def dnd_start(self) -> str:
        """Return the configured DnD start as an ISO clock string."""
        return self._dnd_start.isoformat()

    @property
    def dnd_end(self) -> str:
        """Return the configured DnD end as an ISO clock string."""
        return self._dnd_end.isoformat()

    def _apply_options(self, options: dict[str, Any]) -> None:
        self._dnd_start = _parse_clock(options.get(CONF_DND_START), DEFAULT_DND_START)
        self._dnd_end = _parse_clock(options.get(CONF_DND_END), DEFAULT_DND_END)
        self._already_snoozed_error_text = self._message_template(
            options.get(CONF_ALREADY_SNOOZED_ERROR_TEXT),
            DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
        )
        self._already_completed_error_text = self._message_template(
            options.get(CONF_ALREADY_COMPLETED_ERROR_TEXT),
            DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
        )

    @staticmethod
    def _message_template(value: Any, default: str) -> str:
        """Return a configured lifecycle response or its non-empty default."""
        if not isinstance(value, str) or not (value := value.strip()):
            return default
        return value

    async def async_load(self) -> None:
        """Load reminders from Home Assistant storage."""
        stored = await self._store.async_load()
        if not stored:
            return
        raw_reminders = stored.get("reminders", [])
        if not isinstance(raw_reminders, list):
            _LOGGER.error("Ignoring invalid Smart Reminder storage payload")
            return
        now = utcnow()
        for raw in raw_reminders:
            if not isinstance(raw, dict):
                _LOGGER.warning("Ignoring a non-object reminder in storage")
                continue
            try:
                reminder = Reminder.from_storage(raw, now=now, local_tz=self.time_zone)
            except ReminderValidationError as err:
                _LOGGER.warning(
                    "Ignoring invalid stored reminder %s: %s", raw.get("id"), err
                )
                continue
            if reminder.id in self.reminders:
                _LOGGER.warning("Ignoring duplicate stored reminder ID %s", reminder.id)
                continue
            self.reminders[reminder.id] = reminder

    async def async_start(self) -> None:
        """Start scheduling after HA automations have had a chance to load."""
        self._stopped = False
        if self.hass.state is CoreState.running:
            self._started = True
            await self.async_process_due()
            return

        @callback
        def _handle_started(_event: Event) -> None:
            self._cancel_start_listener = None
            self._started = True
            self.hass.async_create_task(self.async_process_due())

        self._cancel_start_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, _handle_started
        )

    async def async_stop(self) -> None:
        """Stop timers and startup listeners."""
        self._stopped = True
        self._started = False
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
        if self._cancel_start_listener is not None:
            self._cancel_start_listener()
            self._cancel_start_listener = None

    async def async_options_updated(self, options: dict[str, Any]) -> None:
        """Apply changed integration options."""
        async with self._lock:
            self._apply_options(options)
            self._arm_timer()

    def list_serialized(self) -> list[dict[str, Any]]:
        """Return reminders sorted by next execution time."""
        far_future = datetime.max.replace(tzinfo=UTC)
        reminders = sorted(
            self.reminders.values(),
            key=lambda item: (item.next_trigger or far_future, item.name.casefold()),
        )
        return [reminder.to_dict() for reminder in reminders]

    def get(self, reminder_id: str) -> Reminder:
        """Return a reminder or raise a domain-specific error."""
        try:
            return self.reminders[reminder_id]
        except KeyError as err:
            raise ReminderNotFoundError(
                f"Reminder '{reminder_id}' was not found"
            ) from err

    async def async_create(self, payload: dict[str, Any]) -> Reminder:
        """Create and persist a reminder."""
        async with self._lock:
            reminder = Reminder.from_payload(
                payload, now=utcnow(), local_tz=self.time_zone
            )
            if reminder.id in self.reminders:
                raise ReminderAlreadyExistsError(
                    f"Reminder '{reminder.id}' already exists"
                )
            self.reminders[reminder.id] = reminder
            await self._async_save()
            self._notify_updated()
            self._arm_timer()
            return reminder

    async def async_update(self, reminder_id: str, payload: dict[str, Any]) -> Reminder:
        """Update a reminder while preserving runtime state when possible."""
        async with self._lock:
            current = self.get(validate_reminder_id(reminder_id))
            normalized_payload = dict(payload)
            normalized_payload["id"] = current.id
            requested_next_trigger = None
            if "next_trigger" in normalized_payload:
                requested_next_trigger = parse_datetime(
                    normalized_payload.pop("next_trigger"),
                    self.time_zone,
                    "next_trigger",
                )
            updated = Reminder.from_payload(
                normalized_payload, now=utcnow(), local_tz=self.time_zone
            )
            if updated.schedule_signature == current.schedule_signature:
                updated.status = current.status
                updated.next_trigger = current.next_trigger
                updated.cron_anchor = current.cron_anchor
                updated.last_triggered_at = current.last_triggered_at
                updated.last_completed_at = current.last_completed_at
                updated.repeat_count = current.repeat_count
            if requested_next_trigger is not None:
                updated.next_trigger = requested_next_trigger
            self.reminders[current.id] = updated
            await self._async_save()
            self._notify_updated()
            self._arm_timer()
            return updated

    async def async_delete(self, reminder_id: str) -> None:
        """Delete a reminder."""
        async with self._lock:
            reminder_id = validate_reminder_id(reminder_id)
            self.get(reminder_id)
            del self.reminders[reminder_id]
            await self._async_save()
            self._notify_updated()
            self._arm_timer()

    async def async_set_enabled(self, reminder_id: str, enabled: bool) -> None:
        """Enable or disable a reminder."""
        if not isinstance(enabled, bool):
            raise ReminderValidationError("enabled must be a boolean")
        async with self._lock:
            reminder = self.get(validate_reminder_id(reminder_id))
            if reminder.enabled == enabled:
                return
            reminder.enabled = enabled
            await self._async_save()
            self._notify_updated()
            self._arm_timer()

    async def async_snooze(self, reminder_id: str, duration: str) -> Reminder:
        """Snooze a reminder for a compact duration."""
        delta = parse_duration(duration)
        now = utcnow()
        async with self._lock:
            reminder = self.get(validate_reminder_id(reminder_id))
            previous_trigger = reminder.next_trigger
            already_snoozed = reminder.status is ReminderStatus.SNOOZED
            if not already_snoozed:
                reminder.status = ReminderStatus.SNOOZED
                reminder.next_trigger = now + delta
                await self._async_save()
            event_data = self._event_data(
                reminder,
                text=(
                    self._already_snoozed_error_text
                    if already_snoozed
                    else reminder.snoozed_text
                ),
                occurred_at=now,
                scheduled_for=None if already_snoozed else previous_trigger,
            )
            event_data["duration"] = duration.strip().lower()
            event_data["snoozed_until"] = datetime_to_iso(reminder.next_trigger)
            event_data["action_succeeded"] = not already_snoozed
            event_data["reason"] = "already_snoozed" if already_snoozed else None
            if not already_snoozed:
                self._notify_updated()
                self._arm_timer()
        self.hass.bus.async_fire(EVENT_SNOOZED, event_data)
        return reminder

    async def async_complete(self, reminder_id: str) -> Reminder:
        """Complete a reminder and calculate its next lifecycle state."""
        now = utcnow()
        async with self._lock:
            reminder = self.get(validate_reminder_id(reminder_id))
            already_completed = (
                reminder.status is ReminderStatus.SCHEDULED
                and reminder.last_completed_at is not None
            )
            if not already_completed:
                reminder.last_completed_at = now
                reminder.repeat_count = 0
                if reminder.reminder_type is ReminderType.ONCE:
                    reminder.next_trigger = None
                elif reminder.reminder_type is ReminderType.CRON:
                    reminder.status = ReminderStatus.SCHEDULED
                    reminder.next_trigger = next_cron_occurrence(
                        reminder.cron or "",
                        now,
                        self.time_zone,
                        reminder.cron_anchor,
                    )
                else:
                    reminder.status = ReminderStatus.SCHEDULED
                    reminder.next_trigger = now + timedelta(
                        minutes=reminder.delay_minutes or 1
                    )

            event_data = self._event_data(
                reminder,
                text=(
                    self._already_completed_error_text
                    if already_completed
                    else reminder.completed_text
                ),
                occurred_at=now,
                scheduled_for=None,
            )
            event_data["action_succeeded"] = not already_completed
            event_data["reason"] = "already_completed" if already_completed else None
            if not already_completed:
                if reminder.reminder_type is ReminderType.ONCE:
                    del self.reminders[reminder.id]
                await self._async_save()
                self._notify_updated()
                self._arm_timer()
        self.hass.bus.async_fire(EVENT_COMPLETED, event_data)
        return reminder

    async def async_process_due(self) -> None:
        """Process every reminder currently due, coalescing missed repetitions."""
        if self._stopped or not self._started:
            return
        events: list[tuple[str, dict[str, Any]]] = []
        async with self._lock:
            now = utcnow()
            due = sorted(
                (
                    reminder
                    for reminder in self.reminders.values()
                    if reminder.enabled
                    and reminder.next_trigger is not None
                    and reminder.next_trigger <= now
                ),
                key=lambda reminder: reminder.next_trigger or now,
            )
            changed = False
            for reminder in due:
                if (
                    not reminder.ignore_dnd
                    and (dnd_end := self._dnd_end_for(now)) is not None
                ):
                    reminder.next_trigger = dnd_end
                    changed = True
                    continue

                scheduled_for = reminder.next_trigger
                previous_status = reminder.status
                is_repeat = previous_status in (
                    ReminderStatus.ACTIVE,
                    ReminderStatus.SNOOZED,
                )
                event_type = EVENT_REPEATED if is_repeat else EVENT_TRIGGERED
                if is_repeat:
                    text = reminder.repeat_text or reminder.first_text
                else:
                    text = reminder.first_text
                reminder.status = ReminderStatus.ACTIVE
                reminder.last_triggered_at = now
                reminder.repeat_count = reminder.repeat_count + 1 if is_repeat else 0
                reminder.next_trigger = now + timedelta(
                    minutes=reminder.repeat_interval_minutes
                )
                events.append(
                    (
                        event_type,
                        self._event_data(
                            reminder,
                            text=text,
                            occurred_at=now,
                            scheduled_for=scheduled_for,
                        ),
                    )
                )
                changed = True

            if changed:
                await self._async_save()
                self._notify_updated()
            self._arm_timer()

        for event_type, event_data in events:
            self.hass.bus.async_fire(event_type, event_data)

    def _dnd_end_for(self, moment: datetime) -> datetime | None:
        """Return the DnD end in UTC if moment is inside the quiet period."""
        if self._dnd_start == self._dnd_end:
            return None
        local = moment.astimezone(self.time_zone)
        clock = local.timetz().replace(tzinfo=None)
        if self._dnd_start < self._dnd_end:
            if not self._dnd_start <= clock < self._dnd_end:
                return None
            end_day = local.date()
        else:
            if self._dnd_end <= clock < self._dnd_start:
                return None
            end_day = (
                local.date() + timedelta(days=1)
                if clock >= self._dnd_start
                else local.date()
            )
        return _local_datetime(end_day, self._dnd_end, self.time_zone).astimezone(UTC)

    def _event_data(
        self,
        reminder: Reminder,
        *,
        text: str,
        occurred_at: datetime,
        scheduled_for: datetime | None,
    ) -> dict[str, Any]:
        """Build the stable event contract used by automations."""
        return {
            "reminder_id": reminder.id,
            "name": reminder.name,
            "reminder_type": reminder.reminder_type.value,
            "status": reminder.status.value,
            "text": text,
            "recipient_ids": list(reminder.recipient_ids),
            "ignore_dnd": reminder.ignore_dnd,
            "default_snooze_minutes": reminder.default_snooze_minutes,
            "default_snooze_duration": minutes_to_duration(
                reminder.default_snooze_minutes
            ),
            "repeat_count": reminder.repeat_count,
            "occurred_at": datetime_to_iso(occurred_at),
            "scheduled_for": datetime_to_iso(scheduled_for),
            "next_trigger": datetime_to_iso(reminder.next_trigger),
            "cron_anchor": datetime_to_iso(reminder.cron_anchor),
        }

    async def _async_save(self) -> None:
        """Persist all reminders immediately after a state transition."""
        await self._store.async_save({"reminders": self.list_serialized()})

    @callback
    def _notify_updated(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_REMINDERS_UPDATED)

    @callback
    def _arm_timer(self) -> None:
        """Arm one timer for the nearest enabled reminder."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
        if self._stopped or not self._started:
            return
        next_trigger = min(
            (
                reminder.next_trigger
                for reminder in self.reminders.values()
                if reminder.enabled and reminder.next_trigger is not None
            ),
            default=None,
        )
        if next_trigger is None:
            return
        if next_trigger <= utcnow():
            self.hass.async_create_task(self.async_process_due())
            return

        @callback
        def _handle_timer(_now: datetime) -> None:
            self._cancel_timer = None
            self.hass.async_create_task(self.async_process_due())

        self._cancel_timer = async_track_point_in_utc_time(
            self.hass, _handle_timer, next_trigger
        )
