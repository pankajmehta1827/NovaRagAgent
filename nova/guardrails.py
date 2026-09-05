"""Pre-retrieval guardrails.

Everything here runs before a single knowledge chunk is fetched, because some
questions must never reach the answering path at all.

PRD references: 3.3 (bounded deflection for account-specific questions),
FR-3.6 (credential / emergency / abuse refusals), FR-3.8 (ops blocklist),
FR-4.1 (hard-routed escalation categories, explicit human request, frustration).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import config

# --- outcomes ----------------------------------------------------------------

ALLOW = "allow"
DEFLECT = "deflect"  # answer the general question, but state the account boundary
ESCALATE = "escalate"
REFUSE = "refuse"  # fixed, non-generated response


@dataclass
class PreCheck:
    action: str = ALLOW
    reason_code: str = ""
    message: str = ""
    deep_link_key: str = "generic"


# --- reason codes (FR-4.6) ---------------------------------------------------

REASON_CODES = {
    "CUSTOMER_REQUESTED_HUMAN": "Customer asked to speak to a person",
    "FRAUD_OR_UNAUTHORISED": "Suspected fraud or unauthorised account change",
    "BILLING_DISPUTE": "Billing dispute or refund request",
    "COMPLAINT": "Complaint about NovaCell",
    "CANCELLATION": "Cancellation or retention",
    "LOST_OR_STOLEN_SIM": "Lost or stolen SIM — needs immediate blocking",
    "OUTAGE_REPORT": "Customer reporting a network outage",
    "VULNERABLE_CUSTOMER": "Possible vulnerable-customer signal",
    "LOW_CONFIDENCE": "No confidently grounded answer available",
    "NO_GROUNDED_ANSWER": "Two consecutive turns without a grounded answer",
    "FRUSTRATION": "Customer frustration detected",
    "ACCOUNT_SPECIFIC_UNRESOLVED": "Needs live account data the assistant cannot see",
    "BLOCKED_TOPIC": "Topic on the Support Ops block list",
}

# --- pattern tables ----------------------------------------------------------

_HUMAN_REQUEST = re.compile(
    r"\b(speak|talk|chat|connect|put me through|transfer me)\b.{0,25}\b(human|person|agent|advisor|someone|representative|rep)\b"
    r"|\b(human|real person|live agent|customer service rep)\b"
    r"|\b(agent|operator)\s+please\b",
    re.I,
)

_HARD_ROUTES: list[tuple[str, re.Pattern[str]]] = [
    ("LOST_OR_STOLEN_SIM", re.compile(r"\b(lost|stolen|misplaced)\b.{0,25}\b(sim|phone|handset|device)\b|\bmy (phone|sim) (was|got) (stolen|taken)\b", re.I)),
    ("FRAUD_OR_UNAUTHORISED", re.compile(r"\b(fraud|scam|unauthoris|unauthoriz|someone (else )?(changed|accessed|used)|identity theft|sim swap|hacked|didn'?t authorise|did not authorise)\b", re.I)),
    # A *disputed* charge is still a human matter and outranks the refund agent:
    # someone challenging a charge they believe is wrong needs a person, not a
    # self-service reversal. A plain request to reverse a recharge the customer
    # made deliberately is no longer caught here — Agent PRD FR-03 routes that to
    # the Refund Agent, which can only act inside the deterministic rules in
    # nova/refund.py. Keep the two apart carefully: dropping "dispute" or
    # "chargeback" from this line would hand a billing complaint to a bot.
    ("BILLING_DISPUTE", re.compile(r"\b(reimburse|dispute|charge ?back|double ?charged?|wrongly charged|overcharged|credit my account)\b", re.I)),
    ("CANCELLATION", re.compile(r"\b(cancel my (plan|account|contract|service)|terminate my (plan|account|contract)|leave novacell|switch to another (network|carrier)|port out|close my account)\b", re.I)),
    ("COMPLAINT", re.compile(r"\b(complaint|formal complaint|escalate this|ombudsman|regulator|legal action|sue you|take this further)\b", re.I)),
    ("OUTAGE_REPORT", re.compile(r"\b(report (an|the) outage|whole (street|building|area) (is )?(down|out)|everyone (here|in my area) has no|network is down in)\b", re.I)),
    ("VULNERABLE_CUSTOMER", re.compile(r"\b(medical emergency|suicid|self ?harm|domestic (abuse|violence)|i(?:'m| am) (in danger|being threatened))\b", re.I)),
]

_EMERGENCY = re.compile(r"\b(call (911|999|112|emergency services)|life[- ]threatening|someone is dying|ambulance now)\b", re.I)

_CREDENTIAL_SOLICITATION = re.compile(
    r"\b(my (password|pin|otp|one[- ]time code|card number|cvv|passport|social security)|here is my (card|password|pin|otp)"
    r"|card number is|\bcvv\b|\botp\b is)\b",
    re.I,
)

# Account-specific: first-person possession of data only the billing/CRM systems hold.
_ACCOUNT_SPECIFIC: list[tuple[str, re.Pattern[str]]] = [
    ("balance", re.compile(r"\b(my|our)\b.{0,20}\b(balance|remaining data|data left|credit left|minutes left)\b|\bhow much (data|credit|balance) (do i|have i)\b", re.I)),
    ("bill", re.compile(r"\b(my|this month'?s|last month'?s)\b.{0,20}\b(bill|invoice|charges|statement)\b|\bwhy (was|am) i charged\b|\bwhat (is|was) i charged\b", re.I)),
    ("payment", re.compile(r"\b(my)\b.{0,20}\b(payment|autopay|direct debit|card on file)\b|\bdid my payment go through\b", re.I)),
    ("plan", re.compile(r"\bwhat (plan|tariff|package) am i on\b|\b(my)\b.{0,15}\b(current plan|tariff)\b", re.I)),
    ("usage", re.compile(r"\bhow much (data|minutes) have i used\b|\b(my)\b.{0,15}\busage\b", re.I)),
    ("outage", re.compile(r"\bis there an outage (at|in|near) (my|our)\b|\bis the network down (at|in) my\b", re.I)),
    ("roaming", re.compile(r"\bis (my )?roaming (on|active|enabled) (on my account)?\b|\bdo i have (a )?roaming bundle\b", re.I)),
]

_FRUSTRATION = re.compile(
    r"\b(useless|rubbish|terrible|awful|ridiculous|fed up|sick of this|waste of time|you'?re not helping|this is not helping|still not working|third time|again and again)\b"
    r"|[!?]{3,}",
    re.I,
)


# --- fixed responses ---------------------------------------------------------

_EMERGENCY_RESPONSE = (
    "If this is an emergency, please hang up and call your local emergency number "
    "(911, 999 or 112) directly from your phone. Emergency calls connect even without "
    "signal from your own network or without a SIM card.\n\n"
    "I can't help with emergencies — please contact the emergency services now."
)

_CREDENTIAL_RESPONSE = (
    "Please don't share passwords, PINs, one-time codes, or card details with me — "
    "I don't need them and I can't use them. I can't see or change your account.\n\n"
    f"If you need something done on your account, call {config.SUPPORT_PHONE} or use the MyTelecom app, "
    "where NovaCell can verify your identity securely."
)


def _blocked_topic(text: str, blocklist: list[str]) -> str | None:
    low = text.lower()
    for term in blocklist:
        term = term.strip().lower()
        if term and term in low:
            return term
    return None


def check(question: str, history: list[dict], settings: dict) -> PreCheck:
    """Classify a question before retrieval. First match wins, most severe first."""
    text = question.strip()
    if not text:
        return PreCheck()

    if _EMERGENCY.search(text):
        return PreCheck(action=REFUSE, reason_code="VULNERABLE_CUSTOMER", message=_EMERGENCY_RESPONSE)

    if _CREDENTIAL_SOLICITATION.search(text):
        return PreCheck(action=REFUSE, reason_code="", message=_CREDENTIAL_RESPONSE)

    # FR-4.2 — an explicit request for a human is never blocked or deflected.
    if _HUMAN_REQUEST.search(text):
        return PreCheck(action=ESCALATE, reason_code="CUSTOMER_REQUESTED_HUMAN")

    for code, pattern in _HARD_ROUTES:
        if pattern.search(text):
            return PreCheck(action=ESCALATE, reason_code=code)

    blocked = _blocked_topic(text, settings.get("blocklist", []))
    if blocked:
        return PreCheck(action=ESCALATE, reason_code="BLOCKED_TOPIC")

    # FR-4.1(d) — frustration, but only once the customer has already tried.
    if _FRUSTRATION.search(text) and len(history) >= 2:
        return PreCheck(action=ESCALATE, reason_code="FRUSTRATION")

    for key, pattern in _ACCOUNT_SPECIFIC:
        if pattern.search(text):
            return PreCheck(action=DEFLECT, reason_code="ACCOUNT_SPECIFIC_UNRESOLVED", deep_link_key=key)

    return PreCheck()


def deflection_note(deep_link_key: str) -> str:
    """The bounded-deflection footer (PRD 3.3, steps 1 and 3)."""
    where, extra = config.DEEP_LINKS.get(deep_link_key, config.DEEP_LINKS["generic"])
    note = f"I can't see your account details, so I can't look this up for you. You'll find it in **{where}**."
    if extra:
        note += f" {extra}"
    return note
