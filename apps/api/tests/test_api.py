from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth import create_session_token
from app.config import settings

TRIALS = [
    {
        "id": "sub-1",
        "user_id": "u1",
        "service_name": "Netflix",
        "subscription_type": "paid_subscription",
        "billing_amount": "$15.00",
        "billing_frequency": "monthly",
        "end_date": "2099-01-01",
        "status": "active",
    },
    {
        "id": "ref-1",
        "user_id": "u1",
        "service_name": "Adobe",
        "subscription_type": "refund",
        "billing_amount": "$54.99",
        "billing_frequency": None,
        "end_date": None,
        "status": "refund_pending",
    },
]


@pytest.fixture()
def client(monkeypatch):
    async def fake_list_trials(user_id: str):
        return [t for t in TRIALS if t["user_id"] == user_id]

    monkeypatch.setattr(main, "list_trials", fake_list_trials)
    test_client = TestClient(main.app)
    token = create_session_token("u1", "alex@example.com")
    test_client.cookies.set(settings.session_cookie_name, token)
    return test_client


def test_trials_includes_summary(client):
    response = client.get("/trials")

    assert response.status_code == 200
    body = response.json()
    assert len(body["trials"]) == 2
    assert body["summary"]["monthly_total"] == 15.0
    assert body["summary"]["refunds_pending"] == 1


def test_draft_defaults_to_cancel_for_subscription(client):
    response = client.post("/trials/sub-1/draft", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "cancel"
    assert "alex@example.com" in body["body"]


def test_draft_defaults_to_refund_for_refund_record(client):
    response = client.post("/trials/ref-1/draft", json={})

    assert response.status_code == 200
    assert response.json()["kind"] == "refund"


def test_draft_unknown_id_is_404(client):
    assert client.post("/trials/nope/draft", json={}).status_code == 404


def test_draft_bad_kind_is_400(client):
    assert client.post("/trials/sub-1/draft", json={"kind": "explode"}).status_code == 400


def test_draft_requires_login():
    anonymous = TestClient(main.app)

    assert anonymous.post("/trials/sub-1/draft", json={}).status_code == 401
    assert anonymous.get("/trials").status_code == 401
