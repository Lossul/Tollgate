from __future__ import annotations

from datetime import date, datetime


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def days_remaining(end_date: str | None) -> int | None:
    parsed = parse_iso_date(end_date)
    if not parsed:
        return None
    return (parsed - date.today()).days


def status_from_end_date(end_date: str | None) -> str:
    remaining = days_remaining(end_date)
    if remaining is None:
        return "unknown"
    if remaining < 0:
        return "expired"
    if remaining <= 3:
        return "expiring_soon"
    return "active"
