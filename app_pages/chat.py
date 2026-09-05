"""Customer-facing chat surface (PRD §4.1, §4.4, §4.6)."""

import streamlit as st

from nova import escalation, refund, store, ui
from nova.ui import md

# Line icons rather than Streamlit's filled default avatars: the design system's
# icon foundation is Lucide — inline strokes on currentColor, not colour blobs.
AVATARS = {"user": ":material/person:", "assistant": ":material/smart_toy:"}

settings = store.load_settings()

# FR-4.7 — global kill switch. Fail over to the existing contact paths.
if settings.get("kill_switch"):
    st.header("NovaCell support")
    st.warning(
        "Our support assistant is temporarily unavailable.",
        icon=":material/pause_circle:",
    )
    st.markdown(
        "- Call **611** from your NovaCell mobile\n"
        "- Use live chat in the **MyTelecom app** under Help\n"
        "- Check the coverage map at telecom.example.com/coverage"
    )
    st.stop()

agent, settings, error = ui.get_agent()
if error:
    st.header("NovaCell support")
    st.error(error, icon=":material/key_off:")
    st.stop()

session_id = st.session_state.session_id

# Agent PRD §6.2 — one refund conversation per session, over a ledger copied from
# the hard-coded seed. Per-session rather than module-level so a demonstration can
# be run twice, and so one browser's refund never mutates another's account.
if "refund_flow" not in st.session_state:
    st.session_state.refund_flow = refund.RefundFlow(refund.new_ledger())
flow = st.session_state.refund_flow


# --- helpers -----------------------------------------------------------------


def record_feedback(turn_id: str, widget_key: str) -> None:
    """FR-6.1 — thumbs feedback on every answer; a thumbs-down offers a handoff."""
    value = st.session_state.get(widget_key)
    if value is None:
        return
    rating = "up" if value == 1 else "down"
    store.log_feedback({"turn_id": turn_id, "session_id": session_id, "rating": rating})
    if rating == "down":
        st.session_state.offer_escalation_for = turn_id


def do_escalate(reason_code: str, turn=None) -> None:
    """FR-4.2 — an explicit request for a human is never blocked or delayed."""
    history = st.session_state.history
    cited_sources: list[str] = []
    hits: list = []
    if turn is not None:
        source_index = turn.sink.get("source_index", {})
        cited_sources = [source_index[m].citation for m in turn.sink.get("cited", []) if m in source_index]
        hits = turn.hits
    if not cited_sources:
        for message in reversed(st.session_state.messages):
            if message.get("hits"):
                hits = message["hits"]
                break
        cited_sources = [hit.chunk.citation for hit in hits[:3]]

    handoff = escalation.build_handoff(
        reason_code=reason_code,
        history=history,
        cited_sources=cited_sources,
        category=hits[0].chunk.category if hits else "",
        settings=settings,
        session_id=session_id,
    )
    store.log_escalation(handoff)
    st.session_state.handoff = handoff
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": escalation.customer_message(handoff, settings),
            "handoff": handoff,
        }
    )
    st.session_state.offer_escalation_for = None


def render_assistant_extras(message: dict) -> None:
    # Make the product's core promise legible at a glance. "Grounded in verified
    # sources, or it says so" is the whole proposition (FR-2.6, FR-3.2); a
    # customer shouldn't have to open the sources panel to know which they got.
    status = message.get("status")
    if status == "ANSWERED" and (message.get("sink") or {}).get("cited"):
        st.badge("Verified sources", icon=":material/verified:", color="green")
    elif status in {"NO_VERIFIED_ANSWER", "ERROR"}:
        st.badge("No verified answer", icon=":material/help_outline:", color="orange")

    if message.get("refund_steps"):
        # §12 — the workflow steps, not the model's reasoning.
        with st.expander("Refund workflow", icon=":material/account_tree:"):
            st.code("\n".join(message["refund_steps"]), language="text")

    if message.get("deflection"):
        st.info(message["deflection"], icon=":material/account_circle:")
    if message.get("hits") is not None and message.get("sink") is not None:
        ui.render_sources(message["sink"], message["hits"])
    if message.get("handoff"):
        ui.render_handoff(message["handoff"])
    turn_id = message.get("turn_id")
    if turn_id and not message.get("handoff"):
        widget_key = f"feedback-{turn_id}"
        st.feedback(
            "thumbs",
            key=widget_key,
            on_change=record_feedback,
            args=(turn_id, widget_key),
        )


def _record_refund(user_text: str, reply: str, steps: list[str]) -> None:
    """Append a button-driven refund exchange as if it had been typed."""
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "status": "REFUND", "refund_steps": steps}
    )
    st.session_state.history.append({"role": "user", "content": user_text})
    st.session_state.history.append({"role": "assistant", "content": reply})
    store.log_turn(
        {
            "turn_id": f"refund-{len(st.session_state.messages)}",
            "session_id": session_id,
            "question": user_text,
            "status": "REFUND",
            "intent": "refund_request",
            "refund_state": flow.state,
            "refund_steps": steps,
            "escalated": False,
        }
    )


def confirm_refund() -> None:
    """FR-32 — the only path to execution, and only from the confirmation state."""
    before = len(flow.log)
    reply, _ = flow.confirm()
    _record_refund("Yes, proceed.", reply, flow.log[before:])


def cancel_refund() -> None:
    """FR-36d — declining executes nothing."""
    before = len(flow.log)
    reply, _ = flow.cancel()
    _record_refund("No, cancel it.", reply, flow.log[before:])


def clear_conversation() -> None:
    """FR-48 / §11 — reset the transcript and any refund waiting on the customer."""
    st.session_state.messages = []
    st.session_state.history = []
    st.session_state.consecutive_ungrounded = 0
    st.session_state.handoff = None
    st.session_state.offer_escalation_for = None
    st.session_state.refund_flow = refund.RefundFlow(refund.new_ledger())


def use_sample(question: str) -> None:
    st.session_state.pending_prompt = question


# --- sample questions (left panel) -------------------------------------------
# The starter pills on the empty canvas disappear once a conversation begins.
# These stay available for the whole session, grouped by the Tier-1 themes in
# PRD §2.4, so a customer mid-conversation can still find a way in.

SAMPLE_QUESTIONS: dict[str, list[str]] = {
    "Data and speed": [
        "Why is my mobile internet so slow?",
        "How do I check my data balance?",
        "Why is my hotspot not working?",
    ],
    "SIM and eSIM": [
        "How long does SIM activation take?",
        "How do I replace a lost or stolen SIM?",
        "Can I keep my number if I switch to NovaCell?",
    ],
    "Roaming": [
        "What are the roaming charges in the EU?",
        "How do I activate international roaming?",
        "I have no service abroad — what should I do?",
    ],
    "Billing": [
        "When is my bill due?",
        "Why is my bill higher than usual?",
        "How do I set up autopay?",
    ],
    "Calls": [
        "My calls keep dropping — what should I do?",
        "How do I enable Wi-Fi calling?",
        "Why can't I make international calls?",
    ],
    "Account and app": [
        "How do I get an itemised bill?",
        "How do I unlock my phone for another network?",
        "How do I report a network outage?",
    ],
}

# What Nova deliberately will not do. Worth surfacing: the boundary is a feature,
# and these are the paths reviewers most need to see working.
BOUNDARY_QUESTIONS = [
    ("What is my current data balance?", "Needs live account data"),
    ("Someone changed my plan without my permission", "Routed straight to a human"),
    ("What is NovaCell's share price?", "Nothing verified to answer from"),
]

with st.sidebar:
    st.button(
        "Clear conversation",
        icon=":material/restart_alt:",
        width="stretch",
        on_click=clear_conversation,
        help="Resets the transcript, any refund waiting on you, and the demo ledger.",
    )

    ui.kicker("Sample questions")
    st.caption("Tap one to ask it.")
    for topic, questions in SAMPLE_QUESTIONS.items():
        with st.expander(topic):
            for question in questions:
                st.button(
                    question,
                    key=f"sample-{question}",
                    width="stretch",
                    on_click=use_sample,
                    args=(question,),
                )

    ui.kicker("Where Nova stops")
    st.caption("These don't get an answer — by design.")
    for question, why in BOUNDARY_QUESTIONS:
        st.button(
            question,
            key=f"boundary-{question}",
            width="stretch",
            help=why,
            on_click=use_sample,
            args=(question,),
        )


# --- header ------------------------------------------------------------------

ui.kicker("Help")
title_row = st.container(horizontal=True, vertical_alignment="center")
with title_row:
    # The canvas opens the customer flow with the question, not the brand.
    st.header("What's going on with your line?", width="stretch")
    # FR-4.2 — the route to a human is visible from the first frame, not earned.
    if st.session_state.handoff is None:
        st.button(
            "Talk to a person",
            icon=":material/support_agent:",
            width="content",
            on_click=do_escalate,
            args=("CUSTOMER_REQUESTED_HUMAN",),
        )

# NFR-3.8 — AI disclosure at conversation start, stated plainly rather than
# buried. The caption sits under the title on its own line so it reads as a
# sentence instead of competing with the button for the same row.
st.caption(
    "You're chatting with Nova, an AI assistant. It answers only from NovaCell's published "
    "support material, and it can't see your account."
)

# --- history -----------------------------------------------------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=AVATARS[message["role"]]):
        st.markdown(md(message["content"]))
        if message["role"] == "assistant":
            render_assistant_extras(message)

# --- starter prompts (FR-1.5) ------------------------------------------------

# Square buttons rather than st.pills: the design system sets every radius to 0,
# and a pill is round by definition — no theme token can square it.
SUGGESTIONS = [
    (":material/signal_cellular_alt:", "My data is slow", "My mobile data has been really slow since yesterday"),
    (":material/sim_card:", "SIM won't activate", "My new SIM still isn't active after an hour"),
    (":material/flight:", "Going abroad", "I'm travelling to the EU next week — what do I need to set up?"),
    (":material/receipt_long:", "Bill looks high", "Why is my bill higher than usual?"),
]

if not st.session_state.messages:
    ui.kicker("Most asked this week", ink=True)
    starters = st.container(horizontal=True, wrap=True)
    with starters:
        for icon, label, question in SUGGESTIONS:
            st.button(
                label,
                icon=icon,
                key=f"starter-{label}",
                on_click=use_sample,
                args=(question,),
            )

# --- refund confirmation (Agent PRD §11, FR-36) ------------------------------
# Rendered from the flow's own state rather than from the last turn, so the
# buttons survive a rerun and stay in step with what the agent is actually
# waiting for. Typing "yes" or "no" works too — this is the same gate either way.

if flow.state == refund.AWAITING_CONFIRMATION:
    with st.container(border=True):
        st.markdown(
            md(f"**Refund eligible: {refund.CURRENCY}{flow.amount}** — recharge {flow.recharge_id}")
        )
        st.caption("Nothing is refunded until you confirm.")
        buttons = st.container(horizontal=True)
        with buttons:
            st.button(
                "Confirm refund",
                icon=":material/check:",
                type="primary",
                on_click=confirm_refund,
            )
            st.button("Cancel", icon=":material/close:", on_click=cancel_refund)

# --- escalation offer from a thumbs-down (FR-6.1) ----------------------------

if st.session_state.get("offer_escalation_for") and st.session_state.handoff is None:
    st.button(
        "Pass me to a support agent",
        icon=":material/support_agent:",
        type="primary",
        on_click=do_escalate,
        args=("LOW_CONFIDENCE",),
    )

# --- input -------------------------------------------------------------------

typed = st.chat_input("Ask about your NovaCell service", submit_mode="disable")
# A sidebar sample was clicked: its callback ran before this script, so the
# question is waiting in session state. Pop it so it fires exactly once.
prompt = typed or st.session_state.pop("pending_prompt", None)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(md(prompt))

    history = list(st.session_state.history)

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        turn = agent.begin_turn(prompt, history, flow)

        if turn.escalated:
            handoff = agent.escalate(turn, history + [{"role": "user", "content": prompt}], session_id)
            answer = escalation.customer_message(handoff, settings)
            st.markdown(md(answer))
            ui.render_handoff(handoff)
            st.session_state.handoff = handoff
            record = {"role": "assistant", "content": answer, "handoff": handoff}
        elif turn.mode == "fixed":
            answer = turn.fixed_text
            st.markdown(md(answer))
            record = {"role": "assistant", "content": answer}
        else:
            answer = st.write_stream(agent.stream(turn, history))
            record = {"role": "assistant", "content": answer}

        agent.finish_turn(turn, st.session_state.consecutive_ungrounded)

        if turn.sink.get("display"):
            # Citation markers normalised after streaming; the rerun below
            # re-renders this message from the record, so the customer sees the
            # tidied form.
            record["content"] = turn.sink["display"]

        if not turn.escalated:
            if turn.sink.get("status") == "ERROR" and turn.fixed_text:
                answer = turn.fixed_text
                st.markdown(md(answer))
                record["content"] = answer
            if turn.deflection_note:
                st.info(turn.deflection_note, icon=":material/account_circle:")
                record["deflection"] = turn.deflection_note
            if turn.hits:
                ui.render_sources(turn.sink, turn.hits)
                record["hits"] = turn.hits
                record["sink"] = turn.sink
            record["turn_id"] = turn.turn_id
            record["status"] = turn.sink.get("status")
            if turn.refund_log:
                record["refund_steps"] = turn.refund_log

        st.session_state.consecutive_ungrounded = (
            st.session_state.consecutive_ungrounded + 1 if turn.escalation_offer else 0
        )

        # FR-4.1(b) — the second consecutive ungrounded turn escalates rather than
        # asking the customer to try again.
        if turn.escalation_offer and turn.escalated and turn.handoff is None:
            handoff = agent.escalate(turn, history + [{"role": "user", "content": prompt}], session_id)
            follow_up = escalation.customer_message(handoff, settings)
            st.markdown(md(follow_up))
            ui.render_handoff(handoff)
            st.session_state.handoff = handoff
            record["content"] = f"{record['content']}\n\n{follow_up}"
            record["handoff"] = handoff
        elif turn.escalation_offer:
            st.session_state.offer_escalation_for = turn.turn_id

    agent.log(turn, session_id)
    st.session_state.messages.append(record)
    st.session_state.history.append({"role": "user", "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": record["content"]})
    st.rerun()
