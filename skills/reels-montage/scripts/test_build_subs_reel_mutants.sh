#!/usr/bin/env bash
# Mutation run for build_subs_reel.py: break one thing, expect the suite to notice.
# A mutant is CAUGHT only when the suite runs and reports FAIL=N>0 — a suite that
# dies of an exception proves nothing, so a bare non-zero exit is not enough.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/build_subs_reel.py"
TESTS="$HERE/test_build_subs_reel.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$SRC" ] || { echo "missing: $SRC" >&2; exit 1; }
[ -f "$TESTS" ] || { echo "missing: $TESTS" >&2; exit 1; }

base_out="$(python3 "$TESTS" "$SRC" 2>&1)"
base_rc=$?
if [ "$base_rc" -ne 0 ]; then
  echo "BASELINE КРАСНЫЙ — мутационный прогон бессмыслен" >&2
  echo "$base_out" >&2
  exit 1
fi
echo "baseline: $(echo "$base_out" | tail -1)"

CAUGHT=0; MISSED=0; N=0

mutate() {
  local name="$1" from="$2" to="$3"
  N=$((N + 1))
  local f="$TMP/m$N.py"
  python3 - "$SRC" "$f" "$from" "$to" <<'PY'
import sys, pathlib
src, dst, a, b = sys.argv[1:5]
t = pathlib.Path(src).read_text(encoding="utf-8")
if a not in t:
    print("ANCHOR-MISS")
    sys.exit(3)
pathlib.Path(dst).write_text(t.replace(a, b, 1), encoding="utf-8")
PY
  if [ $? -eq 3 ]; then
    echo "  ЯКОРЬ УСТАРЕЛ: $name"
    MISSED=$((MISSED + 1)); return
  fi
  local out rc
  out="$(python3 "$TESTS" "$f" 2>&1)"; rc=$?
  local fails
  fails="$(echo "$out" | grep -oE 'FAIL=[0-9]+' | tail -1 | cut -d= -f2)"
  if [ "$rc" -ne 0 ] && [ -n "${fails:-}" ] && [ "$fails" -gt 0 ]; then
    echo "  пойман: $name (FAIL=$fails)"
    CAUGHT=$((CAUGHT + 1))
  else
    echo "  НЕ ПОЙМАН: $name (rc=$rc, fails=${fails:-нет строки FAIL})"
    MISSED=$((MISSED + 1))
  fi
}

mutate "строка держится дольше следующей (перекрытие полос)" \
  'end = min(float(ln[-1]["end"]) + 0.12, nxt, duration)' \
  'end = min(float(ln[-1]["end"]) + 0.12, duration)'
mutate "у полосы субтитров пропал id" \
  '<div id="sub-{li}" class="clip subs"' \
  '<div class="clip subs"'
mutate "у карточки-хука пропал id" \
  '<div id="hook" class="clip hook" data-start="0.20" ' \
  '<div class="clip hook" data-start="0.20" '
mutate "корень без data-start" \
  '<div id="root" data-composition-id="main" data-start="0"' \
  '<div id="root" data-composition-id="main"'
mutate "таймлиния не на паузе" \
  'gsap.timeline({{ paused: true }})' \
  'gsap.timeline({{ paused: false }})'
mutate "таймлиния не регистрируется" \
  'window.__timelines["main"] = tl;' \
  'const unused = tl;'
mutate "видео без muted/playsinline" \
  'data-track-index="0" muted playsinline' \
  'data-track-index="0"'
mutate "звук выброшен" \
  '<audio id="a-roll-audio" src="assets/source.mp4"' \
  '<audio-disabled id="a-roll-audio" src="assets/source.mp4"'
mutate "первое слово роняется, если оно длиннее лимита" \
  'if cur and too_long:' \
  'if too_long:'
mutate "лимит слов в строке игнорируется" \
  'too_long = len(cand) > max_words or sum(len(x["word"]) + 1 for x in cand) > max_chars' \
  'too_long = sum(len(x["word"]) + 1 for x in cand) > max_chars'
mutate "лимит символов игнорируется" \
  'too_long = len(cand) > max_words or sum(len(x["word"]) + 1 for x in cand) > max_chars' \
  'too_long = len(cand) > max_words'
mutate "твин ставится и на слово за концом ролика" \
  'if float(w["start"]) < duration:' \
  'if True:'
mutate "текст слова не экранируется" \
  'html.escape(str(w["word"]))' \
  'str(w["word"])'
mutate "текст хука не экранируется" \
  'html.escape(hook)' \
  'hook'
mutate "хук может получить нулевую длительность" \
  'max(hook_until - 0.2, 0.5)' \
  'hook_until - 0.2'
mutate "нулевое окно строки не отбрасывается" \
  'if start >= duration or end <= start:' \
  'if start >= duration:'
mutate "отброшенная строка обрывает остальные" \
  'if start >= duration or end <= start:
            continue' \
  'if start >= duration or end <= start:
            break'
mutate "полоса шире кадра" \
  'max-width: {width - 140}px' \
  'max-width: {width}px'
mutate "акцент зашит константой" \
  'color: "{accent}", duration: 0.08' \
  'color: "#c8ff2e", duration: 0.08'
mutate "полоса игнорирует band_top" \
  'top: {band_top}px' \
  'top: 1360px'

mutate "расширение судится с учётом регистра (.MP4 пойдёт на перекодирование)" \
  'if src.suffix.lower() == ".mp4":' \
  'if src.suffix == ".mp4":'
mutate "любой файл копируется как есть, без переупаковки" \
  'if src.suffix.lower() == ".mp4":' \
  'if True:'
mutate "провал переупаковки принимается за успех" \
  'if remux.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:' \
  'if True:'
mutate "пустой результат переупаковки принимается за успех" \
  'if remux.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:' \
  'if remux.returncode == 0:'

echo
echo "мутантов: $N, пойманных: $CAUGHT, НЕ пойманных: $MISSED"
[ "$MISSED" -eq 0 ]
