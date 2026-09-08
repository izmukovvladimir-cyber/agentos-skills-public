---
name: hikerapi
description: Read-only Instagram data fetcher via HikerAPI (instagrapi REST). Pulls user profiles, posts/reels, stories, comments, likers, followers/following, hashtag feeds, and full-text search. Use this skill whenever the operator mentions Instagram analytics, Reels analyzer, competitor research, account scraping, hashtag research, follower lists, comment analysis, or any HikerAPI / instagrapi endpoint -- even if not named. Also trigger on bare instagram.com links (`/p/`, `/reel/`, `/stories/`, `/<username>`) when the task is to FETCH data, and on Reels Challenge funnel ingestion. Skip when the task is to POST to Instagram or use Meta Graph API / Business Suite -- HikerAPI is read-only scrape.
---

# HikerAPI -- Instagram data fetcher

Wrapper around HikerAPI REST (148 endpoints, OpenAPI 3.1.0). Two equivalent
hosts: `api.instagrapi.com` (default -- no Cloudflare, works with Python urllib)
and `api.hikerapi.com` (fallback -- CF blocks urllib by TLS fingerprint, returns
error 1010). Authorization is a single header: `x-access-key: <token>`.

**Spec source of truth:** `https://api.hikerapi.com/openapi.json` (public, ~200KB).
The full endpoint catalog is bundled at `references/endpoints.md` -- read it when
the user asks about an endpoint not listed below.

---

## When to use

Trigger this skill on any of:

- "посмотри инстаграм-аккаунт @...", "сколько подписчиков у...", "что у конкурента"
- "достань реелсы", "проанализируй посты", "скачай комменты", "Reels analyzer"
- "хэштег #...", "что в топе по теме X в IG", "поиск аккаунтов в Instagram"
- любое упоминание HikerAPI, instagrapi, или ссылок `instagram.com/p/<code>` /
  `instagram.com/<username>` / `instagram.com/reel/<code>` -- если задача
  предполагает выгрузку данных оттуда.

Skip this skill when the operator only wants to *post* to Instagram or to use
Meta Graph API -- HikerAPI is read-only scrape, not posting.

---

## Setup (once)

1. Token lives in `$HIKER_API_KEY` (mode 600).
   Fallback: `$HIKER_API_KEY`. Override via env `HIKERAPI_KEY`.
2. If token is missing -- STOP and ask the operator. Do not invent placeholder.
3. Pricing is credit-based -- always run `balance` first when a multi-call job
   could exceed ~1000 calls, and report estimated cost to the operator before
   running.

```bash
# verify access (cheap, 1 credit)
python3 ~/.claude/skills/hikerapi/scripts/hiker.py balance
```

---

## Quick reference -- 80% use cases

All examples assume `hiker=~/.claude/skills/hikerapi/scripts/hiker.py`.
Output is JSON to stdout; pipe to `jq` for shaping.

| Need | Command |
|---|---|
| Account profile by handle | `python3 $hiker user nasa` |
| Account profile by user_id | `python3 $hiker user-id 528817151` |
| User's media (reels + posts) | `python3 $hiker medias 528817151` |
| Active stories | `python3 $hiker stories 528817151` |
| Post details by shortcode | `python3 $hiker post CA2aJYrg6cZ` |
| Post details by URL | `python3 $hiker post https://www.instagram.com/p/CA2aJYrg6cZ/` |
| Comments on a post | `python3 $hiker comments 1234567890` |
| Top media for hashtag | `python3 $hiker hashtag aiart` |
| Recent media for hashtag | `python3 $hiker hashtag aiart --recent` |
| Top search (mixed) | `python3 $hiker search "neuro reels"` |
| Account search | `python3 $hiker search "ai mentor" --mode accounts` |
| Reels search | `python3 $hiker search "viral hooks" --mode reels` |
| Any other endpoint | `python3 $hiker raw /v2/user/followers user_id=528817151` |

`raw` mode forwards `key=value` pairs as query string -- use it for any of the
148 endpoints not wrapped above (see `references/endpoints.md`).

---

## Library mode (inside Python scripts)

```python
import sys
sys.path.insert(0, "~/.claude/skills/hikerapi/scripts")
from hiker import Hiker, HikerError

h = Hiker()
profile = h.user_by_username("@your_account")
uid = profile["user"]["pk"]                 # v2 schema
medias_page = h.user_medias(uid)            # paginated by next_page_id

# iterate all pages with limit
for media in h.paginate("/gql/user/medias", items_key="response.items",
                        user_id=uid, limit=100, flat=True):
    ...
```

Errors raise `HikerError(status, body, path)`. Common cases: 401 -- bad key;
403 -- Cloudflare block (retry on `https://api.instagrapi.com`); 404 -- account
deleted/private; 429 -- rate-limited (back off ~5s).

---

## Endpoint flavors -- which to pick

| Prefix | Speed | Data depth | Notes |
|---|---|---|---|
| `/v2/...` | fast | shallow (GraphQL) | First choice for most reads. |
| `/v1/...` | slow | full (private API) | Use when v2 is missing fields. |
| `/gql/...` | fast | medium | Best for `user_medias`, `comment_likers`. |
| `/v3/...` | -- | -- | Deprecated, avoid. |

Rule of thumb: prefer `by/id` over `by/username` when you already have the
`user_id` -- it skips one resolve call. Always page with `next_page_id` /
`page_token` returned by the previous response, never invent cursors.

---

## Cost & rate-limit hygiene

- Each call = 1+ credits (chunked endpoints may cost more). `/sys/balance`
  is free.
- Before any "scrape full account history" task: estimate calls
  (`ceil(post_count / 12) + ceil(comment_count / 15)` baseline) and check
  balance covers 2x that.
- Throttle parallel calls to <=4 concurrent. Use `time.sleep(0.2)` between
  pagination steps.
- Persist intermediate results to `/tmp/hiker_<task>_<ts>.json` -- never repeat
  a paid call within a session.

---

## Reels Challenge integration (project-specific)

For the Reels analyzer pipeline (handoff , Block 6):

1. `user_by_username` -> save `pk` and basic stats.
2. `user_medias` (paginate, limit ~100 latest reels) -> filter
   `media_type==2` (clips) and sort by `play_count`.
3. For top-N reels: `post_by_code` for full caption + audio info.
4. Audio: download via `/v1/story/download` style or `track/by/id` then
   transcribe with the existing `groq-voice` skill.
5. Comments: `comments` for top-3 reels -> sentiment / hooks.

Always confirm the @username with the operator before kicking off scrapes
spanning >50 calls.

---

## References

- `references/endpoints.md` -- full 148-endpoint catalog grouped by tag.
- Live OpenAPI: `https://api.hikerapi.com/openapi.json`
- Swagger UI: `https://api.hikerapi.com/docs`
- Without Cloudflare: `https://api.instagrapi.com/docs`
