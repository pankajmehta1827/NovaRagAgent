"""Index-time sanitisation of knowledge content.

Implements three PRD requirements that are launch blockers:

* NFR-3.2 — PII scrubbing of the historical ticket corpus.
* FR-3.4  — internal remediation detail stripped from ticket resolutions; a ticket
            fixed only by an internal action yields "this needs an agent", never
            instructions the customer cannot perform.
* FR-3.5  — no commitments. Tickets are indexed for *cause*, never for *remedy*,
            so goodwill credits and compensation never reach a customer.
"""

from __future__ import annotations

import re

# --- PII patterns (NFR-3.1, NFR-3.2) -----------------------------------------

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email removed]"),
    (re.compile(r"\b(?:\+?\d[\d\s().-]{8,}\d)\b"), "[number removed]"),
    (re.compile(r"\b\d{6,}\b"), "[number removed]"),
    (re.compile(r"\b(?:IMEI|ICCID|SIM serial|account (?:no|number)|MSISDN)\s*[:#]?\s*\S+", re.I), "[identifier removed]"),
    (re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"), "the customer"),
    (re.compile(r"\b\d{1,4}\s+[A-Z][a-z]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr)\b"), "[address removed]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[address removed]"),
]

# Short codes and published contact numbers are corporate facts, not PII, and the
# customer needs them. Protect them from the digit scrubbers above.
_PROTECTED = [
    (re.compile(r"\*\d{2,6}#(?:\d+#\*?)?"), "SHORTCODE"),
    (re.compile(r"\b611\b"), "CARELINE"),
]


def scrub_pii(text: str) -> str:
    """Remove personal identifiers while preserving published contact routes."""
    if not text:
        return ""
    vault: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        vault.append(match.group(0))
        return f"\x00{len(vault) - 1}\x00"

    for pattern, _ in _PROTECTED:
        text = pattern.sub(_stash, text)
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    for index, original in enumerate(vault):
        text = text.replace(f"\x00{index}\x00", original)
    return re.sub(r"\s{2,}", " ", text).strip()


# --- internal-action detection (FR-3.4) --------------------------------------
# Phrases that mark a sentence as describing something only NovaCell staff can do.

_INTERNAL_ACTION_MARKERS = [
    # internal systems and network elements
    "backend", "back-end", "back end", "session token", "provisioning",
    "provisioned", "re-provision", "reprovision", "database", "cache clear",
    "cleared the cache", "force-synced", "resynced", "re-synced", "hlr", "hss",
    "imsi", "rnc", "ggsn", " msc", "cdr", "billing engine", "mediation layer",
    "payment gateway", "provision record", "whitelist", "white list",
    "sector antenna", "hardware replacement", "junction box", "backhaul",
    # internal teams and staff actions
    "network team", "network operations", "noc ", "engineering team",
    "billing team", "fraud team", "field team", "field engineer", "repair crew",
    "escalated to", "raised a ticket", "raised an internal", "internal ticket",
    "remote cell", "reconfigured", "remotely", "dispatched", "swapped the record",
    "refreshed the customer", "manually", "on our side", "our systems",
    "our records", "reset on our", "checked the account", "checked the device",
    "investigated and", "reviewed the account", "on file", "proactive sms",
    "offered an upgrade", "sent step-by-step", "sent the customer",
    "customer's profile", "the customer profile", "carrier aggregation on",
    "roaming permissions", "permissions to include", "at customer's request",
    "at the customer's request", "identified the local cell",
]

# --- commitment / remedy language (FR-3.5) -----------------------------------

_COMMITMENT_MARKERS = [
    "compensat", "goodwill", "credited", "credit of", "refund", "reimburs",
    "waived", "waiver", "as a gesture", "discount applied", "free of charge as",
    "within 48 hours", "within 24 hours", "scheduled within", "eta ",
    "service restored after", "repair crew", "resolved within",
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _contains(sentence: str, markers: list[str]) -> bool:
    low = sentence.lower()
    return any(marker in low for marker in markers)


# Ticket resolutions are written by agents, about what an agent did. A verb like
# "enabled" or "reset" therefore says nothing about who can perform the action —
# "Enabled carrier aggregation on the customer's profile" is an internal action,
# not an instruction. The only reliable marker of customer-performable guidance is
# an explicit advisory frame, which is stripped so the step reads as an instruction.
_ADVISORY_FRAME_RE = re.compile(
    r"^(?:guided|advised|instructed|asked|walked)\s+(?:the\s+)?customer\s*(?:to|through)?\s+"
    r"|^customer\s+was\s+(?:advised|asked|instructed)\s+to\s+",
    re.I,
)

# Narration about how the interaction went. Carries no information for a future
# customer with the same symptom.
_HARD_DROP_MARKERS = [
    "customer declined", "customer accepted", "customer confirmed",
    "customer logged in", "customer was unaware", "customer was satisfied",
    "customer requested", "customer agreed", "no further action",
    "service restored", "speeds improved to", "activation succeeded",
    "hotspot functional",
]

# Outcome statements — dropped unless they carry a concrete detail (a setting
# name, a value, a menu path) that a customer could act on.
_OUTCOME_MARKERS = [
    "restored", "resolved", "succeeded", "completed", "improved", "functional",
    "updated correctly", "working again", "back to normal",
]

_DETAIL_RE = re.compile(r"[0-9(><*]|\b(?:APN|PIN|SIM|eSIM|QR|VoLTE|VoWiFi|LTE|MyTelecom)\b")


def redact_resolution(resolution: str) -> tuple[str, str, bool]:
    """Split a ticket resolution into customer-safe parts.

    Returns ``(guidance, known_cause, needs_agent)``:

    * ``guidance`` — steps the customer can perform themselves.
    * ``known_cause`` — safe explanatory detail with no action attached.
    * ``needs_agent`` — True only when the fix genuinely was an internal action
      (internal sentences were dropped) and nothing customer-performable
      survived. A ticket whose value is purely an *explanation* is not an
      agent-only case: the FAQ and guide supply the action, this supplies the
      cause (FR-3.4).

    Sentences describing internal actions (FR-3.4) or commitments such as
    goodwill credits (FR-3.5) are dropped entirely.
    """
    if not resolution:
        return "", "", True

    guidance: list[str] = []
    cause: list[str] = []
    dropped_internal = False
    for sentence in _SENTENCE_SPLIT.split(resolution.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if _contains(sentence, _COMMITMENT_MARKERS):
            continue
        if _contains(sentence, _INTERNAL_ACTION_MARKERS):
            dropped_internal = True
            continue
        if _contains(sentence, _HARD_DROP_MARKERS):
            continue

        stripped = _ADVISORY_FRAME_RE.sub("", sentence)
        if stripped != sentence:
            step = stripped[0].upper() + stripped[1:] if stripped else ""
            if step:
                guidance.append(step)
            continue

        if _contains(sentence, _OUTCOME_MARKERS) and not _DETAIL_RE.search(sentence):
            continue
        cause.append(sentence)

    guidance_text = " ".join(guidance).strip()
    cause_text = " ".join(cause).strip()
    if len(guidance_text.split()) < 5:
        guidance_text = ""
    needs_agent = not guidance_text and (dropped_internal or not cause_text)
    return guidance_text, cause_text, needs_agent


def sanitise_description(description: str) -> str:
    """Customer-facing form of the reported symptom, PII removed."""
    return scrub_pii(description or "")


# --- guide content classification (FR-3.3) -----------------------------------
# The PDF guide is marked "Internal Use Only". Every section must be classified
# customer-safe or internal-only before it can be retrieved for a customer, and
# the classification must be auditable.

_INTERNAL_AUDIENCE_MARKERS = [
    "agents should", "agent must", "agents play", "agents can", "helps agents",
    "the agent must", "fraud team approval", "internal use only",
    "raise a network investigation", "network operations team",
    "billing engine", "mediation layer", "rate plan is applied",
    "ss7", "diameter", "irsf", "attack surface", "attackers",
    "idempotency", "cdr", "ggsn", "msc", "hlr", "hss",
    "flag accounts", "elevated fraud monitoring", "manually reverse",
    "escalate.", "escalate ", "remote cell analysis",
]

_MIN_SECTION_WORDS = 15


def classify_guide_section(title: str, body: str) -> tuple[bool, str]:
    """Return ``(customer_safe, reason)`` for one guide section.

    Conservative by design: anything addressed to agents, describing internal
    systems, or describing security/fraud internals is withheld from customers.
    """
    blob = f"{title}\n{body}".lower()
    hits = [marker.strip() for marker in _INTERNAL_AUDIENCE_MARKERS if marker in blob]
    if hits:
        return False, "internal-audience or internal-systems language: " + ", ".join(sorted(set(hits))[:4])
    if len(body.split()) < _MIN_SECTION_WORDS:
        return False, "section too short to stand alone as an answer"
    return True, "no internal-audience markers found"
