#!/usr/bin/env python3
"""archive.py — архив адаптированных рилсов + feedback-loop.

Две команды:

1) archive.py --new <orig_shortcode> <owner_post_url> [--note "..."]
   Создаёт запись:
   - находит метрики оригинала в /tmp/expand_pool/reels/_scored.json (или _top10.json)
   - сохраняет JSON в ~/.claude/shared/niche-reels-archive/<YYYY-MM>/<orig>__<owner>.json
   - помечает дату публикации, дату check (now+7д)

2) archive.py --check
   - проходит по всем записям с live_metrics is None и check_after_ts < now
   - дёргает HikerAPI /v2/media/info_by_code для owner-кода
   - считает verdict: ratio = owner_views / orig_views
       >= 0.5 — "залетел"
       0.2-0.5 — "средне"
       < 0.2 — "не залетел"
   - инкрементит счётчик циклов в _meta.json; каждые 30 — пишет сводку
     factor_impact.json (для корректировки весов скоринга).

Лог: stdout + /var/log/niche-reels/archive.log (если writable).
"""
from __future__ import annotations
import os

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

log = logging.getLogger("archive")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

ARCHIVE_ROOT = Path("~/.claude/shared/niche-reels-archive")
META_FILE = ARCHIVE_ROOT / "_meta.json"
IMPACT_FILE = ARCHIVE_ROOT / "factor_impact.json"

HIKER_KEY = os.environ["HIKER_API_KEY"]
HIKER_BASE = "https://api.instagrapi.com"

POOL_DIR = Path("/tmp/expand_pool/reels")
SCORED_FILE = POOL_DIR / "_scored.json"
TOP10_FILE = POOL_DIR / "_top10.json"
TOP3_FILE = POOL_DIR / "_top3_per_account.json"

CHECK_DELAY_DAYS = 7
SUMMARY_EVERY_N = 30
MSK = timezone(timedelta(hours=3))
REEL_CODE_RE = re.compile(r"instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)")


def hiker_call(path: str, params: dict[str, Any]) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{HIKER_BASE}{path}?{qs}",
        headers={"x-access-key": HIKER_KEY, "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode()[:200]}
    except Exception as e:
        return {"_error": str(e)}


def extract_code(url_or_code: str) -> str | None:
    m = REEL_CODE_RE.search(url_or_code)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", url_or_code):
        return url_or_code
    return None


def find_orig(orig_code: str) -> dict[str, Any] | None:
    for f in (SCORED_FILE, TOP10_FILE):
        if not f.exists():
            continue
        for r in json.loads(f.read_text(encoding="utf-8")):
            if r.get("code") == orig_code:
                return r
    if TOP3_FILE.exists():
        for acc in json.loads(TOP3_FILE.read_text(encoding="utf-8")):
            for r in acc.get("reels", []):
                if r.get("code") == orig_code:
                    return {
                        "username": acc.get("username"),
                        "code": orig_code,
                        "url": r.get("url"),
                        "raw": r,
                        "score_breakdown": None,
                        "score_total": None,
                    }
    return None


def fetch_live_metrics(code: str) -> dict[str, Any]:
    data = hiker_call("/v2/media/info_by_code", {"code": code})
    if "_error" in data:
        data = hiker_call("/v1/media/by/code", {"code": code})
    if "_error" in data:
        return {"_error": data["_error"]}
    media = data.get("response", {}).get("media") or data.get("media") or data
    views = media.get("play_count") or media.get("view_count") or media.get("ig_play_count") or 0
    return {
        "views": int(views or 0),
        "likes": int(media.get("like_count") or 0),
        "comments": int(media.get("comment_count") or 0),
        "duration": float(media.get("video_duration") or 0),
        "fetched_at_iso": datetime.now(tz=MSK).isoformat(timespec="seconds"),
    }


def verdict_from_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio >= 0.5:
        return "залетел"
    if ratio >= 0.2:
        return "средне"
    return "не залетел"


def cmd_new(orig_code_in: str, owner_url: str, note: str) -> int:
    orig_code = extract_code(orig_code_in)
    owner_code = extract_code(owner_url)
    if not orig_code:
        log.error("bad orig shortcode: %s", orig_code_in)
        return 1
    if not owner_code:
        log.error("bad owner url/shortcode: %s", owner_url)
        return 1

    orig = find_orig(orig_code) or {
        "username": None,
        "code": orig_code,
        "url": f"https://www.instagram.com/reel/{orig_code}/",
        "raw": {},
        "score_breakdown": None,
        "score_total": None,
    }
    raw = orig.get("raw", {})
    orig_metrics = {
        "views": int(raw.get("play_count") or 0),
        "likes": int(raw.get("like_count") or 0),
        "comments": int(raw.get("comment_count") or 0),
        "duration": float(raw.get("duration") or 0),
        "taken_at": raw.get("taken_at"),
    }

    now_ts = int(time.time())
    record: dict[str, Any] = {
        "orig_shortcode": orig_code,
        "orig_username": orig.get("username"),
        "orig_url": orig.get("url"),
        "orig_metrics": orig_metrics,
        "score_total": orig.get("score_total"),
        "score_breakdown": orig.get("score_breakdown"),
        "owner_shortcode": owner_code,
        "owner_url": owner_url,
        "published_at_ts": now_ts,
        "published_at_iso": datetime.now(tz=MSK).isoformat(timespec="seconds"),
        "check_after_ts": now_ts + CHECK_DELAY_DAYS * 86400,
        "live_metrics": None,
        "verdict": None,
        "ratio_views": None,
        "note": note or "",
    }

    month_dir = ARCHIVE_ROOT / datetime.now(tz=MSK).strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    out_file = month_dir / f"{orig_code}__{owner_code}.json"
    out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("archived → %s", out_file)
    print(json.dumps({"saved": str(out_file), "check_after": record["published_at_iso"]}, ensure_ascii=False))
    return 0


def iter_records() -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    if not ARCHIVE_ROOT.exists():
        return out
    for f in ARCHIVE_ROOT.rglob("*.json"):
        if f.name.startswith("_") or f.name == "factor_impact.json":
            continue
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except Exception as e:
            log.warning("bad record %s: %s", f, e)
    return out


def write_factor_impact(records: list[dict[str, Any]]) -> None:
    """Сводка: для каждого binary-фактора скоринга — mean(ratio) когда был и когда не был."""
    factor_keys = [
        "median_x3", "views_1m", "fresh_48h", "er_5pct",
        "duration_24_60s", "trigger_comments_gt10",
    ]
    per_factor: dict[str, dict[str, list[float]]] = {
        k: {"with": [], "without": []} for k in factor_keys
    }
    closed = [r for r in records if r.get("ratio_views") is not None]
    for r in closed:
        sb = r.get("score_breakdown") or {}
        ratio = r["ratio_views"]
        for k in factor_keys:
            bucket = "with" if (sb.get(k) or 0) > 0 else "without"
            per_factor[k][bucket].append(ratio)
    impact: dict[str, dict[str, Any]] = {}
    for k, buckets in per_factor.items():
        impact[k] = {
            "n_with": len(buckets["with"]),
            "n_without": len(buckets["without"]),
            "mean_ratio_with": round(mean(buckets["with"]), 3) if buckets["with"] else None,
            "mean_ratio_without": round(mean(buckets["without"]), 3) if buckets["without"] else None,
        }
        if impact[k]["mean_ratio_with"] is not None and impact[k]["mean_ratio_without"] is not None:
            impact[k]["lift"] = round(impact[k]["mean_ratio_with"] - impact[k]["mean_ratio_without"], 3)
    payload = {
        "generated_at": datetime.now(tz=MSK).isoformat(timespec="seconds"),
        "n_records_total": len(records),
        "n_closed": len(closed),
        "factors": impact,
        "note": "lift>0 → фактор полезен; lift<0 → фактор скоринга вводит в заблуждение, корректируй вес.",
    }
    IMPACT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("factor_impact written → %s (closed=%d)", IMPACT_FILE, len(closed))


def cmd_check() -> int:
    records = iter_records()
    if not records:
        log.info("archive empty")
        return 0
    now = int(time.time())
    closed_now = 0
    for path, rec in records:
        if rec.get("live_metrics") is not None:
            continue
        if rec.get("check_after_ts", 0) > now:
            continue
        code = rec.get("owner_shortcode")
        if not code:
            continue
        log.info("check %s (owner=%s)", rec.get("orig_shortcode"), code)
        live = fetch_live_metrics(code)
        if "_error" in live:
            log.warning("  fetch fail: %s", live["_error"])
            continue
        rec["live_metrics"] = live
        orig_views = (rec.get("orig_metrics") or {}).get("views") or 0
        vlad_views = live.get("views") or 0
        ratio = round(vlad_views / orig_views, 3) if orig_views else None
        rec["ratio_views"] = ratio
        rec["verdict"] = verdict_from_ratio(ratio)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("  verdict=%s ratio=%s", rec["verdict"], ratio)
        closed_now += 1
        time.sleep(0.5)

    # _meta cycle counter
    meta = {"cycles": 0}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta["cycles"] = int(meta.get("cycles", 0)) + 1
    meta["last_run_iso"] = datetime.now(tz=MSK).isoformat(timespec="seconds")
    meta["last_closed_count"] = closed_now
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if meta["cycles"] % SUMMARY_EVERY_N == 0:
        log.info("cycle %d → writing factor_impact summary", meta["cycles"])
        all_recs = [r for _, r in iter_records()]
        write_factor_impact(all_recs)

    print(json.dumps({"closed_this_run": closed_now, "cycles": meta["cycles"]}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive niche-reels and feedback-loop")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--new", nargs=2, metavar=("ORIG_CODE", "OWNER_URL"))
    grp.add_argument("--check", action="store_true")
    grp.add_argument("--summary", action="store_true", help="force-write factor_impact.json")
    ap.add_argument("--note", default="", help="optional note for --new")
    args = ap.parse_args()

    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    if args.new:
        return cmd_new(args.new[0], args.new[1], args.note)
    if args.check:
        return cmd_check()
    if args.summary:
        all_recs = [r for _, r in iter_records()]
        write_factor_impact(all_recs)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
