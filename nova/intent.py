"""Intent detection: does this message continue the RAG pipeline, or start a refund?

Agent PRD §6.1. Two intents only (FR-01). The classifier runs on the existing cheap
utility model (FR-04) and returns a structured value (FR-05); if that call fails for
any reason the deterministic fallback below decides, because a classifier outage
must degrade to the existing behaviour rather than to an exception.

The distinction FR-05a asks for is genuinely semantic — "cancel my recharge" is a
refund request, "how do I cancel a recharge?" is a support question about the same
subject — which is why a model does this rather than a keyword list.
"""

from __future__ import annotations

import re

from groq import Groq

from . import config

REQUIREMENT_INQUIRY = "requirement_inquiry"
REFUND_REQUEST = "refund_request"

_VALID = {REQUIREMENT_INQUIRY, REFUND_REQUEST}

_SYSTEM = """You classify one message from a mobile network customer into exactly one intent.

refund_request — the customer is asking for money back, or to cancel or reverse a
recharge or payment they have already made. They are asking you to act.

requirement_inquiry — anything else, including questions ABOUT refunds, charges or
cancellation. They are asking you to explain.

The difference is whether the customer wants an action taken on their own money now,
or wants information.

  "I want a refund of 999"            -> refund_request
  "Cancel my recharge from yesterday"  -> refund_request
  "Give me my money back"              -> refund_request
  "How do I request a refund?"         -> requirement_inquiry
  "What is your refund policy?"        -> requirement_inquiry
  "How do I cancel a recharge?"        -> requirement_inquiry
  "Why is my internet slow?"           -> requirement_inquiry
  "Why is my bill higher this month?"  -> requirement_inquiry

Reply with exactly one word: refund_request or requirement_inquiry. Nothing else."""


# Fallback only. An imperative ask for money back, not a question about the topic.
_REFUND_ACTION = re.compile(
    r"\b(i want|i'?d like|give me|send me|please|can i (get|have)|i need)\b[^.?!]{0,40}"
    r"\b(refund|money back|reversal|reverse)\b"
    r"|\brefund (me|my|it|this|that)\b"
    r"|\b(cancel|reverse|undo)\b[^.?!]{0,30}\b(recharge|top ?up|payment|transaction)\b"
    r"|\bwant my money back\b",
    re.I,
)
_INFORMATIONAL = re.compile(r"^\s*(how|what|when|where|why|which|who|does|do|can you tell|is there)\b", re.I)


def _fallback(message: str) -> str:
    """Deterministic classification for when the model call fails."""
    text = (message or "").strip()
    if _INFORMATIONAL.match(text):
        return REQUIREMENT_INQUIRY
    if _REFUND_ACTION.search(text):
        return REFUND_REQUEST
    return REQUIREMENT_INQUIRY


def classify(client: Groq, message: str, history: list[dict] | None = None) -> tuple[str, dict]:
    """Return ``(intent, usage)``. Never raises into the turn."""
    if not (message or "").strip():
        return REQUIREMENT_INQUIRY, {}

    # FR-46 — recent turns as context, so "yes, the 499 one" is readable. Bounded
    # to keep this stage cheap (FR-50).
    recent = (history or [])[-4:]
    transcript = "\n".join(f"{turn['role']}: {turn['content']}" for turn in recent)
    prompt = (f"Conversation so far:\n{transcript}\n\n" if transcript else "") + f"Newest message: {message}"

    try:
        response = client.chat.completions.create(
            model=config.UTILITY_MODEL,
            max_completion_tokens=200,
            temperature=0.0,
            reasoning_effort="low",
            reasoning_format="hidden",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        return _fallback(message), {}

    raw = (response.choices[0].message.content or "").strip().lower()
    intent = next((value for value in _VALID if value in raw), _fallback(message))
    usage = {
        "model": config.UTILITY_MODEL,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }
    return intent, usage
