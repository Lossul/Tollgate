from __future__ import annotations

import re
from typing import Any

from .trial_utils import days_remaining

# Record types that are real recurring charges / trials (vs. refund records).
SUBSCRIPTION_TYPES = {"paid_subscription", "free_trial", "unknown"}
REFUND_TYPES = {"refund", "duplicate_charge"}

# Words that show up in a sender display name but are not part of the service name.
_NAME_NOISE = {
    "inc",
    "llc",
    "ltd",
    "co",
    "corp",
    "billing",
    "support",
    "team",
    "receipts",
    "receipt",
    "noreply",
    "no",
    "reply",
    "payments",
    "payment",
    "account",
    "accounts",
    "subscriptions",
    "subscription",
    "membership",
    "the",
}

_WEEKS_PER_MONTH = 52 / 12


def parse_amount(value: Any) -> float | None:
    """'$1,299.00' -> 1299.0. Returns None if there is no usable number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?", str(value))
    if not match:
        return None
    whole = match.group(1).replace(",", "")
    cents = match.group(2) or "0"
    try:
        return float(f"{whole}.{cents}")
    except ValueError:
        return None


def monthly_cost(amount: Any, frequency: str | None) -> float | None:
    """Normalize a charge to a per-month cost. None if frequency is unknown."""
    value = parse_amount(amount)
    if value is None or not frequency:
        return None
    freq = frequency.strip().lower()
    if freq in {"monthly", "month", "mo"}:
        return value
    if freq in {"yearly", "annually", "year", "yr", "annual"}:
        return value / 12
    if freq in {"weekly", "week"}:
        return value * _WEEKS_PER_MONTH
    return None


def normalize_service_name(name: str | None) -> str:
    if not name:
        return ""
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    kept = [t for t in tokens if t not in _NAME_NOISE]
    return "".join(kept or tokens)


def _record_score(trial: dict[str, Any], position: int) -> tuple:
    """Higher is better. Prefer complete records, then the latest renewal date,
    then whichever came first in the list (Gmail returns newest first)."""
    has_amount = parse_amount(trial.get("billing_amount")) is not None
    has_frequency = bool(trial.get("billing_frequency"))
    end_date = trial.get("end_date") or ""
    return (has_amount and has_frequency, has_amount, end_date, -position)


def dedupe_by_service(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per service. A subscription that bills monthly produces a
    receipt email every month; without this the dashboard would list it (and
    count its cost) once per email. Refund records are separate events and are
    left alone."""
    best: dict[str, tuple[tuple, int, dict[str, Any]]] = {}
    passthrough: list[tuple[int, dict[str, Any]]] = []

    for position, trial in enumerate(trials):
        if trial.get("subscription_type") in REFUND_TYPES:
            passthrough.append((position, trial))
            continue
        key = normalize_service_name(trial.get("service_name")) or f"__id_{position}"
        score = _record_score(trial, position)
        current = best.get(key)
        if current is None or score > current[0]:
            best[key] = (score, position, trial)

    merged = [(position, rec) for _, position, rec in best.values()] + passthrough
    merged.sort(key=lambda item: item[0])
    return [rec for _, rec in merged]


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers for the top of the dashboard."""
    subs = [t for t in dedupe_by_service(trials) if t.get("subscription_type") in SUBSCRIPTION_TYPES]
    refunds = [t for t in trials if t.get("subscription_type") in REFUND_TYPES]

    monthly_total = 0.0
    paid_counted = 0
    paid_unpriced = 0
    trial_exposure = 0.0
    trials_active = 0
    trials_unpriced = 0

    for sub in subs:
        sub_type = sub.get("subscription_type")
        cost = monthly_cost(sub.get("billing_amount"), sub.get("billing_frequency"))

        if sub_type == "free_trial":
            remaining = days_remaining(sub.get("end_date"))
            if remaining is not None and remaining < 0:
                continue  # trial already over
            trials_active += 1
            if cost is None:
                trials_unpriced += 1
            else:
                trial_exposure += cost
            continue

        if cost is None:
            paid_unpriced += 1
        else:
            monthly_total += cost
            paid_counted += 1

    refund_amount = 0.0
    refunds_pending = 0
    for item in refunds:
        if item.get("status") == "refund_pending":
            refunds_pending += 1
        value = parse_amount(item.get("billing_amount"))
        if value is not None and item.get("subscription_type") == "refund":
            refund_amount += value

    return {
        "monthly_total": round(monthly_total, 2),
        "yearly_total": round(monthly_total * 12, 2),
        "paid_counted": paid_counted,
        "paid_unpriced": paid_unpriced,
        "trials_active": trials_active,
        "trials_unpriced": trials_unpriced,
        "trial_monthly_exposure": round(trial_exposure, 2),
        "refund_count": len(refunds),
        "refunds_pending": refunds_pending,
        "refund_amount": round(refund_amount, 2),
    }
