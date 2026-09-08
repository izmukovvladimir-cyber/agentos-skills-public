#!/usr/bin/env python3
"""Pull full following list for each of 6 опорных через HikerAPI."""
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

KEY = os.environ["HIKER_API_KEY"]
BASE = "https://api.instagrapi.com"
OUT_DIR = Path("/tmp/expand_pool")
OUT_DIR.mkdir(exist_ok=True)

USERNAMES = [
    "donor_one",
    "donor_two",
    "donor_three",
    "donor_four",
    "donor_five",
    "donor_six",
]


def call(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{BASE}{path}?{qs}",
        headers={"x-access-key": KEY, "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode()[:300]}
    except Exception as e:
        return {"_error": str(e)}


def get_user_id(username: str) -> tuple[str | None, dict]:
    data = call("/v1/user/by/username", {"username": username})
    uid = data.get("pk") or data.get("id")
    return (str(uid) if uid else None, data)


def pull_following(uid: str, username: str) -> list[dict]:
    all_users = []
    page_id = None
    page = 0
    while True:
        page += 1
        params = {"user_id": uid}
        if page_id:
            params["page_id"] = page_id
        data = call("/v2/user/following", params)
        if "_error" in data:
            print(f"  [{username}] page {page} ERROR: {data.get('_error')} body={data.get('_body','')[:120]}")
            break
        users = data.get("response", {}).get("users") or data.get("users", [])
        if not users and page == 1:
            print(f"  [{username}] page {page} empty, keys={list(data.keys())[:6]}")
        all_users.extend(users)
        page_id = data.get("next_page_id") or data.get("response", {}).get("next_page_id")
        print(f"  [{username}] page {page}: +{len(users)} (total {len(all_users)}) next={'Y' if page_id else 'N'}")
        if not page_id:
            break
        if page >= 50:  # safety cap
            print(f"  [{username}] safety cap 50 pages")
            break
        time.sleep(0.5)
    return all_users


def main():
    summary = {}
    for username in USERNAMES:
        print(f"\n=== {username} ===")
        uid, profile = get_user_id(username)
        if not uid:
            print(f"  user_id NOT FOUND: {json.dumps(profile)[:200]}")
            summary[username] = {"error": "no_user_id"}
            continue
        print(f"  user_id={uid} followers={profile.get('follower_count') or profile.get('edge_followed_by',{}).get('count','?')}")
        users = pull_following(uid, username)
        out = OUT_DIR / f"{username}_following.json"
        out.write_text(json.dumps({"username": username, "user_id": uid, "count": len(users), "users": users}, ensure_ascii=False, indent=2))
        summary[username] = {"user_id": uid, "count": len(users), "file": str(out)}
        print(f"  saved {len(users)} → {out}")
        time.sleep(1.0)

    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    for u, s in summary.items():
        print(f"  {u}: {s}")


if __name__ == "__main__":
    main()
