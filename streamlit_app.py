"""NovaCell AI Support Console.

Entry point and console shell. Chat is the customer surface; Support Ops is the
knowledge and quality surface described in PRD §4.5. The shell carries the shared
identity so the two pages read as one product rather than two apps.
"""

import streamlit as st

# Centered: the customer surface is a conversation, and Streamlit's centered
# column is the right reading width for one. The ops console lives with it —
# its tables scroll rather than the chat becoming unreadable.
st.set_page_config(
    page_title="NovaCell AI Support Console",
    page_icon=":material/cell_tower:",
    layout="centered",
)

if "session_id" not in st.session_state:
    import uuid

    st.session_state.session_id = uuid.uuid4().hex[:12]
    st.session_state.messages = []
    st.session_state.history = []
    st.session_state.consecutive_ungrounded = 0
    st.session_state.handoff = None
    st.session_state.offer_escalation_for = None
    st.session_state.pending_prompt = None

page = st.navigation(
    [
        st.Page("app_pages/chat.py", title="Chat", icon=":material/forum:", default=True),
        st.Page("app_pages/ops_console.py", title="Support Ops", icon=":material/tune:"),
    ],
    position="top",
)

# --- console shell -----------------------------------------------------------
# The canvas opens every artboard with an accent kicker over a heavy rule rather
# than a logo bar, so the shell follows that: kicker, rule, page. It establishes
# the product and gets out of the way — the customer's chat still opens with its
# own question, not with a console.

from nova import ui  # noqa: E402  — after set_page_config, which must run first

ui.apply_design()

shell = st.container(horizontal=True, vertical_alignment="center")
with shell:
    with st.container(width="stretch"):
        ui.kicker("NovaCell · Care · AI Support Console")
    with st.container(width="content"):
        ui.kicker("v1", ink=True)
ui.rule()

page.run()
