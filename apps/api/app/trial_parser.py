from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parseaddr
from typing import Any

import httpx
from dateutil import parser as dateparser

from .config import settings

URL_PATTERN = re.compile(r"https?://[^\s)\]]+")
DATE_PATTERN = re.compile(
    r"(\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|"
    r"August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b)",
    re.IGNORECASE,
)
RELATIVE_DAYS_PATTERN = re.compile(
    r"\b(?:in|after)?\s*(\d{1,3})\s+days?\s+(?:left|remaining|until|before|to go)\b",
    re.IGNORECASE,
)
AMOUNT_PATTERN = re.compile(
    r"\$\s*(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)",
    re.IGNORECASE,
)
FREQUENCY_PATTERN = re.compile(
    r"\b(monthly|annually|yearly|per\s+month|per\s+year|every\s+month|every\s+year"
    r"|\/month|\/year|\/mo\b|\/yr\b|per\s+year|a\s+month|a\s+year)\b",
    re.IGNORECASE,
)

TRIAL_STRONG_TERMS = (
    "free trial",
    "start your free",
    "trial ends",
    "trial ending",
    "trial expires",
    "trial period",
    "your trial",
    "after your trial",
    "trial will end",
    "trial subscription",
)
SUBSCRIPTION_STRONG_TERMS = (
    "has been renewed",
    "have been charged",
    "has been charged",
    "we charged",
    "successfully charged",
    "membership renewed",
    "subscription renewed",
    "subscription has been",
    "membership has been",
    "your membership fee",
    "your subscription fee",
    "annual membership",
    "monthly membership",
    "billed monthly",
    "billed annually",
    "billed yearly",
    "charged to your",
    "payment of",
    "your invoice",
    "payment received",
    "payment successful",
    "billing statement",
    "auto-renew",
    "autorenewal",
    "auto renewal",
    "renews on",
    "renewal date",
    "next billing",
    "next charge",
)
TRIAL_SUPPORT_TERMS = (
    "subscription",
    "membership",
    "renewal",
    "billing",
    "charged",
    "charge",
    "cancel anytime",
    "payment method",
)
NON_SUBSCRIPTION_TERMS = (
    "daily digest",
    "newsletter",
    "security alert",
    "verification code",
    "password reset",
    "class reminder",
    "event reminder",
    "tracking number",
    "has shipped",
    # one-time purchase / ride / food receipt signals
    "your trip",
    "your ride",
    "your order",
    "order receipt",
    "trip receipt",
    "order total",
    "items in your",
    "you ordered",
    "order from",
    "estimated delivery",
    "estimated arrival",
    "delivered to",
    "order is on its way",
    "order has been placed",
    "items subtotal",
    "uber eats",
    "doordash",
    "grubhub",
    "instacart",
)

FREQUENCY_NORMALIZE = {
    "monthly": "monthly",
    "annually": "yearly",
    "yearly": "yearly",
    "per month": "monthly",
    "per year": "yearly",
    "every month": "monthly",
    "every year": "yearly",
    "/month": "monthly",
    "/year": "yearly",
    "/mo": "monthly",
    "/yr": "yearly",
    "a month": "monthly",
    "a year": "yearly",
}


@dataclass
class TrialParseResult:
    is_trial: bool
    subscription_type: str | None  # "free_trial" | "paid_subscription" | "unknown"
    service_name: str | None
    billing_amount: str | None
    billing_frequency: str | None
    trial_start_date: str | None
    trial_end_date: str | None
    cancel_url: str | None
    confidence: float
    notes: str | None


async def parse_trial_email(
    *,
    subject: str,
    sender: str,
    snippet: str,
) -> TrialParseResult:
    text = "\n".join([subject, sender, snippet]).strip()

    if settings.claude_api_key:
        result = await _parse_with_claude(text)
        if result is not None:
            return result

    return _heuristic_parse(subject=subject, sender=sender, snippet=snippet)


def _heuristic_parse(*, subject: str, sender: str, snippet: str) -> TrialParseResult:
    combined = f"{subject}\n{snippet}".lower()
    combined_text = subject + " " + snippet

    billing_amount = _find_amount(combined_text)
    billing_frequency = _find_frequency(combined_text)
    cancel_url = _find_url(snippet)

    has_trial_signal = any(term in combined for term in TRIAL_STRONG_TERMS)
    has_subscription_signal = any(term in combined for term in SUBSCRIPTION_STRONG_TERMS)
    support_hits = sum(1 for term in TRIAL_SUPPORT_TERMS if term in combined)
    negative_signal = any(term in combined for term in NON_SUBSCRIPTION_TERMS)

    # Shipping/order confirmation emails are not subscription signals
    if negative_signal and not has_trial_signal and not has_subscription_signal:
        return TrialParseResult(
            is_trial=False,
            subscription_type=None,
            service_name=_guess_service_name(sender),
            billing_amount=None,
            billing_frequency=None,
            trial_start_date=None,
            trial_end_date=None,
            cancel_url=cancel_url,
            confidence=0.1,
            notes="Non-subscription signal detected",
        )

    # Determine subscription type
    if has_trial_signal:
        subscription_type = "free_trial"
    elif has_subscription_signal or billing_amount:
        subscription_type = "paid_subscription"
    elif support_hits >= 2:
        subscription_type = "unknown"
    else:
        subscription_type = None

    is_tracked = has_trial_signal or has_subscription_signal or bool(billing_amount) or support_hits >= 2

    # Extract end date (trial end or next renewal)
    date_str = _find_date(combined_text)
    trial_end_date = _parse_date(date_str) if date_str else None
    if not trial_end_date:
        relative_days = _find_relative_days(combined_text)
        if relative_days is not None:
            trial_end_date = (date.today() + timedelta(days=relative_days)).isoformat()

    # Confidence scoring
    confidence = 0.2
    if has_trial_signal:
        confidence = 0.65
    elif has_subscription_signal:
        confidence = 0.70
    elif billing_amount:
        confidence = 0.60
    elif support_hits >= 2:
        confidence = 0.45

    if trial_end_date:
        confidence = max(confidence, 0.70)
    if billing_amount and billing_frequency:
        confidence = max(confidence, 0.75)

    return TrialParseResult(
        is_trial=is_tracked,
        subscription_type=subscription_type,
        service_name=_guess_service_name(sender),
        billing_amount=billing_amount,
        billing_frequency=billing_frequency,
        trial_start_date=None,
        trial_end_date=trial_end_date,
        cancel_url=cancel_url,
        confidence=confidence,
        notes="Heuristic parse",
    )


async def _parse_with_claude(text: str) -> TrialParseResult | None:
    prompt = (
        "You are extracting subscription and free-trial data from an email. "
        "Return JSON only with these keys: "
        "is_subscription, subscription_type, service_name, billing_amount, billing_frequency, "
        "trial_end_date, cancel_url, confidence.\n\n"
        "Rules:\n"
        "- is_subscription: true if this email is about a paid subscription, free trial, membership, "
        "or recurring charge. False for shipping, newsletters, password resets, etc.\n"
        "- subscription_type: 'free_trial' if it's a trial that will convert to paid; "
        "'paid_subscription' if it's an active recurring charge or renewal; 'unknown' if unclear.\n"
        "- service_name: the company or product name (e.g. 'Amazon Prime', 'Spotify Premium').\n"
        "- billing_amount: the dollar amount as a string (e.g. '$9.99', '$139.00'). null if not found.\n"
        "- billing_frequency: 'monthly', 'yearly', or 'weekly'. null if not found.\n"
        "- trial_end_date: ISO 8601 date (YYYY-MM-DD) when the trial ends or next renewal date. null if not found.\n"
        "- cancel_url: URL to manage or cancel the subscription. null if not found.\n"
        "- confidence: 0.0-1.0 confidence that this is a real subscription or trial email.\n\n"
        f"Email:\n{text}"
    )

    payload = {
        "model": settings.claude_model,
        "max_tokens": 400,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "x-api-key": settings.claude_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(settings.claude_api_url, json=payload, headers=headers)
        if response.status_code >= 400:
            return None
        data = response.json()

    content = data.get("content", [])
    text_out = ""
    if isinstance(content, list) and content:
        text_out = "".join(item.get("text", "") for item in content if item.get("type") == "text")
    elif isinstance(content, str):
        text_out = content

    json_blob = _extract_json(text_out)
    if not json_blob:
        return None

    try:
        parsed = json.loads(json_blob)
    except json.JSONDecodeError:
        return None

    return TrialParseResult(
        is_trial=_clean_bool(parsed.get("is_subscription")),
        subscription_type=_clean_str(parsed.get("subscription_type")),
        service_name=_clean_str(parsed.get("service_name")),
        billing_amount=_clean_str(parsed.get("billing_amount")),
        billing_frequency=_clean_str(parsed.get("billing_frequency")),
        trial_start_date=None,
        trial_end_date=_clean_date(parsed.get("trial_end_date")),
        cancel_url=_clean_str(parsed.get("cancel_url")),
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
        notes="Claude parse",
    )


def _extract_json(text: str) -> str | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _guess_service_name(sender: str) -> str | None:
    name, email = parseaddr(sender)
    if name:
        return name.strip()
    if email and "@" in email:
        domain = email.split("@", 1)[1]
        return domain.split(".")[0].title()
    return None


def _find_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if match:
        return match.group(0)
    return None


def _find_date(text: str) -> str | None:
    match = DATE_PATTERN.search(text)
    if match:
        return match.group(0)
    return None


def _find_relative_days(text: str) -> int | None:
    match = RELATIVE_DAYS_PATTERN.search(text)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except (TypeError, ValueError):
        return None
    if value < 0 or value > 365:
        return None
    return value


def _find_amount(text: str) -> str | None:
    match = AMOUNT_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(0).replace(" ", "")
    return raw if raw else None


def _find_frequency(text: str) -> str | None:
    match = FREQUENCY_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).strip().lower()
    return FREQUENCY_NORMALIZE.get(raw, raw)


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value, fuzzy=True)
        if not dt:
            return None
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _clean_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return value[:10]
        return _parse_date(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    return None


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, int):
        return value != 0
    return False
