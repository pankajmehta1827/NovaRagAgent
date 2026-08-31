"""Nova — NovaCell's grounded Tier-1 support assistant.

Implements the v1 scope of PRD.md: a conversational assistant answering Tier-1
customer questions from three verified sources (FAQ, resolved tickets, PDF
guides), with citation-grounded answers, an explicit refusal path, bounded
deflection for account-specific questions, and graceful escalation to a human.
"""

__all__ = [
    "config",
    "conversation",
    "escalation",
    "guardrails",
    "ingest",
    "llm",
    "retriever",
    "sanitise",
    "store",
]
