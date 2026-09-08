# Pipeline scripts

Запуск ежедневный 06:00 МСК → 08:00 МСК.

## Pipeline (порядок)

1. **pull_reels.py** — парсит свежие рилсы за 24h по watchlist (12 аккаунтов из `config/watchlist.json`). Сохраняет в `/tmp/reels_pipeline/<YYYY-MM-DD>/_top3_per_account.json`.

2. **download_thumbs.py** — скачивает первые кадры для топ-15 по просмотрам в `thumbs/`.

3. **Визуальный фильтр (я как агент)** — читаю каждый кадр, отсеваю не-разговорные. Топ-5-7 остаётся.

4. **transcribe.py** — для топ-5: скачивает mp4, извлекает audio через ffmpeg, транскрибирует через Groq Whisper (через curl — обход Cloudflare 1010).

5. **Рерайт (я как агент)** — для каждого транскрипта: перевод RU (если EN), рерайт 20-30%, расстановка пауз, написание ТЗ монтажёру по сценам.

6. **send_morning_digest.py** — формирует сообщения в Telegram chat владелец (HTML `<pre>` блоки + ссылки + комментарии).

## Скрипты которые есть

- `pull_following.py` — расширение watchlist через follow-list (запускается раз в неделю или по требованию)
- `filter_dedup.py` — фильтр + дедуп пула follow-list по нише
- `enrich_followers.py` — дозапрос followers count для топ-N кандидатов
- `pull_reels.py` — ежедневный парсинг рилсов
- `download_thumbs.py` — скачивание первых кадров
- `transcribe.py` — транскрибация через Groq (curl-вариант)

## Скрипты от Кодера

- `score.py` — композитный скоринг по `references/criteria.md` + `config/watchlist.json.scoring`.
  Входит `_top3_per_account.json`, выходит `_scored.json` и `_top10.json`.
  Сам фетчит медиану автора (последние 30 клипов через HikerAPI) и подсчитывает
  триггер-комменты только для рилсов с базовым score >= 30 (экономит лимит).

- `send_morning_digest.py` — финальная отправка в Telegram владелец.
  Контракт: директория `--packs-dir` (default `/tmp/expand_pool/reels/packs/`),
  внутри `pack_01.json` … `pack_05.json` (формат: priority, author_*, topic,
  card, teleprompter, editor_brief, опционально carousel) + опциональный
  `meta.json` с intro/final/date_label. Все code-блоки — `<pre>` HTML.
  `--dry-run` печатает без отправки.

- `archive.py` — feedback-loop.
  - `--new <orig_shortcode> <owner_post_url> [--note "..."]` — пишет JSON в
    `~/.claude/shared/niche-reels-archive/<YYYY-MM>/<orig>__<owner>.json`
    с метриками оригинала из `_scored.json` и check_after_ts = now+7д.
  - `--check` — для записей старше 7д тянет live-метрики owner-постов через
    HikerAPI, ставит verdict (залетел / средне / не залетел), каждые 30
    циклов пишет `factor_impact.json` со сводкой lift по факторам скоринга.
  - `--summary` — принудительно перегенерировать `factor_impact.json`.

- `cron/daily_morning_auto.sh` + `cron/weekly_check.sh` + `cron/crontab.txt` —
  расписание. **Установка одной командой:**
  ```bash
  (crontab -l 2>/dev/null; cat ~/.claude/skills/niche-reels-research/cron/crontab.txt) | crontab -
  crontab -l  # проверь
  ```
  - 06:00 МСК пн-пт = `0 3 * * 1-5` (VPS в UTC, МСК-3) → `daily_morning_auto.sh`
    делает pull + score + thumbs + notify <agent> в Telegram.
  - 09:00 МСК вс = `0 6 * * 0` → `weekly_check.sh` → `archive.py --check`.
  - <agent> после notify сама делает: визуальный фильтр → `transcribe.py` →
    рерайт → `send_morning_digest.py`.

Логи: `~/.claude/skills/niche-reels-research/logs/`.
Секреты: читаются из окружения — `$HIKER_API_KEY`, `$GROQ_API_KEY`,
`$TELEGRAM_BOT_TOKEN` (экспортируются перед запуском скриптов).

## Зависимости

- python 3.10+
- ffmpeg (системный)
- curl (для обхода Cloudflare 1010 у Groq)
- Ключи в переменных окружения: `$HIKER_API_KEY`, `$GROQ_API_KEY`, `$TELEGRAM_BOT_TOKEN`

## Запуск (вручную, до cron)

```bash
cd ~/.claude/skills/niche-reels-research/scripts
python3 pull_reels.py
python3 download_thumbs.py
# я читаю кадры, отсеиваю
python3 transcribe.py
# я делаю рерайт + ТЗ + телесуфлёры
python3 send_morning_digest.py
```

## Стоимость одного утра

- HikerAPI: ~30 запросов (профиль + clips + media-by-code для топ-15)
- Groq Whisper: 5 транскриптов × ~1 мин = $0.01
- Claude (моя работа): 0 (в Max-подписке владелец)

Итого: 5-10 ₽ за утренний прогон. Если каждый день — 100-200 ₽/мес.

## Видение

Сейчас pipeline = 4 скрипта + 2 ручных шага агента (фильтр + рерайт).
Цель: после Pro HikerAPI + cron + Кодера-доработки = 1 cron-задача → пакет в Telegram без участия агента.

владелец в 08:00 видит готовое.
