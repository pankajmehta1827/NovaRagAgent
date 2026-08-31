# Nova — NovaCell AI support assistant

Reference implementation of the v1 scope in [PRD.md](PRD.md): a grounded Tier-1
support assistant that answers from NovaCell's four verified knowledge sources
(plans catalog, FAQ, resolved tickets, and the technical guide), refuses when
it can't answer, and escalates cleanly to a human.

## Run it

```bash
uv venv && uv pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your `GROQ_API_KEY`, then:

```bash
.venv/Scripts/streamlit run streamlit_app.py
```

The app is the **NovaCell AI Support Console**, with two surfaces under one shell:
**Chat** (the customer surface — Nova itself) and **Support operations** (knowledge,
metrics, answer gate, kill switch).

Before any knowledge or rule change ships, run the offline regression suite —
it covers everything that doesn't need the API:

```bash
.venv/Scripts/python selfcheck.py
```

## Design

The UI is converted from the **Modernist** design system shipped with the
`NovaCell AI support console/` canvas (`_ds/modernist-*/styles.css`): Archivo at
weight 800, a warm off-white ground, a single vermilion accent, and zero corner
radius throughout. `.streamlit/config.toml` carries the tokens; `nova/ui.py`
carries the three patterns Streamlit has no native element for — the letter-spaced
uppercase kicker, the 2px structural rule, and the muted source footnote.

Two consequences worth knowing:

- **The system is mono** ("one accent voice"), so status tints come from the
  neutral ramps and vermilion is reserved for what needs attention. A calm
  "assistant is live" reads as ink; an offline assistant reads as accent.
- **The canvas ships no dark variant.** `[theme.dark]` is derived here from the
  same ramps rather than left to Streamlit's defaults.

## How a turn works

```
question
  ├─ guardrails.check ─────────── refuse (emergency, credentials)
  │                               escalate (human request, fraud, dispute, …)
  │                               deflect (account-specific → bounded deflection)
  ├─ llm.expand_query ─────────── gpt-oss-20b bridges symptom language
  ├─ retriever.search ─────────── BM25 + char-4-gram, RRF fused, per-source capped
  │      └─ below relevance floor → refuse without calling the answer model
  ├─ llm.stream_answer ────────── gpt-oss-120b, sources as untrusted data,
  │                               STATUS control line, [S#] citations
  ├─ confidence gate ──────────── retrieval strength + source agreement + citations
  └─ escalation ───────────────── reason code, transcript, cited sources, hours-aware
```

## Module map

| Module | Responsibility | PRD |
|---|---|---|
| `nova/ingest.py` | Load and chunk the four sources; produce the audit report | FR-2.1, FR-2.3, FR-2.9 |
| `nova/sanitise.py` | PII scrubbing, internal-action redaction, guide classification gate | NFR-3.2, FR-3.4, FR-3.5, FR-3.3 |
| `nova/retriever.py` | Hybrid lexical retrieval and absolute relevance scoring | FR-2.2, FR-2.4 |
| `nova/guardrails.py` | Pre-retrieval routing: refuse / escalate / deflect | 3.3, FR-3.6, FR-3.8, FR-4.1 |
| `nova/llm.py` | Query expansion and grounded answer generation | FR-2.5, FR-3.7, NFR-4.2 |
| `nova/conversation.py` | Turn orchestration and the confidence gate | FR-3.1, FR-3.2, FR-4.1 |
| `nova/escalation.py` | Handoff payload and hours-aware routing | FR-4.3, FR-4.4 |
| `nova/store.py` | Settings, FAQ overrides, turn logs, metrics, unanswered queue | FR-5.x, FR-6.2, FR-6.3 |
| `app_pages/chat.py` | Customer surface | §4.1, §4.6 |
| `app_pages/ops_console.py` | Support Ops surface | §4.5 |

## What the safety layers actually do to this corpus

Run `selfcheck.py` to see it, but concretely:

- **17 of 49 guide chunks are withheld from customers.** The PDF is marked
  *Internal Use Only*; the classifier withholds the SS7/Diameter vulnerability
  material, the billing-engine architecture, the agent-directed passages, and the
  "Step 7 — Escalate" internal procedure, while publishing the customer-safe
  troubleshooting steps around it. Chunking is paragraph-level precisely so the
  gate isn't all-or-nothing per section.
- **Ticket TK-020 is excluded entirely** — its status is `escalated`, not
  `resolved` (FR-2.9).
- **14 of 19 resolved tickets are indexed as agent-only outcomes.** Their fixes
  were internal (a faulty sector antenna, a billing sync delay, a backend session
  reset, a portal bug, a device whitelist, an RNC reconfiguration). Nova keeps the
  symptom and the safe cause, drops the internal detail, and does not hand the
  customer instructions they cannot perform. This is a finding about the corpus,
  not a bug: it is exactly the low-coverage risk flagged as R-4 in the PRD.
- **Goodwill credits and repair ETAs never reach a customer** (FR-3.5).
- **The plans catalog outranks every other source** (`SOURCE_TRUST["plans"] = 4`):
  it's the single structured, versioned source of truth for prices and
  allowances, so it wins any conflict with the FAQ, guide, or a ticket.

## Known gaps against the PRD

Deliberate, and worth stating rather than papering over:

- **Retrieval is lexical, not embedding-based.** The hybrid is BM25 plus character
  n-grams, with the LLM query rewrite carrying the semantic load. On a 90-chunk
  corpus this measurably works; at FAQ scale it should be replaced with a proper
  embedding index, which is what FR-2.2 assumes.
- **No re-ranker model.** Fusion plus the trust tilt stands in for FR-2.4's
  re-rank stage.
- **Persistence is flat files.** `runtime/*.jsonl` stands in for the analytics
  warehouse (FR-6.2) and the knowledge CMS (FR-5.1).
- **No live agent desktop.** `escalation.build_handoff` produces the payload
  FR-4.3 specifies; nothing consumes it yet.
- **The weekly human review sample (FR-6.4) and the adversarial refusal eval set
  (NFR-1.3) are not built.** `selfcheck.py` is the seed of FR-6.5, covering
  ingestion, sanitisation, classification, retrieval and guardrails.
