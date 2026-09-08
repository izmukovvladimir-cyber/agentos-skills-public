#!/usr/bin/env python3
"""mark_shown.py — write-side дедупа: фиксирует показанные посты в историю.

Документированный шаг SKILL.md 05:00. Запускать ПОСЛЕ сборки packs/, перед/после
send_morning_digest.py. Запуск ТОЛЬКО через .venv-embed/bin/python (нужен fastembed).

Что делает по каждому pack_*.json:
  1. Достаёт shortcode из editor_brief / carousel (URL .../reel/<sc>/ или .../p/<sc>/ —
     контракт SKILL гарантирует РЕФЕРЕНС-URL в editor_brief).
  2. Тему (caption) берёт из дедупленных пулов (_reels_deduped/_carousels_deduped);
     fallback — topic + первые строки card.
  3. reels_seen.json: shortcode -> {status:"shown", date}. MERGE — не затирает уже
     стоящие taken/shot/rejected (фидбек владельца сильнее).
  4. themes_seen.json: append {shortcode, username, date, theme_text, embedding, kind}.
     Идемпотентно — shortcode с уже записанной темой пропускается.

Без этого шага theme-дедуп слеп: история тем не накапливается.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_embed
import lib_paths

log = logging.getLogger("mark_shown")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SKILL_DIR = lib_paths.SKILL_DIR
WATCHLIST_FILE = lib_paths.config_file()
# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy paths.
CACHE_DIR = lib_paths.cache_dir()
SEEN_FILE = CACHE_DIR / "reels_seen.json"
THEMES_FILE = CACHE_DIR / "themes_seen.json"

POOL_DIR = lib_paths.pool_dir()
REELS_DEDUPED = POOL_DIR / "_reels_deduped.json"
CAROUSELS_DEDUPED = POOL_DIR / "_carousels_deduped.json"
DEFAULT_PACKS_DIR = lib_paths.packs_dir()  # board #56: same canonical packs the digest ships (owner→SKILL_DIR/packs), not stale pool/packs

MSK = timezone(timedelta(hours=3))
# instagram.com/reel/<sc>/ или /p/<sc>/ или /reels/<sc>/
URL_RE = re.compile(r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)", re.IGNORECASE)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("cannot read %s (%s) — using default", path, e)
        return default


def _load_history_strict(path: Path, expected_type: type, label: str) -> tuple[Any, bool]:
    """Загрузка живого файла истории. Возвращает (value, ok).

    missing → (default, True): первый запуск, начинаем с нуля.
    valid → (value, True). существует но битый/неверный тип → (None, False):
    caller ОБЯЗАН прервать запись, иначе _atomic_write перезапишет живой файл
    <agent> пустышкой и потеряет статусы taken/shot/rejected.
    """
    default = expected_type()
    if not path.exists():
        return default, True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.error("%s существует но нечитаем (%s) — ОТМЕНА записи (риск потери данных)", label, e)
        return None, False
    if not isinstance(data, expected_type):
        log.error("%s существует но не %s — ОТМЕНА записи (риск потери данных)", label, expected_type.__name__)
        return None, False
    return data, True


def _atomic_write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _pool_caption_map() -> dict[str, dict[str, str]]:
    """shortcode -> {caption, username, kind} из дедупленных пулов."""
    out: dict[str, dict[str, str]] = {}
    for path, kind in ((REELS_DEDUPED, "reel"), (CAROUSELS_DEDUPED, "carousel")):
        loaded = _load_json(path, [])
        if not isinstance(loaded, list):
            log.warning("%s не список — пропускаю", path.name)
            continue
        for item in loaded:
            if not isinstance(item, dict):
                continue
            sc = item.get("code") or item.get("shortcode") or (item.get("raw") or {}).get("code")
            if not sc:
                continue
            raw = item.get("raw") or {}
            out[sc] = {
                "caption": (raw.get("caption") or item.get("caption") or "").strip(),
                "username": item.get("username") or "",
                "kind": kind,
            }
    return out


def _extract_shortcodes(pack: dict[str, Any]) -> list[str]:
    """Все shortcode из текстовых полей пака (editor_brief — обязательный REFERENCE-URL)."""
    blob = " ".join(
        str(pack.get(f) or "") for f in ("editor_brief", "carousel", "card", "url", "shortcode")
    )
    seen: list[str] = []
    for m in URL_RE.findall(blob):
        if m not in seen:
            seen.append(m)
    # допускаем явное поле shortcode без URL
    explicit = pack.get("shortcode")
    if explicit and explicit not in seen:
        seen.append(explicit)
    return seen


def main() -> int:
    # ПЕРВОЙ строкой, до разбора аргументов и до любого чтения: под системным python3 скрипт
    # падал на импорте fastembed уже ПОСЛЕ того, как подборка ушла клиенту, и история дедупа
    # не обновлялась вовсе. Перезапуск возвращает управление сюда же, но в нужном интерпретаторе.
    lib_embed.reexec_in_venv(Path(__file__))
    ap = argparse.ArgumentParser(description="record shown reels/carousels into dedup history")
    ap.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS_DIR)
    ap.add_argument("--dry-run", action="store_true", help="не писать историю")
    args = ap.parse_args()

    if not args.packs_dir.exists():
        log.error("packs dir not found: %s", args.packs_dir)
        return 1
    packs = sorted(args.packs_dir.glob("pack_*.json"))
    if not packs:
        log.error("no pack_*.json in %s", args.packs_dir)
        return 1

    cfg = _load_json(WATCHLIST_FILE, {})
    model = cfg.get("limits", {}).get("theme_model", lib_embed.DEFAULT_MODEL)

    pool_map = _pool_caption_map()
    # strict-загрузка живой истории: битый существующий файл → прерываем БЕЗ записи,
    # иначе перезапишем reels_seen.json <agent> пустышкой и потеряем taken/shot/rejected.
    # Первичное чтение — только чтобы решить какие темы эмбеддить (что ещё не в истории).
    # Эмбеддинг медленный (~20с загрузка модели) → делаем ДО финального чтения, чтобы
    # окно гонки read-modify-write было миллисекундным, а не на всё время эмбеддинга.
    _, ok_seen0 = _load_history_strict(SEEN_FILE, dict, "reels_seen.json")
    themes0, ok_themes0 = _load_history_strict(THEMES_FILE, list, "themes_seen.json")
    if not (ok_seen0 and ok_themes0):
        log.error("история повреждена — прерываю без записи, проверь файлы вручную")
        return 1
    themed_codes0 = {t.get("shortcode") for t in themes0 if isinstance(t, dict) and t.get("shortcode")}

    today = datetime.now(MSK).strftime("%Y-%m-%d")

    # собрать (shortcode, username, theme_text, kind) по всем пакам
    to_record: list[dict[str, str]] = []
    for pf in packs:
        pack = _load_json(pf, {})
        if not isinstance(pack, dict):
            log.warning("bad pack %s — skip", pf.name)
            continue
        codes = _extract_shortcodes(pack)
        if not codes:
            log.warning("no shortcode in %s — skip", pf.name)
            continue
        for sc in codes:
            info = pool_map.get(sc, {})
            theme_text = info.get("caption") or (
                f"{pack.get('topic', '')} {(pack.get('card') or '')[:200]}".strip()
            )
            to_record.append({
                "shortcode": sc,
                "username": info.get("username") or pack.get("author_username") or "",
                "theme_text": theme_text,
                "kind": info.get("kind") or "reel",
            })

    # эмбеддинг новых тем (медленно) — заранее, до финального чтения истории
    fresh = [r for r in to_record if r["shortcode"] not in themed_codes0 and r["theme_text"].strip()]
    vecs = lib_embed.embed_texts([r["theme_text"] for r in fresh], model)
    new_theme_entries: list[dict[str, Any]] = []
    for r, vec in zip(fresh, vecs):
        if not vec:
            continue
        new_theme_entries.append({
            "shortcode": r["shortcode"],
            "username": r["username"],
            "date": today,
            "kind": r["kind"],
            "theme_text": r["theme_text"][:512],
            "embedding": vec,
        })

    if args.dry_run:
        log.info("[DRY-RUN] packs=%d records=%d would +seen<=%d +themes=%d (model=%s)",
                 len(packs), len(to_record), len(to_record), len(new_theme_entries), model)
        return 0

    # ПОВТОРНОЕ чтение прямо перед записью — закрывает гонку: пока шёл эмбеддинг, другой
    # процесс/<agent> мог проставить taken/shot/rejected. Мержим в свежую копию, abort при порче.
    seen, ok_seen = _load_history_strict(SEEN_FILE, dict, "reels_seen.json")
    themes, ok_themes = _load_history_strict(THEMES_FILE, list, "themes_seen.json")
    if not (ok_seen and ok_themes):
        log.error("история повреждена перед записью — прерываю, чтобы не потерять данные")
        return 1
    themed_now = {t.get("shortcode") for t in themes if isinstance(t, dict) and t.get("shortcode")}

    new_seen = 0
    for r in to_record:
        if r["shortcode"] not in seen:  # не трогаем существующие taken/shot/rejected/shown
            seen[r["shortcode"]] = {"status": "shown", "date": today}
            new_seen += 1

    new_themes = 0
    for e in new_theme_entries:
        if e["shortcode"] not in themed_now:  # идемпотентно даже если тема добавилась во время эмбеддинга
            themes.append(e)
            themed_now.add(e["shortcode"])
            new_themes += 1

    _atomic_write(SEEN_FILE, seen)
    _atomic_write(THEMES_FILE, themes)
    log.info("packs=%d records=%d +seen=%d +themes=%d → %s (%d codes), %s (%d themes)",
             len(packs), len(to_record), new_seen, new_themes,
             SEEN_FILE.name, len(seen), THEMES_FILE.name, len(themes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
