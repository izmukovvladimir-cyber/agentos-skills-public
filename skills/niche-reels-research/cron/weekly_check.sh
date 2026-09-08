#!/usr/bin/env bash
# weekly_check.sh — feedback-loop archive --check.
# Запускается воскресенье 09:00 МСК: подтягивает live-метрики для всех записей
# старше 7 дней, ставит verdict залетел/не залетел, каждые 30 циклов
# обновляет factor_impact.json.

set -euo pipefail

SKILL_DIR="~/.claude/skills/niche-reels-research"
LOG_DIR="$SKILL_DIR/logs"
mkdir -p "$LOG_DIR"
STAMP=$(date +%Y-%m-%d)
LOG="$LOG_DIR/weekly_check_${STAMP}.log"

exec > >(tee -a "$LOG") 2>&1

echo "=== niche-reels weekly check · $(date -Is) ==="

cd "$SKILL_DIR/scripts"
python3 archive.py --check

echo "=== done · $(date -Is) ==="
