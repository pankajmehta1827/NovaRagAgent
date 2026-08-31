"""Streamlit glue: cached resources and shared rendering helpers."""

from __future__ import annotations

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
# the muted source footnote. Colours come from currentColor and the theme's
# primary so both light and dark variants follow config.toml rather than being
# hard-coded here.

_DESIGN_CSS = """
<style>
  .nc-kicker {
    font-size: 10px; letter-spacing: .1em; text-transform: uppercase;
    font-weight: 800; color: var(--primary-color, #ec3013);
    margin: 0 0 2px;
  }
  .nc-kicker-ink { color: currentColor; opacity: .55; }
  .nc-rule { border: 0; border-top: 2px solid currentColor; opacity: .28; margin: 4px 0 12px; }
  .nc-source { font-size: 11px; opacity: .55; margin: 6px 0 0; }
  .nc-num { font-size: 11px; letter-spacing: .08em; font-weight: 800;
            color: var(--primary-color, #ec3013); margin-right: 8px; }
</style>
"""


def apply_design() -> None:
    """Load the console's design-system extras. Call once, from the shell."""
    st.html(_DESIGN_CSS)


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
