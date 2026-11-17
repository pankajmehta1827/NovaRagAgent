---
name: system-design-doc
description: "Create a complete System Design Document (SDD) for ANY system — an existing codebase, or a new system described in plain words (e.g. 'design a URL shortener', 'design a ride-hailing backend') — with every diagram generated and validated by Archify (github.com/tt-a1i/archify): architecture/context maps, request sequences, decision workflows, data flows, and state lifecycles as interactive HTML plus PNG previews embedded in Markdown. Use when the user asks for a system design, system design doc, design document, technical design, architecture document, SDD, HLD/LLD, design review write-up, or interview-style system design. Not for a single standalone diagram (use Archify directly) or for numeric charts."
license: MIT
metadata:
  version: "1.2"
  diagrams: "Archify v3.0.1 (tt-a1i/archify, MIT)"
---

# System Design Document (with Archify diagrams)

Produce `docs/system-design/<slug>/SYSTEM_DESIGN.md` in the **current project**:
a reviewable design document whose prose is grounded in source evidence and
whose figures are Archify diagrams that passed Archify's own validation gates.

```
docs/system-design/<slug>/
├── SYSTEM_DESIGN.md
└── diagrams/
    ├── 01-context/        candidate.json · context.html · preview.png · context.finalize-summary.json
    ├── 02-components/
    ├── 03-<flow>-sequence/
    └── …
```

Use the user's location instead if they name one. `<slug>` is the kebab-case
system name (e.g. `checkout-service`). Run every command from the project root.

**Paths in this skill.** `<skill-dir>` means the directory that contains this
SKILL.md (the skill's base directory, wherever it is installed: a project's
`.claude/skills/`, `~/.claude/skills/`, or an account-synced skill folder).
Resolve it to an absolute path once and substitute it below; never assume the
skill lives inside the project being documented.

## 1. Set up Archify

```bash
eval "$(bash <skill-dir>/scripts/ensure-archify.sh --env)" && echo "$ARCHIFY" && node "$ARCHIFY" doctor
```

The script finds an installed Archify (`$ARCHIFY_HOME`, `.claude/skills/archify`,
`~/.claude/skills/archify`, …) or clones the pinned release into
`~/.cache/archify/<tag>`; it needs Node ≥ 18, git, and no `npm install`. It also
exports `ARCHIFY_CHROME` when it finds Chrome/Chromium (including Playwright's
under `/opt/pw-browsers`). Shell state does not persist between tool calls, so
**prefix every later `node "$ARCHIFY" …` command with the same `eval`.**

`ARCHIFY_PKG="$(dirname "$(dirname "$ARCHIFY")")"` is the Archify package root.
Before writing the first diagram, read in one batch:

- `$ARCHIFY_PKG/SKILL.md` — the Archify contract (type router, finalize, repair).
- `$ARCHIFY_PKG/references/authoring-defaults.md`
- `$ARCHIFY_PKG/references/repository-authoring.md` (when documenting real code)

Archify's own rules govern every diagram; this skill only decides **which**
diagrams the document needs and how they are assembled. Read Archify's other
references (`authoring-contract.md`, `delivery-contract.md`,
`architecture-layout-repair.md`) only when a finalize gate fails and its
diagnostics point there.

## 2. Scope the document

Pick the mode first:

- **Mode A — existing system.** The subject is the current repository (or a slice
  of it). Evidence is the code; every claim cites `path:line`.
- **Mode B — new system from a description.** The subject is an idea ("design a
  URL shortener", "design a payments ledger"). There may be no repository at all.
  Evidence is the user's requirements plus explicit, labelled assumptions.

Then settle (ask only if genuinely ambiguous):

- **Subject** — what system, which slice.
- **Audience and depth** — high-level (HLD: §1–5, §9–13) or detailed (LLD: all sections).
- **Inputs** — existing PRDs, READMEs, ADRs, tickets the user points at.

## 3. Gather evidence

For an existing codebase, follow Archify's
`references/repository-authoring.md`, which applies to the prose as much as to
the diagrams:

1. Freeze identity: `git rev-parse HEAD`, `git remote get-url origin` (strip any
   credentials), `git status --short`. Archify verifies evidence against
   **committed** bytes, so diagram sources must cite the committed revision.
   If the project is not a git repository, skip `meta.repository`/`sources` and
   `--repo-root`, and cite paths in the prose only.
2. Read project docs first (README, PRD, design notes, `CLAUDE.md`), then
   manifests and entry points, then follow imports to the actual I/O, external
   calls, persistence, and control gates.
3. Record facts with `path:line-range` as you read. Note every unknown next to
   the claim it affects; unresolved ones go to §13, not into the prose.
4. Stop when each template section and each planned diagram has evidence.

**Mode B (new system).** Do the design work before drawing anything:

1. **Clarify requirements.** Functional scope (the 3–6 core use cases) and
   non-functional targets: users / DAU, read:write ratio, peak QPS, data size and
   growth, latency SLOs, availability, consistency needs, compliance, budget,
   and any mandated tech. Ask the user for the facts that change the design; for
   anything they leave open, state an explicit assumption in an **Assumptions**
   table (§3) instead of silently inventing it.
2. **Estimate capacity** (back-of-the-envelope) in §11: QPS (avg and peak),
   storage per year, bandwidth, cache size, number of shards or instances. Show
   the arithmetic so a reviewer can redo it.
3. **Design the API and data model** (§7.2, §8) before the component diagram:
   entities, keys, access patterns, and the storage choice each pattern drives.
4. **Choose components with trade-offs.** Every major choice (database, cache,
   queue, sync vs async, consistency model, partitioning key) gets a decision
   record in §5.3 with at least one rejected alternative and why.
5. **Walk the critical paths and failure modes**: the main read and write flows,
   then what happens when each dependency is slow or down (§6, §10).

Mark every design choice **Proposed**. Diagrams in Mode B omit
`meta.repository` and `sources`, and `finalize` runs without `--repo-root`.

## 4. Plan the figures

Read `<skill-dir>/references/sdd-template.md`. Map each diagram slot to an
Archify type by the question it answers:

| Document section | Question | Archify type |
|---|---|---|
| §4 System context | What does it talk to, across which trust boundaries? | `architecture` |
| §5 Components | What are the parts and how does the main journey flow? | `architecture` |
| §6 Runtime flows | What calls happen, in what order? | `sequence` |
| §6 Decision / process | Which gates and branches decide the outcome? | `workflow` |
| §7 Data flow | Where does data enter, transform, persist, get consumed? | `dataflow` |
| §7 Lifecycle | Which states can an entity be in, and what moves it? | `lifecycle` |
| §10 Deployment | How is it deployed and run? (only if non-trivial) | `architecture` |

Typical documents need 4–7 figures. Each figure answers one question; never
cram two questions into one diagram, and skip a slot whose diagram would only
repeat another. There is no figure quota.

## 5. Generate each diagram with Archify

For each planned figure `NN-<slug>` of type `<type>`, with
`<dir>` = `docs/system-design/<doc>/diagrams/NN-<slug>`:

1. **Author** `<dir>/candidate.json` following Archify's Fast authoring path:
   read the type's schema and example from Archify's Type router (examples
   teach shape, not facts), use fresh ids and wording,
   `meta.quality_profile: "showcase"`, and `meta.output: "<dir>/<slug>.html"`
   (relative to the project root). For repository-backed figures, set
   `meta.repository` (credential-free origin + 40-char commit) and give every
   key node `sources` (`path`, `line`, `end_line`).
2. **Finalize** — one invocation, candidate unchanged while it runs:

   ```bash
   eval "$(bash <skill-dir>/scripts/ensure-archify.sh --env)" && \
   node "$ARCHIFY" finalize <type> <dir>/candidate.json <dir>/<slug>.html \
     --repo-root . --quality showcase --json
   ```

   Drop `--repo-root .` in Mode B or for a non-git project.

   **Re-running `finalize` on the same output** (after any repair): first delete
   that figure's previous sidecars, or the browser gate refuses to overwrite them
   with `viewer/evidence-path-conflict`. Use literal paths, e.g.
   `rm -f "<dir>/<slug>.finalize.json" "<dir>/<slug>.finalize-summary.json" "<dir>/<slug>.delivery.json" "<dir>/<slug>.browser-check.json"`.
3. **Repair** on a non-zero exit, per Archify's delivery contract: read the
   compact output / `evidence.summaryReceipt`, fix the failed gate in the
   connected neighbourhood, rerun the full finalize. Never report a failing
   gate as success. Follow Archify's visual-review-recommendation rules when a
   passing receipt carries them.
4. **Preview PNG** for the Markdown (needs `ARCHIFY_CHROME`):

   ```bash
   eval "$(bash <skill-dir>/scripts/ensure-archify.sh --env)" && \
   node "$ARCHIFY" visual-check <dir>/<slug>.html --summary --require-provenance --out-dir <dir>/visual && \
   cp <dir>/visual/<slug>.visual-check.1440x900.light.png <dir>/preview.png && rm -rf <dir>/visual
   ```

   Look at `preview.png` (Read the image). It is your perceptual check: labels
   legible, no overlapping arrows, nothing clipped. If it is poor, repair the
   candidate and rerun steps 2–4. Report the review truthfully.
5. **Tidy** — keep `candidate.json`, `<slug>.html`, `preview.png`, and
   `<slug>.finalize-summary.json`; delete the other Archify sidecars
   (`*.finalize.json`, `*.delivery.json`, `*.browser-check.json`) so the
   commit stays small. Record the gate results for Appendix A.

Finish (pass) each figure before embedding it. Read
[references/archify-layout-tips.md](references/archify-layout-tips.md) before the
first candidate of each type — it lists the gate failures that cost the most
retries and how to avoid them up front.

## 6. Write the document

Fill `SYSTEM_DESIGN.md` from the template:

- Replace every `[[diagram: …]]` slot with the embed block at the bottom of the
  template (PNG linked to the interactive HTML, gate line underneath).
- Text and figures must agree: the same component names, the same edges, the
  same conditions. If writing the prose reveals a diagram error, fix the
  candidate and re-finalize rather than explaining around it.
- Cite sources inline (`src/orders/service.ts:40-88`) for claims about existing code.
- Use tables for responsibilities, requirements, failure modes, and decisions.
- Fill Appendix A (diagram index) with each figure's type, question, HTML path,
  and gate results.
- Keep the document's language consistent with Archify's `meta.locale`.

## 7. Verify and hand off

Before reporting done:

- [ ] Every figure's latest `finalize` exited 0 (`validate`, `deliver`, `check`
      pass; `browser-check` pass, or truthfully `skipped` when no Chrome).
- [ ] Every embed's PNG and HTML link resolves (`ls` the paths).
- [ ] Every section is filled, marked N/A with a reason, or tracked in §13.
- [ ] No invented facts: each claim about code has a source ref; each unknown is in §13.

Report to the user: the path of `SYSTEM_DESIGN.md`, the figure list with each
figure's Archify gate results and whether you actually reviewed its preview, the
open questions from §13, and any Archify update notice from a receipt
(`update.noticeRequired`). Commit only if the user's workflow calls for it.

## Updating an existing document

Reuse the same `docs/system-design/<slug>/` folder. Re-freeze the commit,
re-check the evidence behind changed areas, edit the affected candidates in
place and re-finalize them, update prose, bump **Last updated**. For a
before/after architecture view, Archify's
`node "$ARCHIFY" compare architecture <base.json> <head.json> <out.html>` renders
the diff.
