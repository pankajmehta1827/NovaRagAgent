# System Design Document template

Copy this outline into `SYSTEM_DESIGN.md` and fill every section from evidence.
Delete a section only when it truly does not apply, and say so in one line
("No asynchronous processing: every request is served inline.") rather than
silently dropping it. Diagram slots are marked `[[diagram: <type> — <question>]]`;
replace each with the embed block shown at the bottom of this file.

Every factual claim about an existing system carries a source reference in the
form `path/to/file.py:12-40`. Claims about a *proposed* system are marked
**Proposed**. Unknowns go in §13, never into the prose as guesses.

---

```markdown
# <System name> — System Design

| | |
|---|---|
| **Status** | Draft · In review · Approved |
| **Authors** | <names> |
| **Last updated** | <YYYY-MM-DD> |
| **Repository** | <credential-free origin> @ `<40-char commit>` |
| **Related** | <PRD / RFC / ticket links> |

## 1. Overview
Two or three paragraphs: what the system does, for whom, and the single most
important design idea. A reader who stops here should know what it is.

## 2. Goals and non-goals
- **Goals** — measurable where possible (latency, accuracy, availability).
- **Non-goals** — what is deliberately out of scope, and why.

## 3. Requirements
### 3.1 Functional
Numbered list (`FR-1 …`) traceable to the PRD where one exists.
### 3.2 Non-functional
Table: quality attribute · target · how it is met / measured
(performance, availability, security, privacy, cost, observability, compliance).
### 3.3 Assumptions (required for a new system)
Table: # · assumption · why it matters · how to validate. Every number used in
§11 that the user did not give must appear here.

## 4. System context
Who and what sits outside the system: users, operators, external APIs, identity
providers, data sources. One short paragraph per external dependency, stating
the protocol and the trust boundary crossed.

[[diagram: architecture — What does the system talk to, and across which trust boundaries?]]

## 5. Architecture
### 5.1 Component overview
[[diagram: architecture — What are the major components and how does the main user journey move through them?]]

### 5.2 Component responsibilities
Table: component · responsibility · key modules (with source refs) · owns which state.

### 5.3 Key design decisions
For each: **Decision**, **Context**, **Alternatives considered**, **Consequences**.
(Lightweight ADRs. Link to full ADRs if they exist.)

## 6. Runtime behaviour
One subsection per critical flow (the main happy path, plus each flow with
non-obvious branching such as auth, payments, escalation, retries).

### 6.1 <Main flow name>
[[diagram: sequence — What calls happen, in what order, when <trigger>?]]
Narrative of the steps, including error, timeout, and fallback handling.

### 6.2 <Decision / process flow name>
[[diagram: workflow — Which gates and branches decide the outcome of <process>?]]

## 7. Data design
### 7.1 Data flow
[[diagram: dataflow — Where does data enter, how is it transformed, and where is it stored and consumed?]]
### 7.2 Data model and storage
Entities / documents / indexes, their schema, where they live, retention.
### 7.3 Data lifecycle
[[diagram: lifecycle — Which states can a <session / ticket / order> be in, and what moves it between them?]]

## 8. Interfaces
APIs, UI surfaces, CLI entry points, events and their contracts (request /
response shapes, auth, idempotency, versioning). For a new system, list each
endpoint as `METHOD /path` · request · response · errors · idempotency.

## 9. Security and privacy
Authentication, authorization, secrets handling, input sanitisation, PII
handling, prompt-injection / abuse defences (for LLM systems), audit trail.

## 10. Reliability and operations
Failure modes table: failure · detection · impact · mitigation.
Deployment topology, configuration, feature flags / kill switches, monitoring,
alerting, runbooks.

[[diagram: architecture — How is the system deployed and run? (only if deployment is non-trivial)]]

## 11. Scalability and performance
### 11.1 Capacity estimates (required for a new system)
Show the arithmetic: DAU → requests/day → average and peak QPS (state the peak
factor); bytes per record × records/day → storage per year (with replication);
read bandwidth; cache size (hot set × object size); instance or shard counts.
### 11.2 Bottlenecks and scaling plan
Expected load, bottlenecks, caching, partitioning or sharding key, rate limits,
cost drivers, and what changes at 10× load.

## 12. Testing and quality
Unit / integration / regression / evaluation suites, how to run them, and
what they do and do not cover.

## 13. Risks, open questions, and future work
- **Risks** — with likelihood, impact, mitigation.
- **Open questions** — every unknown recorded during research, with the claim it affects.
- **Future work** — follow-ups deliberately deferred.

## Appendix A — Diagram index
Table: # · diagram · type · question it answers · HTML · Archify gates.

## Appendix B — Glossary
```

---

## Diagram embed block

Each diagram lives in `diagrams/<NN>-<slug>/`. Embed it like this so the doc
renders on GitHub (PNG) and still links to the interactive Archify viewer:

```markdown
**Figure N — <title>.** <one sentence: the question this diagram answers.>

[![<title>](diagrams/<NN>-<slug>/preview.png)](diagrams/<NN>-<slug>/<slug>.html)

<sub>Interactive version: [`diagrams/<NN>-<slug>/<slug>.html`](diagrams/<NN>-<slug>/<slug>.html)
· Archify `<type>` · gates: validate ✔ deliver ✔ check ✔ browser-check ✔</sub>
```

If no preview PNG could be captured (no Chrome), drop the image line and keep
the link, and record `browser-check: skipped` truthfully in the gates line.
