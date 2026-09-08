#!/usr/bin/env python3
"""HikerAPI thin wrapper. Library + CLI. No external deps.

Reads access key from (in order):
  1. env HIKERAPI_KEY (или $HIKER_API_KEY)
  2. file ~/.secrets/hikerapi-key (mode 600)

Usage as CLI:
  python hiker.py balance
  python hiker.py user <username>
  python hiker.py medias <user_id> [--limit N]
  python hiker.py post <code_or_url>
  python hiker.py comments <media_id>
  python hiker.py hashtag <name> [--top|--recent]
  python hiker.py search <query>
  python hiker.py raw <path> key=val key=val...

Library:
  from hiker import Hiker
  h = Hiker()
  h.balance()
  h.user_by_username("nasa")
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.instagrapi.com"  # CF-free; api.hikerapi.com blocks urllib by TLS fingerprint
FALLBACK_BASE = "https://api.hikerapi.com"
# Ключ берётся из окружения ($HIKERAPI_KEY / $HIKER_API_KEY); файл — запасной путь.
KEY_PATHS = [
    Path.home() / ".secrets/hikerapi-key",
]


class HikerError(RuntimeError):
    def __init__(self, status: int, body: str, path: str):
        super().__init__(f"HikerAPI {status} on {path}: {body[:200]}")
        self.status = status
        self.body = body
        self.path = path


def _load_key() -> str:
    key = os.environ.get("HIKERAPI_KEY") or os.environ.get("HIKER_API_KEY")
    if key:
        return key.strip()
    for p in KEY_PATHS:
        if p.is_file():
            return p.read_text().strip()
    raise RuntimeError(
        "HikerAPI key not found. Set $HIKERAPI_KEY or place key in "
        f"{KEY_PATHS[0]} (mode 600)."
    )


class Hiker:
    def __init__(self, key: str | None = None, base: str = DEFAULT_BASE, timeout: int = 30):
        self.key = key or _load_key()
        self.base = base.rstrip("/")
        self.timeout = timeout

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        qs = urllib.parse.urlencode(clean)
        url = f"{self.base}{path}"
        if qs:
            url += "?" + qs
        req = urllib.request.Request(url, headers={
            "x-access-key": self.key,
            "accept": "application/json",
            "user-agent": "hikerapi-skill/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise HikerError(e.code, body, path) from None

    def paginate(self, path: str, cursor_in: str = "page_id", cursor_out: str = "next_page_id",
                 items_key: str | None = None, limit: int | None = None,
                 **params: Any) -> Iterator[dict[str, Any]]:
        """Iterate pages.

        cursor_in: query param name accepted by the endpoint (page_id, next_max_id, page_token).
        cursor_out: response field with next cursor (next_page_id, next_max_id, page_token).
        items_key: dotted path inside the page dict to extract list of items
                   (e.g. "response.items"). If None, yields whole page dicts.
        """
        seen = 0
        while True:
            page = self.get(path, **params)
            if items_key:
                obj: Any = page
                for part in items_key.split("."):
                    if not isinstance(obj, dict): obj = None; break
                    obj = obj.get(part)
                items = obj if isinstance(obj, list) else []
                for it in items:
                    yield it
                    seen += 1
                    if limit and seen >= limit:
                        return
            else:
                yield page
                seen += 1
                if limit and seen >= limit:
                    return
            nxt = page.get(cursor_out)
            if not nxt:
                return
            params[cursor_in] = nxt
            time.sleep(0.2)

    # ---- High-frequency helpers ----
    def balance(self) -> dict[str, Any]:
        return self.get("/sys/balance")

    def user_by_username(self, username: str) -> dict[str, Any]:
        return self.get("/v2/user/by/username", username=username)

    def user_by_id(self, user_id: str) -> dict[str, Any]:
        return self.get("/v2/user/by/id", id=str(user_id))

    def user_medias(self, user_id: str, page_id: str | None = None, flat: bool = True) -> dict[str, Any]:
        """Лента через `/gql`. ОСТОРОЖНО С ПАГИНАЦИЕЙ: курсор бывает застревает.

        Замер  по @your_account: с третьей страницы ручка отдаёт ОДИН И ТОТ
        ЖЕ `next_max_id` и те же 12 медиа при `more_available: True`, шесть страниц дали
        15 уникальных постов (дубли с четвёртой страницы 12 из 12). Обход при этом не
        падает и выглядит работающим, поэтому сторож долга по кодвордам месяц листал бы
        до предела страниц и объявлял охват неполным по ложной причине.
        Для окна больше пары страниц берите `user_medias_v2`, а здесь обязательно
        сравнивайте очередной курсор с уже виденными.
        """
        return self.get("/gql/user/medias", user_id=str(user_id),
                        profile_grid_items_cursor=page_id, flat=flat)

    def user_medias_v2(self, user_id: str, page_id: str | None = None) -> dict[str, Any]:
        """Лента через `/v2`: пагинация честная, отдаются ВСЕ типы постов.

        Тот же замер: 4 страницы дали 48 уникальных постов, дублей 0, даты убывают ровно,
        в выдаче разом фото feed, клипы и карусели, то есть кодворд под каруселью виден.
        Курсор лежит в `next_page_id`, параметр называется `page_id`.
        КАПШЕН ЗДЕСЬ ТОЛЬКО СЛОВАРЁМ `caption.text`, поля `caption_text` нет вовсе:
        читающий одно имя сложит пустые капшены без единой ошибки (0 непустых из 84
        у <agent>). Читайте оба имени.
        """
        params: dict[str, Any] = {"user_id": str(user_id)}
        if page_id:
            params["page_id"] = str(page_id)
        return self.get("/v2/user/medias", **params)

    def user_stories(self, user_id: str) -> dict[str, Any]:
        return self.get("/v2/user/stories", user_id=str(user_id))

    def post_by_code(self, code: str) -> dict[str, Any]:
        return self.get("/v2/media/info/by/code", code=code)

    def post_by_url(self, url: str) -> dict[str, Any]:
        return self.get("/v2/media/info/by/url", url=url)

    def comments(self, media_id: str, page_id: str | None = None) -> dict[str, Any]:
        return self.get("/v2/media/comments", id=str(media_id), page_id=page_id)

    def hashtag_top(self, name: str, page_id: str | None = None) -> dict[str, Any]:
        return self.get("/v2/hashtag/medias/top", name=name, page_id=page_id)

    def hashtag_recent(self, name: str, page_id: str | None = None) -> dict[str, Any]:
        return self.get("/v2/hashtag/medias/recent", name=name, page_id=page_id)

    def search_top(self, query: str) -> dict[str, Any]:
        return self.get("/v2/fbsearch/topsearch", query=query)

    def search_accounts(self, query: str) -> dict[str, Any]:
        return self.get("/v2/fbsearch/accounts", query=query)

    def search_reels(self, query: str) -> dict[str, Any]:
        return self.get("/v2/fbsearch/reels", query=query)


def _print(obj: Any) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="HikerAPI CLI wrapper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("balance")
    p = sub.add_parser("user");      p.add_argument("username")
    p = sub.add_parser("user-id");   p.add_argument("user_id")
    p = sub.add_parser("medias");    p.add_argument("user_id"); p.add_argument("--page", default=None)
    p = sub.add_parser("medias-v2"); p.add_argument("user_id"); p.add_argument("--page", default=None)
    p = sub.add_parser("stories");   p.add_argument("user_id")
    p = sub.add_parser("post");      p.add_argument("code_or_url")
    p = sub.add_parser("comments");  p.add_argument("media_id"); p.add_argument("--page", default=None)
    p = sub.add_parser("hashtag");   p.add_argument("name"); p.add_argument("--recent", action="store_true")
    p = sub.add_parser("search");    p.add_argument("query"); p.add_argument("--mode", choices=["top","accounts","reels"], default="top")
    p = sub.add_parser("raw");       p.add_argument("path"); p.add_argument("kv", nargs="*")

    args = parser.parse_args(argv)

    try:
        h = Hiker()
        if args.cmd == "balance":
            _print(h.balance())
        elif args.cmd == "user":
            _print(h.user_by_username(args.username))
        elif args.cmd == "user-id":
            _print(h.user_by_id(args.user_id))
        elif args.cmd == "medias":
            _print(h.user_medias(args.user_id, page_id=args.page))
        elif args.cmd == "medias-v2":
            _print(h.user_medias_v2(args.user_id, page_id=args.page))
        elif args.cmd == "stories":
            _print(h.user_stories(args.user_id))
        elif args.cmd == "post":
            arg = args.code_or_url
            _print(h.post_by_url(arg) if arg.startswith("http") else h.post_by_code(arg))
        elif args.cmd == "comments":
            _print(h.comments(args.media_id, page_id=args.page))
        elif args.cmd == "hashtag":
            fn = h.hashtag_recent if args.recent else h.hashtag_top
            _print(fn(args.name))
        elif args.cmd == "search":
            fn = {"top": h.search_top, "accounts": h.search_accounts, "reels": h.search_reels}[args.mode]
            _print(fn(args.query))
        elif args.cmd == "raw":
            params = dict(kv.split("=", 1) for kv in args.kv if "=" in kv)
            _print(h.get(args.path, **params))
    except HikerError as e:
        print(f"ERROR {e.status}: {e.body[:300]}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
