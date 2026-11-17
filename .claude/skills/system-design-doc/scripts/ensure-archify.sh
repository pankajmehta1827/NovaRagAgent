#!/usr/bin/env bash
# Locate (or fetch) the Archify diagram skill and print the absolute path to its
# CLI entry point, bin/archify.mjs. Everything else goes to stderr so callers can
# capture the path with: ARCHIFY="$(bash ensure-archify.sh)"
#
# With --env it prints shell exports instead, including ARCHIFY_CHROME when a
# Chrome/Chromium is found (Archify's browser gate is skipped without one):
#   eval "$(bash ensure-archify.sh --env)"
#
# Search order:
#   1. $ARCHIFY_HOME                      (explicit override)
#   2. .claude/skills/archify             (project install)
#   3. ~/.claude/skills/archify           (user install, e.g. `npx skills add tt-a1i/archify -g`)
#   4. ~/.agents/skills/archify           (other agent installs)
#   5. ~/.cache/archify/<tag>             (previous fetch by this script)
# If none has bin/archify.mjs, clone github.com/tt-a1i/archify at $ARCHIFY_REF
# into the cache. No npm install is needed: Archify ships its runtime.
set -euo pipefail

ARCHIFY_REF="${ARCHIFY_REF:-v3.0.1}"
ARCHIFY_REPO="${ARCHIFY_REPO:-https://github.com/tt-a1i/archify.git}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/archify/${ARCHIFY_REF}"

mode="${1:-path}"

log() { printf '[ensure-archify] %s\n' "$*" >&2; }

# A skill package has bin/ at its root; a repository checkout nests it in archify/.
entry_for() {
  local dir="$1"
  if [ -f "$dir/bin/archify.mjs" ]; then printf '%s\n' "$dir/bin/archify.mjs"; return 0; fi
  if [ -f "$dir/archify/bin/archify.mjs" ]; then printf '%s\n' "$dir/archify/bin/archify.mjs"; return 0; fi
  return 1
}

if ! command -v node >/dev/null 2>&1; then
  log "node is not on PATH; Archify needs Node.js >= 18."
  exit 1
fi
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt 18 ]; then
  log "Node.js $(node --version) is too old; Archify needs >= 18."
  exit 1
fi

entry=""
for dir in "${ARCHIFY_HOME:-}" ".claude/skills/archify" "$HOME/.claude/skills/archify" \
           "$HOME/.agents/skills/archify" "$CACHE_DIR"; do
  [ -n "$dir" ] && [ -d "$dir" ] || continue
  if entry="$(entry_for "$dir")"; then break; fi
done

if [ -z "$entry" ]; then
  log "Archify not found; cloning $ARCHIFY_REPO@$ARCHIFY_REF into $CACHE_DIR"
  mkdir -p "$(dirname "$CACHE_DIR")"
  tmp="$(mktemp -d "$(dirname "$CACHE_DIR")/.clone.XXXXXX")"
  git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$ARCHIFY_REF" "$ARCHIFY_REPO" "$tmp" >&2
  rm -rf "$CACHE_DIR"
  mv "$tmp" "$CACHE_DIR"
  entry="$(entry_for "$CACHE_DIR")" || { log "clone has no bin/archify.mjs"; exit 1; }
fi

entry="$(cd "$(dirname "$entry")" && pwd)/$(basename "$entry")"

if ! node "$entry" doctor >/dev/null 2>&1; then
  log "archify doctor failed; run: node $entry doctor"
  exit 1
fi

if [ "$mode" != "--env" ]; then
  printf '%s\n' "$entry"
  exit 0
fi

printf 'export ARCHIFY=%q\n' "$entry"
chrome="${ARCHIFY_CHROME:-}"
if [ -z "$chrome" ]; then
  for c in google-chrome google-chrome-stable chromium chromium-browser chrome; do
    if command -v "$c" >/dev/null 2>&1; then chrome="$(command -v "$c")"; break; fi
  done
fi
if [ -z "$chrome" ]; then
  # Playwright-managed Chromium (e.g. PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers).
  for root in "${PLAYWRIGHT_BROWSERS_PATH:-}" /opt/pw-browsers "$HOME/.cache/ms-playwright"; do
    [ -n "$root" ] && [ -d "$root" ] || continue
    chrome="$(find "$root" -maxdepth 3 -type f -name chrome -path '*chrome-linux*' 2>/dev/null | sort | tail -1)"
    [ -n "$chrome" ] && break
  done
fi
if [ -n "$chrome" ]; then
  printf 'export ARCHIFY_CHROME=%q\n' "$chrome"
else
  log "no Chrome/Chromium found; finalize will skip browser-check. Set ARCHIFY_CHROME to enable it."
fi
