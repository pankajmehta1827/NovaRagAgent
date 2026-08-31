"""Turn orchestration: guardrails -> retrieval -> grounded answer -> confidence -> escalation.

This is the module that enforces the PRD's shape of a conversation. The order
matters: some questions must never reach retrieval (guardrails), and an answer
that clears the model but not the confidence gate must never reach the customer
as if it were verified.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from groq import Groq

from . import escalation, guardrails, llm, store
from .ingest import IngestReport, build_index
from .retriever import HybridRetriever, normalised_top_score


@dataclass
class Turn:
    """Everything produced for one customer message."""

    turn_id: str
    question: str
    mode: str  # "fixed" | "stream"
    fixed_text: str = ""
    hits: list = field(default_factory=list)
    precheck: guardrails.PreCheck = field(default_factory=guardrails.PreCheck)
    sink: dict[str, Any] = field(default_factory=dict)
    usage: list[dict] = field(default_factory=list)
    retrieval_score: float = 0.0
    confidence: float = 0.0
    escalated: bool = False
    handoff: dict | None = None
    escalation_offer: bool = False
    deflection_note: str = ""
    started_at: float = field(default_factory=time.perf_counter)
    latency_ms: int = 0


class NovaAgent:
    def __init__(self, client: Groq, settings: dict, faq_overrides: dict) -> None:
        self.client = client
        self.settings = settings
        self.chunks, self.report = build_index(settings, faq_overrides)
        self.retriever = HybridRetriever(self.chunks)

    # --- step 1: decide what kind of turn this is ---------------------------

    def begin_turn(self, question: str, history: list[dict]) -> Turn:
        turn = Turn(turn_id=uuid.uuid4().hex[:12], question=question, mode="fixed")
        check = guardrails.check(question, history, self.settings)
        turn.precheck = check

        if check.action == guardrails.REFUSE:
            turn.fixed_text = check.message
            turn.sink["status"] = "REFUSED"
            return turn

        if check.action == guardrails.ESCALATE:
            turn.escalated = True
            turn.sink["status"] = "ESCALATED"
            turn.fixed_text = ""  # filled by the caller once the handoff is built
            return turn

        # Retrieval path. The cheap model bridges symptom language to domain terms.
        expanded, usage = llm.expand_query(self.client, question, history)
        if usage:
            turn.usage.append(usage)

        turn.hits = self.retriever.search(
            expanded,
            top_k=self.settings.get("top_k", 6),
            max_per_source=self.settings.get("max_per_source", 3),
        )
        turn.retrieval_score = normalised_top_score(turn.hits)

        # FR-3.2 — nothing above the relevance floor means no verified answer.
        # Refuse here without calling the answer model: it is both correct and cheap.
        if turn.retrieval_score < self.settings.get("relevance_floor", 0.30):
            turn.sink["status"] = "NO_VERIFIED_ANSWER"
            turn.escalation_offer = True
            turn.fixed_text = (
                "I don't have a verified answer for that in NovaCell's support material, "
                "so I don't want to guess. A support agent can help — shall I pass you over?"
            )
            return turn

        if check.action == guardrails.DEFLECT:
            turn.deflection_note = guardrails.deflection_note(check.deep_link_key)

        turn.mode = "stream"
        return turn

    # --- step 2: stream the grounded answer --------------------------------

    def stream(self, turn: Turn, history: list[dict]) -> Iterator[str]:
        yield from llm.stream_answer(
            client=self.client,
            question=turn.question,
            hits=turn.hits,
            history=history,
            settings=self.settings,
            account_boundary=turn.precheck.action == guardrails.DEFLECT,
            sink=turn.sink,
        )

    # --- step 3: score the answer and decide on escalation -----------------

    def finish_turn(self, turn: Turn, consecutive_ungrounded: int) -> Turn:
        turn.latency_ms = int((time.perf_counter() - turn.started_at) * 1000)

        if turn.sink.get("usage"):
            turn.usage.append(turn.sink["usage"])

        status = turn.sink.get("status", "ANSWERED" if turn.fixed_text else "NO_VERIFIED_ANSWER")

        # Guardrails already decided these turns; the confidence gate does not apply.
        if status in {"REFUSED", "ESCALATED"}:
            return turn

        turn.confidence = self._confidence(turn, status)

        threshold = self.settings.get("confidence_threshold", 0.45)

        if status == "ERROR":
            # NFR-2.5 — degrade to the escalation path, never to a made-up answer.
            turn.escalation_offer = True
            turn.fixed_text = (
                "Something went wrong on my side and I couldn't check NovaCell's support material. "
                "I'd rather hand you to a support agent than guess — shall I do that?"
            )
        elif status == "NO_VERIFIED_ANSWER":
            turn.escalation_offer = True
        elif status == "ANSWERED" and turn.confidence < threshold:
            # Cleared the model but not the gate (FR-3.1).
            turn.escalation_offer = True

        # FR-4.1(b) — two consecutive turns without a grounded answer escalates.
        if turn.escalation_offer and consecutive_ungrounded >= 1:
            turn.escalated = True
            turn.precheck.reason_code = turn.precheck.reason_code or "NO_GROUNDED_ANSWER"
        elif turn.escalation_offer and not turn.precheck.reason_code:
            turn.precheck.reason_code = "LOW_CONFIDENCE"

        return turn

    def _confidence(self, turn: Turn, status: str) -> float:
        if status in {"NO_VERIFIED_ANSWER", "ERROR"}:
            return 0.0
        if status == "CLARIFY":
            return 1.0  # asking one clarifying question is a correct outcome

        retrieval = turn.retrieval_score

        # Source agreement: independent sources converging on the same category is
        # a stronger signal than one lucky chunk.
        top = turn.hits[:3]
        categories = {hit.chunk.category for hit in top if hit.chunk.category}
        sources = {hit.chunk.source for hit in top}
        agreement = 1.0 if (len(sources) > 1 and len(categories) <= 1) else 0.7 if len(top) > 1 else 0.4

        # Citation coverage: an answer that cited nothing is not grounded, whatever
        # it claims (FR-2.5, NFR-1.5).
        cited = turn.sink.get("cited", [])
        citation = 1.0 if cited else 0.0

        # A ticket-only answer is the weakest evidence in the trust hierarchy.
        if turn.hits and all(hit.chunk.source == "ticket" for hit in turn.hits[:2]):
            retrieval *= 0.8

        return round(0.45 * retrieval + 0.2 * agreement + 0.35 * citation, 3)

    # --- step 4: escalate ---------------------------------------------------

    def escalate(self, turn: Turn, history: list[dict], session_id: str) -> dict:
        cited_markers = turn.sink.get("cited", [])
        source_index = turn.sink.get("source_index", {})
        cited_sources = [source_index[m].citation for m in cited_markers if m in source_index]
        if not cited_sources:
            cited_sources = [hit.chunk.citation for hit in turn.hits[:3]]

        category = ""
        if turn.hits:
            category = turn.hits[0].chunk.category or turn.hits[0].chunk.source

        handoff = escalation.build_handoff(
            reason_code=turn.precheck.reason_code or "LOW_CONFIDENCE",
            history=history,
            cited_sources=cited_sources,
            category=category,
            settings=self.settings,
            session_id=session_id,
        )
        turn.handoff = handoff
        turn.escalated = True
        store.log_escalation(handoff)
        return handoff

    # --- step 5: log --------------------------------------------------------

    def log(self, turn: Turn, session_id: str) -> None:
        store.log_turn(
            {
                "turn_id": turn.turn_id,
                "session_id": session_id,
                "question": turn.question,
                "status": turn.sink.get("status", "FIXED"),
                "confidence": turn.confidence,
                "threshold": self.settings.get("confidence_threshold", 0.45),
                "retrieval_score": round(turn.retrieval_score, 3),
                "retrieved": [hit.chunk.id for hit in turn.hits],
                "cited": turn.sink.get("cited", []),
                "top_source": turn.hits[0].chunk.source if turn.hits else "",
                "escalated": turn.escalated,
                "reason_code": turn.precheck.reason_code,
                "latency_ms": turn.latency_ms,
                "usage": turn.usage,
            }
        )


def index_summary(report: IngestReport) -> str:
    counts = report.counts
    return (
        f"{counts.get('total', 0)} chunks indexed — "
        f"{counts.get('faq', 0)} FAQ, {counts.get('ticket', 0)} tickets, {counts.get('guide', 0)} guide sections"
    )
