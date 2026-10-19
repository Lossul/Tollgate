from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr

from .trial_parser import _find_amount, _guess_service_name

# Gmail search used for the refund pass of a scan.
REFUND_GMAIL_QUERY = (
    '(refund OR "has been credited" OR "we\'ve credited" OR "charged twice"'
    ' OR "duplicate charge" OR "double charge" OR overcharged OR "billing error"'
    ' OR "incorrect charge") newer_than:365d'
)

# A refund that is actually happening (or happened).
REFUND_STRONG_TERMS = (
    "refund has been issued",
    "refund has been processed",
    "refund was issued",
    "refund was processed",
    "refund issued",
    "refund processed",
    "refund initiated",
    "refund is on its way",
    "refund is being processed",
    "your refund",
    "we've refunded",
    "we have refunded",
    "has been refunded",
    "have been refunded",
    "been credited",
    "we've credited",
    "we have credited",
    "credited back",
    "credit to your",
)
# Only counts if an amount is also present.
REFUND_WEAK_TERMS = ("refund", "money back", "reimburse")

DUPLICATE_TERMS = (
    "duplicate charge",
    "duplicate payment",
    "charged twice",
    "double charge",
    "double-charged",
    "double charged",
    "billed twice",
    "billing error",
    "overcharge",
    "incorrect charge",
    "charged in error",
)

# Marketing / policy text that mentions refunds without one being owed.
REFUND_NEGATIVE_TERMS = (
    "money-back guarantee",
    "money back guarantee",
    "refund policy",
    "refund and return policy",
    "non-refundable",
    "nonrefundable",
    "no refund",
    "not eligible for a refund",
    "refunds are not",
    "request a refund",
    "eligible for a refund",
    "if you'd like a refund",
    "if you would like a refund",
)

PENDING_TERMS = (
    "on its way",
    "is being processed",
    "will be processed",
    "will be issued",
    "will be credited",
    "will appear",
    "initiated",
    "pending",
    "allow",  # "allow 5-10 business days"
    "business days",
)
DONE_TERMS = (
    "has been issued",
    "was issued",
    "has been processed",
    "was processed",
    "has been refunded",
    "have been refunded",
    "we've refunded",
    "we have refunded",
    "been credited",
    "we've credited",
    "we have credited",
)


@dataclass
class RefundParseResult:
    kind: str  # "refund" | "duplicate_charge"
    service_name: str | None
    amount: str | None
    status: str  # "refund_pending" | "refund_received" | "billing_issue"
    confidence: float


def detect_refund(*, subject: str, sender: str, snippet: str) -> RefundParseResult | None:
    """Return a result if this email is about a refund or a billing problem,
    otherwise None. Pure heuristics, no network."""
    combined = f"{subject}\n{snippet}".lower()
    amount = _find_amount(f"{subject} {snippet}")

    has_negative = any(term in combined for term in REFUND_NEGATIVE_TERMS)
    has_duplicate = any(term in combined for term in DUPLICATE_TERMS)
    has_strong = any(term in combined for term in REFUND_STRONG_TERMS)
    has_weak = any(term in combined for term in REFUND_WEAK_TERMS)

    # Policy / marketing text. Only skip when nothing concrete is happening.
    if has_negative and not has_strong and not has_duplicate:
        return None

    service = _guess_service_name(sender)
    _, address = parseaddr(sender)
    if not service and address:
        service = address

    if has_duplicate:
        return RefundParseResult(
            kind="duplicate_charge",
            service_name=service,
            amount=amount,
            status="billing_issue",
            confidence=0.7 if amount else 0.55,
        )

    if has_strong or (has_weak and amount):
        is_done = any(term in combined for term in DONE_TERMS)
        is_pending = any(term in combined for term in PENDING_TERMS)
        status = "refund_received" if is_done and not is_pending else "refund_pending"
        return RefundParseResult(
            kind="refund",
            service_name=service,
            amount=amount,
            status=status,
            confidence=0.8 if (has_strong and amount) else 0.6,
        )

    return None


__all__ = ["REFUND_GMAIL_QUERY", "RefundParseResult", "detect_refund"]
