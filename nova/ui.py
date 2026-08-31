"""Streamlit glue: cached resources and shared rendering helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re

import streamlit as st

from . import config, llm, store
from .conversation import NovaAgent


def resolve_api_key() -> str | None:
    """Env var, .env, or Streamlit secrets — never hard-coded (NFR-3.x)."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv

        load_dotenv(config.ROOT / ".env")
        key = os.environ.get("GROQ_API_KEY")
        if key:
            return key
    except ImportError:
        pass
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return None


def settings_signature(settings: dict, overrides: dict) -> str:
    """Changes to ops settings or FAQ content must rebuild the index (FR-5.9)."""
    blob = json.dumps([settings, overrides], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@st.cache_resource(show_spinner=False)
def _build_agent(signature: str, api_key: str) -> NovaAgent:
    settings = store.load_settings()
    overrides = store.load_faq_overrides()
    client = llm.get_client(api_key)
    return NovaAgent(client, settings, overrides)


def get_agent() -> tuple[NovaAgent | None, dict, str | None]:
    """Return ``(agent, settings, error)``. Never raises into the page."""
    settings = store.load_settings()
    overrides = store.load_faq_overrides()
    api_key = resolve_api_key()
    if not api_key:
        return None, settings, (
            "GROQ_API_KEY is not set. Copy `.env.example` to `.env` and add your key, "
            "then reload this page."
        )
    try:
        agent = _build_agent(settings_signature(settings, overrides), api_key)
    except Exception as error:
        return None, settings, f"Could not start the assistant: {error}"
    return agent, settings, None


@st.cache_resource(show_spinner=False)
def _build_index(signature: str):
    from .ingest import build_index

    return build_index(store.load_settings(), store.load_faq_overrides())


def get_index():
    """Chunks + audit report, for the ops console. Works without an API key."""
    settings = store.load_settings()
    overrides = store.load_faq_overrides()
    return _build_index(settings_signature(settings, overrides))


def rebuild_index() -> None:
    """Publish knowledge or config changes to the live assistant (FR-5.9)."""
    _build_agent.clear()
    _build_index.clear()


# --- design system ------------------------------------------------------------
# Three patterns from the NovaCell console canvas that Streamlit has no native
# element for: the letter-spaced uppercase kicker, the 2px structural rule, and
# the muted source footnote.
#
# Streamlit 1.62 declares no CSS custom properties — :root carries none of
# --primary-color/--text-color/--background-color — so `var(--primary-color, X)`
# resolves to X every time, in both themes. Anything that must follow the theme
# uses currentColor; anything that must follow the accent is written out for both
# grounds under prefers-color-scheme.

_DESIGN_CSS = """
<style>
  .nc-kicker {
    font-size: 10px; letter-spacing: .1em; text-transform: uppercase;
    font-weight: 800; color: #ec3013; margin: 0 0 2px;
  }
  .nc-kicker-ink { color: currentColor; opacity: .55; }
  .nc-rule { border: 0; border-top: 2px solid currentColor; opacity: .28; margin: 4px 0 12px; }
  .nc-source { font-size: 11px; opacity: .55; margin: 6px 0 0; }
  .nc-num { font-size: 11px; letter-spacing: .08em; font-weight: 800;
            color: #ec3013; margin-right: 8px; }
  @media (prefers-color-scheme: dark) {
    .nc-kicker:not(.nc-kicker-ink), .nc-num { color: #ff563c; }
  }
</style>
"""


def apply_design() -> None:
    """Load the console's design-system extras. Call once, from the shell."""
    st.html(_DESIGN_CSS)


# --- agent mark ----------------------------------------------------------------
# Nova's mark, not a stock photo: the "bot" glyph from Lucide, the same line-icon
# set chat.py already draws its avatars from, on a single vermilion square with
# the system's zero corner radius (the rect's rx is overridden to 0 for that
# reason — Lucide's own default rounds it).
#
# st.html runs its body through DOMPurify, which drops raw <svg>/<path>/<rect>
# tags from the DOM it hands back — a literal inline <svg> here renders as an
# empty box. Encoding the glyph as its own standalone SVG document and loading
# it as a CSS background-image (same technique as the Google "G" below) sails
# straight past that: DOMPurify only inspects the HTML tree, not image bytes.

_BOT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="#faf7f2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="0"/>'
    '<path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>'
    "</svg>"
)
_BOT_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_BOT_SVG.encode()).decode()


def agent_mark(size: int = 64) -> None:
    """The square badge that stands in for Nova wherever the product introduces
    itself — currently the sign-on card, beside the product name."""
    icon = round(size * 0.46)
    st.html(
        f'<div style="width:{size}px;height:{size}px;margin:0 auto 16px;'
        f"background:#ec3013 url('{_BOT_DATA_URI}') "
        f'no-repeat center / {icon}px {icon}px;'
        f'box-shadow:0 2px 6px rgba(0,0,0,.18);"></div>'
    )


# --- Google sign-in button -------------------------------------------------------
# Google's unaltered four-colour "G", on a button shaped by the Modernist system
# rather than by Google's rounded spec — the login reference makes that trade
# deliberately, and the mark is the part of their guidance carrying the identity.
# `key` gives Streamlit's `st-key-<key>` hook (stable since 1.36) something to
# target — it's the only way to skin a real st.button rather than fake one with
# raw HTML, which would need its own click wiring to reach st.login.

_GOOGLE_G_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18">'
    '<path fill="#4285F4" d="M17.64 9.2045c0-.6381-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436'
    'c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.615z"/>'
    '<path fill="#34A853" d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368.859'
    '-3.0477.859-2.344 0-4.3282-1.5831-5.036-3.7104H.9573v2.3318C2.4382 15.9832 5.4818 18 9 18z"/>'
    '<path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.2822-1.1168-.2822-1.71s.1023-1.17.2823-1.71V4.9582'
    'H.9573C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9573 4.0418L3.964 10.71z"/>'
    '<path fill="#EA4335" d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918'
    ' 11.4259 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1627 6.656 3.5795 9 3.5795z"/>'
    "</svg>"
)
_GOOGLE_G_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_GOOGLE_G_SVG.encode()).decode()


def google_signin_button(label: str, *, key: str, on_click, sso_hint: str = "SSO") -> None:
    """The reference's Google button: squared, ruled, with the SSO hint at the end.

    Google's own branding guidance asks for their rounded button; the login
    reference deliberately restyles it into the Modernist system — square, 2px
    ink border, Archivo — and keeps their unaltered four-colour "G", which is the
    part of the guidance that carries the identity. Following the reference here.
    """
    st.html(
        f"""
        <style>
          .st-key-{key} button {{
            background: transparent !important;
            border: 2px solid currentColor !important; border-radius: 0 !important;
            min-height: 48px; padding: 0 16px;
            display: flex !important; align-items: center !important;
            justify-content: flex-start !important; gap: 12px;
          }}
          .st-key-{key} button:hover {{
            background: rgba(128, 128, 128, .18) !important;
          }}
          .st-key-{key} button p {{
            font-family: Archivo, sans-serif !important;
            font-weight: 800 !important; font-size: 14px !important;
          }}
          .st-key-{key} button::before {{
            content: ""; width: 18px; height: 18px; flex: none;
            background: url('{_GOOGLE_G_DATA_URI}') no-repeat center / contain;
          }}
          .st-key-{key} button::after {{
            content: "{sso_hint}"; margin-left: auto;
            font-size: 11px; letter-spacing: .1em; font-weight: 500; opacity: .55;
          }}
        </style>
        """
    )
    st.button(label, key=key, width="stretch", on_click=on_click)


def kicker(text: str, ink: bool = False) -> None:
    """The system's uppercase accent label that sits above a heading."""
    css_class = "nc-kicker nc-kicker-ink" if ink else "nc-kicker"
    st.html(f'<div class="{css_class}">{text}</div>')


def rule() -> None:
    """The 2px structural divider the canvas uses instead of whitespace."""
    st.html('<hr class="nc-rule">')


def source_note(text: str) -> None:
    """The muted `Source: NovaCell doc ...` footnote from the answer screens."""
    st.html(f'<p class="nc-source">{text}</p>')


_UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")


def md(text: str) -> str:
    """Escape ``$`` so Streamlit's LaTeX handling doesn't eat currency amounts.

    A pair of dollar signs in one message renders as maths and the prices vanish
    — unacceptable for a product whose core promise is reproducing prices
    verbatim (FR-2.5).
    """
    return _UNESCAPED_DOLLAR.sub(r"\\$", text or "")


def render_sources(turn_sink: dict, hits: list) -> None:
    """Source attribution on every answer (FR-2.6).

    The canvas states the rule plainly: "Every answer screen cites the NovaCell
    document it came from." So the citation line is always visible under the
    answer, and the expander carries the full excerpts for anyone who wants them.
    """
    source_index = turn_sink.get("source_index") or {}
    cited = turn_sink.get("cited") or []
    shown = [(marker, source_index[marker]) for marker in cited if marker in source_index]
    if not shown:
        shown = [(f"S{i}", hit.chunk) for i, hit in enumerate(hits[:3], start=1)]
    if not shown:
        return

    seen: list[str] = []
    for _, chunk in shown:
        if chunk.citation not in seen:
            seen.append(chunk.citation)
    source_note("Source: " + " · ".join(seen))

    with st.expander(f"Read the source ({len(shown)})", icon=":material/find_in_page:"):
        for marker, chunk in shown:
            kicker(f"{marker} · {chunk.citation}")
            excerpt = chunk.text if len(chunk.text) <= 700 else chunk.text[:700] + "…"
            st.caption(md(excerpt))


def render_handoff(handoff: dict) -> None:
    """What the agent desktop receives (FR-4.3).

    The canvas's escalation screen frames this as "Attached to your chat" — a
    reassurance to the customer that they won't be asked to start over — rather
    than as a debug payload. Same data, read the way they'd read it.
    """
    with st.expander("Attached to your chat", icon=":material/support_agent:"):
        rows = [
            ("Your conversation", f"{len(handoff['transcript'])} messages"),
            ("Why you're being passed on", handoff["reason"]),
            ("Where it's going", "A live agent" if handoff["routing"] == "live_agent_queue" else "A support ticket"),
        ]
        if handoff["ticket_ref"]:
            rows.append(("Your reference", handoff["ticket_ref"]))
        if handoff["cited_sources"]:
            rows.append(("What you were shown", " · ".join(handoff["cited_sources"])))

        for label, value in rows:
            row = st.container(horizontal=True, vertical_alignment="center")
            with row:
                st.caption(label, width="stretch")
                st.markdown(md(f"**{value}**"), width="content")
        source_note(f"Handoff {handoff['handoff_id']}")


# --- login screen ----------------------------------------------------------------
# Converted from "NovaTeleAgent Login.html" — the split layout with a vermilion
# brand panel on the left and the sign-in column on the right.
#
# The mark is the reference's own: a dark square, an "N" letterform, and a
# vermilion dot at the corner. Encoded as a standalone SVG document and loaded as
# a CSS background for the same reason as the bot glyph above — st.html runs its
# body through DOMPurify, which strips raw <svg>/<path> from the returned tree.

_NOVA_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<rect x="1" y="1" width="46" height="46" fill="#201e1d"/>'
    '<path d="M11 37V11h5.6l14.8 17.2V11H37v26h-5.6L16.6 19.8V37H11z" fill="#f3f2f2"/>'
    '<circle cx="37.5" cy="10.5" r="4.5" fill="#ec3013"/>'
    "</svg>"
)
_NOVA_MARK_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(_NOVA_MARK_SVG.encode()).decode()

_ACCENT = "#ec3013"
_ON_ACCENT = "#f3f2f2"

# The reference bleeds its brand panel to the viewport edge. Streamlit's centred
# layout caps and pads the block container, so the login screen lifts both — and
# only the login screen, because the console pages want that reading width back.
_LOGIN_CHROME = """
<style>
  .stMainBlockContainer { max-width: 100% !important; padding: 0 !important; }
  .stAppHeader { background: transparent !important; }
  [data-testid="stSidebarCollapsedControl"] { display: none; }
  .nc-login-brand {
    position: relative; min-height: 100vh; background: __ACCENT__; color: __ON_ACCENT__;
    padding: 40px 48px; display: flex; flex-direction: column; gap: 40px; overflow: hidden;
  }
  .nc-login-brand::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image:
      linear-gradient(to right, rgba(243,242,242,.16) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(243,242,242,.16) 1px, transparent 1px);
    background-size: 96px 96px;
  }
  .nc-login-brand > * { position: relative; }
  .nc-login-id { display: flex; align-items: center; gap: 14px; }
  .nc-login-mark {
    width: 46px; height: 46px; flex: none;
    background: url('__MARK__') no-repeat center / contain;
  }
  .nc-login-name {
    font-family: Archivo, sans-serif; font-weight: 800; font-size: 19px;
    letter-spacing: -0.02em; line-height: 1;
  }
  .nc-login-tag {
    font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
    opacity: .8; margin-top: 4px;
  }
  .nc-login-lede { margin-top: auto; display: flex; flex-direction: column; gap: 24px; }
  .nc-login-lede h1 {
    font-family: Archivo, sans-serif; font-weight: 800;
    font-size: clamp(34px, 3.4vw, 58px); line-height: 1.02; letter-spacing: -0.03em;
    margin: 0; max-width: 13ch;
  }
  .nc-login-lede p { margin: 0; max-width: 40ch; font-size: 16px; line-height: 1.6; opacity: .92; }
  .nc-login-stats {
    border-top: 2px solid rgba(243,242,242,.5); padding-top: 20px;
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;
  }
  .nc-stat-n { font-family: Archivo, sans-serif; font-weight: 800; font-size: 26px; line-height: 1; }
  .nc-stat-l {
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    opacity: .8; margin-top: 6px;
  }
  /* The sign-in column: padded back in (the block container's own padding was
     stripped for the full bleed) and centred against the brand panel's height. */
  .st-key-nc-signin {
    min-height: 100vh; padding: 28px 48px 32px;
    display: flex; flex-direction: column; justify-content: center;
  }
  .nc-login-eyebrow {
    font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
    color: __ACCENT__; margin-bottom: 10px;
  }
  .nc-or { display: flex; align-items: center; gap: 14px; margin: 20px 0 16px; }
  .nc-or span:first-child, .nc-or span:last-child {
    flex: 1; height: 2px; background: currentColor; opacity: .28;
  }
  .nc-or em {
    font-style: normal; font-size: 11px; letter-spacing: 0.14em;
    text-transform: uppercase; opacity: .55;
  }
  .nc-login-assure {
    margin-top: 24px; border-top: 2px solid currentColor; padding-top: 14px;
    font-size: 12px; opacity: .6;
  }
  .nc-login-foot { margin-top: 20px; font-size: 12px; opacity: .55; }
  @media (max-width: 900px) { .nc-login-brand { min-height: auto; padding: 32px 24px; } }
</style>
"""
_LOGIN_CHROME = (
    _LOGIN_CHROME.replace("__ACCENT__", _ACCENT)
    .replace("__ON_ACCENT__", _ON_ACCENT)
    .replace("__MARK__", _NOVA_MARK_DATA_URI)
)


def login_chrome() -> None:
    """Full-bleed page chrome, for the sign-on screen only."""
    st.html(_LOGIN_CHROME)


def login_brand_panel(name: str, tagline: str, headline: str, lede: str, stats: list[tuple[str, str]]) -> None:
    """The vermilion half of the login split.

    ``stats`` is a list of ``(value, label)``. The reference filled this row with
    voice-platform marketing figures; whatever goes here must be true of the
    product, since this is the page that introduces a system whose entire promise
    is that it does not invent numbers.
    """
    cells = "".join(
        f'<div><div class="nc-stat-n">{value}</div><div class="nc-stat-l">{label}</div></div>'
        for value, label in stats
    )
    st.html(
        f"""
        <div class="nc-login-brand">
          <div class="nc-login-id">
            <div class="nc-login-mark"></div>
            <div>
              <div class="nc-login-name">{name}</div>
              <div class="nc-login-tag">{tagline}</div>
            </div>
          </div>
          <div class="nc-login-lede">
            <h1>{headline}</h1>
            <p>{lede}</p>
          </div>
          <div class="nc-login-stats">{cells}</div>
        </div>
        """
    )


def or_divider(label: str = "or") -> None:
    st.html(f'<div class="nc-or"><span></span><em>{label}</em><span></span></div>')
