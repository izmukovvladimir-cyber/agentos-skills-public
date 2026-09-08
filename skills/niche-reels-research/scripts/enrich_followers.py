#!/usr/bin/env python3
"""Дозапросить followers count + media count для top-30."""
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

KEY = os.environ["HIKER_API_KEY"]
BASE = "https://api.instagrapi.com"
POOL = Path("/tmp/expand_pool")


def call(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{BASE}{path}?{qs}",
        headers={"x-access-key": KEY, "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}


def main():
    candidates = json.loads((POOL / "filtered_top60.json").read_text())
    enriched = []
    for i, c in enumerate(candidates[:35], 1):
        username = c["username"]
        print(f"{i:2d}. {username} ...", end=" ", flush=True)
        data = call("/v1/user/by/username", {"username": username})
        if "_error" in data:
            print(f"ERR {data['_error']}")
            c["follower_count_live"] = None
            c["media_count_live"] = None
            enriched.append(c)
            continue
        followers = data.get("follower_count") or 0
        following = data.get("following_count") or 0
        media = data.get("media_count") or 0
        c["follower_count_live"] = followers
        c["following_count_live"] = following
        c["media_count_live"] = media
        c["is_verified"] = data.get("is_verified", c.get("is_verified"))
        c["is_business"] = data.get("is_business")
        c["biography"] = data.get("biography", c.get("biography"))[:300]
        print(f"followers={followers/1000:.1f}k posts={media}")
        enriched.append(c)
        time.sleep(0.3)

    (POOL / "enriched_top35.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(enriched)} → enriched_top35.json")


if __name__ == "__main__":
    main()
