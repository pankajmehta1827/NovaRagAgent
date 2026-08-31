# PRD — NovaCell AI Support Assistant ("Nova")

| Field | Value |
|---|---|
| Product | Nova — AI self-serve support assistant for NovaCell mobile customers |
| Version | v1.0 (draft for review) |
| Date | 30 August 2026 |
| Status | Draft — pending sign-off from Support Ops, Legal/Privacy, Network Ops, Engineering |
| Reviewers | VP Customer Care, Head of Support Ops, Data Protection Officer, Head of Digital |

---

## 1. Problem & Objective

### 1.1 Problem

NovaCell serves ~4M subscribers. Customer support is one of the company's largest operating costs and its lowest-scoring customer touchpoint. The dominant failure is not that answers don't exist — it's that they are **unreachable at the moment of need**.

Three specific breakdowns:

1. **Knowledge is fragmented across three disconnected surfaces.** A public FAQ (customer-facing, shallow), a database of resolved tickets (agent-facing, rich but unstructured and full of internal remediation detail), and official PDF guides (deep technical reference, not written for customers). No surface lets a customer ask one plain-language question and get an answer synthesised from all three.
2. **Tier-1 volume crowds out real work.** The recurring themes — slow/dropped data, unexpected charges, SIM/eSIM activation, roaming setup, voice quality, basic account and app questions — are almost entirely self-resolvable from documentation NovaCell already owns. Customers queue for them anyway; agents burn out repeating them.
3. **Answers are inconsistent.** The same question resolved by three agents, or by FAQ vs. a store visit, produces three different answers. This drives repeat contacts and erodes trust in anything NovaCell says about price and policy.

### 1.2 Objective

Ship a conversational assistant that answers Tier‑1 customer questions in plain language, **grounded exclusively in NovaCell's verified knowledge**, that says "I don't know" rather than guessing, and that hands off cleanly to a human when it should.

**One-line objective:** Make NovaCell's existing, verified knowledge answerable in one conversation — accurately, instantly, and consistently — so customers stop waiting on hold for answers NovaCell already wrote down.

### 1.3 Why now

- The knowledge exists and is already digitised (FAQ, a resolved-ticket corpus growing daily, versioned PDF guides). The blocker was retrieval and synthesis, not content.
- Retrieval-augmented generation with citation-grounded answering is a production-safe pattern, and answer grounding is verifiable and measurable — which makes the "never invent a price" constraint enforceable rather than aspirational.
- Support cost per contact is rising while CSAT falls; the gap widens every quarter we don't act.

### 1.4 Non-goals

Nova is **not** a replacement for the contact centre, not a sales/upsell channel, not an account-servicing tool, and not a general-purpose chatbot. It is a knowledge-answering surface with a well-defined escalation door.

---

## 2. Target Users & Key Use Cases

### 2.1 Primary user — the self-serve subscriber

A NovaCell customer with a Tier‑1 problem, usually on a phone, often mid-frustration, sometimes on a degraded connection (which is frequently the problem itself). They want an answer in under a minute; they do not want to read a 40-page PDF or navigate an FAQ taxonomy. They describe problems in symptoms ("my internet is dead", "why did you charge me $47"), not in NovaCell's category names.

**Success for them:** a correct, specific, actionable answer in two turns or fewer — or an honest, fast handoff.

### 2.2 Secondary user — the Tier‑1 support agent

Handles the escalations Nova can't. Their win is (a) fewer trivial contacts and (b) escalations that arrive with the conversation, the customer's stated symptoms, and the sources Nova already showed them — so they don't restart from zero.

**Success for them:** a warm handoff with context, and a measurable drop in repetitive contacts.

### 2.3 Secondary user — Support Ops / Knowledge Manager

Owns content accuracy. Must be able to correct a wrong answer, add a new FAQ, or retire a stale price **the same day, without an engineering release**. Also the primary consumer of "what did customers ask that we couldn't answer" — the most valuable output of the system after the answers themselves.

**Success for them:** publish-to-live in under 30 minutes, self-service, with rollback.

### 2.4 Key use cases (v1)

Grounded in the three sources' actual coverage:

| # | Use case | Example question | Primary source |
|---|---|---|---|
| UC‑1 | Slow / no mobile data | "My internet is really slow since yesterday" | FAQ + guide troubleshooting steps + resolved tickets (APN reset, throttling after cap) |
| UC‑2 | Unexpected bill charges — *explaining the general cause* | "Why is my bill higher than usual?" | FAQ (billing) + tickets (roaming charges, premium SMS, mid-cycle add-ons) |
| UC‑3 | SIM / eSIM activation | "My new SIM still isn't active after an hour" | FAQ (activation timing) + tickets (eSIM activation failures) |
| UC‑4 | Roaming setup before travel | "I'm going to the EU next week, what do I do?" | FAQ (roaming bundles, activation lead time) + tickets (no service abroad) |
| UC‑5 | Voice call issues | "My calls keep dropping" / "there's an echo" | FAQ (voice) + guide (signal dBm thresholds, VoLTE) + tickets |
| UC‑6 | Account & app basics | "How do I get an itemised bill?" / "I can't log in to the app" | FAQ (billing/account) + tickets |
| UC‑7 | Policy & pricing lookup | "What does the EU roaming bundle cost?" | FAQ (verbatim, with citation) |
| UC‑8 | **Honest refusal + handoff** | "What's my current balance?" / "I think someone changed my plan" | *No source can answer* → boundary response or escalation |

UC‑8 is a first-class use case, not an error path. It is the requirement that makes the other seven trustworthy.

### 2.5 Explicit anti-persona

Customers with account-specific, financial-dispute, fraud, or retention needs. Nova must recognise these fast and route them out — it must not attempt to serve them.

---

## 3. Scope

### 3.1 In scope for v1

**Channel**
- Web chat widget on the NovaCell support site, and the same assistant embedded in the MyTelecom app help section (shared backend, shared conversation contract).
- Anonymous / unauthenticated by default. Logged-in users get the same answers — v1 does not personalise.

**Capability**
- Multi-turn conversation with context carried across turns within a session.
- Retrieval across all three sources in a single query, with source attribution shown to the customer.
- Plain-language synthesis of retrieved content (rewriting technical guide language into customer language) with no factual addition.
- Explicit "I can't answer that confidently" behaviour.
- Escalation to human chat (during staffed hours) or ticket creation (outside them).
- Support Ops knowledge console: add/edit/retire content, re-index, preview, publish, roll back — no code deploy.
- Feedback capture (thumbs up/down + optional free text) on every answer.
- Analytics: containment, escalation reasons, unanswered-question queue, per-source citation coverage.
- English only.

**Knowledge sources**
- **Source A — FAQ** (structured: id, question, answer, category). Customer-facing, authoritative for pricing and policy statements. Highest trust weight.
- **Source B — Resolved tickets** (category, issue_type, description, resolution, status). Indexed **only where `status = 'resolved'`**, and only after PII scrubbing and internal-action redaction (§5.3). Used for "what actually fixed this" patterns.
- **Source C — Official PDF guides** (versioned technical reference, currently v3.2). Indexed section-wise. Currently marked *Internal Use Only* — see the mandatory content-classification gate in FR‑3.3 and Risk R‑2.

### 3.2 Explicitly out of scope for v1

| Out of scope | Rationale |
|---|---|
| **Live billing / CRM / network-status integration** | Fixed constraint. No "my balance", "my bill", "my data left", "is there an outage at my address". Nova answers *how* to find these, not *what* they are. |
| **Any account-mutating action** (plan change, SIM block, port, autopay setup, add-on purchase) | Write access is a materially different risk and auth surface. v1 is read-and-explain only. |
| **Authentication / identity verification** | Follows from no personalisation. Nova never asks for, and must reject, account numbers, SIM serials, card details, passwords, or OTPs (NFR‑3.1). |
| **Voice / IVR channel** | Different latency, error, and disambiguation profile. v2. |
| **Languages other than English** | Translation quality on grounded citations needs its own eval set. v2. |
| **Proactive / outbound messaging** | Different consent and regulatory footprint. |
| **Fraud, disputes, complaints, retention, cancellation, legal requests** | Hard-routed to humans on detection. Nova must never negotiate, promise credit, or accept a complaint as resolved. |
| **Autonomous FAQ authoring by the model** | Nova may *propose* draft content from unanswered questions; a human must approve before it is indexed. No self-feeding knowledge loop. |
| **Device-specific deep diagnostics beyond guide content** | Guide steps only; no live device telemetry. |
| **Agent-side assist / copilot** | The same retrieval layer will serve it, but agent UX is v2. |

### 3.3 Boundary handling — the "my balance" problem

This is the most important product decision in v1, because it is the most likely question and the one Nova cannot answer.

**Decision: bounded deflection, not silent refusal.** When Nova detects an account-specific request it must, in one response:

1. State plainly that it cannot see account details.
2. Answer the *general* version of the question from verified sources ("your data balance is shown in MyTelecom under My Usage, or by dialling `*123#`").
3. Give the direct path — a deep link into the relevant MyTelecom screen where one exists.
4. Offer a human handoff if that path doesn't resolve it.

Rejected alternatives: (a) a plain "I can't help with that" — high abandonment, reads as broken; (b) immediate escalation on every account-shaped question — floods agents with questions the app answers, destroying containment; (c) inferring an answer from context — violates grounding, non-negotiable.

Explicitly forbidden: guessing at a number, quoting an example balance, or restating a price not present in a source.

---

## 4. Functional Requirements

Priority: **P0** = launch blocker, **P1** = required within 30 days of launch, **P2** = desirable.

### 4.1 Conversation

| ID | Requirement | Pri |
|---|---|---|
| FR‑1.1 | Accept free-text natural-language questions up to 1,000 characters; carry conversation context across turns within a session (30‑min idle timeout). | P0 |
| FR‑1.2 | Stream the answer token-by-token so the customer sees a response beginning within the latency target in §5.2. | P0 |
| FR‑1.3 | Answers must be plain-language, ≤150 words by default, and use numbered steps whenever the source content is procedural. | P0 |
| FR‑1.4 | Ask **one** clarifying question when the query is too ambiguous to retrieve against (e.g. a bare "it's not working"). Never ask more than one clarifier before attempting an answer. | P0 |
| FR‑1.5 | Offer 3–5 tappable starter prompts on open, drawn from the top Tier‑1 themes. | P1 |
| FR‑1.6 | Let the customer see the full conversation, copy it, and carry it into a handoff. | P1 |
| FR‑1.7 | Preserve session context across an in-session app/web reload. | P2 |

### 4.2 Retrieval & grounding

| ID | Requirement | Pri |
|---|---|---|
| FR‑2.1 | Every customer question triggers retrieval across **all three** sources in a single pass; the model must never answer from parametric knowledge alone. | P0 |
| FR‑2.2 | Hybrid retrieval — semantic (embedding) + keyword/BM25 — because Tier‑1 queries mix symptom language ("my internet died") with exact tokens ("APN", "eSIM", "*123#", "VoLTE"). Semantic-only retrieval demonstrably misses the exact-token cases. | P0 |
| FR‑2.3 | Chunk per source type: FAQ = one chunk per Q&A pair (never split); tickets = one chunk per ticket with `issue_type` + `description` + sanitised `resolution`; PDF guides = one chunk per numbered section/subsection, heading and version retained. | P0 |
| FR‑2.4 | Re-rank retrieved candidates before generation and pass only the top‑K (target K = 5–8) into context. | P0 |
| FR‑2.5 | **Every factual claim must trace to a retrieved chunk.** Prices, timings, fees, thresholds, phone numbers, and URLs must be reproduced verbatim from source — never paraphrased, rounded, or inferred. | P0 |
| FR‑2.6 | Display source attribution on every answer ("From: NovaCell FAQ — Roaming" / "From: Technical Guide v3.2, §2 Troubleshooting Connectivity"), expandable to the source excerpt. | P0 |
| FR‑2.7 | Source trust hierarchy on conflict: **FAQ > current PDF guide > resolved tickets.** On unresolved conflict between sources of equal rank, Nova must not pick one — it presents the safe common ground and offers escalation, and the conflict is logged to Support Ops. | P0 |
| FR‑2.8 | Prefer recency where sources disagree in time; surface the guide version in the citation so stale content is visible. | P1 |
| FR‑2.9 | Never cite or draw from a ticket whose `status != 'resolved'`; escalated and open tickets are excluded from the index entirely. | P0 |

### 4.3 Safety, confidence & refusal

| ID | Requirement | Pri |
|---|---|---|
| FR‑3.1 | Compute a per-answer confidence signal from retrieval score, source agreement, and answer-to-source entailment. Below threshold → refuse and offer handoff. Threshold configurable by Support Ops without a code release. | P0 |
| FR‑3.2 | If retrieval returns nothing above the relevance floor, Nova must say it doesn't have a verified answer. It must not attempt a "best guess". | P0 |
| FR‑3.3 | **Content-classification gate:** the PDF guide is marked *Internal Use Only*. Before launch, every guide section must be classified customer-safe / internal-only, and internal-only sections excluded from customer-facing retrieval. Internal diagnostics language (backend session-token resets, remote cell analysis procedures, escalation-ticket internals) must never surface to a customer. | P0 |
| FR‑3.4 | Ticket `resolution` text must be transformed into customer-facing guidance at index time: internal actions stripped, customer-actionable steps retained. A ticket resolved by an internal backend action yields "this needs a support agent", not instructions the customer cannot perform. | P0 |
| FR‑3.5 | Nova must never state or imply a commitment: no credits, refunds, compensation, repair timelines, or SLA promises — even where a past ticket records one (e.g. a goodwill data credit). Such tickets are indexed for *cause*, never for *remedy*. | P0 |
| FR‑3.6 | Refuse and redirect on: credential/OTP/card/ID requests, requests to act on the account, medical/legal/emergency content, and abuse. Emergency-services questions get a fixed, non-generated safety response. | P0 |
| FR‑3.7 | Prompt-injection resistance: content retrieved from any source is data, never instruction. Text inside a ticket description or PDF that resembles an instruction must not alter Nova's behaviour. Verified with an adversarial suite pre-launch. | P0 |
| FR‑3.8 | A standing block-list of terms/topics maintained by Support Ops (e.g. an unlaunched product, a withdrawn promotion) forces refusal + handoff regardless of retrieval. | P1 |

### 4.4 Escalation & handoff

| ID | Requirement | Pri |
|---|---|---|
| FR‑4.1 | Escalate on any of: (a) confidence below threshold; (b) two consecutive turns without a grounded answer; (c) explicit customer request for a human — honoured **immediately, always, first turn included**; (d) detected frustration or repeated rephrasing of the same question; (e) hard-routed category — fraud, unauthorised account change, billing dispute, complaint, cancellation, lost/stolen SIM, network outage report, vulnerable-customer signals; (f) any account-specific need the deflection path in §3.3 did not resolve. | P0 |
| FR‑4.2 | An explicit "talk to a human" is never blocked, delayed, gated behind a survey, or answered with another suggestion. One click, always visible. | P0 |
| FR‑4.3 | Handoff payload to the agent desktop: full transcript, detected intent/category, sources Nova cited, escalation reason code, channel and session metadata. | P0 |
| FR‑4.4 | Hours-aware routing: during staffed live-chat hours → live agent queue with position/wait estimate; outside them → ticket creation with a confirmation reference and expected response window, plus the self-serve options (`611`, MyTelecom app, coverage map) sourced from the FAQ. | P0 |
| FR‑4.5 | Escalation must be a clean transfer, not a restart: the customer must not be asked to repeat what they already told Nova. | P0 |
| FR‑4.6 | Reason codes are a fixed enum, logged on every escalation, and reported weekly — the primary input to the v1.x content roadmap. | P0 |
| FR‑4.7 | Global kill switch: Support Ops can disable Nova (per-channel or entirely) within 5 minutes, failing over to existing contact paths. | P0 |

### 4.5 Knowledge management (Support Ops console)

| ID | Requirement | Pri |
|---|---|---|
| FR‑5.1 | Support Ops can create, edit, retire, and restore FAQ entries and publish them live **without an engineering release**. | P0 |
| FR‑5.2 | Upload a new PDF guide version; the system parses, chunks, classifies (FR‑3.3), and indexes it, retiring the old version atomically. | P0 |
| FR‑5.3 | Ticket ingestion runs on a schedule (nightly), pulling newly-resolved tickets through PII scrubbing and redaction. | P0 |
| FR‑5.4 | Preview before publish: run a test query against staged content and see the answer Nova would give. | P0 |
| FR‑5.5 | Versioning and one-click rollback on every knowledge change, with author and timestamp. | P0 |
| FR‑5.6 | **Unanswered-question queue:** every refusal, low-confidence answer, and thumbs-down is clustered by theme and surfaced as a prioritised content backlog. | P0 |
| FR‑5.7 | Nova may draft a proposed FAQ entry from a cluster of unanswered questions; a human must approve it before indexing. No auto-publish. | P1 |
| FR‑5.8 | Freshness SLA dashboard per source: last-indexed timestamp, chunk count, stale-content warnings (guide version older than N months; FAQ entry unedited for N months while receiving thumbs-down). | P1 |
| FR‑5.9 | Publish-to-live latency ≤30 minutes for FAQ edits. | P0 |

### 4.6 Feedback & analytics

| ID | Requirement | Pri |
|---|---|---|
| FR‑6.1 | Thumbs up/down plus optional free text on every answer; a thumbs-down offers immediate escalation. | P0 |
| FR‑6.2 | Log every turn: query, retrieved chunk IDs and scores, cited sources, confidence, latency, cost, outcome. Retention per NFR‑3.3. | P0 |
| FR‑6.3 | Dashboard covering the §6 metrics, sliceable by intent category, channel, and time. | P0 |
| FR‑6.4 | Weekly human review sample: ≥200 conversations scored for groundedness, correctness, and tone by Support Ops QA. | P0 |
| FR‑6.5 | Regression eval suite (golden question → expected-source set) that runs on every knowledge or prompt change and blocks publish on regression beyond tolerance. | P0 |
| FR‑6.6 | Post-conversation CSAT prompt (single question, dismissible). | P1 |

---

## 5. Non-Functional Requirements

### 5.1 Accuracy & quality (the binding constraint)

| ID | Requirement |
|---|---|
| NFR‑1.1 | **Groundedness ≥ 99%** — no answer contains a factual claim absent from its cited sources, measured on the weekly ≥200-conversation human-reviewed sample. |
| NFR‑1.2 | **Zero tolerance for fabricated prices, fees, timings, or policy.** Any single occurrence is a P1 incident: root-caused within 24h, with a fix or scope reduction before the next release. |
| NFR‑1.3 | **Correct-refusal rate ≥ 90%** on a held-out adversarial set of unanswerable, out-of-scope, and account-specific questions. |
| NFR‑1.4 | **Answer helpfulness ≥ 85%** — human-rated as correctly and completely addressing the question, on the same sample. |
| NFR‑1.5 | **Citation precision ≥ 95%** — cited sources genuinely support the answer; no decorative citations. |
| NFR‑1.6 | Consistency: semantically equivalent phrasings of the same question return materially equivalent answers ≥95% of the time. |
| NFR‑1.7 | Tone: plain language, no telecom jargon unless the customer used it, no blame, no over-apologising. Enforced by a rubric in the weekly QA review. |

### 5.2 Latency & availability

| ID | Requirement |
|---|---|
| NFR‑2.1 | Time to first token: **P50 ≤ 1.5s, P95 ≤ 3.0s.** |
| NFR‑2.2 | Complete answer: **P50 ≤ 4s, P95 ≤ 8s.** |
| NFR‑2.3 | Retrieval stage ≤ 500ms P95. |
| NFR‑2.4 | Availability **99.5%** monthly for the chat surface. |
| NFR‑2.5 | Graceful degradation: if the model or retrieval layer is unavailable, show the escalation path and existing self-serve options — never a blank error, never a fallback answer generated without grounding. |
| NFR‑2.6 | Concurrency: sustain 500 concurrent conversations, burst 2,000, without breaching NFR‑2.2. |
| NFR‑2.7 | Usable on 3G-class connections and low-end Android devices — customers with connectivity problems are a core segment (UC‑1). |

### 5.3 Privacy, security & compliance

| ID | Requirement |
|---|---|
| NFR‑3.1 | **PII minimisation:** Nova must not request account numbers, SIM serials, card details, passwords, OTPs, or government ID. If a customer volunteers one, it is redacted at ingress before storage or model context, and Nova states that it doesn't need it. |
| NFR‑3.2 | **Ticket corpus scrubbing is a launch blocker.** Historical tickets contain customer narratives and internal remediation detail. Named entities, identifiers, locations, and account references are removed at index time; a sampled human audit of the scrubbed corpus must pass before launch. |
| NFR‑3.3 | Conversation logs retained **90 days** for quality and analytics, then deleted or irreversibly anonymised. Transcripts attached to escalated tickets follow existing ticket retention policy. |
| NFR‑3.4 | Encryption in transit (TLS 1.2+) and at rest for all conversation and knowledge data. |
| NFR‑3.5 | Customer conversation data must not be used to train third-party models; the inference provider contract must carry zero-retention or equivalent terms. |
| NFR‑3.6 | Data residency per NovaCell's operating jurisdiction; inference region pinned accordingly. |
| NFR‑3.7 | Role-based access to the Support Ops console; every knowledge and configuration change is audit-logged with actor and timestamp. |
| NFR‑3.8 | Clear disclosure that the customer is talking to an AI assistant, at conversation start — not buried in a footer. |
| NFR‑3.9 | WCAG 2.1 AA: screen-reader compatible, keyboard navigable, sufficient contrast, no reliance on colour alone. |
| NFR‑3.10 | Guide content classified *Internal Use Only* is excluded from customer-facing retrieval (FR‑3.3); the classification is auditable. |

### 5.4 Cost

| ID | Requirement |
|---|---|
| NFR‑4.1 | **Fully-loaded cost per contained conversation ≤ $0.25**, against a blended human-contact cost in the $4–6 range. Even at several times the target the unit economics hold; the target exists to keep them healthy at 4M-subscriber scale. |
| NFR‑4.2 | Model selection: **`openai/gpt-oss-120b` served by Groq** for answer generation — grounding discipline and refusal behaviour *are* the product, and this is where quality is worth paying for. At $0.15/MTok input and $0.75/MTok output, a grounded turn (~1.4K input including retrieved chunks, ~150 output) costs roughly **$0.0003**; measured across the nine-scenario smoke test the average was $0.0003/turn, roughly $0.001 per three-turn conversation — two orders of magnitude inside the NFR‑4.1 target. |
| NFR‑4.3 | Prompt caching on the stable system prompt and answer-format instructions, cutting the dominant input-token cost across turns. Given the measured cost against target this is not a launch or scale-up blocker; revisit if traffic or context size grows by orders of magnitude. |
| NFR‑4.4 | Use **`openai/gpt-oss-20b`** ($0.075/$0.30 per MTok) for the cheap non-generative stages — intent classification, escalation-trigger detection, query rewriting — where the quality bar is far lower than for answer generation. Route only what measurement shows holds quality. |
| NFR‑4.5 | Per-conversation and daily spend caps with alerting; automatic throttle-and-degrade to escalation paths on breach, rather than unbounded spend. |
| NFR‑4.6 | Cost per conversation reported alongside containment weekly — containment bought with runaway cost is not a win. |

---

## 6. Success Metrics

### 6.1 North star

**Tier‑1 containment rate** — the share of Nova conversations about in-scope Tier‑1 topics that end without human handoff **and** without the same customer re-contacting within 72 hours.

The re-contact clause is deliberate: containment measured on handoff alone rewards a bot that stonewalls. This metric only moves when the customer's problem is actually solved.

**Target: ≥40% by day 90 post-launch** (baseline 0). Ramp: ≥20% by day 30, ≥30% by day 60.

### 6.2 Primary metrics

| Metric | Target (day 90) | Source |
|---|---|---|
| Tier‑1 containment (per above) | ≥40% | Conversation logs + contact re-join |
| Groundedness (no unsupported claims) | ≥99% | Weekly ≥200-conversation human review |
| Fabricated price/policy incidents | **0** | Incident log |
| Correct-refusal rate on unanswerable questions | ≥90% | Adversarial eval set, per release |
| Thumbs-up rate on answered turns | ≥70% | In-product feedback |
| Post-conversation CSAT | ≥4.0 / 5 | CSAT prompt |
| Tier‑1 contact volume reduction (in-scope categories) | ≥12% vs. pre-launch baseline | Contact-centre reporting |
| P95 time to first token | ≤3.0s | Telemetry |
| Cost per contained conversation | ≤$0.25 | Billing ÷ contained conversations |

### 6.3 Guardrail metrics

Regressions that would make v1 a failure even if containment hits target:

| Guardrail | Threshold |
|---|---|
| False containment — customer re-contacts within 24h of a "contained" conversation | ≤15% |
| Escalation quality — escalated conversations where the agent must re-ask what Nova already captured | ≤10% |
| Abandonment mid-conversation | ≤20% |
| CSAT for *escalated* conversations vs. direct-to-agent baseline | No worse than baseline |
| Average handle time for Nova-escalated contacts | ≤ direct-to-agent AHT |
| Complaints citing the assistant | <0.1% of conversations |

### 6.4 Learning metrics

Not targets — inputs to the roadmap:

- Top 20 unanswered question clusters, weekly.
- Per-source citation share (which of FAQ / tickets / guides actually earns its keep).
- Retrieval-miss rate: questions where the right chunk existed but wasn't retrieved (measured on the golden set).
- Intent distribution vs. the assumed Tier‑1 themes — validates or corrects §2.4.

### 6.5 Launch gates

v1 does not ship to 100% of traffic until, on a pre-launch eval set and a limited-traffic pilot:

1. Groundedness ≥99% and **zero** fabricated price/policy claims across ≥500 reviewed conversations.
2. Correct-refusal ≥90% on the adversarial set.
3. PII scrubbing audit passed (NFR‑3.2) and guide content classification signed off by Legal (FR‑3.3).
4. Prompt-injection suite passed (FR‑3.7).
5. Handoff round-trip verified end-to-end with the live agent desktop, in and out of staffed hours.
6. Kill switch tested (FR‑4.7).

**Rollout:** internal dogfood (support agents) → 5% of web traffic → 25% → 100% web → app. Each stage held a minimum of 5 business days with metrics reviewed against the §6.3 guardrails; any guardrail breach pauses the ramp.

---

## 7. Risks, Assumptions & Open Questions

### 7.1 Risks

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R‑1 | **Hallucinated price or policy** reaches a customer and is treated as a commitment | Critical — regulatory, financial, trust exposure | Medium | Verbatim-reproduction rule (FR‑2.5); FAQ as top-trust source for pricing; entailment check pre-send; zero-tolerance incident process (NFR‑1.2); prominent AI disclosure (NFR‑3.8); pilot ramp with human review |
| R‑2 | **Internal-only guide content leaks to customers** — the guide is explicitly marked *Internal Use Only* and contains internal escalation procedures | High — operational and security exposure | **High if unmitigated** | Mandatory pre-launch section-level classification (FR‑3.3); Legal sign-off as a launch gate; excluded-section audit |
| R‑3 | **PII from historical tickets surfaces in an answer** | Critical — data-protection breach | Medium | Scrubbing at index time (NFR‑3.2); sampled human audit as a launch blocker; resolved-only filter (FR‑2.9) |
| R‑4 | **Thin knowledge base** — the FAQ and ticket corpus available at spec time are small; real query breadth will far exceed coverage | High — low containment, high refusal rate, poor first impression | High | Keep the refusal bar high and accept lower initial containment; unanswered-question queue (FR‑5.6) as the primary v1.x driver; commit Support Ops authoring capacity **before** launch; hold rollout until coverage clears a measured threshold (Q‑8) |
| R‑5 | Customers ask account-specific questions Nova can't serve; deflection reads as a runaround | Medium — abandonment, CSAT damage | High | Bounded deflection with deep links (§3.3); measure abandonment on deflection specifically; if it breaches guardrail, accelerate read-only account integration into v2 |
| R‑6 | Stale content — a price changes and the FAQ isn't updated; Nova confidently quotes the old one | High | Medium | Freshness SLA dashboard (FR‑5.8); guide version in every citation (FR‑2.8); named Support Ops accountability |
| R‑7 | Prompt injection via ticket or guide text | Medium | Low | Data-not-instruction handling and adversarial suite (FR‑3.7) |
| R‑8 | Agents perceive Nova as a job threat and disengage from the escalation loop | Medium — kills the feedback flywheel | Medium | Position as burnout reduction; involve agents in dogfood; make "flag a bad answer" a first-class agent action |
| R‑9 | Cost scales faster than deflection at 4M-subscriber volume | Medium | Low–Medium | Prompt caching (NFR‑4.3); cheaper model for non-generative stages (NFR‑4.4); spend caps that degrade rather than overspend (NFR‑4.5) |
| R‑10 | Containment is gamed — the bot avoids handoff and customers give up | High — looks like success, is failure | Medium | Containment defined to exclude 72h re-contact (§6.1); abandonment and false-containment guardrails (§6.3) |
| R‑11 | Retrieval succeeds but synthesis across conflicting sources produces a subtly wrong answer | Medium | Medium | Trust hierarchy (FR‑2.7); no-pick-on-conflict rule; conflict logging to Support Ops |

### 7.2 Assumptions

To be validated before or during v1 — several are load-bearing.

- **A‑1 (load-bearing):** The three sources, once indexed, cover a substantial majority of real Tier‑1 question *volume*. The corpus available at spec time is small; this must be validated against real query logs from the first pilot before the containment target is treated as achievable.
- **A‑2:** FAQ content is accurate and current, and is the authoritative source for pricing and policy.
- **A‑3:** Support Ops has (or will be given) staffed capacity to own knowledge curation and the unanswered-question backlog. Without this the system degrades within a quarter.
- **A‑4:** Ticket resolutions can be reliably sanitised into customer-safe guidance at acceptable quality. If FR‑3.4 proves unreliable at scale, tickets may need to be demoted to a retrieval signal only.
- **A‑5:** Live-agent chat and ticket creation expose APIs suitable for programmatic handoff with a transcript payload.
- **A‑6:** Customers will engage with a chat assistant for these problems given a visible, unblocked route to a human.
- **A‑7:** Tier‑1 contact baselines and blended cost-per-contact are measurable pre-launch — without a baseline, the volume-reduction target in §6.2 is unprovable.
- **A‑8:** MyTelecom app deep links exist (or can be added) for the screens the deflection path in §3.3 points to.
- **A‑9:** Groq's hosted model roster is stable enough to depend on. Groq retires and renames hosted models, so the model IDs in NFR‑4.2 and NFR‑4.4 must be verified against the live `/models` endpoint before each release, and the regression suite re-run when either changes.

### 7.3 Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q‑1 | What are the actual staffed live-chat hours, and what out-of-hours ticket response SLA should Nova quote? | Support Ops | Before FR‑4.4 build |
| Q‑2 | Who is the named accountable owner for knowledge accuracy, and what is the content-authoring capacity commitment? | VP Customer Care | Before launch gate |
| Q‑3 | Which PDF guide sections are customer-safe, and who signs off? | Legal + Network Ops | Launch blocker (FR‑3.3) |
| Q‑4 | Does the existing agent desktop accept an inbound transcript + metadata payload, or is integration work required? | Engineering | Sprint 1 |
| Q‑5 | Is 90-day conversation retention (NFR‑3.3) acceptable to the DPO in our jurisdiction? | DPO | Before launch |
| Q‑6 | What is the current blended cost per Tier‑1 contact, so NFR‑4.1 and the ROI case can be sized? | Finance | Before launch |
| Q‑7 | Should Nova be the default entry point to support, or an opt-in surface alongside existing paths, at each rollout stage? | Product + Support Ops | Before ramp to 25% |
| Q‑8 | What is the minimum knowledge coverage threshold, measured on real pilot queries, below which we hold rollout? | Product | Before pilot |
| Q‑9 | Do we log unauthenticated conversations against any customer identifier at all, and if so under what consent basis? | DPO + Legal | Before launch |
| Q‑10 | Is there an existing contact-centre intent taxonomy we should align escalation reason codes to, rather than inventing one? | Support Ops | Sprint 1 |

---

## 8. Future Iterations (v2+)

### v1.1 — Consolidation (0–3 months post-launch)
- Close the top 20 unanswered-question clusters with authored FAQ content.
- Tune confidence thresholds against observed correct-refusal and containment data.
- Proactive knowledge-gap alerting for Support Ops.
- Prompt caching and model routing for the non-generative stages (NFR‑4.3, NFR‑4.4).

### v2 — Personalisation (read-only)
The highest-value unlock, and the one v1 deliberately defers. Authenticated, read-only access to billing and account data so Nova can answer "what's my balance", "why is *my* bill $47 higher", "is there an outage at *my* address". Requires authentication, a step-up identity flow, expanded PII handling, and read-only CRM/billing/network-status APIs. Strictly read-only — writes stay out until the read path is proven.

### v2 — Agent assist
Turn the same retrieval layer inward: real-time grounded suggestions in the agent desktop, with the agent's accept/reject as a high-quality content signal. Cheap to build on v1 infrastructure, and it converts agents from sceptics into the system's best content reviewers.

### v2 — Channel and language expansion
- Additional languages, each with its own grounded-answer eval set.
- WhatsApp / SMS / RCS.
- Voice / IVR, once conversational accuracy is proven in text.

### v3 — Guided resolution and action
- Interactive, stateful troubleshooting flows (branching diagnostics built from the guide's structured step sequences, tracking what the customer has already tried).
- Scoped account actions with explicit confirmation: activate a roaming bundle, order a replacement SIM, set up autopay. Each action gated on demonstrated accuracy in the equivalent read-only path.
- Proactive support: outbound notification with self-serve resolution when NovaCell detects an issue affecting a customer (outage, unusual charge pattern) — subject to consent and regulatory review.

### Continuous
- Quarterly re-evaluation of the model against the frozen eval suite as newer models ship.
- Expanding the golden regression set with every real-world failure.
- Ongoing knowledge-freshness governance.
