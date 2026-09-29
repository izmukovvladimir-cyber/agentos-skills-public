#!/usr/bin/env bash
# Is a codeword free for a new funnel? Checks your guide registry and, optionally, the funnel itself.
#
# Env:
#   GUIDES_REGISTRY  path to a JSON file {"guides": [{"codeword", "slug", "title"}, ...]}
#                    (default: <WORKSPACE>/assets/hub/registry.json, WORKSPACE defaults to $PWD)
#   FUNNEL_VERIFY    path to funnel_verify.py from the funnel-verify skill (optional)
#
# Output: EXACT = the word is already taken, SIMILAR = words sharing the first 5 letters (check by eye).
# Exit: 0 = checks ran, 1 = bad input/registry, otherwise the exit code of funnel_verify.py.
set -euo pipefail
word="${1:?usage: word_free.sh СЛОВО}"
reg="${GUIDES_REGISTRY:-${WORKSPACE:-$PWD}/assets/hub/registry.json}"
[[ -f "$reg" ]] || { echo "missing: $reg (set GUIDES_REGISTRY)" >&2; exit 1; }
python3 - "$word" "$reg" <<'PY'
import json, sys
w, reg = sys.argv[1].upper(), sys.argv[2]
with open(reg) as fh:
    guides = json.load(fh)["guides"]
exact = [g for g in guides if str(g.get("codeword", "")).upper() == w]
similar = [g for g in guides if g not in exact and str(g.get("codeword", "")).upper()[:5] == w[:5]]
for g in exact:
    print(f"EXACT: {g['codeword']} -> guide-{g['slug']} | {g['title']}")
for g in similar:
    print(f"SIMILAR: {g['codeword']} -> guide-{g['slug']} | {g['title']}")
if not exact and not similar:
    print("HUB: no match")
PY
if [[ -z "${FUNNEL_VERIFY:-}" ]]; then
  echo "FUNNEL: skipped (set FUNNEL_VERIFY to check the funnel structure)" >&2
  exit 0
fi
[[ -f "$FUNNEL_VERIFY" ]] || { echo "missing: $FUNNEL_VERIFY" >&2; exit 1; }
rc=0
out=$(timeout 150 python3 "$FUNNEL_VERIFY" "$word" 2>&1) || rc=$?
printf '%s\n' "$out" | grep -E "статус|ИТОГ" | head -4 || true
[[ "$rc" -eq 124 ]] && echo "FUNNEL: timeout after 150 s" >&2
[[ "$rc" -ne 0 ]] && echo "FUNNEL: funnel_verify.py exit $rc" >&2
exit "$rc"
