#!/usr/bin/env bash
# daily_morning_auto.sh — авто-часть утреннего pipeline niche-reels.
#
# Шаги (06:00 МСК пн-пт):
#   1) pull_reels.py        — забор свежих рилсов (окно 48ч) со всех аккаунтов config
#   2) score.py             — скоринг + freshness-gate 24/48ч (рилсы)
#   2b) pull_carousels.py   — карусели (media_type 8, окно 5 дней, скоринг по лайкам)
#   3) download_thumbs.py   — превью топа рилсов (из _scored.json) + каруселей
#   4) telegram-notify <agent> (через <agent>-bot) — топ рилсов + каруселей
#
# <agent> (claude-code agent в <agent> workspace) дальше делает руками:
#   - визуальный фильтр (отсев не-разговорных)
#   - transcribe.py для отобранных
#   - рерайт каждого пакета (телесуфлёр + ТЗ монтажёру), кладёт в packs/
#   - send_morning_digest.py (отправит уже от своего имени, шлёт владелец)
#
# Failure modes:
#   - HikerAPI вернул пусто → шлём <agent> warning, не блокируем
#   - Groq упал → не наша проблема на этом этапе (transcribe запускает <agent>)

set -euo pipefail

SKILL_DIR="~/.claude/skills/niche-reels-research"
SCRIPTS_DIR="$SKILL_DIR/scripts"
LOG_DIR="$SKILL_DIR/logs"
TOP10="/tmp/expand_pool/reels/_top10.json"

mkdir -p "$LOG_DIR"
STAMP=$(date +%Y-%m-%d_%H-%M)
LOG="$LOG_DIR/daily_${STAMP}.log"

exec > >(tee -a "$LOG") 2>&1

echo "=== niche-reels daily auto · $(date -Is) ==="

# Single-instance guard: 06:00 МСК cron-скрейп и 07:00 self-heal (daria-morning-trigger)
# не должны идти одновременно — иначе двойной платный проход по HikerAPI. flock -n:
# если другой экземпляр держит лок, выходим сразу (тот допишет данные сам).
LOCK_DIR="~/var/lib/niche-reels"
mkdir -p "$LOCK_DIR"
exec 9>>"$LOCK_DIR/daily_morning_auto.lock"
if ! flock -n 9; then
    echo "SKIP: another daily_morning_auto.sh holds the lock — exit 0"
    exit 0
fi

cd "$SCRIPTS_DIR"

run_step() {
    local name="$1"
    shift
    echo ""
    echo "--- step: $name ---"
    if timeout 1800 "$@"; then
        echo "$name OK"
        return 0
    else
        local rc=$?
        echo "$name FAILED rc=$rc"
        return $rc
    fi
}

# 1. pull
if ! run_step "pull_reels" python3 pull_reels.py; then
    echo "ABORT: pull_reels failed"
    exit 10
fi

# 2. score (рилсы: freshness-gate 24/48ч)
if ! run_step "score" python3 score.py; then
    echo "WARN: score failed, продолжаем без скоринга"
fi

# 2b. карусели (media_type 8, окно 5 дней — у каруселей своя свежесть)
if ! run_step "pull_carousels" python3 pull_carousels.py; then
    echo "WARN: pull_carousels failed, продолжаем без каруселей"
fi

# 3. thumbs (рилсы из _scored.json + карусели из _carousels_top.json)
if ! run_step "download_thumbs" python3 download_thumbs.py; then
    echo "WARN: thumbs failed, продолжаем"
fi

# 4. notify <agent>
# Токен бота и chat id получателя берутся из окружения.
TOKEN="${TELEGRAM_BOT_TOKEN:-}"
NOTIFY_CHAT_ID="${TELEGRAM_CHAT_ID:-0}"  # chat id, куда падает уведомление

if [[ -z "$TOKEN" ]]; then
    echo "WARN: TELEGRAM_BOT_TOKEN not set — skip notify"
    exit 0
fi

count_json() { [[ -f "$1" ]] && python3 -c "import json,sys; print(len(json.load(open('$1'))))" || echo 0; }
COUNT=$(count_json "/tmp/expand_pool/reels/_top15.json")
CCOUNT=$(count_json "/tmp/expand_pool/reels/_carousels_top15.json")

MSG="🎬 niche-reels: утренняя выборка готова

Рилсов: ${COUNT} (свежесть <=48ч) · Каруселей: ${CCOUNT} (свежесть <=5д)
Превью: /tmp/expand_pool/reels/thumbs/ (рилсы NN_, карусели cNN_)
Рилсы: _top15.json · Карусели: _carousels_top15.json
Лог:  $LOG

<agent>: визуальный фильтр → transcribe.py для топ рилсов → рерайт до 10 рилсов + каруселей (МИНИМУМ 5, до 10 — HARD владелец) → send_morning_digest.py к 08:00 МСК."

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${NOTIFY_CHAT_ID}" \
    --data-urlencode "text=${MSG}" \
    --data-urlencode "disable_web_page_preview=true" \
    > /dev/null || echo "WARN: telegram notify failed"

echo ""
echo "=== auto pipeline done · $(date -Is) ==="
