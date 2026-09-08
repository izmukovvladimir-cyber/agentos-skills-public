#!/usr/bin/env bash
# Мутационный прогон выключателя каруселей (заявка <agent> 19.08).
# Пойман = зелёный baseline + живая строка "PASS n FAIL m>0". Набор неубиваемый,
# поэтому "набор не досчитал" означает сломанного мутанта, а не поимку.
set -uo pipefail
HERE=~/.claude/skills/niche-reels-research/scripts
SRC=$HERE/send_morning_digest.py
SANDBOX=$(mktemp -d /tmp/claude-1000/car-mut.XXXXXX)
trap 'cp "$SANDBOX/orig.py" "$SRC" 2>/dev/null; rm -rf "$SANDBOX"' EXIT
cp "$SRC" "$SANDBOX/orig.py"

run() { (cd "$HERE" && python3 test_carousels_disabled.py 2>&1); }

echo "=== baseline"
BASE=$(run)
grep -qE '^PASS [0-9]+ FAIL 0$' <<<"$BASE" || { echo "BASELINE НЕ ЗЕЛЁНЫЙ:"; tail -5 <<<"$BASE"; exit 1; }
echo "baseline: $(grep -E '^PASS' <<<"$BASE")"

CAUGHT=0; MISSED=0
mutate() {
    local name="$1" frm="$2" to="$3" out
    if ! python3 - "$SANDBOX/orig.py" "$SRC" "$frm" "$to" <<'PY'
import sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
frm, to = sys.argv[3], sys.argv[4]
if src.count(frm) != 1:
    print(f"вхождений {src.count(frm)}", file=sys.stderr); sys.exit(2)
pathlib.Path(sys.argv[2]).write_text(src.replace(frm, to, 1), encoding="utf-8")
PY
    then echo "  СЛОМАН МУТАНТ (фрагмент): $name"; MISSED=$((MISSED+1)); cp "$SANDBOX/orig.py" "$SRC"; return; fi
    if ! python3 -c "import ast,sys;ast.parse(open(sys.argv[1],encoding='utf-8').read())" "$SRC" 2>/dev/null; then
        echo "  СЛОМАН МУТАНТ (синтаксис): $name"; MISSED=$((MISSED+1)); cp "$SANDBOX/orig.py" "$SRC"; return
    fi
    out=$(run)
    if grep -qE '^PASS [0-9]+ FAIL [1-9][0-9]*$' <<<"$out"; then
        CAUGHT=$((CAUGHT+1)); echo "  пойман: $name"
    else
        MISSED=$((MISSED+1)); echo "  НЕ ПОЙМАН: $name  [$(grep -E '^PASS' <<<"$out" || echo 'набор не досчитал')]"
    fi
    cp "$SANDBOX/orig.py" "$SRC"
}

echo "=== мутанты"
mutate "выключатель срабатывает на любое ложное значение (не только JSON false)" \
'    return limits.get("carousels_enabled") is not False' \
'    return bool(limits.get("carousels_enabled", True))'

mutate "выключатель не читается вовсе (всегда включено)" \
'    return limits.get("carousels_enabled") is not False' \
'    return True'

mutate "выключено по умолчанию при отсутствии ключа" \
'    return limits.get("carousels_enabled") is not False' \
'    return limits.get("carousels_enabled") is True'

mutate "битый конфиг молча выключает карусели" \
'    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return True
    if not isinstance(limits, dict):' \
'    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return False
    if not isinstance(limits, dict):'

mutate "limits не объект — падение вместо безопасного значения" \
'    if not isinstance(limits, dict):
        return True
    return limits.get("carousels_enabled") is not False' \
'    return limits.get("carousels_enabled") is not False'

mutate "отсутствие файла всегда норма (сбой скрейпа тонет)" \
'        return None if required else {}   # ручной прогон без свежего скрейпа' \
'        return {}   # ручной прогон без свежего скрейпа'

mutate "отсутствие файла всегда сбой (исходный дефект заявки)" \
'        return None if required else {}   # ручной прогон без свежего скрейпа' \
'        return None   # ручной прогон без свежего скрейпа'

mutate "битый существующий файл при выключенных читается как пустой" \
'    if not isinstance(data, list):
        return None' \
'    if not isinstance(data, list):
        return {}'

mutate "флаг не доходит до бэкстопа" \
'        car_prot = _protected_codes(CAROUSELS_SCORED_FILE, required=car_required)' \
'        car_prot = _protected_codes(CAROUSELS_SCORED_FILE)'

mutate "флаг гасит и рилсовый файл тоже" \
'        reels_prot = _protected_codes(SCORED_FILE)' \
'        reels_prot = _protected_codes(SCORED_FILE, required=car_required)'

mutate "guard минимума шумит и при выключенных каруселях" \
'    carousel_short = car_on and len(carousels) < cmin' \
'    carousel_short = len(carousels) < cmin'

mutate "guard минимума замолчал совсем" \
'    carousel_short = car_on and len(carousels) < cmin' \
'    carousel_short = False'

mutate "факт выключения не называется в сводке" \
'    car_off_line = ("" if car_on else' \
'    car_off_line = ("" if True else'

mutate "строка про выключение печатается всегда" \
'    car_off_line = ("" if car_on else' \
'    car_off_line = ("" if False else'

mutate "минимум каруселей теряет перехват кривого limits" \
'    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return CAROUSEL_MIN_FALLBACK' \
'    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return CAROUSEL_MIN_FALLBACK'

echo
echo "ИТОГО: поймано $CAUGHT, не поймано $MISSED"
[[ $MISSED -eq 0 ]] || exit 1
