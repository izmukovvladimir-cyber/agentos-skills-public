#!/usr/bin/env bash
# Публикация базы знаний на GitHub Pages.
# Добавил или поправил гайд → `bash deploy.sh`. Всё остальное само.
# Порядок: build.py → selfcheck.py → выкладка site/ в репозиторий Pages.
#
# Все настройки берутся из registry.json, руками здесь править нечего:
#   site.domain            — домен клиента (пишется в CNAME)
#   site.deploy.repo       — https-адрес репозитория Pages
#   site.deploy.branch     — ветка публикации (обычно main)
#   site.deploy.git_user   — имя в коммитах
#   site.deploy.git_email  — почта в коммитах
#
# Первый запуск требует живой авторизации (`gh auth status`), иначе push упрётся
# в запрос пароля. Токен в этот файл не класть НИКОГДА.
set -euo pipefail

HUB="$(cd "$(dirname "$0")" && pwd)"
REG="$HUB/registry.json"
[ -f "$REG" ] || { echo "нет registry.json рядом с deploy.sh" >&2; exit 1; }

cfg() {
    python3 - "$REG" "$1" <<'PY'
import json, sys
site = json.load(open(sys.argv[1], encoding="utf-8"))["site"]
key = sys.argv[2]
value = site.get("domain") if key == "domain" else site.get("deploy", {}).get(key)
if not value:
    label = "site.domain" if key == "domain" else f"site.deploy.{key}"
    sys.exit(f"registry.json: не заполнено {label}")
print(value)
PY
}

DOMAIN="$(cfg domain)"
REPO="$(cfg repo)"
BRANCH="$(cfg branch)"
GIT_USER="$(cfg git_user)"
GIT_EMAIL="$(cfg git_email)"
PUB="$HUB/.deploy/$DOMAIN"

echo "[1/4] сборка"
python3 "$HUB/build.py"

echo "[2/4] самопроверка"
python3 "$HUB/selfcheck.py"

echo "[3/4] синхронизация с репозиторием публикации"
if [ ! -d "$PUB/.git" ]; then
    git clone "$REPO" "$PUB"
fi
cd "$PUB"
git config user.email "$GIT_EMAIL"
git config user.name "$GIT_USER"
git pull --ff-only origin "$BRANCH" 2>/dev/null || true
rsync -a --delete --exclude='.git' "$HUB/site/" "$PUB/"
printf '%s\n' "$DOMAIN" > "$PUB/CNAME"   # держит привязку домена
touch "$PUB/.nojekyll"                    # отдавать папки как есть, без Jekyll

echo "[4/4] коммит и отправка"
git add -A
if git diff --cached --quiet; then
    echo "изменений нет, публиковать нечего"
    exit 0
fi
git commit -m "redeploy knowledge base $(date -u +%FT%TZ)"
git push origin "$BRANCH"
echo "ГОТОВО. GitHub Pages пересоберётся за 1-10 минут. Живой адрес: https://${DOMAIN}/"
