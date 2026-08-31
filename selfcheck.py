"""Offline self-check for the parts of Nova that must be right before launch.

Exercises ingestion, sanitisation, the content-classification gate, retrieval and
the guardrails — none of which need the API. Run it after any knowledge or rule
change:

    .venv/Scripts/python selfcheck.py

This is the seed of the regression suite the PRD requires in FR-6.5.
"""

from __future__ import annotations

import sys

from nova import guardrails, store
from nova.ingest import build_index
from nova.retriever import HybridRetriever, normalised_top_score

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}{(' — ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


settings = store.load_settings()
chunks, report = build_index(settings, store.load_faq_overrides())
retriever = HybridRetriever(chunks)
by_id = {chunk.id: chunk for chunk in chunks}

print("\n== Index ==")
print(f"  {report.counts}")

print("\n== Ingestion (FR-2.1, FR-2.3) ==")
check("all three sources indexed", all(report.counts.get(s, 0) > 0 for s in ("faq", "ticket", "guide")))
check("FAQ pairs not split", all("\n" not in c.title for c in chunks if c.source == "faq"))

print("\n== Resolved-tickets-only filter (FR-2.9) ==")
check(
    "unresolved tickets excluded",
    bool(report.tickets_excluded_unresolved),
    f"excluded {report.tickets_excluded_unresolved}",
)
check(
    "no escalated ticket in the index",
    not any(c.id == "ticket-TK-020" for c in chunks),
)

print("\n== Guide content-classification gate (FR-3.3) ==")
withheld_titles = " | ".join(item["title"] for item in report.withheld_guide_sections)
check("some sections withheld", bool(report.withheld_guide_sections), f"{len(report.withheld_guide_sections)} withheld")
check("security/fraud section withheld", "Network Security" in withheld_titles)
check("billing architecture section withheld", "Billing System Architecture" in withheld_titles)
check("internal escalate step withheld", "Escalate" in withheld_titles)
check(
    "customer troubleshooting steps still published",
    any("Troubleshooting" in c.title and "APN" in c.text for c in chunks if c.source == "guide"),
)
guide_blob = " ".join(c.text.lower() for c in chunks if c.source == "guide")
check("no SS7 internals reachable by customers", "ss7" not in guide_blob)
check("no agent-directed instructions reachable", "agents should" not in guide_blob)

print("\n== Ticket sanitisation (NFR-3.2, FR-3.4, FR-3.5) ==")
ticket_blob = " ".join(c.text.lower() for c in chunks if c.source == "ticket")
check("no internal backend actions surfaced", "session token" not in ticket_blob and "backend" not in ticket_blob)
check("no compensation or credit promises", "compensat" not in ticket_blob and "goodwill" not in ticket_blob)
check(
    "internal-only fix marked as needing an agent",
    bool(report.tickets_needing_agent),
    f"{len(report.tickets_needing_agent)} tickets",
)
tk3 = by_id.get("ticket-TK-003")
check(
    "TK-003 (backend cache fix) is agent-only, not instructions",
    tk3 is not None and tk3.meta["needs_agent"] and "cache" not in tk3.text.lower(),
)
for leak in ("rnc", "whitelist", "field team", "repair crew", "junction box", "payment gateway", "eta 4 hours"):
    check(f"no internal detail {leak!r} in the ticket index", leak not in ticket_blob)
tk1 = by_id.get("ticket-TK-001")
check(
    "advisory steps survive as customer instructions",
    tk1 is not None and not tk1.meta["needs_agent"] and "toggle airplane mode" in tk1.text.lower(),
    tk1.text.replace("\n", " | ") if tk1 else "",
)

print("\n== Retrieval (FR-2.2, FR-2.4) ==")
cases = [
    ("How much is the EU roaming bundle?", "faq-10"),
    ("my esim wont activate", "ticket-TK-009"),
    ("what is APN and how do I reset it", None),
    ("calls keep dropping", "faq-6"),
    ("how long does SIM activation take", "faq-12"),
]
for query, expected in cases:
    hits = retriever.search(query, top_k=settings["top_k"], max_per_source=settings["max_per_source"])
    ids = [hit.chunk.id for hit in hits]
    if expected:
        check(f"retrieves {expected} for {query!r}", expected in ids, ", ".join(ids[:4]))
    else:
        check(f"retrieves something for {query!r}", bool(hits), ", ".join(ids[:4]))
    check(
        f"  source cap respected for {query!r}",
        all(sum(1 for h in hits if h.chunk.source == s) <= settings["max_per_source"] for s in ("faq", "ticket", "guide")),
    )

print("\n== Relevance floor (FR-3.2) ==")
off_topic = retriever.search("what is the capital of France", top_k=6)
check(
    "off-topic question falls below the relevance floor",
    normalised_top_score(off_topic) < settings["relevance_floor"],
    f"score {normalised_top_score(off_topic):.3f} vs floor {settings['relevance_floor']}",
)
on_topic = retriever.search("why is my mobile internet so slow", top_k=6)
check(
    "on-topic question clears the relevance floor",
    normalised_top_score(on_topic) >= settings["relevance_floor"],
    f"score {normalised_top_score(on_topic):.3f}",
)

print("\n== Guardrails (3.3, FR-3.6, FR-4.1) ==")
guardrail_cases = [
    ("What is my current data balance?", guardrails.DEFLECT, "balance"),
    ("Why is my bill higher this month?", guardrails.DEFLECT, "bill"),
    ("I want to speak to a human", guardrails.ESCALATE, "CUSTOMER_REQUESTED_HUMAN"),
    ("Someone changed my plan without my permission", guardrails.ESCALATE, "FRAUD_OR_UNAUTHORISED"),
    ("My phone was stolen last night", guardrails.ESCALATE, "LOST_OR_STOLEN_SIM"),
    ("I want a refund for the double charge", guardrails.ESCALATE, "BILLING_DISPUTE"),
    ("I want to cancel my plan", guardrails.ESCALATE, "CANCELLATION"),
    ("My card number is 4111111111111111", guardrails.REFUSE, ""),
    ("How do I enable Wi-Fi calling?", guardrails.ALLOW, ""),
    ("What does the EU roaming bundle cost?", guardrails.ALLOW, ""),
]
for question, expected_action, expected_detail in guardrail_cases:
    result = guardrails.check(question, [], settings)
    detail = result.deep_link_key if result.action == guardrails.DEFLECT else result.reason_code
    ok = result.action == expected_action and (not expected_detail or detail == expected_detail)
    check(f"{question!r} -> {expected_action}", ok, f"got {result.action}/{detail}")

print("\n== PII scrubbing (NFR-3.1) ==")
from nova.sanitise import scrub_pii  # noqa: E402

scrubbed = scrub_pii("Contact Mr John Smith on 07700 900123 or john.smith@example.com, IMEI 356938035643809.")
check("name removed", "John Smith" not in scrubbed, scrubbed)
check("email removed", "@example.com" not in scrubbed)
check("phone removed", "900123" not in scrubbed)
check("published short codes preserved", "*123#" in scrub_pii("Dial *123# to check your balance."))
check("care line preserved", "611" in scrub_pii("Call 611 for help."))

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("All checks passed.")
