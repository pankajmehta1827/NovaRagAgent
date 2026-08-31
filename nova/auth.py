"""Sign-on for the console.

Two paths, and the page is explicit about which one is in play:

* **Google** — Streamlit's native OIDC (``st.login`` / ``st.user`` / ``st.logout``),
  active as soon as ``[auth]`` and ``[auth.google]`` are present in
  ``.streamlit/secrets.toml``. Streamlit runs the whole OAuth exchange; this
  module never sees or stores a credential.
* **Demo** — a session-scoped entry used when Google is not configured, so the
  app still runs out of the box. It is labelled as a demo everywhere it appears
  and grants no privileges: it exists to gate the surface, not to secure it.

Nothing here is an authorisation boundary. The ops console is reachable by anyone
who gets past this page, which is fine for a reference implementation and is not
fine for production — see the note in README.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

PROVIDER = "google"


# A scaffolded secrets.toml ships with these in place of real values. Treating a
# placeholder as configuration would put a "Continue with Google" button on the
# page that can only ever fail, which is worse than honestly offering the demo.
_PLACEHOLDERS = (
    "your-client-id",
    "your-client-secret",
    "generate-a-long-random-string",
    "changeme",
    "",
)

_REQUIRED_AUTH = ("redirect_uri", "cookie_secret")
_REQUIRED_PROVIDER = ("client_id", "client_secret", "server_metadata_url")


def _looks_real(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and not any(text.startswith(p) for p in _PLACEHOLDERS if p)


def google_configured() -> bool:
    """True when secrets carry a complete, non-placeholder [auth.google] block.

    Every key ``st.login`` needs must be present and filled in. A partially
    filled file reports False so the page keeps offering the demo path rather
    than advertising a sign-in that would 500 on click.
    """
    try:
        auth = st.secrets.get("auth")
    except Exception:
        # No secrets.toml at all — st.secrets raises rather than returning empty.
        return False
    if not auth:
        return False
    try:
        if not all(_looks_real(auth.get(key)) for key in _REQUIRED_AUTH):
            return False
        provider = auth.get(PROVIDER)
        if not provider:
            return False
        return all(_looks_real(provider.get(key)) for key in _REQUIRED_PROVIDER)
    except Exception:
        return False


def _oidc_user() -> dict[str, Any] | None:
    try:
        if st.user.get("is_logged_in"):
            return dict(st.user)
    except Exception:
        pass
    return None


def current_user() -> dict[str, Any] | None:
    """The signed-in identity, or None. Shape is the same for both paths."""
    signed_in = _oidc_user()
    if signed_in:
        return {
            "name": signed_in.get("name") or signed_in.get("email") or "Signed in",
            "email": signed_in.get("email", ""),
            "mode": "google",
        }
    if st.session_state.get("demo_user"):
        return {"name": "Demo operator", "email": "", "mode": "demo"}
    return None


def is_signed_in() -> bool:
    return current_user() is not None


def sign_in_google() -> None:
    st.login(PROVIDER)


def start_demo() -> None:
    st.session_state.demo_user = True


def sign_out() -> None:
    user = current_user()
    st.session_state.pop("demo_user", None)
    if user and user["mode"] == "google":
        st.logout()
