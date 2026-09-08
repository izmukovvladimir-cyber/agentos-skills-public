#!/usr/bin/env python3
"""Pull top-3 reels в окне свежести для каждого аккаунта из config/watchlist.json.

Параллельный проход по аккаунтам (ThreadPoolExecutor) — sequential-версия не
укладывалась в окно при росте watchlist (44 акк → timeout 1800c, rc=124;
план владельца 100→200). Конкурентность = limits.scrape_workers (по умолчанию 8),
сама по себе служит rate-limit'ом; call() дополнительно ретраит 429/5xx с backoff.
Порядок выдачи детерминирован (по порядку watchlist), несмотря на гонку потоков.
"""
import json
import os
import random
import time
import urllib.request
import urllib.parse
import urllib.error
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median as _median

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_resolve
import lib_paths

KEY = os.environ["HIKER_API_KEY"]
BASE = "https://api.instagrapi.com"
# Per-client isolation: env NRR_CLIENT_DIR redirects config/cache/pool into the
# client workspace (see lib_paths.py). Unset = legacy shared paths (<agent>'s run).
OUT_DIR = lib_paths.pool_dir()
OUT_DIR.mkdir(exist_ok=True, parents=True)

SKILL_DIR = lib_paths.SKILL_DIR
WATCHLIST_FILE = lib_paths.config_file()

# Ретрай-политика для параллельных запросов: при 429/5xx или сетевом сбое
# отступаем и повторяем (а не роняем аккаунт). Транзиентные коды HikerAPI.
RETRY_HTTP = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


def load_watchlist() -> tuple[list[str], int, int]:
    """Источник правды — config/watchlist.json. Возвращает (usernames, fallback_hours, workers)."""
    cfg = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))

    def names(key: str) -> list[str]:
        out = []
        for a in cfg.get(key, []) or []:
            u = a.get("username") if isinstance(a, dict) else a
            if u:
                out.append(u)
        return out

    banned = {
        str(a.get("username") if isinstance(a, dict) else a).lower()
        for a in cfg.get("rejected", []) or []
        if (a.get("username") if isinstance(a, dict) else a)
    }
    usernames = [
        u for u in names("anchor_accounts") + names("expansion_accounts")
        if u.lower() not in banned
    ]
    limits = cfg.get("limits", {})
    fallback_h = int(limits.get("fallback_lookback_hours", 48))
    workers = int(limits.get("scrape_workers", 8))
    workers = max(1, min(workers, 24))  # здравый потолок
    # сколько лучших (по просмотрам) роликов брать с каждого аккаунта в пул.
    # 3 было слишком мало: у плодовитых авторов 4-5-й виральный ролик отсекался
    # до скоринга. 8 ловит реальные выстрелы.
    per_account = int(limits.get("reels_per_account", 8))
    per_account = max(1, min(per_account, 20))
    return usernames, fallback_h, workers, per_account


WATCHLIST, FALLBACK_HOURS, SCRAPE_WORKERS, REELS_PER_ACCOUNT = load_watchlist()
MEDIAN_SAMPLE_SIZE = 30

# Потолок свежести = fallback окно из конфига (по умолчанию 48ч). 24ч-приоритет — в score.py.
SINCE_TS = int(time.time()) - FALLBACK_HOURS * 3600


def call(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            url, headers={"x-access-key": KEY, "accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            if e.code in RETRY_HTTP and attempt < MAX_RETRIES:
                # jitter: параллельные потоки не должны ретраить в один такт
                # (синхронный повтор усиливает rate-limit и множит платные вызовы)
                time.sleep(1.5 * (2 ** attempt) * (0.6 + 0.8 * random.random()))
                last_err = f"HTTP {e.code}"
                continue
            return {"_error": f"HTTP {e.code}", "_body": body}
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * (2 ** attempt) * (0.6 + 0.8 * random.random()))
                last_err = str(e)
                continue
            return {"_error": str(e)}
    return {"_error": last_err or "retries exhausted"}


UID_CACHE_FILE = lib_paths.cache_dir() / "uid_cache.json"
_RESOLVER = lib_resolve.Resolver(
    call, UID_CACHE_FILE, lib_resolve.load_watchlist_seeds(WATCHLIST_FILE)
)


def get_user_id(username: str, log: list | None = None) -> tuple[str | None, int | None]:
    """Возвращает (user_id, follower_count) через устойчивый резолв (lib_resolve).

    HikerAPI /v1/user/by/username периодически отдаёт 404 UserNotFound
    (замаскированный IG rate-limit) для живого аккаунта → раньше он выпадал из
    пула. Теперь uid неизменного аккаунта кэшируется (cache/uid_cache.json) и
    вытягивается в throttle-день, а followers из того же ответа кормит метрику
    «просмотров больше, чем подписчиков» (главный признак виралки). Детали fallback-цепочки — в lib_resolve.py."""
    return _RESOLVER.resolve(username, log)


def _is_empty_404(data: dict) -> bool:
    """404 NotFound на clips/medias это не сбой, а «у аккаунта нет медиа».

    HikerAPI на живом пустом аккаунте (media_count=0) отдаёт HTTP 404 с телом
    `NotFoundError` / «Entries not found». Это ОКОНЧАТЕЛЬНЫЙ ответ (404 нет в
    RETRY_HTTP, повторять нечего), а не rate-limit и не сбой. Смешивать его с
    реальным сбоем нельзя: пустой аккаунт неделями эскалируется как clips_fetch_failed
    (разобранный случай донора)."""
    if data.get("_error") != "HTTP 404":
        return False
    body = str(data.get("_body", "")).lower()
    return "notfound" in body or "entries not found" in body or "not found" in body


def page_covers_window(items: list[dict], since_ts: int) -> bool:
    """Страница целиком за окном свежести, значит листать дальше незачем.

    Судим СТРАНИЦУ, а не отдельный ролик: закреплённые посты лежат вверху ленты и
    бывают древними, поэтому признак «встретился старый» закрыл бы окно на первой
    странице (замер <agent>  по @your_account, три поста от 17.05 сверху).
    Пустая страница окно НЕ закрывает: нечитаемое это не «старое».
    """
    dates = []
    for it in items:
        m = it.get("media") if isinstance(it, dict) and "media" in it else it
        if not isinstance(m, dict):
            continue
        t = m.get("taken_at") or m.get("taken_at_ts") or m.get("1ltaken_at") or 0
        if isinstance(t, str):
            t = int(t) if t.isdigit() else 0
        if t:
            dates.append(int(t))
    return bool(dates) and max(dates) < since_ts


MAX_PAGES = 6


def get_user_clips(uid: str, username: str, log: list[str]) -> tuple[list[dict], str]:
    """Use /v2/user/clips for reels-only. Возвращает (clips, status).

    status:
      "ok"      — окно свежести закрыто: дошли до страницы целиком старше окна либо
                  лента кончилась. Клипов может быть 0, это законно.
      "partial" — страницы читались, но окно НЕ закрыто (сбой поздней страницы либо
                  предел MAX_PAGES). Собранное отдаём, аккаунт ошибкой НЕ метим, но
                  недобор называем вслух: до  он уходил под статусом "ok"
                  и выглядел как «у автора мало роликов» (нашла агент Александры).
      "empty"   — аккаунт ЖИВ, но медиа нет (404 NotFound на clips И medias). Не ошибка.
      "failed"  — реальный сбой первой страницы (rate-limit/5xx/сеть). Вызывающий
                  помечает ошибкой, иначе тотальный отказ эндпоинта выглядел бы как
                  «все аккаунты пусты» и проскочил бы мимо ok==0-гварда.
    """
    out = []
    page_id = None
    pages = 0
    covered = False
    why = f"предел {MAX_PAGES} страниц"
    for page in range(1, MAX_PAGES + 1):
        params = {"user_id": uid}
        if page_id:
            params["page_id"] = page_id
        # Instagram отдаёт 5xx на поздние страницы через раз, тем же ключом соседний
        # обход проходит целиком. Без ретрая это тихий недобор роликов в подборке.
        data = call("/v2/user/clips", params)
        for _ in range(2):
            if "_error" not in data or _is_empty_404(data):
                break
            time.sleep(3)
            data = call("/v2/user/clips", params)
        from_medias = False
        if "_error" in data:
            log.append(f"  [{username}] clips error: {data.get('_error')} body={data.get('_body','')[:80]}")
            # try medias as fallback
            if page == 1:
                clips_empty = _is_empty_404(data)
                data = call("/v2/user/medias", {"user_id": uid})
                if "_error" in data:
                    # оба эндпоинта дали окончательный 404 → аккаунт пуст, это не сбой
                    if clips_empty and _is_empty_404(data):
                        log.append(f"  [{username}] clips+medias = 404 NotFound → аккаунт без медиа")
                        return [], "empty"
                    return [], "failed"
                from_medias = True
            else:
                why = f"страница {page} не прочиталась за 3 попытки"
                break  # сбой поздней страницы — оставляем собранное, статус partial
        pages += 1
        items = data.get("response", {}).get("items") or data.get("items") or []
        for it in items:
            media = it.get("media") if "media" in it else it
            out.append(media)
        if page_covers_window(items, SINCE_TS):
            covered, why = True, "окно закрыто"
            break
        if from_medias:
            # Курсор medias в clips НЕ подставляем: это разные ленты, и на следующей
            # итерации чужой page_id уходил в clips (нашла агент Александры ).
            why = "фолбэк на medias, дальше не листаем"
            break
        page_id = data.get("next_page_id") or data.get("response", {}).get("next_page_id")
        if not page_id:
            covered, why = True, "лента кончилась"
            break
        time.sleep(0.4)
    log.append(f"  [{username}] охват: страниц {pages}, {why}")
    return out, ("ok" if covered else "partial")


def _views(m):
    return m.get("play_count") or m.get("view_count") or m.get("ig_play_count") or 0


def process_account(username: str) -> dict:
    """Полный per-account проход — выполняется в пуле потоков.

    Логи аккаунта буферизуются и печатаются одним блоком, чтобы вывод не
    перемешивался между параллельными потоками.
    """
    log: list[str] = [f"\n=== {username} ==="]
    try:
        uid, followers = get_user_id(username, log)
        if not uid:
            log.append("  no user_id")
            print("\n".join(log), flush=True)
            return {"username": username, "error": "no_uid", "reels": []}
        log.append(f"  followers={followers}")

        clips, status = get_user_clips(uid, username, log)
        if status == "failed":
            log.append("  clips+medias первая страница упала → аккаунт помечен ошибкой")
            print("\n".join(log), flush=True)
            return {"username": username, "error": "clips_fetch_failed", "reels": []}
        if status == "empty":
            log.append("  аккаунт жив, но медиа нет → no_media (не ошибка API)")
            print("\n".join(log), flush=True)
            return {"username": username, "error": "no_media", "reels": []}
        log.append(f"  {len(clips)} clips total fetched")
        if status == "partial":
            # Недобор называем вслух и уносим в результат: до  он уходил под
            # статусом "ok" и читался как «у автора мало роликов», то есть слабый пак
            # выглядел свойством донора, а не сбоем сбора.
            log.append("  ОХВАТ НЕПОЛНЫЙ: окно свежести прочитано не целиком, роликов могло быть больше")

        # baseline: медиана просмотров по последним ~30 клипам (считаем здесь, не ре-фетчим в score.py)
        base_views = [_views(c) for c in clips[:MEDIAN_SAMPLE_SIZE] if _views(c) > 0]
        median_views = int(_median(base_views)) if base_views else None
        log.append(f"  median_views={median_views} (n={len(base_views)})")

        # фильтруем только видео + в окне свежести
        fresh = []
        for c in clips:
            taken_at = c.get("taken_at") or c.get("taken_at_ts") or 0
            if isinstance(taken_at, str):
                try:
                    taken_at = int(taken_at)
                except ValueError:
                    taken_at = 0
            if taken_at < SINCE_TS:
                continue
            mtype = c.get("media_type")
            if mtype not in (2, "2"):
                continue
            fresh.append(c)

        log.append(f"  {len(fresh)} fresh (<={FALLBACK_HOURS}ч) видео")

        fresh.sort(key=_views, reverse=True)
        top_reels = fresh[:REELS_PER_ACCOUNT]

        reel_info = []
        for r in top_reels:
            code = r.get("code") or r.get("shortcode")
            v = r.get("video_url")
            tn = (r.get("image_versions2", {}) or {}).get("candidates", [])
            thumb = tn[0]["url"] if tn else None
            vc = _views(r)
            ri = {
                "code": code,
                "url": f"https://www.instagram.com/reel/{code}/" if code else None,
                "taken_at": r.get("taken_at"),
                "duration": r.get("video_duration"),
                "play_count": vc,
                "like_count": r.get("like_count"),
                "comment_count": r.get("comment_count"),
                "follower_count": followers,
                # главный признак виралки: просмотров больше, чем подписчиков
                "views_over_followers": (vc > followers) if (followers and vc) else None,
                "views_per_follower": round(vc / followers, 2) if (followers and vc) else None,
                "caption": (r.get("caption_text") or (r.get("caption") or {}).get("text") or "")[:300],
                "video_url": v,
                "thumb_url": thumb,
            }
            reel_info.append(ri)
            log.append(f"    {code}: views={ri['play_count']} likes={ri['like_count']} "
                       f"comm={ri['comment_count']} v/f={ri['views_per_follower']} dur={ri['duration']}")

        print("\n".join(log), flush=True)
        return {"username": username, "user_id": uid, "follower_count": followers,
                "median_views": median_views, "fresh_count": len(fresh),
                # Поле читается сводкой прогона: аккаунт с неполным охватом это не
                # «мало роликов», а «прочитано не всё». Ключ аддитивный, старые
                # читатели его игнорируют.
                "coverage": status, "reels": reel_info}
    except Exception as e:
        log.append(f"  EXC {type(e).__name__}: {e}")
        print("\n".join(log), flush=True)
        return {"username": username, "error": f"exc:{e}", "reels": []}


def _atomic_write_json(path: Path, obj) -> None:
    """Запись через temp + os.replace — триггер/score.py не поймают частичный файл."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _scrape(usernames: list[str]) -> dict[str, dict]:
    """Параллельный проход по списку аккаунтов. Возвращает {username: result}."""
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=SCRAPE_WORKERS) as ex:
        futures = {ex.submit(process_account, u): u for u in usernames}
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                results[u] = fut.result()
            except Exception as e:
                results[u] = {"username": u, "error": f"future:{e}", "reels": []}
    return results


# Пауза перед добором упавших — дать транзиентным 429/5xx/таймаутам остыть.
RETRY_COOLDOWN_SEC = 20


def main() -> int:
    print(f"workers={SCRAPE_WORKERS} accounts={len(WATCHLIST)} fallback={FALLBACK_HOURS}ч")
    results = _scrape(WATCHLIST)

    # Авто-добор: упавшие аккаунты (no_uid / clips_fetch_failed / exc / future)
    # проходим ещё ОДИН раз доп-проходом ДО score.py — транзиентный сбой
    # (rate-limit, 5xx, таймаут, flaky resolve) не должен молча терять виральные
    # ролики аккаунта. Добор только по упавшим (обычно горстка) → дёшево по HikerAPI.
    # no_uid (private/renamed) обычно не лечится, но стоит копейки и иногда оживает.
    # no_media НЕ ретраим: 404 NotFound окончательный, повтор лишь жжёт платный вызов.
    first_failed = [u for u in WATCHLIST
                    if results.get(u, {}).get("error")
                    and results.get(u, {}).get("error") != "no_media"]
    recovered: list[str] = []
    if first_failed:
        print(f"\n=== RETRY === {len(first_failed)} упавших, доп-проход через "
              f"{RETRY_COOLDOWN_SEC}с: {', '.join(first_failed)}")
        time.sleep(RETRY_COOLDOWN_SEC)
        retry_results = _scrape(first_failed)
        for u in first_failed:
            r = retry_results.get(u)
            if not r:
                continue
            if not r.get("error"):
                results[u] = r          # ожил → берём свежий успех
                recovered.append(u)
            else:
                results[u] = r          # всё ещё упал → держим свежий статус/ошибку
        if recovered:
            print(f"RETRY recovered ({len(recovered)}): {', '.join(recovered)}")

    # Детерминированный порядок выдачи — по порядку watchlist, не по гонке потоков.
    summary = [results[u] for u in WATCHLIST if u in results]

    _atomic_write_json(OUT_DIR / "_top3_per_account.json", summary)
    ok = sum(1 for s in summary if not s.get("error"))
    failed = [s["username"] for s in summary if s.get("error")]

    # Артефакт покрытия для утренней сводки (send_morning_digest.py): сколько
    # аккаунтов прогнали, кто упал (после ретрая), кого добрали. Atomic — дайджест
    # не поймает частичный файл.
    coverage = {
        "ts": int(time.time()),
        "total": len(summary),
        "ok": ok,
        "failed": [{"username": s["username"], "error": s.get("error")}
                   for s in summary if s.get("error")],
        "recovered_on_retry": recovered,
    }
    _atomic_write_json(OUT_DIR / "_coverage.json", coverage)

    print(f"\n=== SAVED === {OUT_DIR / '_top3_per_account.json'}  (ok={ok}/{len(summary)})")
    if recovered:
        print(f"recovered on retry ({len(recovered)}): {', '.join(recovered)}")
    if failed:
        print(f"FAILED accounts ({len(failed)}): {', '.join(failed)}")
    # Полный провал (0 ok) = API down / битый ключ → нечем кормить downstream.
    # daily_morning_auto.sh ABORT'нет на ненулевом коде. Частичный успех → 0
    # (downstream работает на собранном, лучше неполный пакет, чем сорванный).
    if ok == 0 and summary:
        print("ABORT signal: zero accounts scraped successfully")
        return 1
    return 0


def selftest() -> int:
    """Контрольный набор на признак покрытия окна. Сеть не трогает.

    Прогон: python3 pull_reels.py --selftest
    """
    cut = 1756500000
    cases = [
        ("древние сверху плюс свежие: окно НЕ закрыто",
         [{"media": {"taken_at": cut - 9000000}}, {"media": {"taken_at": cut + 500}}], False),
        ("страница целиком за окном: закрыто",
         [{"media": {"taken_at": cut - 100}}, {"media": {"taken_at": cut - 900}}], True),
        ("пустая страница окно не закрывает", [], False),
        ("даты строкой из API",
         [{"media": {"taken_at": str(cut - 100)}}], True),
        ("дат нет вовсе", [{"media": {"pk": "1"}}], False),
        ("плоский элемент без ключа media", [{"taken_at": cut + 10}], False),
    ]
    bad = 0
    for name, items, want in cases:
        got = page_covers_window(items, cut)
        ok = got == want
        bad += not ok
        print(f"  [{'ok' if ok else 'ПРОВАЛ'}] {name}" + ("" if ok else f" — ждали {want}, got {got}"))
    print(f"selftest: случаев {len(cases)}, провалов {bad}")
    return 10 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(main())
