from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.refund_parser import detect_refund
from app.trial_parser import _heuristic_parse

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "emails.json").read_text(encoding="utf-8")
)


def _ids(fixtures):
    return [f["name"] for f in fixtures]


@pytest.mark.parametrize("fx", FIXTURES, ids=_ids(FIXTURES))
def test_refund_detection(fx):
    result = detect_refund(subject=fx["subject"], sender=fx["sender"], snippet=fx["snippet"])
    expected = fx["expect_refund"]

    if expected is None:
        assert result is None
        return

    assert result is not None
    assert result.kind == expected["kind"]
    assert result.status == expected["status"]
    assert result.amount == expected["amount"]


SUBSCRIPTION_FIXTURES = [f for f in FIXTURES if "expect_subscription" in f]


@pytest.mark.parametrize("fx", SUBSCRIPTION_FIXTURES, ids=_ids(SUBSCRIPTION_FIXTURES))
def test_subscription_parsing(fx):
    result = _heuristic_parse(subject=fx["subject"], sender=fx["sender"], snippet=fx["snippet"])
    expected = fx["expect_subscription"]

    assert result.is_trial == expected["is_trial"]
    for field in ("subscription_type", "billing_amount", "billing_frequency", "trial_end_date"):
        if field in expected:
            assert getattr(result, field) == expected[field], field


@pytest.mark.parametrize("fx", SUBSCRIPTION_FIXTURES, ids=_ids(SUBSCRIPTION_FIXTURES))
def test_real_subscriptions_are_not_flagged_as_refunds(fx):
    # A renewal receipt must never be routed down the refund path.
    assert detect_refund(subject=fx["subject"], sender=fx["sender"], snippet=fx["snippet"]) is None
