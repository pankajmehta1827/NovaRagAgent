"""Central configuration for Nova.

Everything Support Ops is allowed to change at runtime lives in DEFAULT_SETTINGS
and is overridable from the ops console without a code release (PRD FR-5.1, FR-3.1).
"""

from __future__ import annotations

from pathlib import Path

# --- paths -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "Data"
RUNTIME_DIR = ROOT / "runtime"

FAQ_PATH = DATA_DIR / "faq.csv"
TICKETS_PATH = DATA_DIR / "tickets.db"
GUIDE_PATH = DATA_DIR / "telecom_guide.pdf"

SETTINGS_PATH = RUNTIME_DIR / "settings.json"
FAQ_OVERRIDES_PATH = RUNTIME_DIR / "faq_overrides.json"
TURNS_LOG_PATH = RUNTIME_DIR / "turns.jsonl"
FEEDBACK_LOG_PATH = RUNTIME_DIR / "feedback.jsonl"
ESCALATIONS_LOG_PATH = RUNTIME_DIR / "escalations.jsonl"

# --- models (PRD NFR-4.2, NFR-4.4) -------------------------------------------
# Served by Groq. Confirm against the live roster with `python -c "from groq
# import Groq; print([m.id for m in Groq().models.list().data])"` — Groq retires
# and renames hosted models, and a stale ID fails at request time.

# Answer generation. Grounding discipline and refusal behaviour are the product,
# so this is where quality is worth paying for.
ANSWER_MODEL = "openai/gpt-oss-120b"

# Cheap non-generative stages: query rewriting and intent/trigger classification.
UTILITY_MODEL = "openai/gpt-oss-20b"

# Reasoning depth. This route is latency-sensitive (NFR-2.1) and grounded
# synthesis from six retrieved chunks is not a hard reasoning task.
ANSWER_REASONING_EFFORT = "low"

# Per-1M-token prices, used only for the cost estimate in the ops console
# (NFR-4.6). Operator-maintained — verify against Groq's current price list.
PRICE_PER_MTOK = {
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.75},
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
}

# --- source trust hierarchy (PRD FR-2.7) -------------------------------------

SOURCE_TRUST = {"faq": 3, "guide": 2, "ticket": 1}
SOURCE_LABEL = {
    "faq": "NovaCell FAQ",
    "guide": "Technical Guide v3.2",
    "ticket": "Resolved support ticket",
}

# --- ops-editable settings ---------------------------------------------------

DEFAULT_SETTINGS: dict = {
    # FR-3.1 / FR-3.2 — confidence gate and relevance floor.
    "confidence_threshold": 0.45,
    "relevance_floor": 0.30,
    # FR-2.4 — how many chunks reach the model.
    "top_k": 6,
    "max_per_source": 3,
    # FR-1.3
    "max_answer_words": 150,
    # FR-3.8 — forced refusal regardless of retrieval.
    "blocklist": [],
    # FR-4.4 — staffed live-chat hours (local time, 24h clock).
    "staffed_hours_start": 8,
    "staffed_hours_end": 22,
    # FR-4.7 — global kill switch.
    "kill_switch": False,
    # FR-3.3 — guide sections force-included/excluded by Support Ops, overriding
    # the automatic classifier. Keyed by section id.
    "guide_force_internal": [],
    "guide_force_customer_safe": [],
}

# --- deflection targets (PRD 3.3) --------------------------------------------
# Where to send a customer whose question needs live account data that v1 cannot see.

DEEP_LINKS = {
    "balance": ("MyTelecom app > My Usage", "Or dial *123# from your NovaCell mobile."),
    "bill": ("MyTelecom app > Billing > Itemised Bill", "Bills for the last 12 months are available there."),
    "payment": ("MyTelecom app > Billing > Payment Methods", None),
    "plan": ("MyTelecom app > My Plan", None),
    "usage": ("MyTelecom app > My Usage", "Or dial *123#."),
    "outage": ("MyTelecom app > Help > Report an Issue", "Coverage map: telecom.example.com/coverage"),
    "roaming": ("MyTelecom app > Plan & Services > International Roaming", None),
    "generic": ("MyTelecom app", "Or call 611 to speak to our team."),
}

SUPPORT_PHONE = "611"
