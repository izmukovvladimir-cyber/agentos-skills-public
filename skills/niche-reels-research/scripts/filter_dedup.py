#!/usr/bin/env python3
"""Объединяет все following.json, дедуплицирует, фильтрует по нише."""
import json
import re
from pathlib import Path
from collections import defaultdict

POOL = Path("/tmp/expand_pool")
ANCHORS = ["liza.tkachyk", "ilia.paliy", "batischv", "ikatevibe", "burmistrov_ai", "dashi_agent"]

# Ниша: AI / нейро / IG-рост / маркетинг / Reels / контент / promo
NICHE_KEYWORDS = [
    "ai", "ии", "нейро", "neuro", "нейросет", "промпт", "prompt", "gpt", "claude",
    "instagram", "ig", "инст", "рилс", "reel", "блог", "blog", "контент", "content",
    "маркет", "market", "smm", "traffic", "трафик", "продюс", "produc",
    "tiktok", "тикток", "автомат", "automat", "agent", "агент",
    "tech", "тех", "креатор", "creator", "монетиз", "metiz", "monetiz",
    "коуч", "coach", "наставник", "ментор", "mentor", "expert", "эксперт",
    "soft", "программ", "develop", "разработ", "code", "вайб",
    "школ", "school", "курс", "course", "обучен", "education",
    "бизнес", "business", "предпринима", "entrepre",
    "видео", "video", "shorts", "shortform", "ugc", "креатив",
    "design", "дизайн", "редак", "edit",
    "анализ", "analytic", "growth", "рост",
]

LANG_BAN = []  # пока не баним по языку

# Технические бренды / партнёры — не интересны как доноры контента
SKIP_USERS = {"instagram", "facebook", "meta", "whatsapp", "messenger", "threads"}


def normalize(s: str) -> str:
    return (s or "").lower()


def in_niche(user: dict) -> tuple[bool, list[str]]:
    username = normalize(user.get("username", ""))
    full_name = normalize(user.get("full_name", ""))
    biography = normalize(user.get("biography", ""))
    blob = f"{username} {full_name} {biography}"
    hits = [kw for kw in NICHE_KEYWORDS if kw in blob]
    return (len(hits) > 0, hits)


def main():
    seen = {}  # pk -> {user, anchors:set, hits:set}
    for anchor in ANCHORS:
        path = POOL / f"{anchor}_following.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for u in data.get("users", []):
            pk = u.get("pk") or u.get("id")
            if not pk:
                continue
            uname = normalize(u.get("username", ""))
            if uname in SKIP_USERS:
                continue
            if pk not in seen:
                seen[pk] = {"user": u, "anchors": set(), "hits": set()}
            seen[pk]["anchors"].add(anchor)

    # фильтр по нише
    filtered = []
    for pk, entry in seen.items():
        is_niche, hits = in_niche(entry["user"])
        if is_niche:
            entry["hits"] = hits
            filtered.append(entry)

    # сортировка: по количеству опорных (cross-followed), потом по keyword hits, потом по followers
    def sort_key(e):
        return (
            -len(e["anchors"]),
            -len(e["hits"]),
            -(e["user"].get("follower_count") or 0),
        )

    filtered.sort(key=sort_key)

    # отчёт
    print(f"\nTotal unique users in pool: {len(seen)}")
    print(f"In niche (по keywords): {len(filtered)}")
    print(f"Cross-followed (>=2 опорных): {sum(1 for e in filtered if len(e['anchors']) >= 2)}")

    # сохранить
    out = []
    for e in filtered[:60]:
        u = e["user"]
        out.append({
            "username": u.get("username"),
            "full_name": u.get("full_name"),
            "pk": u.get("pk") or u.get("id"),
            "is_verified": u.get("is_verified"),
            "is_private": u.get("is_private"),
            "follower_count": u.get("follower_count"),
            "biography": (u.get("biography") or "")[:200],
            "anchors": sorted(list(e["anchors"])),
            "anchor_count": len(e["anchors"]),
            "niche_hits": e["hits"][:5],
        })

    (POOL / "filtered_top60.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nSaved top 60 → {POOL / 'filtered_top60.json'}")

    # короткий вывод в консоль
    print("\n=== TOP 30 ===")
    for i, e in enumerate(out[:30], 1):
        v = "✓" if e["is_verified"] else " "
        followers = e["follower_count"]
        followers_str = f"{followers/1000:.1f}k" if followers else "?"
        anchors_str = ",".join(a[:6] for a in e["anchors"])
        bio = (e["biography"] or "").replace("\n", " ")[:80]
        print(f"{i:2d}. {v} @{e['username']:25s} {followers_str:>7s}  [{e['anchor_count']}x: {anchors_str}]")
        print(f"     {e['full_name']:40s}  hits={e['niche_hits']}")
        if bio:
            print(f"     bio: {bio}")


if __name__ == "__main__":
    main()
