from __future__ import annotations

import pytest

from app.drafts import build_draft, default_kind


def _trial(**overrides):
    base = {
        "id": "t1",
        "service_name": "Notion",
        "subscription_type": "paid_subscription",
        "billing_amount": "$10.00",
        "billing_frequency": "monthly",
        "end_date": "2026-10-21",
    }
    base.update(overrides)
    return base


def test_cancel_paid_subscription_mentions_price_and_account():
    draft = build_draft(_trial(), "cancel", user_email="alex@example.com")

    assert draft["kind"] == "cancel"
    assert "Notion" in draft["subject"]
    assert "$10.00/monthly" in draft["body"]
    assert "alex@example.com" in draft["body"]


def test_cancel_free_trial_mentions_end_date():
    draft = build_draft(_trial(subscription_type="free_trial"), "cancel")

    assert "free trial" in draft["subject"].lower()
    assert "2026-10-21" in draft["body"]


def test_unknown_fields_become_placeholders_not_guesses():
    draft = build_draft(
        _trial(billing_amount=None, billing_frequency=None, service_name=""),
        "cancel",
    )

    assert "[SERVICE NAME]" in draft["body"]
    assert "[AMOUNT]" in draft["body"]
    assert "[ACCOUNT EMAIL]" in draft["body"]
    assert "None" not in draft["body"]


@pytest.mark.parametrize(
    "sub_type, subject_fragment",
    [
        ("duplicate_charge", "Duplicate charge"),
        ("refund", "refund"),
        ("paid_subscription", "Refund request"),
    ],
)
def test_refund_drafts_by_type(sub_type, subject_fragment):
    draft = build_draft(_trial(subscription_type=sub_type), "refund")

    assert draft["kind"] == "refund"
    assert subject_fragment in draft["subject"]
    assert "[CHARGE DATE]" in draft["body"]


def test_default_kind():
    assert default_kind(_trial(subscription_type="refund")) == "refund"
    assert default_kind(_trial(subscription_type="duplicate_charge")) == "refund"
    assert default_kind(_trial(subscription_type="free_trial")) == "cancel"
    assert build_draft(_trial(subscription_type="refund"))["kind"] == "refund"


def test_invalid_kind_raises():
    with pytest.raises(ValueError):
        build_draft(_trial(), "explode")
