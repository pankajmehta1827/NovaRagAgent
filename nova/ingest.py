"""Knowledge ingestion for NovaCell's four sources.

PRD references: FR-2.1 (all sources), FR-2.3 (per-source chunking),
FR-2.9 (resolved tickets only), FR-3.3 (guide content-classification gate),
FR-3.4 / NFR-3.2 (ticket sanitisation), FR-5.1..5.3 (ops-editable content).

Every ingest run also produces an audit report so Support Ops can see exactly
what was indexed, what was withheld, and why.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import config
from .sanitise import classify_guide_section, redact_resolution, sanitise_description, scrub_pii


@dataclass
class Chunk:
    """One retrievable unit of verified NovaCell knowledge."""

    id: str
    source: str  # "faq" | "ticket" | "guide"
    title: str
    text: str
    category: str = ""
    trust: int = 1
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        """A citation must identify the document, not just its category.

        Two billing FAQs both citing "NovaCell FAQ — billing" are
        indistinguishable to a customer and useless to Support Ops trying to see
        which article is doing the deflection, so the entry id is part of it.
        """
        label = config.SOURCE_LABEL[self.source]
        if self.source in ("guide", "plans"):
            return f"{label}, {self.title}"
        if self.source == "faq":
            return f"{label} {self.meta.get('faq_id', '?')} — {self.category or 'General'}"
        return f"{label} {self.meta.get('ticket_id', '')} — {self.title}".strip()

    @property
    def retrieval_text(self) -> str:
        """What the retriever matches against: title carries strong signal."""
        return f"{self.title}\n{self.text}"


@dataclass
class IngestReport:
    """Auditable record of one indexing run (FR-3.3, FR-5.8)."""

    counts: dict[str, int] = field(default_factory=dict)
    withheld_guide_sections: list[dict[str, str]] = field(default_factory=list)
    tickets_needing_agent: list[str] = field(default_factory=list)
    tickets_excluded_unresolved: list[str] = field(default_factory=list)


# --- Source A: FAQ -----------------------------------------------------------


def load_faq(overrides: dict[str, dict] | None = None) -> list[Chunk]:
    """FAQ = one chunk per Q&A pair, never split (FR-2.3).

    ``overrides`` carries Support Ops edits made in the console: an entry may be
    edited in place, retired (``retired: true``), or newly added (FR-5.1).
    """
    overrides = overrides or {}
    chunks: list[Chunk] = []
    seen: set[str] = set()

    if config.FAQ_PATH.exists():
        with config.FAQ_PATH.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                faq_id = (row.get("id") or "").strip()
                if not faq_id:
                    continue
                seen.add(faq_id)
                override = overrides.get(faq_id, {})
                if override.get("retired"):
                    continue
                question = (override.get("question") or row.get("question") or "").strip()
                answer = (override.get("answer") or row.get("answer") or "").strip()
                category = (override.get("category") or row.get("category") or "").strip()
                if not question or not answer:
                    continue
                chunks.append(
                    Chunk(
                        id=f"faq-{faq_id}",
                        source="faq",
                        title=question,
                        text=answer,
                        category=category,
                        trust=config.SOURCE_TRUST["faq"],
                        meta={"faq_id": faq_id, "edited": bool(override)},
                    )
                )

    # Entries authored in the console that do not exist in the CSV.
    for faq_id, override in overrides.items():
        if faq_id in seen or override.get("retired"):
            continue
        question = (override.get("question") or "").strip()
        answer = (override.get("answer") or "").strip()
        if not question or not answer:
            continue
        chunks.append(
            Chunk(
                id=f"faq-{faq_id}",
                source="faq",
                title=question,
                text=answer,
                category=(override.get("category") or "").strip(),
                trust=config.SOURCE_TRUST["faq"],
                meta={"faq_id": faq_id, "authored": True},
            )
        )
    return chunks


# --- Source B: resolved tickets ----------------------------------------------


def load_tickets(report: IngestReport) -> list[Chunk]:
    """Resolved tickets only, PII-scrubbed and internal-action redacted.

    FR-2.9 excludes anything not ``status = 'resolved'``. FR-3.4 rewrites the
    resolution into customer-actionable guidance, or marks the ticket as
    agent-only when nothing customer-actionable survives.
    """
    chunks: list[Chunk] = []
    if not config.TICKETS_PATH.exists():
        return chunks

    connection = sqlite3.connect(config.TICKETS_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT ticket_id, category, issue_type, description, resolution, status FROM tickets"
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        if (row["status"] or "").strip().lower() != "resolved":
            report.tickets_excluded_unresolved.append(row["ticket_id"])
            continue

        symptom = sanitise_description(row["description"])
        guidance, cause, needs_agent = redact_resolution(scrub_pii(row["resolution"] or ""))

        parts = [f"Reported symptom: {symptom}"]
        if cause:
            parts.append(f"Known cause: {cause}")
        if guidance:
            parts.append(f"What the customer can do: {guidance}")
        if needs_agent:
            report.tickets_needing_agent.append(row["ticket_id"])
            parts.append(
                "Outcome: this case was resolved by a NovaCell support agent working on the "
                "account, so there may be no fix the customer can apply themselves."
            )
        body = "\n".join(parts)

        chunks.append(
            Chunk(
                id=f"ticket-{row['ticket_id']}",
                source="ticket",
                title=row["issue_type"] or "Support case",
                text=body,
                category=row["category"] or "",
                trust=config.SOURCE_TRUST["ticket"],
                meta={"ticket_id": row["ticket_id"], "needs_agent": needs_agent},
            )
        )
    return chunks


# --- Source C: PDF guide -----------------------------------------------------

_SECTION_RE = re.compile(r"^(\d+)\.\s+(.{3,90})$")
_STEP_RE = re.compile(r"^(Step\s+\d+)\s*[-–—]\s*(.+)$")
_LABEL_RE = re.compile(r"^([A-Z][A-Za-z0-9 /(),'&-]{2,60}):\s+(.+)$")
_BULLET_RE = re.compile(r"^[-–—•]\s+(.+)$")
_NOISE_RE = re.compile(r"Telecom Technical Reference Guide\s*[-–—]\s*Internal Use Only|^Page \d+$", re.M)


def _guide_text() -> str:
    try:
        import pypdf
    except ImportError:  # pragma: no cover - dependency is declared
        return ""
    if not config.GUIDE_PATH.exists():
        return ""
    reader = pypdf.PdfReader(config.GUIDE_PATH)
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _NOISE_RE.sub("", raw)


def _top_level_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    buffer: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        match = _SECTION_RE.match(stripped)
        if match:
            if current_title:
                sections.append((current_title, "\n".join(buffer).strip()))
            current_title = f"Section {match.group(1)} {match.group(2).strip()}"
            buffer = []
        elif current_title:
            buffer.append(stripped)
    if current_title:
        sections.append((current_title, "\n".join(buffer).strip()))
    return sections


def _paragraph_label(line: str) -> str | None:
    """The heading of a new paragraph block, if this line starts one."""
    step = _STEP_RE.match(line)
    if step:
        return f"{step.group(1)}: {step.group(2).strip().rstrip('.').split('.')[0][:60]}"
    label = _LABEL_RE.match(line)
    if label:
        return label.group(1).strip()
    return None


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split the guide into paragraph-level chunks under each numbered section.

    Granularity is a safety requirement, not just a retrieval one. Whole-section
    chunking makes the classification gate all-or-nothing: one internal sentence
    about SS7 in the roaming section would withhold the roaming prices customers
    need. Splitting at "Step N —" and "Label:" boundaries lets the gate withhold
    the internal paragraph and publish the rest (FR-2.3, FR-3.3).
    """
    chunks: list[tuple[str, str]] = []

    for title, body in _top_level_sections(text):
        blocks: list[tuple[str | None, list[str]]] = [(None, [])]
        for raw_line in body.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            label = _paragraph_label(line)
            bullet = _BULLET_RE.match(line)
            if label:
                blocks.append((label, [line]))
            elif bullet and len(blocks[-1][1]) > 1:
                blocks.append((None, [line]))
            else:
                blocks[-1][1].append(line)

        for label, lines in blocks:
            text_block = " ".join(lines).strip()
            if not text_block:
                continue
            chunk_title = f"{title} — {label}" if label else title
            chunks.append((chunk_title, text_block))

    return chunks


def load_guide(report: IngestReport, settings: dict) -> list[Chunk]:
    """Guide sections that pass the customer-safe classification gate (FR-3.3)."""
    chunks: list[Chunk] = []
    forced_internal = set(settings.get("guide_force_internal", []))
    forced_safe = set(settings.get("guide_force_customer_safe", []))

    for index, (title, body) in enumerate(_split_sections(_guide_text()), start=1):
        chunk_id = f"guide-{index}"
        customer_safe, reason = classify_guide_section(title, body)
        if chunk_id in forced_internal:
            customer_safe, reason = False, "withheld by Support Ops"
        elif chunk_id in forced_safe:
            customer_safe, reason = True, "released by Support Ops"

        if not customer_safe:
            report.withheld_guide_sections.append({"id": chunk_id, "title": title, "reason": reason})
            continue

        chunks.append(
            Chunk(
                id=chunk_id,
                source="guide",
                title=title,
                text=body,
                trust=config.SOURCE_TRUST["guide"],
                meta={"classification": reason},
            )
        )
    return chunks


# --- Source D: plans catalog --------------------------------------------------


def _format_price(value: Any, currency: str) -> str:
    if isinstance(value, (int, float)):
        return f"{currency} {value:,.2f}"
    return str(value)


def _plan_body(plan: dict, currency: str) -> str:
    """Reproduce every catalog figure verbatim (FR-2.5): this is the exact source
    the answer prompt's verbatim-facts rule expects for prices and allowances.
    """
    lines: list[str] = []
    if plan.get("monthly_price") is not None:
        lines.append(f"Monthly price: {_format_price(plan['monthly_price'], currency)}")
    if plan.get("price") is not None:
        unit = plan.get("price_unit", "")
        lines.append(f"Price: {_format_price(plan['price'], currency)}" + (f" ({unit})" if unit else ""))
    if plan.get("price_per_line") is not None:
        lines.append(f"Effective price per line: {_format_price(plan['price_per_line'], currency)}")
    if plan.get("lines_included") is not None:
        lines.append(f"Lines included: {plan['lines_included']}")
    if plan.get("data_unlimited"):
        lines.append("Data: unlimited")
    elif plan.get("data_gb") is not None:
        lines.append(f"Data: {plan['data_gb']} GB")
    if plan.get("talk_minutes") is not None:
        lines.append(f"Talk: {plan['talk_minutes']}")
    if plan.get("texts") is not None:
        lines.append(f"Text: {plan['texts']}")
    if plan.get("hotspot_gb") is not None:
        lines.append(f"Mobile hotspot: {plan['hotspot_gb']} GB")
    if plan.get("network"):
        lines.append(f"Network: {plan['network']}")
    if plan.get("coverage"):
        lines.append(f"Coverage: {plan['coverage']}")
    if plan.get("contract"):
        lines.append(f"Contract: {plan['contract']}")
    if plan.get("eligibility"):
        lines.append(f"Eligibility: {plan['eligibility']}")
    if plan.get("intro_offer"):
        lines.append(f"Intro offer: {plan['intro_offer']}")
    for feature in plan.get("features") or []:
        lines.append(f"- {feature}")
    if plan.get("best_for"):
        lines.append(f"Best for: {plan['best_for']}")
    return "\n".join(lines)


def load_plans() -> list[Chunk]:
    """Plan/add-on catalog = one chunk per entry, never split (FR-2.3).

    The single structured, ops-maintained source of truth for prices and
    allowances (see ``last_updated`` in plans.json) — highest trust in the
    hierarchy (FR-2.7).
    """
    chunks: list[Chunk] = []
    if not config.PLANS_PATH.exists():
        return chunks
    try:
        payload = json.loads(config.PLANS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return chunks

    currency = payload.get("currency", "USD")
    for plan in payload.get("plans", []):
        plan_id = (plan.get("id") or "").strip()
        name = (plan.get("name") or "").strip()
        if not plan_id or not name:
            continue
        chunks.append(
            Chunk(
                id=f"plan-{plan_id}",
                source="plans",
                title=name,
                text=_plan_body(plan, currency),
                category=plan.get("category", ""),
                trust=config.SOURCE_TRUST["plans"],
                meta={"plan_id": plan_id, "type": plan.get("type", "")},
            )
        )
    return chunks


# --- combined ----------------------------------------------------------------


def build_index(settings: dict, faq_overrides: dict[str, dict] | None = None) -> tuple[list[Chunk], IngestReport]:
    report = IngestReport()
    faq = load_faq(faq_overrides)
    tickets = load_tickets(report)
    guide = load_guide(report, settings)
    plans = load_plans()
    report.counts = {
        "faq": len(faq),
        "ticket": len(tickets),
        "guide": len(guide),
        "plans": len(plans),
        "total": len(faq) + len(tickets) + len(guide) + len(plans),
    }
    return faq + tickets + guide + plans, report
