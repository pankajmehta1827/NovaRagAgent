# Archify layout tips (learned from real runs)

Archify's own references remain authoritative. These are the gate failures that
cost the most retries when building a full design document with Archify v3.0.1,
and the first-draft choices that avoid them. Check the numbers against the
diagnostic text if a newer Archify reports different limits.

## All types

- **Desktop readability.** At the 1440px reader, 7px source text must project to
  ≥ 6px, so a fixed `meta.viewBox` width above about **1085** fails
  `composition/desktop-readability`. Prefer width 1080 or omit `viewBox`.
- **Canvas ratio.** A showcase canvas with a fixed viewBox needs width ÷ height
  ≥ **1.55** (`composition/viewport-height`). If content is tall, cut or merge
  elements, or omit `viewBox` where the type allows intrinsic height.
- **Re-runs.** Delete the previous `*.finalize*.json`, `*.delivery.json` and
  `*.browser-check.json` for that figure before rerunning `finalize`.
- **Sublabels** of about 25 characters fit a 150px-wide node; longer ones get
  truncated or fail readability.

## Architecture

- Lay out a grid: main journey left → right on one row (gaps ≥ 6.5px × label
  chars + 21px), branches and stores directly above or below their owner so edges
  are one straight segment. 220–250px column pitch and 170px row pitch with
  150×64 nodes worked first time for 12 nodes.
- Start with automatic routes; add `fromSide` / `toSide` / `via` only for a
  measured failure.
- Leave out boundaries whose bounding box would also enclose non-member nodes;
  explain the trust boundary in a card instead.

## Sequence

- Messages that share horizontal space need **≥ 28px** of `y` separation.
- Every message `y` must stay ≤ `viewBox[1] − 83`; the legend needs content to
  end about **98px** above the bottom (the validator reports the exact minimum).
- About 15 messages fit a 1080×692 canvas. Merge trivial returns (for example
  "classify → inquiry" as one labelled call) rather than growing the canvas.
- `column_fit: "spread"` with 7 participants at width 1080 kept labels legible.

## Workflow (schema v2)

- Columns are **0–5** only; lanes are rows. Put the main path in `mainPath` and
  let it advance one column per step.
- Don't pin `route` presets (`bottom-channel` and so on) on the first draft; the
  validator rejects presets that cannot meet its clearance rules, and the
  automatic candidate is usually fine.
- An exception lane (`"variant": "exception"`) last keeps error exits readable.

## Dataflow

- Rows have fixed tops (128, 242, 356, 470, … px) and a default node height of
  about 58px; a node's `y` is `rowTop + yOffset`, and its connection ports sit at
  the **centre of each side**.
- Several flows converging on one node collide unless they share a corridor:
  give each flow `"route": "vertical-channel"` with the same `channelX` (just
  left of the target), `labelSegment: 0`, and a `labelAt` above each source's
  horizontal segment.
- A tall target node (`height` ≈ 400 spanning four rows, `row: 0`) reads well as
  an index or store that many sources feed.
- Keep each node in one stage column; a flow that has to skip a column passes
  through nodes in between and fails `clean-flow/edge-through-node`.

## Lifecycle (schema v2)

- `col` is **0–4**, the same x in every lane; lanes are rows with `main` first
  and the terminal lane last.
- Put an exit state in the column of the state it leaves; two terminal states
  can't share a column in one lane, so add a lane (for example "review") instead.
- Automatic routing handled 10 transitions, including two into one terminal
  state, with no hints.
