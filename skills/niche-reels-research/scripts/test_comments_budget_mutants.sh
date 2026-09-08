#!/bin/bash
# Мутационный прогон бюджета комментов в score.py (заявка <agent>, ).
# Мутант считается ПОЙМАННЫМ только если набор ДОШЁЛ до итоговой строки и там FAIL>0.
# Набор, умерший до итога, поймавшим не считается — иначе любой синтаксический мусор
# «ловится» и прогон перестаёт что-либо значить.
set -uo pipefail
cd "$(dirname "$0")"
SRC=score.py
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"; cp -a "$TMP.orig" "$SRC" 2>/dev/null; rm -f "$TMP.orig"' EXIT
cp -a "$SRC" "$TMP.orig"

baseline=$(python3 test_comments_budget.py 2>/dev/null | grep -oP 'FAIL=\d+' | tail -1)
if [ "$baseline" != "FAIL=0" ]; then
  echo "БАЗА НЕ ЗЕЛЁНАЯ ($baseline) — мутационный прогон бессмыслен"; exit 2
fi
echo "база: $baseline"

CAUGHT=0; MISSED=0; N=0
mutate() {
  local name="$1" old="$2" new="$3"
  N=$((N+1))
  cp -a "$TMP.orig" "$SRC"
  if ! grep -qF -- "$old" "$SRC"; then
    echo "  ЯКОРЬ НЕ НАЙДЕН: $name"; MISSED=$((MISSED+1)); return
  fi
  python3 - "$SRC" "$old" "$new" <<'PY'
import sys
p, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p, encoding='utf-8').read()
open(p, 'w', encoding='utf-8').write(s.replace(old, new, 1))
PY
  out=$(python3 test_comments_budget.py 2>/dev/null | grep -oP 'FAIL=\d+' | tail -1)
  if [ -z "$out" ]; then
    echo "  НЕ ПОЙМАН (набор не дошёл до итога): $name"; MISSED=$((MISSED+1))
  elif [ "$out" = "FAIL=0" ]; then
    echo "  НЕ ПОЙМАН: $name"; MISSED=$((MISSED+1))
  else
    CAUGHT=$((CAUGHT+1))
  fi
  cp -a "$TMP.orig" "$SRC"
}

mutate "дефолт бюджета обнулён" 'COMMENTS_BUDGET_DEFAULT_S = 300.0' 'COMMENTS_BUDGET_DEFAULT_S = 0.0'
mutate "потолок снят" 'COMMENTS_BUDGET_MAX_S = 3600.0' 'COMMENTS_BUDGET_MAX_S = 10.0**12'
mutate "ноль проходит как бюджет" 'if not math.isfinite(val) or val <= 0:' 'if not math.isfinite(val) or val < 0:'
mutate "isfinite снят (inf/nan проходят)" 'if not math.isfinite(val) or val <= 0:' 'if val <= 0:'
mutate "срез потолка не делается" '        return COMMENTS_BUDGET_MAX_S' '        return val'
mutate "битое значение возвращается как есть" '        log.warning("%s=%r не число, беру дефолт %.0f с",
                    COMMENTS_BUDGET_ENV, raw, COMMENTS_BUDGET_DEFAULT_S)
        return COMMENTS_BUDGET_DEFAULT_S' '        log.warning("%s=%r не число, беру дефолт %.0f с",
                    COMMENTS_BUDGET_ENV, raw, COMMENTS_BUDGET_DEFAULT_S)
        return 0.0'
mutate "предупреждение о битом env приглушено" '        log.warning("%s=%r не число, беру дефолт %.0f с",' '        log.debug("%s=%r не число, беру дефолт %.0f с",'
mutate "предупреждение о срезе приглушено" '        log.warning("%s=%r выше потолка, срезаю до %.0f с",' '        log.debug("%s=%r выше потолка, срезаю до %.0f с",'
mutate "предупреждение о невалидном приглушено" '        log.warning("%s=%r вне разумного (нужно положительное число), беру дефолт %.0f с",' '        log.debug("%s=%r вне разумного (нужно положительное число), беру дефолт %.0f с",'
mutate "env не читается вовсе" '    raw = src.get(COMMENTS_BUDGET_ENV)' '    raw = None'
mutate "os.environ подменён пустым" '    src = os.environ if env is None else env' '    src = {} if env is None else env'
mutate "дедлайн в fetch_comments не сверяется" '        if left is not None and left <= 0:' '        if False:'
mutate "дедлайн страницы сдвинут" '        if left is not None and left <= 0:' '        if left is not None and left <= -10**9:'
mutate "признак усечения не поднимается" '            budget_hit = True
            log.debug("comments: бюджет исчерпан на %s' '            budget_hit = False
            log.debug("comments: бюджет исчерпан на %s'
mutate "усечение всегда ложь на выходе" '    return texts[:COMMENT_FETCH_LIMIT], budget_hit' '    return texts[:COMMENT_FETCH_LIMIT], False'
mutate "таймаут запроса не режется остатком" '        call_timeout = HIKER_TIMEOUT_S if left is None else min(HIKER_TIMEOUT_S, left)' '        call_timeout = HIKER_TIMEOUT_S'
mutate "таймаут в вызов не передаётся" 'data = hiker_call("/v2/media/comments", params, timeout=call_timeout)' 'data = hiker_call("/v2/media/comments", params)'
mutate "пауза тратится после исчерпания" '        if deadline is not None and time.monotonic() >= deadline:
            # Пауза между страницами' '        if False:
            # Пауза между страницами'
mutate "частичные не считаются" '            comments_partial += 1' '            pass'
mutate "итог игнорирует частичные" '    if comments_skipped or comments_partial:' '    if comments_skipped:'
mutate "main не строит дедлайн" '    deadline = time.monotonic() + budget_s' '    deadline = time.monotonic() + 10.0**12'
mutate "main не зовёт бюджет" '    budget_s = comments_budget_s()' '    budget_s = 10.0**12'
mutate "main не передаёт дедлайн в fetch" 'fetch_comments(s["media_pk"], s["code"], deadline=deadline)' 'fetch_comments(s["media_pk"], s["code"])'
mutate "пометка пропуска не ставится" '            s["score_breakdown"]["extras"]["comments_skipped"] = True' '            s["score_breakdown"]["extras"]["comments_skipped_x"] = True'
mutate "пометка обработанного не ставится" '        s["score_breakdown"]["extras"]["comments_skipped"] = bool(budget_hit)' '        pass'
mutate "усечённый помечается проверенным" '        s["score_breakdown"]["extras"]["comments_skipped"] = bool(budget_hit)' '        s["score_breakdown"]["extras"]["comments_skipped"] = False'
mutate "поля пропущенного не обнуляются" '            s["score_breakdown"]["extras"]["trigger_comments_n"] = 0' '            s["score_breakdown"]["extras"]["trigger_comments_n_x"] = 0'
mutate "громкая строка про исчерпание убрана" '            "БЮДЖЕТ КОММЕНТОВ ИСЧЕРПАН (%.0f с): не проверены вовсе %d, проверены "' '            "comments budget spent (%.0f s): %d "'
mutate "громкая строка приглушена до info" '        log.warning(
            "БЮДЖЕТ КОММЕНТОВ ИСЧЕРПАН' '        log.info(
            "БЮДЖЕТ КОММЕНТОВ ИСЧЕРПАН'
mutate "строка не называет непроверенное" 'комментах, это непроверенное. Поднять бюджет: "
            "%s=<секунды> (потолок %.0f).' 'комментах. Поднять бюджет."
            "%.0s%.0s'
mutate "строка не называет общее число" '"частично %d, всего кандидатов %d. У них отсутствие бонуса НЕ означает "' '"частично %d. У них отсутствие бонуса НЕ означает %.0s"'
mutate "проверка дедлайна в цикле кандидатов снята" '        if time.monotonic() >= deadline:
            # Пропуск помечается' '        if False:
            # Пропуск помечается'

mutate "резолв не судится бюджетом" '        if left is not None and left <= 0:
            log.debug("comments: бюджет исчерпан до резолва pk для %s", code)
            return [], True' '        if False:
            log.debug("comments: бюджет исчерпан до резолва pk для %s", code)
            return [], True'
mutate "таймаут резолва не урезан остатком" '            code, timeout=HIKER_TIMEOUT_S if left is None else min(HIKER_TIMEOUT_S, left))' '            code, timeout=HIKER_TIMEOUT_S)'
mutate "неудачный резолв на исчерпанном бюджете не помечен" '        if not pk and left is not None and time.monotonic() >= deadline:' '        if False:'
mutate "отказ на исчерпанном бюджете не помечен" '            if deadline is not None and time.monotonic() >= deadline:
                budget_hit = True' '            if False:
                budget_hit = True'
mutate "любой отказ объявляется бюджетом" '            if deadline is not None and time.monotonic() >= deadline:
                budget_hit = True' '            if deadline is not None:
                budget_hit = True'
mutate "у резолва отобран параметр таймаута" 'def resolve_pk_from_code(code: str, timeout: float = HIKER_TIMEOUT_S) -> str:' 'def resolve_pk_from_code(code: str, timeout: float = 1.0) -> str:'


mutate "пустая выборка снова зовётся частичной" '            if sampled:
                comments_partial += 1
            else:
                comments_skipped += 1' '            comments_partial += 1'
mutate "пауза тратится после последнего кандидата" '        if deadline is not None and time.monotonic() >= deadline:
            continue
        time.sleep(0.4)' '        time.sleep(0.4)'


echo "----"
echo "мутантов $N, поймано $CAUGHT, НЕ поймано $MISSED"
[ "$MISSED" -eq 0 ] || exit 1
