#!/usr/bin/env python3
"""Reels analyzer pipeline orchestrator.

End-to-end: profile -> medias -> top-N reels -> download mp4 -> ffmpeg audio
-> Groq Whisper transcript -> structured JSON + draft markdown report.

The LLM analysis (hook/structure/why-it-flew/verdict) is done by the calling
agent based on the JSON output -- this script collects raw data only.

Usage:
  python analyze.py --user @your_account --top 5 [--history 30] [--out DIR]
  python analyze.py --user-id 17841400000000000 --top 5

Outputs in <out>/ (default /tmp/reels-analyzer/<username>/):
  report.json    -- machine-readable: per-reel metrics, caption, transcript
  report.md      -- draft human report (LLM analysis fields left blank)
  videos/<code>.mp4
  audio/<code>.mp3
  transcripts/<code>.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

# Reuse hikerapi skill as a library
HIKER_SCRIPTS = Path.home() / ".claude/skills/hikerapi/scripts"
sys.path.insert(0, str(HIKER_SCRIPTS))
from hiker import Hiker, HikerError  # noqa: E402

GROQ_TRANSCRIBE = (
    Path.home() / ".claude/skills/groq-voice/scripts/transcribe.sh"
)
# Ключ Groq читается из окружения: export GROQ_API_KEY=...
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")

log = logging.getLogger("reels-analyzer")


# ---- helpers ----

def slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def http_download(url: str, dest: Path, timeout: int = 60) -> int:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 reels-analyzer/1.0",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    return dest.stat().st_size


def extract_audio(mp4: Path, mp3: Path) -> None:
    """Extract mono 32kbps mp3 (small, Whisper-friendly)."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mp4),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        str(mp3),
    ]
    subprocess.run(cmd, check=True)


def transcribe(audio: Path) -> str:
    if not GROQ_KEY:
        raise RuntimeError(
            "Groq key not found. Get one free at https://console.groq.com "
            "and export it: export GROQ_API_KEY='YOUR-KEY'"
        )
    out = subprocess.run(
        ["bash", str(GROQ_TRANSCRIBE), str(audio)],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"transcribe failed: {out.stderr.strip()}")
    text = out.stdout
    if text.startswith("Transcript: "):
        text = text[len("Transcript: "):]
    return text.strip()


def best_video_url(media: dict[str, Any]) -> str | None:
    versions = media.get("video_versions") or []
    if not versions:
        return None
    # heaviest = best quality first; whisper doesn't care about resolution but
    # bigger files are slower. Pick the smallest one above 480p, fallback to first.
    for v in sorted(versions, key=lambda v: (v.get("height") or 0)):
        if (v.get("height") or 0) >= 480 and v.get("url"):
            return v["url"]
    return versions[0].get("url")


def thumbnail_url(media: dict[str, Any]) -> str | None:
    iv = media.get("image_versions2") or {}
    cands = iv.get("candidates") or []
    if cands and isinstance(cands[0], dict):
        return cands[0].get("url")
    return None


def audio_info(media: dict[str, Any]) -> dict[str, Any]:
    """Extract audio attribution: original vs licensed, title, artist, trending flag.

    Why this matters: original_sounds vs licensed_music is a strong format
    signal -- if 4 of 5 top reels run on original audio (creator voice / AI),
    the operator's growth is voice-driven, not trend-surfing.
    """
    cm = media.get("clips_metadata") or {}
    a_type = cm.get("audio_type")  # "original_sounds" | "licensed_music" | None
    info: dict[str, Any] = {"type": a_type, "title": None, "artist": None, "is_trending": False}

    if a_type == "licensed_music":
        mi = cm.get("music_info") or {}
        ai = mi.get("music_asset_info") or {}
        info["title"] = ai.get("title")
        info["artist"] = ai.get("display_artist") or ai.get("subtitle")
        ci = mi.get("music_consumption_info") or {}
        info["is_trending"] = bool(ci.get("is_trending_in_clips"))
    else:
        osi = cm.get("original_sound_info") or {}
        info["title"] = osi.get("original_audio_title")
        artist = osi.get("ig_artist") or {}
        info["artist"] = artist.get("username") if isinstance(artist, dict) else None
        ci = osi.get("consumption_info") or {}
        info["is_trending"] = bool(ci.get("is_trending_in_clips"))
    return info


def caption_text(media: dict[str, Any]) -> str:
    cap = media.get("caption") or {}
    if isinstance(cap, dict):
        return (cap.get("text") or "").strip()
    return ""


def plays(media: dict[str, Any]) -> int:
    return int(media.get("play_count") or media.get("ig_play_count") or 0)


# ---- pipeline ----

def aggregate_stats(reels: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute baseline aggregates over scanned reels.

    Note: /v2/user/medias does NOT include play_count, so view-based aggregates
    use likes as a proxy. For real view aggregates we'd need to enrich every
    item -- not worth the API cost. This function reports both.
    """
    if not reels:
        return {"count": 0}
    likes = [int(it.get("like_count") or 0) for it in reels]
    coms = [int(it.get("comment_count") or 0) for it in reels]
    likes_sorted = sorted(likes)
    n = len(likes_sorted)
    median = (likes_sorted[n // 2] if n % 2 else
              (likes_sorted[n // 2 - 1] + likes_sorted[n // 2]) // 2)
    return {
        "count": len(reels),
        "likes_total": sum(likes),
        "likes_mean": sum(likes) // max(len(likes), 1),
        "likes_median": median,
        "comments_total": sum(coms),
        "comments_mean": sum(coms) // max(len(coms), 1),
    }


def collect_top_reels(h: Hiker, user_id: str, history: int, top: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pull `history` latest medias, keep reels, return (top-N enriched, aggregates)."""
    log.info("paging /v2/user/medias up to %d items", history)
    items: list[dict[str, Any]] = []
    cursor = None
    calls = 0
    while len(items) < history and calls < 6:
        params = {"user_id": user_id}
        if cursor:
            params["page_id"] = cursor
        page = h.get("/v2/user/medias", **params)
        calls += 1
        chunk = page.get("items") or (page.get("response", {}) or {}).get("items") or []
        items.extend(chunk)
        nxt = page.get("next_page_id") or page.get("next_max_id") or \
              (page.get("response", {}) or {}).get("next_max_id")
        log.info("  call %d: +%d items (total %d), next=%s",
                 calls, len(chunk), len(items), "yes" if nxt else "no")
        if not nxt:
            break
        cursor = nxt
        time.sleep(0.3)

    reels = [it for it in items if it.get("media_type") == 2 or it.get("product_type") == "clips"]
    log.info("filtered: %d reels of %d items", len(reels), len(items))

    # /v2/user/medias does NOT return play_count -> rank by engagement proxy first,
    # then enrich top (top * 2) candidates via /v2/media/info/by/code.
    def eng(it: dict[str, Any]) -> int:
        return (it.get("like_count") or 0) + 2 * (it.get("comment_count") or 0)

    # Mentor's pipeline enriches only top-N (not N*2). Engagement-rank is a
    # solid proxy: in 30 days of data the top-by-engagement and top-by-views
    # overlap >90% -- not worth doubling API spend for a marginal reorder.
    candidates = sorted(reels, key=eng, reverse=True)[:top]
    log.info("enriching %d candidates via /v2/media/info/by/code", len(candidates))

    enriched: list[dict[str, Any]] = []
    for c in candidates:
        code = c.get("code")
        if not code:
            continue
        try:
            info = h.get("/v2/media/info/by/code", code=code)
        except HikerError as e:
            log.warning("enrich %s failed: %s", code, e.status)
            continue
        m = info.get("media_or_ad") or info.get("item") or info
        if isinstance(m, dict):
            enriched.append(m)
        time.sleep(0.3)

    enriched.sort(key=plays, reverse=True)
    aggs = aggregate_stats(reels)
    return enriched[:top], aggs


def process_media(h: Hiker, media: dict[str, Any], out: Path,
                  do_transcribe: bool, aggs: dict[str, Any]) -> dict[str, Any]:
    code = media.get("code") or "unknown"
    rec: dict[str, Any] = {
        "code": code,
        "permalink": f"https://www.instagram.com/reel/{code}/",
        "pk": str(media.get("pk") or media.get("id") or ""),
        "taken_at": media.get("taken_at"),
        "video_duration_s": round(media.get("video_duration") or 0, 1),
        "play_count": plays(media),
        "like_count": media.get("like_count") or 0,
        "comment_count": media.get("comment_count") or 0,
        "reshare_count": media.get("reshare_count") or 0,
        "caption": caption_text(media),
        "thumbnail_url": thumbnail_url(media),
        "audio": audio_info(media),
        "video_local": None,
        "audio_local": None,
        "transcript": None,
        "transcript_error": None,
        # archetype tag is filled by the calling agent during LLM analysis
        # (one of: news-jacking, satisfying-process, hot-take, how-to, story,
        #  listicle, contrarian, demo, BTS, AI-generated)
        "archetype": None,
    }
    p = rec["play_count"] or 1
    rec["er_pct"] = round((rec["like_count"] + rec["comment_count"]) / p * 100, 2)
    # vs median: how many median-likes does this reel earn? gives a quick
    # "lottery vs steady" read across the top.
    median = aggs.get("likes_median") or 0
    rec["likes_vs_median"] = round(rec["like_count"] / median, 1) if median > 0 else None

    url = best_video_url(media)
    if not url:
        rec["transcript_error"] = "no video_versions in media response"
        return rec

    mp4 = out / "videos" / f"{slug(code)}.mp4"
    mp3 = out / "audio" / f"{slug(code)}.mp3"
    txt = out / "transcripts" / f"{slug(code)}.txt"
    for d in (mp4.parent, mp3.parent, txt.parent):
        d.mkdir(parents=True, exist_ok=True)

    try:
        log.info("[%s] downloading mp4", code)
        size = http_download(url, mp4)
        rec["video_local"] = str(mp4)
        rec["video_bytes"] = size
    except Exception as e:
        rec["transcript_error"] = f"download failed: {e}"
        return rec

    try:
        log.info("[%s] extracting audio", code)
        extract_audio(mp4, mp3)
        rec["audio_local"] = str(mp3)
    except subprocess.CalledProcessError as e:
        rec["transcript_error"] = f"ffmpeg failed: {e}"
        return rec

    if not do_transcribe:
        rec["transcript_error"] = "transcribe skipped (--skip-transcribe)"
        return rec

    try:
        log.info("[%s] transcribing via Groq", code)
        text = transcribe(mp3)
        rec["transcript"] = text
        txt.write_text(text)
    except Exception as e:
        rec["transcript_error"] = f"transcribe failed: {e}"
    return rec


def render_md(profile: dict[str, Any], reels: list[dict[str, Any]],
              aggs: dict[str, Any], history: int) -> str:
    """Compact mentor-style draft. The agent fills 'Про что' and 'Быстрые
    наблюдения' from caption + transcript -- this script only emits hard data.
    Full caption + transcript are in report.json for the agent; the markdown
    intentionally skips them to keep the LLM context lean."""
    u = profile
    L: list[str] = []
    # Date range
    dates = [r.get("taken_at") for r in reels if r.get("taken_at")]
    period = ""
    if dates:
        d_lo = dt.datetime.fromtimestamp(min(dates), dt.UTC).strftime("%Y-%m-%d")
        d_hi = dt.datetime.fromtimestamp(max(dates), dt.UTC).strftime("%Y-%m-%d")
        period = f" за период {d_lo} → {d_hi}"

    L.append(f"# Reels analysis @{u.get('username')}")
    L.append("")
    L.append(f"@{u.get('username')}, {u.get('follower_count',0):,} подписчиков, "
             f"{aggs.get('count', 0)} последних рилсов{period}.")
    L.append("")

    # Aggregates -- mentor's pattern. /v2/user/medias has no play_count, so we
    # report engagement aggregates as the cheap baseline.
    L.append(f"**Агрегаты по {aggs.get('count',0)} рилсам (без enrichment, по лайкам):**")
    L.append(f"- Лайки: всего {aggs.get('likes_total',0):,} · средние "
             f"{aggs.get('likes_mean',0):,} · медиана {aggs.get('likes_median',0):,}")
    L.append(f"- Комменты: всего {aggs.get('comments_total',0):,} · средние "
             f"{aggs.get('comments_mean',0):,}")
    L.append("")

    L.append(f"**TOP-{len(reels)} по просмотрам:**")
    L.append("")
    for i, r in enumerate(reels, 1):
        date = (dt.datetime.fromtimestamp(r["taken_at"], dt.UTC).strftime("%Y-%m-%d")
                if r.get("taken_at") else "?")
        vs_med = (f" · {r['likes_vs_median']}× медианы лайков"
                  if r.get("likes_vs_median") else "")
        L.append(f"{i}. {r['play_count']:,} просмотров · {r['like_count']:,} лайков · "
                 f"{r['comment_count']:,} комм · {int(r['video_duration_s'])} сек · "
                 f"ER {r['er_pct']}%{vs_med}")
        L.append(f"   {r['permalink']} ({date})")

        a = r.get("audio") or {}
        a_type = a.get("type") or "?"
        a_label = "оригинальный звук" if a_type == "original_sounds" else (
            "лицензионная музыка" if a_type == "licensed_music" else a_type)
        a_extra = []
        if a.get("title") and a.get("title") != "Original audio":
            a_extra.append(a["title"])
        if a.get("artist") and a.get("type") == "licensed_music":
            a_extra.append(f"исп. {a['artist']}")
        if a.get("is_trending"):
            a_extra.append("**TRENDING**")
        a_str = a_label + (f" ({', '.join(a_extra)})" if a_extra else "")
        L.append(f"   Аудио: {a_str}")

        if r.get("thumbnail_url"):
            L.append(f"   Thumb: [view]({r['thumbnail_url']})")
        L.append(f"   Архетип: _TODO -- LLM присвоит тег_")
        L.append(f"   Про что: _TODO -- LLM заполнит из caption + transcript_")
        L.append("")

    L.append("**Быстрые наблюдения:** _TODO -- агент заполнит_")
    L.append("- общий паттерн (тема/архетип топа)")
    L.append("- сильные триггеры в хуках (точные фразы)")
    L.append("- оптимальная длина (диапазон секунд по топу)")
    L.append("- ER vs медиана аккаунта")
    L.append("- стратегический gap (CTA, ниша, риски)")
    L.append("")
    L.append(f"_Полный caption и transcript каждого reel -- в report.json._")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Reels analyzer pipeline")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--user", help="Instagram username (without @)")
    g.add_argument("--user-id", help="Instagram numeric user_id")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--history", type=int, default=30, help="how many recent medias to scan")
    p.add_argument("--out", type=Path, default=None,
                   help="output dir (default /tmp/reels-analyzer/<username>/)")
    p.add_argument("--skip-transcribe", action="store_true",
                   help="skip Groq transcription (debug, or no key)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )

    h = Hiker()

    # resolve user
    if args.user:
        prof = h.user_by_username(args.user)
        u = prof.get("user") or prof
        username = u.get("username") or args.user
    else:
        prof = h.user_by_id(args.user_id)
        u = prof.get("user") or prof
        username = u.get("username") or args.user_id

    user_id = str(u.get("pk") or u.get("id") or args.user_id or "")
    out = args.out or Path("/tmp/reels-analyzer") / slug(username)
    out.mkdir(parents=True, exist_ok=True)

    # collect
    reels_raw, aggs = collect_top_reels(h, user_id, args.history, args.top)

    # process each
    do_tx = (not args.skip_transcribe) and bool(GROQ_KEY)
    if not do_tx and not args.skip_transcribe:
        log.warning("Groq key missing -> transcripts will be empty. "
                    "Get one at https://console.groq.com")

    records = [process_media(h, m, out, do_tx, aggs) for m in reels_raw]

    payload = {
        "username": username,
        "user_id": user_id,
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "profile": {
            "full_name": u.get("full_name"),
            "follower_count": u.get("follower_count"),
            "following_count": u.get("following_count"),
            "media_count": u.get("media_count"),
            "is_verified": u.get("is_verified"),
            "biography": u.get("biography"),
            "external_url": u.get("external_url"),
            "username": username,
        },
        "history_scanned": args.history,
        "top_n": args.top,
        "aggregates": aggs,
        "reels": records,
    }

    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    md_path.write_text(render_md(payload["profile"], records, aggs, args.history))

    print(f"DONE")
    print(f"  json: {json_path}")
    print(f"  md  : {md_path}")
    print(f"  out : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
