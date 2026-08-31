"""Sign-on — the first screen, before the console.

Converted from `NovaTeleAgent Login.html`: a full-bleed split, vermilion brand
panel on the left, sign-in column on the right, in the Modernist system the rest
of the console already uses.

Two deliberate departures from the reference, both because this page fronts a
real system rather than a prototype:

* The reference's stat row carries voice-platform marketing figures (1.4s median
  pickup, 38 languages, 99.98% uptime). None of those are true here, and this is
  the front door of a product whose whole promise is that it doesn't invent
  numbers — so the row states what is actually true of the index.
* The reference's email-and-password form is a mock: its own script pops
  "Signed in as …" after a 1.2s timer without checking anything. There is no user
  store behind this app, so a password box here could only ever be theatre.
  Google is the real path; where the form was, this offers the honest
  alternative — a labelled demo entry — and only when Google isn't configured.
"""

import streamlit as st

from nova import auth, ui

ui.login_chrome()

brand, form = st.columns([1.05, 1], gap="xxsmall", vertical_alignment="top")

with brand:
    ui.login_brand_panel(
        name="NovaTeleAgent",
        tagline="Grounded support platform",
        headline="Every answer traced to a document.",
        lede=(
            "Nova answers Tier-1 questions from NovaCell's own FAQ, plans catalog, "
            "resolved tickets and technical guide — and says so plainly when none "
            "of them can answer."
        ),
        stats=[
            ("4", "Knowledge sources"),
            ("100%", "Answers cited"),
            ("0", "Invented facts"),
        ],
    )

with form:
    with st.container(key="nc-signin"), st.container(width=392, horizontal_alignment="left"):
        st.html('<div class="nc-login-eyebrow">Agent console</div>')
        st.header("Sign in")
        st.caption("Use your work account to reach the support console.")

        if auth.google_configured():
            ui.google_signin_button(
                "Continue with Google",
                key="google-signin",
                on_click=auth.sign_in_google,
            )
            st.caption("Google handles the sign-in. NovaCell never sees your password.")
        else:
            ui.or_divider("no SSO configured")
            st.button(
                "Connect to NovaTeleAgent",
                icon=":material/arrow_forward:",
                type="primary",
                width="stretch",
                on_click=auth.start_demo,
            )
            st.caption(
                "Demo entry — Google sign-in is not configured on this deployment, "
                "so this grants access without verifying who you are."
            )

        st.html(
            '<div class="nc-login-assure">Nova answers Tier-1 questions only. It cannot '
            "see your account, and it hands you to a person whenever you ask.</div>"
        )
        st.html(
            '<div class="nc-login-foot">© 2026 NovaCell · Nova answers from published '
            "support material only.</div>"
        )
