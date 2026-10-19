from __future__ import annotations

import pytest

from app.savings import (
    dedupe_by_service,
    monthly_cost,
    normalize_service_name,
    parse_amount,
    summarize,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$9.99", 9.99),
        ("$1,299.00", 1299.0),
        ("$10", 10.0),
        ("  $ 4.5", 4.5),
        (None, None),
        ("free", None),
        ("", None),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "amount, frequency, expected",
    [
        ("$15.00", "monthly", 15.0),
        ("$120.00", "yearly", 10.0),
        ("$120.00", "annually", 10.0),
        ("$10.00", "weekly", pytest.approx(43.33, abs=0.01)),
        ("$10.00", None, None),
        ("$10.00", "fortnightly", None),
        (None, "monthly", None),
    ],
)
def test_monthly_cost(amount, frequency, expected):
    assert monthly_cost(amount, frequency) == expected


def test_normalize_service_name_strips_noise():
    assert normalize_service_name("Netflix, Inc.") == "netflix"
    assert normalize_service_name("Spotify Billing") == "spotify"
    assert normalize_service_name("The New York Times") == "newyorktimes"
    assert normalize_service_name(None) == ""


def _sub(name, amount=None, freq=None, end=None, sub_type="paid_subscription", **extra):
    return {
        "service_name": name,
        "billing_amount": amount,
        "billing_frequency": freq,
        "end_date": end,
        "subscription_type": sub_type,
        **extra,
    }


def test_dedupe_keeps_one_row_per_service_preferring_complete_latest():
    trials = [
        _sub("Netflix", None, None, None),
        _sub("Netflix, Inc.", "$15.49", "monthly", "2026-10-12"),
        _sub("Netflix", "$15.49", "monthly", "2026-11-12"),
        _sub("Spotify", "$11.99", "monthly", "2026-11-03"),
    ]
    result = dedupe_by_service(trials)

    assert len(result) == 2
    netflix = next(t for t in result if "netflix" in t["service_name"].lower())
    assert netflix["end_date"] == "2026-11-12"


def test_dedupe_leaves_refund_events_alone():
    trials = [
        _sub("Adobe", "$54.99", None, None, sub_type="refund"),
        _sub("Adobe", "$22.00", None, None, sub_type="refund"),
        _sub("Adobe", "$54.99", "monthly", "2026-11-01"),
    ]
    result = dedupe_by_service(trials)

    assert len(result) == 3


def test_summarize_totals():
    trials = [
        _sub("Netflix", "$15.00", "monthly", "2026-11-12"),
        _sub("Netflix", "$15.00", "monthly", "2026-10-12"),  # duplicate receipt
        _sub("Dropbox", "$120.00", "yearly", "2027-01-01"),
        _sub("Mystery App", None, None, None),
        _sub("Notion", "$10.00", "monthly", "2099-01-01", sub_type="free_trial"),
        _sub("Old Trial", "$99.00", "monthly", "2000-01-01", sub_type="free_trial"),
        _sub("Adobe", "$54.99", None, None, sub_type="refund", status="refund_pending"),
        _sub("Dropbox", "$11.99", None, None, sub_type="duplicate_charge", status="billing_issue"),
    ]
    summary = summarize(trials)

    assert summary["monthly_total"] == 25.0  # 15 + 120/12
    assert summary["yearly_total"] == 300.0
    assert summary["paid_counted"] == 2
    assert summary["paid_unpriced"] == 1
    assert summary["trials_active"] == 1  # expired trial excluded
    assert summary["trial_monthly_exposure"] == 10.0
    assert summary["refund_count"] == 2
    assert summary["refunds_pending"] == 1
    assert summary["refund_amount"] == 54.99  # duplicate charges are not money coming back


def test_summarize_empty():
    summary = summarize([])

    assert summary["monthly_total"] == 0
    assert summary["yearly_total"] == 0
    assert summary["refund_count"] == 0
