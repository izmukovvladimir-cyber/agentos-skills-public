#!/usr/bin/env bash
# Мутационные контроли признака «донор формата» (заявка <agent> ).
#
# ПЕСОЧНИЦА ОБЯЗАТЕЛЬНА: правятся КОПИИ скриптов во временном каталоге, боевые
# hook_fidelity_check.py и send_morning_digest.py не трогаются. Тест берётся оттуда же и
# ищет скрипты рядом с собой, поэтому копии кладутся в один каталог с ним.
#
# ПОЙМАННЫМ считается только FAIL=<не ноль>. Упавший или зависший набор от сработавшей
# защиты не отличить, такие исходы идут в BROKEN и требуют правки теста.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES=(hook_fidelity_check.py send_morning_digest.py lib_paths.py test_format_donor.py)
for f in "${FILES[@]}"; do
    [ -f "$DIR/$f" ] || { echo "missing: $DIR/$f" >&2; exit 1; }
done

sandbox=$(mktemp -d)
trap 'rm -rf "$sandbox"' EXIT
caught=0; missed=0; broken=0

prepare() {
    rm -rf "$sandbox/run"; mkdir -p "$sandbox/run"
    for f in "${FILES[@]}"; do cp "$DIR/$f" "$sandbox/run/$f"; done
}

run_suite() {
    ( cd "$sandbox/run" && PYTHONDONTWRITEBYTECODE=1 \
        timeout --kill-after=30s 300s python3 test_format_donor.py 2>&1 ) || true
}

fails_in() {
    local line; line=$(printf '%s\n' "$1" | grep -oE 'FAIL=[0-9]+' | tail -1 || true)
    if [ -z "$line" ]; then echo -1; else echo "${line#FAIL=}"; fi
}

prepare
base_out=$(run_suite); base_fail=$(fails_in "$base_out")
if [ "$base_fail" != "0" ]; then
    echo "BASELINE НЕ ЗЕЛЁНЫЙ (FAIL=$base_fail) — прогон бессмыслен" >&2
    printf '%s\n' "$base_out" | tail -20 >&2; exit 2
fi
echo "baseline: FAIL=0, прогон осмыслен"

mutate() {
    local name="$1" file="$2" old="$3" new="$4"
    prepare
    local f="$sandbox/run/$file"
    if ! python3 - "$f" "$old" "$new" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
if sys.argv[2] not in s:
    sys.exit(3)
p.write_text(s.replace(sys.argv[2], sys.argv[3], 1), encoding="utf-8")
PY
    then
        echo "BROKEN: $name — мутация не применилась (шаблон не найден)"; broken=$((broken+1)); return
    fi
    if cmp -s "$f" "$DIR/$file"; then
        echo "BROKEN: $name — после замены файл совпал с оригиналом"; broken=$((broken+1)); return
    fi
    local out fails; out=$(run_suite); fails=$(fails_in "$out")
    if [ "$fails" = "-1" ]; then
        echo "BROKEN: $name — набор не дошёл до итога"; broken=$((broken+1))
    elif [ "$fails" -gt 0 ]; then
        echo "CAUGHT: $name (FAIL=$fails)"; caught=$((caught+1))
    else
        echo "MISSED: $name — защита снята, тесты зелёные"; missed=$((missed+1))
    fi
}

# ── сам признак ──────────────────────────────────────────────────────────
mutate "признак донора не срабатывает никогда" hook_fidelity_check.py \
    '    if str(pack.get("hook_source", "")).strip().lower() == "format_donor":
        reason = _s(pack.get("hook_source_reason"))' \
    '    if False:
        reason = _s(pack.get("hook_source_reason"))'

# ХУДШАЯ мутация набора: пометка снова снимается свободным вхождением подстроки, то есть
# «НЕ ДОНОР ФОРМАТА» в ТЗ монтажу выключало бы блокирующий гейт.
mutate "пометка ловится подстрокой где угодно" hook_fidelity_check.py \
    '    if not up.startswith(FORMAT_DONOR_MARK):' \
    '    if FORMAT_DONOR_MARK not in up:'

mutate "заявка без причины принимается за донора" hook_fidelity_check.py \
    '        if declared and reason:
            return reason' \
    '        if declared:
            return reason or "без причины"'

mutate "ключ hook_source читается регистрозависимо" hook_fidelity_check.py \
    '    if str(pack.get("hook_source", "")).strip().lower() == "format_donor":
        reason = _s(pack.get("hook_source_reason"))' \
    '    if str(pack.get("hook_source", "")) == "format_donor":
        reason = _s(pack.get("hook_source_reason"))'

mutate "пометка в ТЗ монтажу не читается" hook_fidelity_check.py \
    '    for raw in str(brief or "").splitlines():
        declared, reason = _donor_line(raw)' \
    '    for raw in []:
        declared, reason = _donor_line(raw)'

mutate "заявка без причины проглатывается молча" hook_fidelity_check.py \
    '            if not reason:' \
    '            if False:'

# ── границы пропуска ─────────────────────────────────────────────────────
# Пометка означает «телесуфлёр написан с нуля», а не «его нет».
mutate "донор без телесуфлёра проезжает молча" hook_fidelity_check.py \
    '            if not tele.strip():' \
    '            if False:'

mutate "пропуск донора печатается обычным токеном" hook_fidelity_check.py \
    '        print(f"{DONOR_SKIP_TOKEN} {s}")' \
    '        print(f"[skip] {s}")'

# ── печать причины в сводку клиента ──────────────────────────────────────
mutate "причина не доходит до сводки" send_morning_digest.py \
    '        donor_note = ""
        if donors:' \
    '        donor_note = ""
        if False:'

mutate "донор глушит настоящее нарушение" send_morning_digest.py \
    '        if r.returncode == 0:
            return CheckResult(donor_note)' \
    '        if True:
            return CheckResult(donor_note)'

mutate "сводка не называет число карточек" send_morning_digest.py \
    '{len(donors)} шт.: "' \
    'шт.: "'

mutate "граница маркера не проверяется (склейка проходит)" hook_fidelity_check.py \
    '    if rest[0] != ":" and not rest[0].isspace():
        return False, ""' \
    '    if False:
        return False, ""'

mutate "разделитель после пометки не обязателен" hook_fidelity_check.py \
    '    if rest[0] not in DONOR_SEPARATORS:
        return False, ""                     # «ДОНОР ФОРМАТА НЕ СТАВИТЬ» — не объявление
    return True, rest.lstrip(DONOR_SEPARATORS).strip()' \
    '    return True, rest.lstrip(DONOR_SEPARATORS).strip()'

# ── обрезка причины ──────────────────────────────────────────────────────
mutate "причина режется посреди слова" hook_fidelity_check.py \
    '    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]' \
    '    sp = cut.rfind(" ")
    if False:
        cut = cut[:sp]'

mutate "многоточие вылезает за лимит" hook_fidelity_check.py \
    '    head = s[:limit - 1]' \
    '    head = s[:limit]'

mutate "у длинного слова пропал потолок" hook_fidelity_check.py \
    '    if len(s) <= limit:
        return s' \
    '    if " " not in s[:limit] or len(s) <= limit:
        return s'

echo "----"
echo "CAUGHT=$caught MISSED=$missed BROKEN=$broken"
[ "$missed" -eq 0 ] && [ "$broken" -eq 0 ]
