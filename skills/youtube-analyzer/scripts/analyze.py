#!/usr/bin/env python3
"""YouTube analyzer pipeline orchestrator.

End-to-end: handle -> channel resolve (videos/shorts) -> flat-playlist listing
-> top-N by views -> per-video metadata -> captions priority chain
(ru-manual > en-manual > ru-auto > en-auto > Groq Whisper fallback) ->
structured JSON + draft markdown.

The LLM analysis (title/description/hook/retention/CTA/verdict) is done by
the calling agent based on the JSON output -- this script collects raw data only.

Usage:
  python analyze.py --handle @your_account --top 5 [--out DIR]
  python analyze.py --handle "https://www.youtube.com/@your_account"
  python analyze.py --handle "UCxxxxxxxxxxxxx"
  python analyze.py --handle ... --no-transcribe   # skip caption fetch + Groq

Outputs in <out>/ (default /tmp/youtube-analyzer/<handle>/):
  report.json             -- machine-readable: per-video metrics, captions
  report.md               -- draft report (LLM analysis fields blank)
  audio/<id>.mp3          -- only if Groq fallback path was hit
  transcripts/<id>.txt    -- captions text or Whisper output
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

# Путь к yt-dlp: переопределяется через $YT_DLP_BIN, иначе берётся из PATH.
YT_DLP = os.environ.get("YT_DLP_BIN", "yt-dlp")
# Файл cookies (Netscape): путь задаётся через $YOUTUBE_COOKIES или --cookies.
COOKIES_FILE = Path(os.environ.get("YOUTUBE_COOKIES", str(Path.home() / ".secrets/youtube-cookies.txt")))
DENO_BIN_DIR = Path.home() / ".deno/bin"

# Residential proxy to bypass YouTube's data-center bot-wall. Resolved (in order):
#   --proxy arg  >  YT_PROXY env  >  secret file below.
# Format: socks5://user:pass@host:port (AdsPower & most residential = SOCKS5),
# or http://user:pass@host:port. Secret file is mode-600, never logged.
PROXY_FILE = Path(os.environ.get("YT_PROXY_FILE", str(Path.home() / ".secrets/youtube-proxy.txt")))


def _load_default_proxy() -> str | None:
    env = os.environ.get("YT_PROXY")
    if env:
        return env
    if PROXY_FILE.is_file():
        val = PROXY_FILE.read_text().strip()
        return val or None
    return None


PROXY: str | None = _load_default_proxy()

GROQ_TRANSCRIBE = (
    Path.home() / ".claude/skills/groq-voice/scripts/transcribe.sh"
)
# Ключ Groq читается из окружения: export GROQ_API_KEY=...
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")


def _yt_dlp_env() -> dict[str, str]:
    """Env with Deno on PATH (needed by yt-dlp-ejs to solve YouTube n challenge)."""
    env = os.environ.copy()
    if DENO_BIN_DIR.is_dir():
        env["PATH"] = f"{DENO_BIN_DIR}:{env.get('PATH', '')}"
    return env


def _cookies_args() -> list[str]:
    """Inject --cookies if file present (mode-600 secret)."""
    if COOKIES_FILE.is_file():
        return ["--cookies", str(COOKIES_FILE)]
    return []


def _proxy_args() -> list[str]:
    """Inject --proxy if a residential proxy is configured (bypass bot-wall)."""
    if PROXY:
        return ["--proxy", PROXY]
    return []

log = logging.getLogger("youtube-analyzer")


# ---- helpers ----

def slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def normalize_handle(raw: str) -> tuple[str, str]:
    """Return (display_handle, canonical_url_root).

    Accepts: "@your_account", "@your_account", full /@handle URL, /channel/UC... URL.
    """
    s = raw.strip()
    # Channel ID
    m = re.match(r"^(UC[0-9A-Za-z_-]{20,24})$", s)
    if m:
        return s, f"https://www.youtube.com/channel/{s}"
    m = re.search(r"youtube\.com/channel/(UC[0-9A-Za-z_-]+)", s)
    if m:
        return m.group(1), f"https://www.youtube.com/channel/{m.group(1)}"
    # @handle URL or bare handle
    m = re.search(r"youtube\.com/@([A-Za-z0-9._-]+)", s)
    if m:
        return m.group(1), f"https://www.youtube.com/@{m.group(1)}"
    s = s.lstrip("@")
    return s, f"https://www.youtube.com/@{s}"


def yt_dlp_json(args: list[str], timeout: int = 120) -> dict[str, Any] | list[dict[str, Any]]:
    """Run yt-dlp returning parsed JSON. Raises on failure."""
    cmd = [YT_DLP, *_proxy_args(), *_cookies_args(), *args]
    log.debug("yt-dlp %s", " ".join(args))
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False, env=_yt_dlp_env()
    )
    if out.returncode != 0:
        raise RuntimeError(f"yt-dlp failed (rc={out.returncode}): {out.stderr.strip()[:400]}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def yt_dlp_run(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    cmd = [YT_DLP, *_proxy_args(), *_cookies_args(), *args]
    log.debug("yt-dlp %s", " ".join(args))
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False, env=_yt_dlp_env()
    )
    return out.returncode, out.stdout, out.stderr


def fetch_channel_listing(url_root: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Try /videos first; if absent, fall back to /shorts. Merge both if both
    exist. Returns (entries, channel_meta).

    Each entry: {"id", "title", "view_count", "duration", "url", ...}
    channel_meta: {"channel", "channel_id", "channel_follower_count", "uploader", ...}
    """
    entries: dict[str, dict[str, Any]] = {}
    meta: dict[str, Any] = {}
    tabs = ["/videos", "/shorts"]
    seen_any = False

    for tab in tabs:
        u = url_root + tab
        try:
            data = yt_dlp_json(["-J", "--flat-playlist", "--no-warnings", u])
        except RuntimeError as e:
            msg = str(e)
            if "does not have a videos tab" in msg or "does not have a shorts tab" in msg \
                    or "tab was not found" in msg or "Not Found" in msg:
                log.info("tab %s missing on %s", tab, url_root)
                continue
            # Other errors -- only raise if we never got a tab
            log.warning("tab %s error: %s", tab, msg[:200])
            continue
        seen_any = True
        if not isinstance(data, dict):
            continue
        # Fill channel meta from the first successful tab
        if not meta:
            meta = {
                "channel": data.get("channel") or data.get("uploader") or data.get("title"),
                "channel_id": data.get("channel_id") or data.get("id"),
                "channel_follower_count": data.get("channel_follower_count"),
                "uploader": data.get("uploader"),
                "uploader_id": data.get("uploader_id"),
                "description": (data.get("description") or "")[:500],
                "channel_url": data.get("channel_url") or url_root,
            }
        # /shorts and /videos both expose .entries flat
        for e in data.get("entries") or []:
            if not isinstance(e, dict):
                continue
            vid = e.get("id")
            if not vid:
                continue
            if vid not in entries:
                # Tag which tab it came from for later format detection
                e["_tab"] = tab.lstrip("/")
                entries[vid] = e

    if not seen_any:
        raise RuntimeError(
            f"No videos or shorts tab found on {url_root}. "
            "Channel may be empty, age-gated, or the handle is wrong."
        )

    return list(entries.values()), meta


def video_full_metadata(video_url: str) -> dict[str, Any]:
    """Run yt-dlp -j on a single video to get full metadata."""
    data = yt_dlp_json(["-j", "--skip-download", "--no-warnings", video_url])
    return data if isinstance(data, dict) else {}


def vtt_to_text(path: Path) -> str:
    """Strip WebVTT timestamps + dedupe overlapping/repeated cue lines.

    YouTube auto-captions emit rolling cues where each cue repeats the previous
    line plus a new word. We dedupe by remembering the last non-empty line
    written and only appending lines that are not a prefix of, equal to, or
    a continuation of the previous line.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    out: list[str] = []
    last = ""
    ts_re = re.compile(r"^\d{2}:\d{2}[:.]")
    tag_re = re.compile(r"<[^>]+>")
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("WEBVTT") or s.startswith("Kind:") or s.startswith("Language:"):
            continue
        if ts_re.match(s) or "-->" in s:
            continue
        if s.startswith("NOTE"):
            continue
        # Strip inline timing tags like <00:00:01.000><c>foo</c>
        s = tag_re.sub("", s).strip()
        if not s:
            continue
        if s == last:
            continue
        # If new line starts with the previous line, prefer the longer one
        if last and s.startswith(last):
            if out:
                out[-1] = s
            else:
                out.append(s)
            last = s
            continue
        # If previous line starts with this line, skip (we already have longer)
        if last and last.startswith(s):
            continue
        out.append(s)
        last = s
    return "\n".join(out).strip()


def fetch_captions(video_id: str, work_dir: Path) -> tuple[str | None, str | None, str | None]:
    """Try caption priority chain.

    Returns (text, language, source) where source is one of:
    'manual_ru', 'manual_en', 'auto_ru', 'auto_en', or (None, None, None) on miss.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tpl = str(work_dir / "%(id)s")

    plans = [
        (["--write-sub", "--sub-lang", "ru"], "manual_ru", "ru"),
        (["--write-sub", "--sub-lang", "en"], "manual_en", "en"),
        (["--write-auto-sub", "--sub-lang", "ru"], "auto_ru", "ru"),
        (["--write-auto-sub", "--sub-lang", "en"], "auto_en", "en"),
    ]
    for flags, source, lang in plans:
        # Clean any leftover from prior attempts
        for p in work_dir.glob(f"{video_id}.*.vtt"):
            p.unlink(missing_ok=True)
        rc, _, err = yt_dlp_run([
            *flags, "--sub-format", "vtt", "--skip-download",
            "--no-warnings", "-o", out_tpl, url,
        ], timeout=60)
        # yt-dlp returns 0 even when no subs exist; check for the file
        candidates = list(work_dir.glob(f"{video_id}.{lang}*.vtt"))
        if not candidates:
            candidates = list(work_dir.glob(f"{video_id}.*.vtt"))
        if candidates:
            text = vtt_to_text(candidates[0])
            if text:
                return text, lang, source
            # Empty parse -> remove and try next
            for c in candidates:
                c.unlink(missing_ok=True)
    return None, None, None


def groq_fallback(video_id: str, work_dir: Path) -> tuple[str | None, str | None]:
    """Download audio via yt-dlp, transcribe via Groq Whisper.

    Returns (text, error). On success error is None.
    """
    if not GROQ_KEY:
        return None, (
            "Groq key not found ($GROQ_API_KEY) -- captions absent and "
            "no fallback available. Get a free key at https://console.groq.com "
            "and export: export GROQ_API_KEY='YOUR-KEY'"
        )
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(audio_dir / "%(id)s.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"
    rc, _, err = yt_dlp_run([
        "-x", "--audio-format", "mp3", "--audio-quality", "5",
        "--no-warnings", "-o", out_tpl, url,
    ], timeout=180)
    if rc != 0:
        return None, f"yt-dlp audio download failed: {err.strip()[:200]}"
    candidates = list(audio_dir.glob(f"{video_id}.mp3"))
    if not candidates:
        return None, "audio file not produced"
    mp3 = candidates[0]
    out = subprocess.run(
        ["bash", str(GROQ_TRANSCRIBE), str(mp3)],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        return None, f"groq transcribe failed: {out.stderr.strip()[:200]}"
    text = out.stdout
    if text.startswith("Transcript: "):
        text = text[len("Transcript: "):]
    return text.strip(), None


# ---- pipeline ----

def aggregate_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {"count": 0}
    views = [int(e.get("view_count") or 0) for e in entries]
    durs = [int(e.get("duration") or 0) for e in entries if e.get("duration")]
    views_nz = [v for v in views if v > 0]
    median = int(statistics.median(views_nz)) if views_nz else 0

    def _is_short(e: dict[str, Any]) -> bool:
        if e.get("_tab") == "shorts":
            return True
        d = e.get("duration") or 0
        return 0 < d <= 60

    def _is_long(e: dict[str, Any]) -> bool:
        if e.get("_tab") == "shorts":
            return False
        d = e.get("duration") or 0
        return d > 60

    return {
        "count": len(entries),
        "views_total": sum(views),
        "views_mean": sum(views) // max(len(views), 1),
        "views_median": median,
        "duration_mean_s": (sum(durs) // len(durs)) if durs else 0,
        "shorts_count": sum(1 for e in entries if _is_short(e)),
        "long_count": sum(1 for e in entries if _is_long(e)),
    }


def detect_format(duration_s: int | None, tab: str | None) -> str:
    # Tab is the strongest signal: /shorts tab -> Short by definition.
    if tab == "shorts":
        return "Short"
    if tab == "videos":
        d = duration_s or 0
        return "Short" if 0 < d <= 60 else "Long"
    # Unknown tab + unknown duration -> "?"
    d = duration_s or 0
    if d == 0:
        return "?"
    return "Short" if d <= 60 else "Long"


def best_thumbnail(meta: dict[str, Any]) -> str | None:
    thumbs = meta.get("thumbnails") or []
    if not thumbs:
        return meta.get("thumbnail")
    # highest resolution
    sized = [t for t in thumbs if isinstance(t, dict) and t.get("url")]
    if not sized:
        return None
    sized.sort(
        key=lambda t: (t.get("height") or 0) * (t.get("width") or 0),
        reverse=True,
    )
    return sized[0].get("url")


def process_video(entry: dict[str, Any], work_dir: Path,
                  do_transcribe: bool, aggs: dict[str, Any]) -> dict[str, Any]:
    vid = entry.get("id")
    log.info("[%s] fetching full metadata", vid)
    try:
        meta = video_full_metadata(f"https://www.youtube.com/watch?v={vid}")
    except RuntimeError as e:
        meta = {}
        meta_err = str(e)[:200]
    else:
        meta_err = None

    # Fall back to entry data if metadata fetch failed
    src = meta if meta else entry

    duration = int(src.get("duration") or entry.get("duration") or 0)
    fmt = detect_format(duration, entry.get("_tab"))
    description = (src.get("description") or "")
    upload_date = src.get("upload_date")  # YYYYMMDD

    rec: dict[str, Any] = {
        "id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": src.get("title") or entry.get("title") or "",
        "description": description,
        "description_first_200": description[:200],
        "duration_s": duration,
        "format": fmt,
        "view_count": int(src.get("view_count") or entry.get("view_count") or 0),
        "like_count": int(src.get("like_count") or 0),
        "comment_count": int(src.get("comment_count") or 0),
        "upload_date": upload_date,
        "thumbnail_url": best_thumbnail(src),
        "channel": src.get("channel"),
        "channel_follower_count": src.get("channel_follower_count"),
        "uploader": src.get("uploader"),
        "available_subtitles": sorted(list((src.get("subtitles") or {}).keys()))[:8],
        "available_auto_captions": sorted(list((src.get("automatic_captions") or {}).keys()))[:8],
        "transcript": None,
        "transcript_language": None,
        "transcript_source": None,
        "transcript_error": None,
        "metadata_error": meta_err,
        # Filled by LLM during phase 2
        "archetype": None,
    }

    # Engagement vs median
    p = rec["view_count"] or 1
    rec["er_pct"] = round((rec["like_count"] + rec["comment_count"]) / p * 100, 2)
    median = aggs.get("views_median") or 0
    rec["views_vs_median"] = round(rec["view_count"] / median, 1) if median > 0 else None

    if not do_transcribe:
        rec["transcript_error"] = "transcribe skipped (--no-transcribe)"
        return rec

    # Caption priority chain
    sub_dir = work_dir / "transcripts"
    sub_dir.mkdir(parents=True, exist_ok=True)
    text, lang, source = fetch_captions(vid, sub_dir)
    if text:
        rec["transcript"] = text
        rec["transcript_language"] = lang
        rec["transcript_source"] = source
        (sub_dir / f"{slug(vid)}.txt").write_text(text)
        # Clean intermediate VTT files
        for p in sub_dir.glob(f"{vid}.*.vtt"):
            p.unlink(missing_ok=True)
        return rec

    log.info("[%s] no captions, falling back to Groq Whisper", vid)
    text, err = groq_fallback(vid, work_dir)
    if text:
        rec["transcript"] = text
        rec["transcript_language"] = "auto"
        rec["transcript_source"] = "groq_whisper"
        (sub_dir / f"{slug(vid)}.txt").write_text(text)
    else:
        rec["transcript_error"] = err or "no transcript available"
    return rec


def render_md(channel_meta: dict[str, Any], records: list[dict[str, Any]],
              aggs: dict[str, Any], total_videos_seen: int) -> str:
    """Compact mentor-style draft. The agent fills 'Архетип', 'Про что',
    and 'Быстрые наблюдения' from title + description + transcript.
    Full transcripts live in report.json to keep the markdown lean.
    """
    L: list[str] = []
    handle_raw = channel_meta.get("uploader_id") or channel_meta.get("channel") or ""
    handle = handle_raw.lstrip("@")

    L.append(f"# YouTube analysis @{handle}")
    L.append("")
    subs = channel_meta.get("channel_follower_count") or 0
    L.append(
        f"@{handle} ({channel_meta.get('channel') or '?'}), "
        f"{subs:,} подписчиков, проанализировано {len(records)} из "
        f"{total_videos_seen} видео в канале."
    )
    L.append("")

    L.append(f"**Агрегаты по {aggs.get('count', 0)} видео (full listing):**")
    L.append(
        f"- Просмотры: всего {aggs.get('views_total', 0):,} · средние "
        f"{aggs.get('views_mean', 0):,} · медиана {aggs.get('views_median', 0):,}"
    )
    L.append(
        f"- Формат: Shorts {aggs.get('shorts_count', 0)} · Long-form "
        f"{aggs.get('long_count', 0)} · средняя длительность "
        f"{aggs.get('duration_mean_s', 0)} сек"
    )
    L.append("")

    L.append(f"**TOP-{len(records)} по просмотрам:**")
    L.append("")
    for i, r in enumerate(records, 1):
        date = "?"
        if r.get("upload_date") and len(r["upload_date"]) == 8:
            d = r["upload_date"]
            date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        vs_med = (
            f" · {r['views_vs_median']}× медианы"
            if r.get("views_vs_median")
            else ""
        )
        L.append(
            f"{i}. {r['view_count']:,} просмотров · "
            f"{r['like_count']:,} лайков · {r['comment_count']:,} комм · "
            f"{r['duration_s']} сек ({r['format']}) · ER {r['er_pct']}%{vs_med}"
        )
        L.append(f"   **«{r['title']}»**")
        L.append(f"   {r['url']} ({date})")
        if r.get("description_first_200"):
            first_line = r["description_first_200"].split("\n")[0][:160]
            if first_line:
                L.append(f"   Описание (1-я строка): {first_line}")
        if r.get("thumbnail_url"):
            L.append(f"   Thumb: [view]({r['thumbnail_url']})")
        # Transcript source flag
        ts = r.get("transcript_source") or "—"
        if r.get("transcript_error"):
            L.append(f"   Транскрипт: _ОШИБКА: {r['transcript_error']}_")
        else:
            L.append(f"   Транскрипт: {ts} ({r.get('transcript_language') or '?'})")
        L.append("   Архетип: _TODO -- LLM присвоит тег_")
        L.append("   Про что: _TODO -- LLM заполнит из title + description + transcript_")
        L.append("")

    L.append("**Быстрые наблюдения:** _TODO -- агент заполнит_")
    L.append("- доминирующий тайтл-паттерн (числа, скобки, эмоция, длина)")
    L.append("- паттерн description-хука (первая строка)")
    L.append("- общий video-хук (что в первые 1-2 секунды)")
    L.append("- архитектура CTA (voice / on-screen / desc / pinned comment)")
    L.append("- стратегический gap (subscribe funnel, retention, CTA)")
    L.append("")
    L.append("_Полный title, description и transcript каждого видео -- в report.json._")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="YouTube channel analyzer pipeline")
    p.add_argument("--handle", "-H", required=True,
                   help="YouTube handle (@your_account, @your_account, full URL, or UC...)")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--out", type=Path, default=None,
                   help="output dir (default /tmp/youtube-analyzer/<handle>/)")
    p.add_argument("--no-transcribe", action="store_true",
                   help="skip caption fetch + Groq fallback (debug / fast metadata only)")
    p.add_argument("--proxy", default=None,
                   help="residential proxy to bypass YouTube bot-wall "
                        "(http://user:pass@host:port). Overrides YT_PROXY env var.")
    p.add_argument("--cookies", type=Path, default=None,
                   help="path to a Netscape cookies.txt (overrides default secret path)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    global PROXY, COOKIES_FILE
    if args.proxy:
        PROXY = args.proxy
    if args.cookies:
        COOKIES_FILE = args.cookies
    if PROXY:
        log.info("using proxy %s", re.sub(r"//[^@]+@", "//***@", PROXY))

    if not (Path(YT_DLP).is_file() or shutil.which(YT_DLP)):
        log.error("yt-dlp not found at %s", YT_DLP)
        log.error("Install: pipx install yt-dlp  (or pip install --user yt-dlp)")
        return 2

    handle, url_root = normalize_handle(args.handle)
    out = args.out or Path("/tmp/youtube-analyzer") / slug(handle)
    out.mkdir(parents=True, exist_ok=True)

    log.info("resolving %s -> %s", handle, url_root)
    try:
        entries, channel_meta = fetch_channel_listing(url_root)
    except RuntimeError as e:
        log.error("listing failed: %s", e)
        return 1

    if not channel_meta.get("uploader_id"):
        channel_meta["uploader_id"] = handle

    log.info("got %d videos in listing", len(entries))

    # Sort by view count desc, take top-N
    entries.sort(key=lambda e: int(e.get("view_count") or 0), reverse=True)
    top = entries[: args.top]
    log.info("top-%d view counts: %s",
             args.top, [e.get("view_count") for e in top])

    aggs = aggregate_stats(entries)
    do_transcribe = not args.no_transcribe

    records = [
        process_video(e, out, do_transcribe, aggs) for e in top
    ]

    payload = {
        "handle": handle,
        "channel_url": channel_meta.get("channel_url"),
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "channel": channel_meta,
        "total_videos_seen": len(entries),
        "top_n": args.top,
        "aggregates": aggs,
        "videos": records,
    }

    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    md_path.write_text(render_md(channel_meta, records, aggs, len(entries)))

    print("DONE")
    print(f"  json: {json_path}")
    print(f"  md  : {md_path}")
    print(f"  out : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
