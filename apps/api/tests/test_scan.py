from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth import create_session_token
from app.config import settings


def _message(message_id: str, subject: str, sender: str, snippet: str) -> dict:
    return {
        "id": message_id,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
            ]
        },
    }


MESSAGES = {
    # Two monthly Netflix receipts: should collapse to one row.
    "m1": _message(
        "m1",
        "Your Netflix membership has been renewed",
        "Netflix <info@mailer.netflix.com>",
        "Your Netflix membership has been renewed. You were charged $15.49 per month. Next billing date: December 12, 2026.",
    ),
    "m2": _message(
        "m2",
        "Your Netflix membership has been renewed",
        "Netflix <info@mailer.netflix.com>",
        "Your Netflix membership has been renewed. You were charged $15.49 per month. Next billing date: November 12, 2026.",
    ),
    # Only found by the refund pass.
    "m3": _message(
        "m3",
        "Your refund has been issued",
        "Adobe <mail@adobe.com>",
        "We've issued a refund of $54.99 to your original payment method. Please allow 5-10 business days.",
    ),
    "m4": _message(
        "m4",
        "We charged you twice",
        "Dropbox <no-reply@dropbox.com>",
        "It looks like you were charged twice for your Plus plan: $11.99 on Oct 2.",
    ),
}


@pytest.fixture()
def scan_env(monkeypatch):
    calls: list[str | None] = []
    stored: dict[str, list] = {}

    async def fake_get_user(user_id: str):
        return {
            "id": user_id,
            "google_tokens": {
                "access_token": "fake",
                "expires_at": int(time.time()) + 3600,
            },
        }

    async def fake_list_messages(access_token, *, max_results=50, query=None):
        calls.append(query)
        if query == main.REFUND_GMAIL_QUERY:
            # m2 overlaps with the subscription pass on purpose.
            return [{"id": "m2"}, {"id": "m3"}, {"id": "m4"}]
        return [{"id": "m1"}, {"id": "m2"}]

    async def fake_get_message_metadata(access_token, message_id):
        return MESSAGES[message_id]

    async def fake_replace(user_id, trials):
        stored["trials"] = trials
        return trials

    monkeypatch.setattr(main, "get_user", fake_get_user)
    monkeypatch.setattr(main, "list_messages", fake_list_messages)
    monkeypatch.setattr(main, "get_message_metadata", fake_get_message_metadata)
    monkeypatch.setattr(main, "replace_email_trials", fake_replace)

    client = TestClient(main.app)
    client.cookies.set(settings.session_cookie_name, create_session_token("u1", "alex@example.com"))
    return client, calls, stored


def test_scan_finds_refunds_and_dedupes_subscriptions(scan_env):
    client, calls, stored = scan_env

    response = client.post("/scan", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["scanned"] == 4  # m2 not double counted across the two passes
    assert len(calls) == 2 and main.REFUND_GMAIL_QUERY in calls

    by_type: dict[str, list] = {}
    for trial in stored["trials"]:
        by_type.setdefault(trial["subscription_type"], []).append(trial)

    assert len(by_type["paid_subscription"]) == 1  # two Netflix receipts -> one row
    assert by_type["paid_subscription"][0]["end_date"] == "2026-12-12"
    assert by_type["refund"][0]["billing_amount"] == "$54.99"
    assert by_type["refund"][0]["status"] == "refund_pending"
    assert by_type["duplicate_charge"][0]["billing_amount"] == "$11.99"


def test_custom_query_skips_refund_pass(scan_env):
    client, calls, _ = scan_env

    response = client.post("/scan", json={"query": "from:netflix"})

    assert response.status_code == 200
    assert calls == ["from:netflix"]
