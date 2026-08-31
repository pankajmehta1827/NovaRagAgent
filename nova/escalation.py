"""Handoff to a human (PRD FR-4.1 to FR-4.6).

Escalation is a clean transfer, never a restart: the payload carries the whole
conversation, the sources Nova already showed, the detected category and a reason
code, so the agent never asks the customer to repeat themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from . import config
from .guardrails import REASON_CODES


def within_staffed_hours(settings: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    start = settings.get("staffed_hours_start", 8)
    end = settings.get("staffed_hours_end", 22)
    return start <= now.hour < end


def build_handoff(
    reason_code: str,
    history: list[dict],
    cited_sources: list[str],
    category: str,
    settings: dict,
    session_id: str,
    channel: str = "web",
) -> dict[str, Any]:
    """The payload handed to the agent desktop (FR-4.3)."""
    now = datetime.now()
    staffed = within_staffed_hours(settings, now)
    return {
        "handoff_id": f"HO-{uuid.uuid4().hex[:8].upper()}",
        "created_at": now.isoformat(timespec="seconds"),
        "session_id": session_id,
        "channel": channel,
        "reason_code": reason_code,
        "reason": REASON_CODES.get(reason_code, reason_code),
        "detected_category": category,
        "routing": "live_agent_queue" if staffed else "ticket",
        "ticket_ref": None if staffed else f"TK-{uuid.uuid4().hex[:6].upper()}",
        "cited_sources": cited_sources,
        "transcript": [{"role": turn["role"], "content": turn["content"]} for turn in history],
    }


def customer_message(handoff: dict, settings: dict) -> str:
    """What the customer sees at the moment of handoff (FR-4.4, FR-4.5)."""
    start = settings.get("staffed_hours_start", 8)
    end = settings.get("staffed_hours_end", 22)
    if handoff["routing"] == "live_agent_queue":
        return (
            "I'm passing you to a NovaCell support agent now. They'll see everything you've "
            "told me and the information I showed you, so you won't need to repeat yourself.\n\n"
            f"If you'd rather not wait, you can call {config.SUPPORT_PHONE} instead."
        )
    return (
        f"Our live chat team is available {start}:00–{end}:00. Outside those hours I've created a "
        f"support ticket for you — reference **{handoff['ticket_ref']}**. Your full conversation is "
        "attached to it, so the agent picking it up will already have the context.\n\n"
        f"If it's urgent, call {config.SUPPORT_PHONE} — that line is answered outside chat hours."
    )
