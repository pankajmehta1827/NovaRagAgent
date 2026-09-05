"""Refund agent: simulated account data, deterministic tools, and the workflow state.

Agent PRD §6.3-§6.8. The important structural point is that almost nothing here is
decided by the model. Eligibility (FR-29, FR-30, GR-05), the ₹499 approval limit
(FR-36a), which recharge an amount refers to (FR-27a), and what counts as a
confirmation (FR-36c) are all resolved in this module, deterministically. The LLM's
only job in the refund route is classifying the intent; it never validates, never
decides the limit, and — per FR-23a — is never given ``process_refund`` or
``submit_to_support`` as callable tools. Application code calls those, and only
after this module says it may.

Everything is simulated (FR-35, GR-07). No payment, billing or CRM system is touched.

Currency note: the PRD specifies ₹499 / ₹999, while the rest of NovaCell's knowledge
base quotes USD. The refund ledger below is self-contained demo data, so it uses the
PRD's rupee figures as written rather than silently converting them.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any

CURRENCY = "₹"

# FR-15, FR-16 — treated as if it arrived from authenticated session context. The
# customer is never asked for it (FR-17).
SESSION_USER_ID = "user_123"

# FR-36 / FR-37. Enforced here, in code, never by the model (FR-36a).
APPROVAL_LIMIT = 499

# FR-25.
REFUND_WINDOW_DAYS = 7

# --- simulated account data (FR-14, FR-18, FR-18a) ---------------------------
# Seed only. A live ledger is deep-copied per session so a demonstration can be
# run more than once, and so one browser's refund never mutates another's.

_SEED_USERS: dict[str, dict[str, Any]] = {
    "user_123": {
        "name": "Rahul",
        "plan": "Pro",
        "plan_amount": 999,
        "recharges": [
            {
                "recharge_id": "rch_456",
                "recharge_amount": 999,
                "recharge_status": "completed",
                "recharge_age_days": 2,
                "refund_status": "not_refunded",
            },
            {
                "recharge_id": "rch_457",
                "recharge_amount": 499,
                "recharge_status": "completed",
                "recharge_age_days": 1,
                "refund_status": "not_refunded",
            },
        ],
    }
}


def new_ledger() -> dict[str, Any]:
    """A fresh copy of the simulated accounts (§11 — clearing the chat reseeds)."""
    return copy.deepcopy(_SEED_USERS)


# --- workflow states (§10) ---------------------------------------------------

REQUESTED = "refund_requested"
AWAITING_AMOUNT = "awaiting_amount"
VALIDATED = "refund_validated"
AWAITING_CONFIRMATION = "awaiting_confirmation"
CONFIRMED = "refund_confirmed"
PROCESSED = "refund_processed"
REJECTED = "refund_rejected"
CANCELLED = "refund_cancelled"
SUBMITTED = "refund_submitted_for_review"

# The only state from which application code may execute a refund. Keeping this as
# a named set means the guard in `confirm` reads as the rule it enforces (GR-01,
# GR-02): validated *and* explicitly confirmed, or nothing happens.
_EXECUTABLE_FROM = frozenset({AWAITING_CONFIRMATION})


# --- tools (§6.4) ------------------------------------------------------------
# Structured results (FR-22). `get_user_account` and `validate_refund` are safe to
# describe to a model; `process_refund` and `submit_to_support` are not exposed as
# callable tools anywhere (FR-23a).


def get_user_account(ledger: dict, user_id: str) -> dict[str, Any]:
    """FR-19 — retrieve the account and its recharges."""
    account = ledger.get(user_id)
    if account is None:
        return {"found": False, "user_id": user_id}
    return {"found": True, "user_id": user_id, **copy.deepcopy(account)}


def _refundable(recharge: dict) -> bool:
    return (
        recharge["recharge_status"] == "completed"
        and recharge["refund_status"] != "refunded"
        and recharge["recharge_age_days"] <= REFUND_WINDOW_DAYS
    )


def _select_recharge(recharges: list[dict], amount: int) -> dict | None:
    """FR-27a — decide deterministically which recharge an amount refers to.

    An exact amount match identifies that recharge outright, even when it has
    already been refunded: someone asking for ₹499 back twice should be told the
    ₹499 recharge is already refunded, not that ₹499 exceeds something. Otherwise
    the newest recharge that could cover the amount wins, with the recharge id as
    a tie-break so the choice never depends on dict ordering.
    """
    exact = [r for r in recharges if r["recharge_amount"] == amount]
    if exact:
        return sorted(exact, key=lambda r: (r["recharge_age_days"], r["recharge_id"]))[0]

    covering = [r for r in recharges if r["recharge_amount"] >= amount and _refundable(r)]
    if covering:
        return sorted(covering, key=lambda r: (r["recharge_age_days"], r["recharge_id"]))[0]
    return None


def validate_refund(ledger: dict, user_id: str, amount: int) -> dict[str, Any]:
    """FR-20, §6.5 — deterministic eligibility. Decides eligibility only.

    Whether an eligible refund can be executed *here* is a separate question,
    answered by the approval limit in `route`.
    """
    account = get_user_account(ledger, user_id)
    if not account["found"]:
        return {"eligible": False, "reason": "No account found.", "requested_amount": amount}

    recharges = account["recharges"]

    if amount is None or amount <= 0:
        return {
            "eligible": False,
            "reason": "A refund amount must be greater than zero.",
            "requested_amount": amount,
        }

    recharge = _select_recharge(recharges, amount)
    if recharge is None:
        largest = max((r["recharge_amount"] for r in recharges), default=0)
        return {
            "eligible": False,
            "reason": (
                f"The requested amount exceeds your recharge amount. Your largest recent "
                f"recharge was {CURRENCY}{largest}."
            ),
            "requested_amount": amount,
            "recharge_amount": largest,
        }

    result = {
        "requested_amount": amount,
        "recharge_amount": recharge["recharge_amount"],
        "recharge_id": recharge["recharge_id"],
    }

    # Order matters only for which reason the customer is given; every one of these
    # is a hard stop.
    if recharge["recharge_status"] != "completed":
        return {**result, "eligible": False, "reason": f"That recharge is {recharge['recharge_status']}, not completed."}
    if recharge["refund_status"] == "refunded":
        return {**result, "eligible": False, "reason": "That recharge has already been refunded."}
    if recharge["recharge_age_days"] > REFUND_WINDOW_DAYS:
        return {
            **result,
            "eligible": False,
            "reason": (
                f"That recharge is {recharge['recharge_age_days']} days old, outside the "
                f"{REFUND_WINDOW_DAYS}-day refund window."
            ),
        }
    if amount > recharge["recharge_amount"]:
        return {**result, "eligible": False, "reason": "The requested amount exceeds the recharge amount."}

    return {**result, "eligible": True, "reason": "Refund is eligible."}


def process_refund(ledger: dict, user_id: str, recharge_id: str, amount: int) -> dict[str, Any]:
    """FR-21, §6.6 — simulated execution. Never exposed to the model (FR-23a).

    A refund consumes the whole recharge; no remaining balance is tracked (FR-28a).
    """
    account = ledger.get(user_id)
    if account is None:
        return {"success": False, "reason": "No account found."}
    for recharge in account["recharges"]:
        if recharge["recharge_id"] == recharge_id:
            if recharge["refund_status"] == "refunded":
                return {"success": False, "reason": "That recharge has already been refunded."}
            recharge["refund_status"] = "refunded"  # FR-33
            return {
                "success": True,
                "refund_id": f"ref_{uuid.uuid4().hex[:6]}",  # FR-34
                "amount": amount,
                "recharge_id": recharge_id,
                "status": "refunded",
            }
    return {"success": False, "reason": "Recharge not found."}


def submit_to_support(user_id: str, amount: int, recharge_id: str) -> dict[str, Any]:
    """FR-21a — hand an over-limit refund to the Support Team.

    This records a submission and nothing more. The application must not simulate
    or report the outcome of that review (FR-40a, GR-09), so there is deliberately
    no status field here beyond "submitted".
    """
    return {
        "submitted": True,
        "reference": f"sup_{uuid.uuid4().hex[:6]}",
        "amount": amount,
        "recharge_id": recharge_id,
        "user_id": user_id,
        "status": "submitted",
    }


# --- reading the customer's message ------------------------------------------

# Deterministic, because FR-44 forbids inventing an amount and a model asked for a
# number will always produce one.
_AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)|\b([\d,]{3,})\b", re.I)

_YES = re.compile(
    r"^\s*(yes|yeah|yep|yup|ok|okay|sure|confirm(ed)?|proceed|go ahead|do it|please do|"
    r"yes[, ]+(please|proceed|go ahead|do it)|refund it)\s*[.!]?\s*$",
    re.I,
)
_NO = re.compile(
    r"^\s*(no|nope|nah|cancel|stop|don'?t|do not|not now|never ?mind|leave it|forget it|"
    r"no[, ]+(thanks|thank you|don'?t))\s*[.!]?\s*$",
    re.I,
)


def extract_amount(text: str) -> int | None:
    """The amount the customer actually named, or None. Never a guess."""
    best: int | None = None
    for match in _AMOUNT.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        try:
            value = int(float(raw.replace(",", "")))
        except ValueError:
            continue
        # A currency-marked figure is unambiguous; prefer it over a bare number.
        if match.group(1) is not None:
            return value
        best = value if best is None else best
    return best


def read_confirmation(text: str) -> str:
    """FR-36c / FR-36e — "yes", "no", or ambiguous. Ambiguity never executes."""
    stripped = (text or "").strip()
    if _YES.match(stripped):
        return "yes"
    if _NO.match(stripped):
        return "no"
    return "ambiguous"


# --- the workflow ------------------------------------------------------------


class RefundFlow:
    """One customer's refund conversation.

    Held by the UI in session state and handed the customer's messages. Every
    transition returns the reply to show plus the workflow steps to log (§12).
    """

    def __init__(self, ledger: dict, user_id: str = SESSION_USER_ID) -> None:
        self.ledger = ledger
        self.user_id = user_id
        self.state: str = ""
        self.amount: int | None = None
        self.recharge_id: str = ""
        self.log: list[str] = []

    # -- helpers --

    def _note(self, line: str) -> None:
        self.log.append(line)

    def _pending(self) -> bool:
        return self.state in {AWAITING_AMOUNT, AWAITING_CONFIRMATION}

    def reset(self) -> None:
        """§11 — clearing the conversation drops any pending refund."""
        self.state = ""
        self.amount = None
        self.recharge_id = ""
        self.log = []

    # -- entry points --

    def handle(self, message: str) -> tuple[str, bool]:
        """Route one message. Returns ``(reply, needs_confirmation_ui)``."""
        if self.state == AWAITING_CONFIRMATION:
            return self._handle_confirmation(message)
        if self.state == AWAITING_AMOUNT:
            return self._start(message, reprompt=True)
        return self._start(message)

    # -- step 1: determine the amount (§6.8) --

    def _start(self, message: str, reprompt: bool = False) -> tuple[str, bool]:
        self.state = REQUESTED
        self._note("[Intent] refund_request")

        account = get_user_account(self.ledger, self.user_id)
        self._note("[Agent] get_user_account")
        if not account["found"]:
            self.state = REJECTED
            return "I couldn't find your account details, so I can't look at a refund.", False

        amount = extract_amount(message)

        if amount is None:
            # FR-41, FR-42, FR-42a — offer, ask which, or ask. Never invent (FR-44).
            eligible = [r for r in account["recharges"] if _refundable(r)]
            if len(eligible) == 1:
                amount = eligible[0]["recharge_amount"]
                self._note(f"[Agent] single_eligible_recharge amount={amount}")
            elif len(eligible) > 1:
                self.state = AWAITING_AMOUNT
                self._note("[Agent] awaiting_amount")
                amounts = " and ".join(
                    f"{CURRENCY}{r['recharge_amount']}"
                    for r in sorted(eligible, key=lambda r: -r["recharge_amount"])
                )
                return (
                    f"I can see more than one recent recharge — {amounts}. "
                    "Which amount would you like refunded?",
                    False,
                )
            else:
                self.state = AWAITING_AMOUNT
                self._note("[Agent] awaiting_amount")
                return (
                    "I couldn't work out which recharge you mean. How much would you like "
                    "refunded?",
                    False,
                )

        self.amount = amount
        return self._validate()

    # -- step 2: validate, then apply the approval limit --

    def _validate(self) -> tuple[str, bool]:
        amount = self.amount
        self._note(f"[Agent] validate_refund(amount={amount})")
        result = validate_refund(self.ledger, self.user_id, amount)
        self._note(f"[Validation] eligible={result['eligible']}")

        if not result["eligible"]:
            self.state = REJECTED
            return f"I can't refund {CURRENCY}{amount}. {result['reason']}", False

        self.state = VALIDATED
        self.recharge_id = result["recharge_id"]

        # FR-37 to FR-40a — over the limit, this application does not execute and
        # does not speak for the Support Team's decision.
        if amount > APPROVAL_LIMIT:
            receipt = submit_to_support(self.user_id, amount, self.recharge_id)
            self.state = SUBMITTED
            self._note(f"[Agent] submit_to_support(amount={amount})")
            self._note(f"[Support] submitted reference={receipt['reference']}")
            return (
                f"Your refund request for {CURRENCY}{amount} has been submitted to our "
                "Support Team. They will review the request and process it or take the "
                f"necessary action. Your reference is **{receipt['reference']}**.",
                False,
            )

        # FR-36 — at or below the limit, ask before doing anything.
        self.state = AWAITING_CONFIRMATION
        self._note("[Agent] awaiting_user_confirmation")
        return (
            f"Refund eligible: **{CURRENCY}{amount}** from recharge {self.recharge_id}.\n\n"
            "Do you want me to go ahead with this refund?",
            True,
        )

    # -- step 3: confirmation --

    def _handle_confirmation(self, message: str) -> tuple[str, bool]:
        verdict = read_confirmation(message)
        if verdict == "yes":
            return self.confirm()
        if verdict == "no":
            return self.cancel()
        # FR-36e — ambiguity asks again rather than executing.
        self._note("[Agent] confirmation_ambiguous")
        return (
            f"Sorry, I need a clear yes or no before I refund {CURRENCY}{self.amount}. "
            "Would you like me to go ahead?",
            True,
        )

    def confirm(self) -> tuple[str, bool]:
        """Execute. Reachable only from AWAITING_CONFIRMATION (GR-01, GR-02)."""
        if self.state not in _EXECUTABLE_FROM:
            self._note("[Agent] confirm_rejected_wrong_state")
            return "There's no refund waiting for confirmation right now.", False

        self._note("[User] confirmed")
        self.state = CONFIRMED

        # Re-validate immediately before executing. The ledger could have changed
        # since the offer, and conversation history must never be what authorises a
        # refund (GR-03, GR-10).
        result = validate_refund(self.ledger, self.user_id, self.amount)
        if not result["eligible"] or result.get("recharge_id") != self.recharge_id:
            self.state = REJECTED
            self._note("[Validation] eligible=False on re-check")
            return f"I can't refund {CURRENCY}{self.amount} after all. {result['reason']}", False

        self._note(f"[Agent] process_refund(amount={self.amount})")
        receipt = process_refund(self.ledger, self.user_id, self.recharge_id, self.amount)
        if not receipt["success"]:
            self.state = REJECTED
            self._note("[Refund] failed")
            return f"I couldn't complete that refund. {receipt['reason']}", False

        self.state = PROCESSED
        self._note("[Refund] success")
        return (
            f"Done — {CURRENCY}{self.amount} has been refunded. Your refund reference is "
            f"**{receipt['refund_id']}**. It should reach your original payment method "
            "within a few working days.",
            False,
        )

    def cancel(self) -> tuple[str, bool]:
        """FR-36d — a rejection executes nothing."""
        self.state = CANCELLED
        self._note("[User] declined")
        return "No problem — I haven't refunded anything. Is there anything else I can help with?", False
