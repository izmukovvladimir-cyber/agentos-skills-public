#!/usr/bin/env python3
"""dedupe_filter.py — pk-дедуп + theme-дедуп пула рилсов и каруселей.

Закрывает документированный в SKILL.md шаг 03:15 (раньше делался <agent> вручную).
Запускать ПОСЛЕ score.py / pull_carousels.py и ПЕРЕД download_thumbs.py.
Запуск ТОЛЬКО через .venv-embed/bin/python (нужен fastembed).

Два слоя фильтрации:
  1. pk-дедуп: shortcode уже в cache/reels_seen.json (любой статус) → выбрасываем.
     «Старое не показываю никогда» (SKILL HARD RULE дедупликации).
  2. theme-дедуп: embedding(caption) кандидата сравнивается с темами уже показанных
     постов за окно theme_dedup_window_days И с темами, уже принятыми в этом прогоне.
     max cosine >= theme_similarity_threshold → выбрасываем (тема повторяется даже
     от другого автора). Кандидаты идут по убыванию скора — остаётся сильнейший
     представитель темы.

Вход:  /tmp/expand_pool/reels/_scored.json            (рилсы от score.py)
       /tmp/expand_pool/reels/_carousels_scored.json  (карусели от pull_carousels.py)
Выход: /tmp/expand_pool/reels/_reels_deduped.json
       /tmp/expand_pool/reels/_carousels_deduped.json
       /tmp/expand_pool/reels/_top10.json          (перегенерён из дедупленных рилсов)
       /tmp/expand_pool/reels/_carousels_top.json  (перегенерён из дедупленных каруселей)

reels_seen.json пишет mark_shown.py (статус shown финальных постов). themes_seen.json
тоже пишет mark_shown.py. dedupe_filter ТОЛЬКО читает обе истории.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_embed

log = logging.getLogger("dedupe_filter")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SKILL_DIR = Path(__file__).resolve().parent.parent
WATCHLIST_FILE = SKILL_DIR / "config" / "watchlist.json"
CACHE_DIR = SKILL_DIR / "cache"
SEEN_FILE = CACHE_DIR / "reels_seen.json"
THEMES_FILE = CACHE_DIR / "themes_seen.json"

POOL_DIR = Path("/tmp/expand_pool/reels")
REELS_IN = POOL_DIR / "_scored.json"
CAROUSELS_IN = POOL_DIR / "_carousels_scored.json"
REELS_OUT = POOL_DIR / "_reels_deduped.json"
CAROUSELS_OUT = POOL_DIR / "_carousels_deduped.json"
TOP10_FILE = POOL_DIR / "_top10.json"
CAROUSELS_TOP_FILE = POOL_DIR / "_carousels_top.json"

MSK = timezone(timedelta(hours=3))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("cannot read %s (%s) — using default", path, e)
        return default


def _shortcode(item: dict[str, Any]) -> str | None:
    return item.get("code") or item.get("shortcode") or (item.get("raw") or {}).get("code")


def _caption(item: dict[str, Any]) -> str:
    raw = item.get("raw") or {}
    return (raw.get("caption") or item.get("caption") or "").strip()


def _seen_codes(seen: dict[str, Any]) -> set[str]:
    """Все shortcode из reels_seen.json — показанное не возвращаем (любой статус)."""
    return set(seen.keys())


def _themes_in_window(themes: list[dict[str, Any]], window_days: int) -> list[dict[str, Any]]:
    """Темы за последние window_days (по полю date YYYY-MM-DD). Без date — пропускаем."""
    cutoff = (datetime.now(MSK) - timedelta(days=window_days)).date()
    out: list[dict[str, Any]] = []
    for t in themes:
        d = t.get("date")
        if not d:
            continue
        try:
            if datetime.strptime(d, "%Y-%m-%d").date() >= cutoff:
                out.append(t)
        except ValueError:
            continue
    return out


def dedupe(
    candidates: list[dict[str, Any]],
    seen_codes: set[str],
    history_vecs: list[list[float]],
    threshold: float,
    model: str,
    kind: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """pk + theme дедуп одного пула. candidates ОТСОРТИРОВАНЫ по убыванию скора.

    Возвращает (accepted, stats). accepted сохраняют исходный порядок (по скору).
    """
    stats = {"in": len(candidates), "bad_entry": 0, "pk_dropped": 0, "no_caption": 0, "theme_dropped": 0}

    # 1) pk-дедуп (битые не-dict записи пропускаем, чтобы не ронять прогон)
    after_pk: list[dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            stats["bad_entry"] += 1
            continue
        sc = _shortcode(c)
        if sc and sc in seen_codes:
            stats["pk_dropped"] += 1
            continue
        after_pk.append(c)

    # 2) theme-дедуп. Эмбеддим caption разом (один прогон модели).
    captions = [_caption(c) for c in after_pk]
    cand_vecs = lib_embed.embed_texts(captions, model)

    accepted: list[dict[str, Any]] = []
    accepted_vecs: list[list[float]] = []
    for c, cap, vec in zip(after_pk, captions, cand_vecs):
        if not cap or not vec:
            # нет темы для сравнения — пропускаем фильтр, но помечаем
            stats["no_caption"] += 1
            accepted.append(c)
            continue
        pool = history_vecs + accepted_vecs
        mc = lib_embed.max_cosine(vec, pool)
        if mc >= threshold:
            stats["theme_dropped"] += 1
            log.info("  [%s] theme-dup %.3f >= %.2f: @%s %s — %r",
                     kind, mc, threshold, c.get("username"), _shortcode(c), cap[:60])
            continue
        accepted.append(c)
        accepted_vecs.append(vec)

    stats["out"] = len(accepted)
    return accepted, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="pk + theme dedup for niche-reels pool")
    ap.add_argument("--dry-run", action="store_true", help="не писать выходные файлы")
    args = ap.parse_args()

    cfg = _load_json(WATCHLIST_FILE, {})
    limits = cfg.get("limits", {})
    window_days = int(limits.get("theme_dedup_window_days", 21))
    threshold = float(limits.get("theme_similarity_threshold", 0.85))
    model = limits.get("theme_model", lib_embed.DEFAULT_MODEL)
    top_reels_n = int(limits.get("thumbs_review_n", 15))
    top_carousels_n = int(limits.get("thumbs_review_n", 15))

    seen = _load_json(SEEN_FILE, {})
    seen_codes = _seen_codes(seen if isinstance(seen, dict) else {})

    themes_all = _load_json(THEMES_FILE, [])
    if not isinstance(themes_all, list):
        themes_all = []
    themes_win = _themes_in_window(themes_all, window_days)
    # валидируем embedding из истории — битый (строка/dict/смешанный) пропускаем, иначе cosine упадёт
    history_vecs = [t["embedding"] for t in themes_win if lib_embed.is_vector(t.get("embedding"))]
    skipped_bad = sum(1 for t in themes_win if t.get("embedding") and not lib_embed.is_vector(t.get("embedding")))
    if skipped_bad:
        log.warning("themes_seen: %d записей с битым embedding пропущено", skipped_bad)
    log.info("history: %d themes total, %d in %dd window, %d with embedding; seen_codes=%d; thr=%.2f model=%s",
             len(themes_all), len(themes_win), window_days, len(history_vecs), len(seen_codes), threshold, model)

    reels = _load_json(REELS_IN, [])
    carousels = _load_json(CAROUSELS_IN, [])
    if not isinstance(reels, list):
        reels = []
    if not isinstance(carousels, list):
        carousels = []

    reels_kept, rstats = dedupe(reels, seen_codes, history_vecs, threshold, model, "reels")
    # карусели дедупим против ТОЙ ЖЕ истории + уже принятых рилсов:
    # тема не должна повторяться между рилсом и каруселью в одной выдаче.
    # пустые caption НЕ эмбеддим — иначе e5 даёт вектор от "query: " и режет карусели зря.
    reel_caps = [_caption(c) for c in reels_kept if isinstance(c, dict) and _caption(c)]
    reels_vecs = lib_embed.embed_texts(reel_caps, model)
    car_history = history_vecs + [v for v in reels_vecs if v]
    carousels_kept, cstats = dedupe(carousels, seen_codes, car_history, threshold, model, "carousels")

    log.info("REELS     %s", rstats)
    log.info("CAROUSELS %s", cstats)

    if args.dry_run:
        log.info("[DRY-RUN] не пишу файлы")
        return 0

    POOL_DIR.mkdir(parents=True, exist_ok=True)
    REELS_OUT.write_text(json.dumps(reels_kept, ensure_ascii=False, indent=2), encoding="utf-8")
    CAROUSELS_OUT.write_text(json.dumps(carousels_kept, ensure_ascii=False, indent=2), encoding="utf-8")
    TOP10_FILE.write_text(json.dumps(reels_kept[:top_reels_n], ensure_ascii=False, indent=2), encoding="utf-8")
    CAROUSELS_TOP_FILE.write_text(json.dumps(carousels_kept[:top_carousels_n], ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("saved: %s (%d), %s (%d), top%d, carousels_top%d",
             REELS_OUT.name, len(reels_kept), CAROUSELS_OUT.name, len(carousels_kept),
             top_reels_n, top_carousels_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
