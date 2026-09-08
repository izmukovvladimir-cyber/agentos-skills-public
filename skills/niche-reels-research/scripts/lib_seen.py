#!/usr/bin/env python3
"""lib_seen.py — единый загрузчик истории показанных постов (reels_seen.json).

ОДИН источник для score.py (рилсы) и pull_carousels.py (карусели): любой
shortcode, попавший в cache/reels_seen.json (статус shown / taken / rejected —
ЛЮБОЙ), больше НИКОГДА не показываем повторно («старое не показываю никогда»).

Раньше seen-фильтр жил в dedupe_filter.py, но тот не подключён к cron
(daily_morning_auto.sh) → показанное вчера всплывало снова. Фильтр перенесён в
живой пайплайн (score.py + pull_carousels.py), а логика чтения истории
вынесена сюда, чтобы парсер был ОДИН (иначе дублирование = дублирование багов).

reels_seen.json пишет mark_shown.py. Этот модуль только ЧИТАЕТ.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("lib_seen")

import lib_paths

SKILL_DIR = lib_paths.SKILL_DIR
# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy path.
SEEN_FILE = lib_paths.cache_dir() / "reels_seen.json"


def load_seen_codes(path: Path | None = None) -> set[str]:
    """Множество всех shortcode из reels_seen.json (любой статус).

    Битый/отсутствующий файл → пустое множество (фильтр становится no-op,
    прогон не падает). Любой не-dict верхний уровень тоже трактуем как пусто.
    """
    p = path or SEEN_FILE
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("lib_seen: cannot read %s (%s) — treating as empty", p, e)
        return set()
    if not isinstance(data, dict):
        log.warning("lib_seen: %s is not a dict — treating as empty", p)
        return set()
    return {str(k) for k in data.keys() if k}
