from __future__ import annotations

from typing import Any

# Template based on purpose: no LLM, no network, works offline and for free.
# Anything we cannot know is left as a [PLACEHOLDER] for the user to fill in
# rather than guessed.

VALID_KINDS = {"cancel", "refund"}


def default_kind(trial: dict[str, Any]) -> str:
    sub_type = trial.get("subscription_type")
    if sub_type in {"refund", "duplicate_charge"}:
        return "refund"
    return "cancel"


def _price_phrase(trial: dict[str, Any]) -> str:
    amount = trial.get("billing_amount")
    frequency = trial.get("billing_frequency")
    if amount and frequency:
        return f"{amount}/{frequency}"
    if amount:
        return str(amount)
    return "[AMOUNT]"


def build_draft(
    trial: dict[str, Any],
    kind: str | None = None,
    *,
    user_email: str | None = None,
) -> dict[str, str]:
    """Return {"kind", "subject", "body"} for a cancel or refund/claim email."""
    kind = kind or default_kind(trial)
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown draft kind: {kind}")

    service = (trial.get("service_name") or "").strip() or "[SERVICE NAME]"
    account = user_email or "[ACCOUNT EMAIL]"
    signoff = f"Thanks,\n[YOUR NAME]\n{account}"

    if kind == "cancel":
        return _cancel_draft(trial, service, account, signoff)
    return _refund_draft(trial, service, account, signoff)


def _cancel_draft(
    trial: dict[str, Any], service: str, account: str, signoff: str
) -> dict[str, str]:
    is_trial = trial.get("subscription_type") == "free_trial"
    end_date = trial.get("end_date")

    subject = f"Please cancel my {service} {'free trial' if is_trial else 'subscription'}"

    lines = [
        "Hello,",
        "",
        f"Please cancel the {service} {'free trial' if is_trial else 'subscription'} "
        f"on the account registered to {account}, effective immediately.",
        "",
    ]
    if is_trial:
        lines.append(
            "I do not want to be charged when the trial ends"
            + (f" on {end_date}." if end_date else ".")
        )
    else:
        lines.append(
            f"I was being billed {_price_phrase(trial)}. "
            "Please make sure no further charges are made to my payment method."
        )
    lines += [
        "",
        "Please reply to confirm the cancellation and tell me the date the "
        "account will end. If any part of this cannot be done by email, let me "
        "know the exact steps and I will complete them.",
        "",
        signoff,
    ]
    return {"kind": "cancel", "subject": subject, "body": "\n".join(lines)}


def _refund_draft(
    trial: dict[str, Any], service: str, account: str, signoff: str
) -> dict[str, str]:
    sub_type = trial.get("subscription_type")
    amount = trial.get("billing_amount") or "[AMOUNT]"

    if sub_type == "duplicate_charge":
        subject = f"Duplicate charge on my {service} account"
        opening = (
            f"I noticed what looks like a duplicate or incorrect charge of {amount} "
            f"from {service} on the account registered to {account}."
        )
        ask = (
            "Please review the charges on my account and refund the extra "
            "payment to the original payment method."
        )
    elif sub_type == "refund":
        subject = f"Following up on my {service} refund"
        opening = (
            f"I received a notice that a refund of {amount} from {service} was "
            f"issued or is being processed, but I have not seen it yet."
        )
        ask = (
            "Could you confirm the refund date and amount, and the card or "
            "account it will return to?"
        )
    else:
        subject = f"Refund request for my {service} charge"
        opening = (
            f"I am writing to request a refund of the {_price_phrase(trial)} "
            f"charge from {service} on the account registered to {account}."
        )
        ask = (
            "Please refund this charge to my original payment method, and let "
            "me know if you need anything further from me."
        )

    lines = [
        "Hello,",
        "",
        opening,
        "",
        ask,
        "",
        "Relevant details: charge date [CHARGE DATE], order or invoice number "
        "[ORDER NUMBER].",
        "",
        "I would appreciate a reply within a few business days.",
        "",
        signoff,
    ]
    return {"kind": "refund", "subject": subject, "body": "\n".join(lines)}
