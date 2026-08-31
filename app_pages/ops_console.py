"""Support Ops console (PRD §4.5, §4.6, FR-3.1, FR-3.3, FR-3.8, FR-4.7).

Everything here changes the live assistant without an engineering release.
"""

from collections import Counter

import streamlit as st

from nova import config, store, ui

# The console shell already says "Console", so this page names what it governs.
ui.kicker("Operations")
st.header("Support operations")

settings = store.load_settings()
overrides = store.load_faq_overrides()
chunks, report = ui.get_index()

# --- live status -------------------------------------------------------------

st.caption("Knowledge, quality and availability for the customer assistant.")

status_row = st.container(horizontal=True, vertical_alignment="center")
with status_row:
    st.metric("Indexed chunks", report.counts.get("total", 0), icon=":material/database:", border=True)
    st.metric("FAQ", report.counts.get("faq", 0), icon=":material/quiz:", border=True)
    st.metric("Tickets", report.counts.get("ticket", 0), icon=":material/confirmation_number:", border=True)
    st.metric("Guide sections", report.counts.get("guide", 0), icon=":material/menu_book:", border=True)

if st.button("Republish index", icon=":material/publish:", type="primary"):
    ui.rebuild_index()
    st.rerun()

# --- customer availability (FR-4.7) ------------------------------------------
# The kill switch is deliberately awkward to reach and trivial to reverse. Its
# effect is invisible from the console — customers just see an outage notice —
# so the console must always state which way it is set, and recovery must be one
# obvious click rather than a toggle someone has to remember flipping.

with st.container(border=True):
    if settings["kill_switch"]:
        st.error(
            "**The assistant is switched off for customers.** Anyone opening Chat sees an "
            "outage notice and is directed to 611 and the MyTelecom app.",
            icon=":material/pause_circle:",
        )
        if st.button("Switch the assistant back on", icon=":material/play_arrow:", type="primary"):
            settings["kill_switch"] = False
            store.save_settings(settings)
            ui.rebuild_index()
            st.rerun()
    else:
        st.success("The assistant is live for customers.", icon=":material/check_circle:")
        with st.expander("Emergency kill switch", icon=":material/pause_circle:"):
            st.caption(
                "Takes the assistant offline for every customer immediately and fails over to "
                "611 and the MyTelecom app. For a live incident — a wrong price published, a "
                "grounding failure in the wild — not for routine changes."
            )
            confirm = st.checkbox("I understand this takes the assistant offline for all customers")
            if st.button(
                "Switch off now",
                icon=":material/pause_circle:",
                disabled=not confirm,
            ):
                settings["kill_switch"] = True
                store.save_settings(settings)
                ui.rebuild_index()
                st.rerun()

tab_metrics, tab_gaps, tab_faq, tab_content, tab_gate = st.tabs(
    ["Metrics", "Unanswered questions", "FAQ content", "Content audit", "Answer gate"]
)

# --- metrics (FR-6.3) --------------------------------------------------------

with tab_metrics:
    window = st.segmented_control("Window", [7, 30, 90], default=30, format_func=lambda d: f"{d} days")
    stats = store.metrics(days=window or 30)

    row1 = st.container(horizontal=True)
    with row1:
        st.metric("Containment", f"{stats['containment_rate']:.0%}", icon=":material/task_alt:", border=True, help="Sessions ending without a human handoff. Target ≥40% by day 90.")
        st.metric("Sessions", stats["sessions"], icon=":material/forum:", border=True)
        st.metric("Turns", stats["turns"], icon=":material/chat_bubble:", border=True)
        st.metric("Escalated", stats["escalated_sessions"], icon=":material/support_agent:", border=True)

    row2 = st.container(horizontal=True)
    with row2:
        st.metric("Answered", f"{stats['answered_rate']:.0%}", icon=":material/verified:", border=True)
        st.metric("Refused", f"{stats['refusal_rate']:.0%}", icon=":material/help_outline:", border=True, help="Turns where no verified answer existed. A healthy number, not a failure.")
        st.metric(
            "Thumbs up",
            f"{stats['thumbs_up_rate']:.0%}" if stats["feedback_count"] else "—",
            icon=":material/thumb_up:",
            border=True,
            help=f"{stats['feedback_count']} ratings. Target ≥70%.",
        )

    row3 = st.container(horizontal=True)
    with row3:
        st.metric("P50 latency", f"{stats['p50_latency_ms'] / 1000:.1f}s", icon=":material/speed:", border=True, help="Target P50 ≤4s end to end.")
        st.metric("P95 latency", f"{stats['p95_latency_ms'] / 1000:.1f}s", icon=":material/timer:", border=True, help="Target P95 ≤8s.")
        st.metric("Cost / session", f"${stats['cost_per_session']:.4f}", icon=":material/payments:", border=True, help="Target ≤$0.25 per contained conversation.")
        st.metric("Spend in window", f"${stats['total_cost_usd']:.4f}", icon=":material/receipt_long:", border=True)

    escalations = store.read_escalations()
    if escalations:
        ui.kicker("Escalation reasons", ink=True)
        counts = Counter(item.get("reason", item.get("reason_code", "?")) for item in escalations)
        st.dataframe(
            [{"Reason": reason, "Count": count} for reason, count in counts.most_common()],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("No escalations logged yet.")

# --- unanswered questions (FR-5.6) -------------------------------------------

with tab_gaps:
    st.caption(
        "Every refusal, low-confidence answer and thumbs-down lands here. This is the "
        "content backlog — the highest-value output of the assistant after the answers."
    )
    queue = store.unanswered_queue()
    if not queue:
        st.info("Nothing in the queue.", icon=":material/inbox:")
    else:
        st.dataframe(
            [
                {
                    "When": item["timestamp"],
                    "Question": item["question"],
                    "Status": item["status"],
                    "Confidence": item["confidence"],
                    "Reason": item["reason_code"],
                    "Thumbs down": item["thumbs_down"],
                }
                for item in queue
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(f"{len(queue)} items. Author an FAQ entry in the next tab to close one.")

# --- FAQ authoring (FR-5.1, FR-5.4, FR-5.5, FR-5.9) --------------------------

with tab_faq:
    st.caption("Edits publish to the live assistant on republish — no engineering release.")

    faq_chunks = {chunk.meta["faq_id"]: chunk for chunk in chunks if chunk.source == "faq"}
    retired = {faq_id for faq_id, entry in overrides.items() if entry.get("retired")}
    options = ["+ New entry"] + sorted(faq_chunks, key=lambda x: int(x) if x.isdigit() else 0) + sorted(retired)
    choice = st.selectbox(
        "Entry",
        options,
        format_func=lambda x: x if x == "+ New entry"
        else (f"{x} · [retired]" if x in retired else f"{x} · {faq_chunks[x].title[:60]}"),
    )

    if choice == "+ New entry":
        existing_ids = [int(i) for i in list(faq_chunks) + list(retired) if i.isdigit()]
        new_id = str(max(existing_ids or [0]) + 1)
        with st.form("new_faq"):
            question = st.text_input("Question")
            answer = st.text_area("Answer", height=140)
            category = st.text_input("Category", value="general")
            if st.form_submit_button("Publish entry", icon=":material/add:", type="primary"):
                if question.strip() and answer.strip():
                    store.save_faq_override(
                        new_id, {"question": question, "answer": answer, "category": category}
                    )
                    ui.rebuild_index()
                    st.success(f"Published FAQ entry {new_id}.")
                    st.rerun()
                else:
                    st.error("Question and answer are both required.")
    else:
        is_retired = choice in retired
        current = overrides.get(choice, {})
        chunk = faq_chunks.get(choice)
        with st.form("edit_faq"):
            question = st.text_input("Question", value=current.get("question") or (chunk.title if chunk else ""))
            answer = st.text_area("Answer", value=current.get("answer") or (chunk.text if chunk else ""), height=160)
            category = st.text_input("Category", value=current.get("category") or (chunk.category if chunk else ""))
            buttons = st.container(horizontal=True)
            with buttons:
                save = st.form_submit_button("Publish edit", icon=":material/save:", type="primary")
                retire = st.form_submit_button(
                    "Restore" if is_retired else "Retire",
                    icon=":material/restore_from_trash:" if is_retired else ":material/delete:",
                )
                rollback = st.form_submit_button("Roll back to source", icon=":material/undo:")
        if save:
            store.save_faq_override(choice, {"question": question, "answer": answer, "category": category})
            ui.rebuild_index()
            st.rerun()
        if retire:
            entry = dict(current)
            entry.update({"question": question, "answer": answer, "category": category, "retired": not is_retired})
            store.save_faq_override(choice, entry)
            ui.rebuild_index()
            st.rerun()
        if rollback:
            store.delete_faq_override(choice)
            ui.rebuild_index()
            st.rerun()

    ui.kicker("Preview", ink=True)
    st.caption("Check what the retriever finds before customers do (FR-5.4).")
    probe = st.text_input("Test question", placeholder="How much is the EU roaming bundle?")
    if probe:
        from nova.retriever import HybridRetriever

        hits = HybridRetriever(chunks).search(probe, top_k=settings["top_k"], max_per_source=settings["max_per_source"])
        if not hits:
            st.warning("Nothing retrieved — the assistant would refuse this question.")
        for position, hit in enumerate(hits, start=1):
            with st.container(border=True):
                st.markdown(f"**S{position} · {hit.chunk.citation}**  ·  score {hit.score:.4f}")
                st.caption(hit.chunk.text[:400])

# --- content audit (FR-3.3, FR-3.4, FR-2.9, NFR-3.2) -------------------------

with tab_content:
    ui.kicker("Guide sections withheld from customers", ink=True)
    st.caption(
        "The technical guide is marked Internal Use Only. Every section is classified "
        "before it can reach a customer, and the classification is auditable (FR-3.3)."
    )
    if report.withheld_guide_sections:
        st.dataframe(
            [
                {"Section": item["id"], "Title": item["title"], "Why withheld": item["reason"]}
                for item in report.withheld_guide_sections
            ],
            hide_index=True,
            width="stretch",
        )
        release = st.selectbox(
            "Release a section to customers",
            ["—"] + [item["id"] for item in report.withheld_guide_sections],
        )
        if release != "—" and st.button("Release section", icon=":material/lock_open:"):
            settings.setdefault("guide_force_customer_safe", []).append(release)
            settings["guide_force_internal"] = [
                s for s in settings.get("guide_force_internal", []) if s != release
            ]
            store.save_settings(settings)
            ui.rebuild_index()
            st.rerun()
    else:
        st.info("No sections withheld.", icon=":material/check_circle:")

    published = [chunk for chunk in chunks if chunk.source == "guide"]
    if published:
        with st.expander(f"Guide sections published to customers ({len(published)})"):
            for chunk in published:
                st.markdown(f"**{chunk.id} · {chunk.title}**")
                st.caption(chunk.meta.get("classification", ""))
        withhold = st.selectbox("Withhold a published section", ["—"] + [c.id for c in published])
        if withhold != "—" and st.button("Withhold section", icon=":material/lock:"):
            settings.setdefault("guide_force_internal", []).append(withhold)
            settings["guide_force_customer_safe"] = [
                s for s in settings.get("guide_force_customer_safe", []) if s != withhold
            ]
            store.save_settings(settings)
            ui.rebuild_index()
            st.rerun()

    ui.kicker("Ticket corpus", ink=True)
    cols = st.container(horizontal=True)
    with cols:
        st.metric("Indexed", report.counts.get("ticket", 0), icon=":material/check_circle:", border=True)
        st.metric("Excluded (not resolved)", len(report.tickets_excluded_unresolved), icon=":material/block:", border=True)
        st.metric("Agent-only outcome", len(report.tickets_needing_agent), icon=":material/support_agent:", border=True)
    if report.tickets_excluded_unresolved:
        st.caption("Excluded by FR-2.9: " + ", ".join(report.tickets_excluded_unresolved))
    if report.tickets_needing_agent:
        st.caption(
            "Resolved only by internal action, so indexed as 'needs an agent' rather than as "
            "instructions (FR-3.4): " + ", ".join(report.tickets_needing_agent)
        )

# --- answer gate (FR-3.1, FR-3.8, FR-4.4) ------------------------------------

with tab_gate:
    st.caption("Tuning these changes the live assistant's behaviour immediately.")
    with st.form("gate"):
        confidence_threshold = st.slider(
            "Confidence threshold",
            0.0, 1.0, float(settings["confidence_threshold"]), 0.05,
            help="Below this, the assistant refuses and offers a handoff instead of answering.",
        )
        relevance_floor = st.slider(
            "Retrieval relevance floor",
            0.0, 1.0, float(settings["relevance_floor"]), 0.05,
            help="Below this, the assistant refuses without calling the answer model at all.",
        )
        sizes = st.container(horizontal=True)
        with sizes:
            top_k = st.number_input("Chunks in context", 1, 12, int(settings["top_k"]))
            max_per_source = st.number_input("Max per source", 1, 6, int(settings["max_per_source"]))
            max_words = st.number_input("Answer word cap", 50, 400, int(settings["max_answer_words"]), step=10)
        hours = st.container(horizontal=True)
        with hours:
            start = st.number_input("Live chat opens", 0, 23, int(settings["staffed_hours_start"]))
            end = st.number_input("Live chat closes", 1, 24, int(settings["staffed_hours_end"]))
        blocklist = st.text_area(
            "Block list — one term per line",
            value="\n".join(settings.get("blocklist", [])),
            help="Any question containing one of these is refused and routed to a human (FR-3.8).",
        )
        if st.form_submit_button("Save settings", icon=":material/save:", type="primary"):
            settings.update(
                {
                    "confidence_threshold": confidence_threshold,
                    "relevance_floor": relevance_floor,
                    "top_k": int(top_k),
                    "max_per_source": int(max_per_source),
                    "max_answer_words": int(max_words),
                    "staffed_hours_start": int(start),
                    "staffed_hours_end": int(end),
                    "blocklist": [line.strip() for line in blocklist.splitlines() if line.strip()],
                }
            )
            store.save_settings(settings)
            ui.rebuild_index()
            st.rerun()

    ui.kicker("Models", ink=True)
    st.markdown(
        f"- **Answers:** `{config.ANSWER_MODEL}` — grounding and refusal behaviour are the product\n"
        f"- **Query rewriting:** `{config.UTILITY_MODEL}` — cheap non-generative stage"
    )
