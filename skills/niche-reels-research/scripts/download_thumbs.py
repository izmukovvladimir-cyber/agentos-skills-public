#!/usr/bin/env python3
"""Download thumbnails для топа рилсов И каруселей.

ВАЖНО: источник топа рилсов — `_scored.json` (выход score.py: freshness-gate уже
применён, сортировка по скору). РАНЬШЕ был баг — читали `_top3_per_account.json`
и сортировали по сырым просмотрам, из-за чего gate обходился и в обзор попадало
стале. Fallback на _top3 оставлен только если _scored.json отсутствует.

Выход:
  thumbs/NN_<user>_<code>.jpg        — превью рилсов
  thumbs/cNN_<user>_<code>.jpg       — превью каруселей
  _top15.json                        — плоский топ рилсов для разбора <agent>
  _carousels_top15.json (если есть)  — плоский топ каруселей
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy path.
POOL = lib_paths.pool_dir()
THUMB_DIR = POOL / "thumbs"
THUMB_DIR.mkdir(exist_ok=True)
TOP_N = 15


def fetch_thumb(url: str, out: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            out.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"   thumb ERR {out.name}: {e}")
        return False


def reels_top() -> list[dict]:
    """Берём gated выход score.py. Каждый item: username, code, score, extras, raw."""
    scored_f = POOL / "_scored.json"
    if scored_f.exists():
        scored = json.loads(scored_f.read_text())
        flat = []
        for s in scored[:TOP_N]:
            raw = dict(s.get("raw", {}))
            ex = s.get("score_breakdown", {}).get("extras", {})
            raw["username"] = s.get("username")
            raw["code"] = raw.get("code") or s.get("code")
            raw["url"] = s.get("url") or raw.get("url")
            raw["score_total"] = s.get("score_total")
            raw["age_h"] = ex.get("age_h")
            raw["viral_ratio"] = ex.get("viral_ratio")
            raw.setdefault("play_count", ex.get("views"))
            flat.append(raw)
        return flat
    # fallback (старое поведение) — БЕЗ freshness-gate, только если score не отработал
    print("WARN: _scored.json отсутствует — fallback на _top3 (gate НЕ применён!)")
    data = json.loads((POOL / "_top3_per_account.json").read_text())
    all_reels = []
    for acc in data:
        for r in acc.get("reels", []):
            if r.get("play_count"):
                all_reels.append({**r, "username": acc["username"]})
    all_reels.sort(key=lambda r: r.get("play_count") or 0, reverse=True)
    return all_reels[:TOP_N]


def carousels_top() -> list[dict]:
    f = POOL / "_carousels_top.json"
    if not f.exists():
        return []
    scored = json.loads(f.read_text())
    flat = []
    for s in scored[:TOP_N]:
        raw = dict(s.get("raw", {}))
        ex = s.get("extras", {})
        raw["username"] = s.get("username")
        raw["code"] = raw.get("code") or s.get("code")
        raw["url"] = s.get("url") or raw.get("url")
        raw["score_total"] = s.get("score_total")
        raw["age_h"] = ex.get("age_h")
        raw["viral_ratio"] = ex.get("viral_ratio")
        raw["slides"] = ex.get("slides")
        flat.append(raw)
    return flat


def main() -> None:
    reels = reels_top()
    print(f"=== REELS top {len(reels)} ===")
    for i, r in enumerate(reels, 1):
        code = r.get("code") or f"unknown_{i}"
        url = r.get("thumb_url")
        if url and fetch_thumb(url, THUMB_DIR / f"{i:02d}_{r['username']}_{code}.jpg"):
            print(f"{i:2d}. {r['username']:20s} {code} views={(r.get('play_count') or 0)/1000:.0f}k "
                  f"age={r.get('age_h')}ч ratio={r.get('viral_ratio')}")
        else:
            print(f"{i:2d}. {code} — no thumb url")
    (POOL / "_top15.json").write_text(json.dumps(reels, ensure_ascii=False, indent=2))
    print(f"Saved {len(reels)} reels → _top15.json")

    carousels = carousels_top()
    if carousels:
        print(f"\n=== CAROUSELS top {len(carousels)} ===")
        for i, c in enumerate(carousels, 1):
            code = c.get("code") or f"unknown_{i}"
            url = c.get("thumb_url")
            if url and fetch_thumb(url, THUMB_DIR / f"c{i:02d}_{c['username']}_{code}.jpg"):
                print(f"c{i:2d}. {c['username']:20s} {code} likes={c.get('like_count')} "
                      f"age={c.get('age_h')}ч ratio={c.get('viral_ratio')} slides={c.get('slides')}")
            else:
                print(f"c{i:2d}. {code} — no thumb url")
        (POOL / "_carousels_top15.json").write_text(json.dumps(carousels, ensure_ascii=False, indent=2))
        print(f"Saved {len(carousels)} carousels → _carousels_top15.json")
    else:
        print("\n(каруселей нет — _carousels_top.json отсутствует или пуст)")


if __name__ == "__main__":
    main()
