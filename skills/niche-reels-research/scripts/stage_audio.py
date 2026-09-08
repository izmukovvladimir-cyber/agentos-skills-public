#!/usr/bin/env python3
"""stage_audio.py — download reels + stage audio.mp3 for transcribe.py.

This is the MISSING LINK between the scrape and the transcript. transcribe.py
only reads audio that is ALREADY staged at pool/work/<code>/audio.mp3 — with
nothing staged it silently transcribes zero files. Anyone who ran
`transcribe.py` straight after `score.py` got no transcripts, concluded "the
reel has no script available", and wrote the voice-over from the caption and
the on-screen title instead. That is invented copy, not a rewrite, and it
breaks the rewrite rule (keep the original hook + core, rewrite ~25%).

The real script IS obtainable: HikerAPI /v1/media/by/code returns `video_url`
for a shortcode. Download it, strip the audio, transcribe. Until
this step lived only in throwaway dl_transcribe_<date>.py scripts, so it never
made it into anyone's documented route.

Usage (client run — isolated, always set the env):
  export NRR_CLIENT_DIR=~/.claude-lab/client-<slug>/.claude/reels-digest
  python3 stage_audio.py                     # all codes in pool/_top10.json
  python3 stage_audio.py --codes A,B,C       # explicit shortcodes
  python3 stage_audio.py --from _carousels_top15.json   # another pool file
  python3 transcribe.py                      # then transcribe what got staged

Team run (<agent>, no env): reads /tmp/expand_pool/reels — legacy behaviour.

Idempotent: an existing audio.mp3 is kept, the reel is not re-downloaded.
Exit 0 = every requested code is staged. Exit 10 = at least one failed (read
the per-code reason; a private/deleted reel legitimately has no video_url —
drop that reel from the pack rather than inventing its script).
"""
from __future__ import annotations
import os

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

HIKER_KEY = os.environ["HIKER_API_KEY"]
BASE = "https://api.instagrapi.com"

POOL = lib_paths.pool_dir()
WORK = POOL / "work"


def hiker(path: str, params: dict) -> dict:
    cmd = ["curl", "-s", "-H", f"x-access-key: {HIKER_KEY}", "-G", f"{BASE}{path}"]
    for k, v in params.items():
        cmd += ["--data-urlencode", f"{k}={v}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        return {"_error": str(e), "_raw": r.stdout[:200]}


def _code_of(item: dict) -> str:
    """Shortcode of a pool item: `code`, else parsed out of url/link."""
    code = item.get("code")
    if isinstance(code, str) and code:
        return code
    url = item.get("url") or item.get("link") or ""
    m = re.search(r"/reel/([A-Za-z0-9_-]+)", url if isinstance(url, str) else "")
    return m.group(1) if m else ""


def codes_from_pool(pool_file: str) -> list[str]:
    path = POOL / pool_file
    if not path.is_file():
        sys.exit(f"stage_audio: {path} not found — run pull_reels.py + score.py first.")
    data = json.loads(path.read_text())
    items = data if isinstance(data, list) else data.get("items", [])
    return [c for c in (_code_of(i) for i in items if isinstance(i, dict)) if c]


def stage(code: str) -> bool:
    wd = WORK / code
    wd.mkdir(parents=True, exist_ok=True)
    mp3 = wd / "audio.mp3"
    if mp3.exists() and mp3.stat().st_size > 1000:
        print(f"{code}: already staged")
        return True

    data = hiker("/v1/media/by/code", {"code": code})
    vurl = data.get("video_url") if isinstance(data, dict) else None
    if not vurl:
        # Not a failure of the recipe: a photo post, a private or deleted reel
        # genuinely has no video_url. Drop it from the pack — never invent copy.
        print(f"{code}: NO video_url — skip this reel ({str(data)[:120]})")
        return False

    mp4 = wd / "video.mp4"
    subprocess.run(["curl", "-s", "-L", "-o", str(mp4), vurl], timeout=240)
    if not mp4.exists() or mp4.stat().st_size < 1000:
        print(f"{code}: download failed")
        return False

    subprocess.run(["ffmpeg", "-y", "-i", str(mp4), "-vn", "-ac", "1",
                    "-ar", "16000", "-b:a", "64k", str(mp3)],
                   capture_output=True, timeout=120)
    ok = mp3.exists() and mp3.stat().st_size > 1000
    print(f"{code}: staged {'OK' if ok else 'FAILED (ffmpeg)'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="comma-separated shortcodes; default = whole --from file")
    ap.add_argument("--from", dest="pool_file", default="_top10.json",
                    help="pool file to take codes from (default: _top10.json)")
    a = ap.parse_args()

    codes = ([c.strip() for c in a.codes.split(",") if c.strip()] if a.codes
             else codes_from_pool(a.pool_file))
    if not codes:
        sys.exit("stage_audio: no codes to stage.")

    WORK.mkdir(parents=True, exist_ok=True)
    scope = "client" if lib_paths.is_client_run() else "team (legacy)"
    print(f"stage_audio: {len(codes)} codes → {WORK}  [{scope}]")

    failed = [c for c in codes if not stage(c)]
    print(f"\nstaged {len(codes) - len(failed)}/{len(codes)}")
    if failed:
        print(f"NOT staged: {', '.join(failed)}")
        print("→ these reels have no obtainable script: drop them from the pack. "
              "Do NOT write the voice-over from the caption.")
        return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
