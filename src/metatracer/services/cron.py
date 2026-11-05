"""Five-field UTC crontab for ``metatracer watch --cron`` (TASK-44).

No third-party scheduler. Invalid expressions fail before a scan starts.
Timezone is UTC so Docker/systemd without a host TZ stay deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_ALIASES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DOW_NAMES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}

_BOUNDS = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week
)

_MAX_MINUTES = 366 * 24 * 60


class CronError(ValueError):
    """The crontab is not a 5-field UTC expression MetaTracer accepts."""


@dataclass(frozen=True, slots=True)
class CronSchedule:
    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]
    source: str

    def matches(self, moment: datetime) -> bool:
        stamp = _as_utc(moment)
        return (
            stamp.minute in self.minute
            and stamp.hour in self.hour
            and stamp.day in self.day
            and stamp.month in self.month
            and (stamp.weekday() + 1) % 7 in self.weekday
        )


def parse_cron(expr: str) -> CronSchedule:
    """Parse a 5-field crontab or a ``@daily``-style alias."""
    raw = (expr or "").strip()
    if not raw:
        raise CronError("crontab is empty")
    lowered = raw.lower()
    if lowered in _ALIASES:
        raw = _ALIASES[lowered]
    fields = raw.split()
    if len(fields) != 5:
        raise CronError("crontab must have 5 fields (minute hour day month weekday)")
    minute = _parse_field(fields[0], *_BOUNDS[0], names=None)
    hour = _parse_field(fields[1], *_BOUNDS[1], names=None)
    day = _parse_field(fields[2], *_BOUNDS[2], names=None)
    month = _parse_field(fields[3], *_BOUNDS[3], names=_MONTH_NAMES)
    weekday = _parse_field(fields[4], *_BOUNDS[4], names=_DOW_NAMES, sunday_seven=True)
    return CronSchedule(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        weekday=weekday,
        source=expr.strip(),
    )


def next_fire(schedule: CronSchedule, after: datetime) -> datetime:
    """Return the next UTC minute strictly after ``after`` that matches.

    Raises :class:`CronError` if nothing matches in 366 days (e.g. 31 February).
    """
    cursor = _as_utc(after).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(_MAX_MINUTES):
        if schedule.matches(cursor):
            return cursor
        cursor += timedelta(minutes=1)
    raise CronError("crontab does not fire in the next 366 days")


def seconds_until(schedule: CronSchedule, after: datetime | None = None) -> float:
    """Seconds to sleep until the next fire (>= 1)."""
    now = after if after is not None else datetime.now(UTC)
    delta = (next_fire(schedule, now) - _as_utc(now)).total_seconds()
    return max(1.0, delta)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _parse_field(
    field: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None,
    sunday_seven: bool = False,
) -> frozenset[int]:
    values: set[int] = set()
    for part in field.lower().split(","):
        part = part.strip()
        if not part:
            raise CronError("empty crontab field")
        values.update(_parse_part(part, minimum, maximum, names=names, sunday_seven=sunday_seven))
    if not values:
        raise CronError("crontab field selected no values")
    return frozenset(values)


def _parse_part(
    part: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None,
    sunday_seven: bool,
) -> set[int]:
    step = 1
    body = part
    if "/" in part:
        body, step_raw = part.split("/", 1)
        if not step_raw.isdigit() or int(step_raw) < 1:
            raise CronError(f"invalid crontab step: {part}")
        step = int(step_raw)
    if body in {"", "*"}:
        start, end = minimum, maximum
    elif "-" in body:
        left, right = body.split("-", 1)
        start = _atom(left, minimum, maximum, names=names, sunday_seven=sunday_seven)
        end = _atom(right, minimum, maximum, names=names, sunday_seven=sunday_seven)
        if end < start:
            raise CronError(f"crontab range inverted: {part}")
    else:
        value = _atom(body, minimum, maximum, names=names, sunday_seven=sunday_seven)
        if step != 1 and body != "*":
            # "5/2" means 5,7,9… through the field max (common cron dialect).
            start, end = value, maximum
        else:
            return {value}
        return set(range(start, end + 1, step))
    return set(range(start, end + 1, step))


def _atom(
    token: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None,
    sunday_seven: bool,
) -> int:
    token = token.strip()
    if names and token in names:
        return names[token]
    if not token.isdigit():
        raise CronError(f"invalid crontab token: {token}")
    value = int(token)
    if sunday_seven and value == 7:
        value = 0
    if value < minimum or value > maximum:
        raise CronError(f"crontab value {value} out of range {minimum}-{maximum}")
    return value
