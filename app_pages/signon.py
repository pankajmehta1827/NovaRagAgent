"""Sign-on — the first screen, before the console.

Structure follows the reference: a centred card carrying a mark, the product
name, one line of what it does, and a single sign-in action. The styling follows
the Modernist system the rest of the console was converted to, rather than the
reference's dark indigo, so the first screen and the product behind it read as
one thing.
"""

import streamlit as st

from nova import auth, ui

# The card sits in the upper-middle of the viewport rather than dead centre —
# vertical centring in Streamlit means padding that shifts on every viewport.
st.container(height=40, border=False)

card = st.container(width=520, horizontal_alignment="center", border=True)
with card:
    ui.agent_mark()
    ui.kicker("NovaCell · Care")
    st.title("Nova TeleAgent", text_alignment="center")
    st.markdown(
        "Grounded answers from NovaCell's own documentation — the FAQ, the "
        "plans catalog, resolved tickets and the technical guide. Nothing invented.",
        text_alignment="center",
    )
    ui.rule()

    if auth.google_configured():
        ui.google_signin_button(
            "Continue with Google",
            key="google-signin",
            on_click=auth.sign_in_google,
        )
        st.caption(
            "Google handles the sign-in. NovaCell never sees your password.",
            text_alignment="center",
        )
    else:
        st.button(
            "Connect to Nova TeleAgent",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            on_click=auth.start_demo,
        )
        st.caption(
            "Demo entry — Google sign-in is not configured on this deployment, so "
            "this grants access without verifying who you are.",
            text_alignment="center",
        )

with st.container(width=520, horizontal_alignment="center"):
    ui.source_note(
        "Nova answers Tier-1 questions only. It cannot see your account, and it "
        "hands you to a person whenever you ask."
    )
