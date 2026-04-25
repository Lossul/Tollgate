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
TRIAL_SUPPORT_TERMS = (
    "subscription",
    "membership",
    "auto-renew",
    "renews",
    "renewal",
    "billing",
    "charged",
    "charge",
    "cancel anytime",
    "payment method",
)
NON_TRIAL_TERMS = (
    "daily digest",
    "newsletter",
    "order",
    "shipment",
    "security alert",
    "verification code",
    "password reset",
    "class reminder",
    "event reminder",
)


@dataclass
class TrialParseResult:
    is_trial: bool
    service_name: str | None
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
    if "trial" not in combined and "free" not in combined:
        return TrialParseResult(
            is_trial=False,
            service_name=_guess_service_name(sender),
            trial_start_date=None,
            trial_end_date=None,
            cancel_url=_find_url(snippet),
            confidence=0.1,
            notes="No trial signals",
        )

    combined_text = subject + " " + snippet
    date_str = _find_date(combined_text)
    trial_end_date = _parse_date(date_str) if date_str else None
    if not trial_end_date:
        relative_days = _find_relative_days(combined_text)
        if relative_days is not None:
            trial_end_date = (date.today() + timedelta(days=relative_days)).isoformat()
    strong_signal = any(term in combined for term in TRIAL_STRONG_TERMS)
    support_hits = sum(1 for term in TRIAL_SUPPORT_TERMS if term in combined)
    negative_signal = any(term in combined for term in NON_TRIAL_TERMS)
    is_trial = strong_signal or support_hits >= 2
    if negative_signal and not strong_signal:
        is_trial = False

    confidence = 0.2
    if strong_signal:
        confidence = 0.65
    elif support_hits >= 2:
        confidence = 0.45
    if trial_end_date:
        confidence = max(confidence, 0.7)

    return TrialParseResult(
        is_trial=is_trial,
        service_name=_guess_service_name(sender),
        trial_start_date=None,
        trial_end_date=trial_end_date,
        cancel_url=_find_url(snippet),
        confidence=confidence,
        notes="Heuristic parse",
    )


async def _parse_with_claude(text: str) -> TrialParseResult | None:
    prompt = (
        "You are extracting free-trial data from an email. "
        "Return JSON only with keys: is_trial, service_name, trial_start_date, trial_end_date, cancel_url, confidence. "
        "Use ISO 8601 dates (YYYY-MM-DD) when possible. "
        "Use is_trial=true only when there is credible evidence this email is about a free trial that can convert to paid. "
        "If unknown, use null. Confidence between 0 and 1.\n\n"
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
        is_trial=_clean_bool(parsed.get("is_trial")),
        service_name=_clean_str(parsed.get("service_name")),
        trial_start_date=_clean_date(parsed.get("trial_start_date")),
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
