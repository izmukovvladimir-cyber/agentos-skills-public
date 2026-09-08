"""lib_paths.py — per-client path resolution for the niche-reels pipeline.

Isolation rule: every client agent parses ONLY its own
watchlist and writes ONLY into its own workspace. Client watchlists must never
mix with the team  watchlist, and the shared config must not
be read on a client run.

Contract:
  env NRR_CLIENT_DIR = absolute base dir of the client instance, e.g.
      ~/.claude/reels-digest
  Layout under that base dir (created on demand by the scripts):
      config/watchlist.json   client watchlist — same schema as the shared one
      cache/                  uid_cache.json, reels_seen.json, themes_seen.json
      pool/                   scrape/score output (_scored.json, _top10.json,
                              thumbs/, packs/, ...)
      out/                    rendered digest HTML (send_morning_digest)

  env UNSET  -> legacy shared behaviour byte-for-byte:
      config  = <skill>/config/watchlist.json
      cache   = <skill>/cache/
      pool    = /tmp/expand_pool/reels
      out     = <agent> assets/montage
  so <agent>'s 06:00 МСК cron run (daily_morning_auto.sh, no env) is untouched.

The env var is read at import time on purpose: one process = one tenant.
"""
from __future__ import annotations

import os
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

_raw = os.environ.get("NRR_CLIENT_DIR", "").strip()
CLIENT_DIR: Path | None = Path(_raw).expanduser() if _raw else None


def is_client_run() -> bool:
    return CLIENT_DIR is not None


def config_file() -> Path:
    if CLIENT_DIR:
        return CLIENT_DIR / "config" / "watchlist.json"
    return SKILL_DIR / "config" / "watchlist.json"


def cache_dir() -> Path:
    if CLIENT_DIR:
        return CLIENT_DIR / "cache"
    return SKILL_DIR / "cache"


def pool_dir() -> Path:
    if CLIENT_DIR:
        return CLIENT_DIR / "pool"
    return Path("/tmp/expand_pool/reels")


def out_dir() -> Path:
    if CLIENT_DIR:
        return CLIENT_DIR / "out"
    return Path("~/.claude/assets/montage")


def packs_dir() -> Path:
    """Canonical packs location — the ONE place the daily gen_packs writes AND send_morning_digest
    reads. Client: isolated under its own pool (pool_dir()/packs). Owner: the skill's own packs/ dir
    (SKILL_DIR/packs), where the daily gen_packs_<MMDD>.py writes (Path(__file__).parent.parent/packs).

    NOTE (board #56, ): the owner default was previously pool_dir()/packs =
    /tmp/expand_pool/reels/packs, but the daily gen_packs stopped writing there (it now writes
    SKILL_DIR/packs), so /tmp packs froze at an old date_label and a stale digest almost shipped.
    Anchoring both read and write to this one function removes that divergence. The owner's scored/
    coverage files stay in pool_dir() (/tmp/expand_pool/reels) and are refreshed by the daily scrape,
    so they remain consistent with the fresh SKILL_DIR/packs."""
    if CLIENT_DIR:
        return pool_dir() / "packs"
    return SKILL_DIR / "packs"
