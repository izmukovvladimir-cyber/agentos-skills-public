#!/usr/bin/env python3
"""pull_carousels.py — забор + скоринг свежих каруселей (media_type 8) из watchlist.

Отличия от pull_reels.py:
  - media_type == 8 (carousel/album), не 2 (reels).
  - окно свежести = limits.carousel_lookback_hours (по умолчанию 120ч / 5 дней) —
    карусели стареют медленнее рилсов, владелец разрешил до 5 дней.
  - у альбомов нет play_count → метрика виральности по лайкам:
    viral_ratio = like_count / median(like_count последних ~30 постов автора).

Параллельный проход по аккаунтам (ThreadPoolExecutor, limits.scrape_workers) —
как в pull_reels.py: sequential не масштабировался к 100→200 аккаунтам.
Скоринг и SEEN-GATE выполняются ПОСЛЕ сбора (в главном потоке) — порядок и
дедуп детерминированы.

Вход:  config/watchlist.json (anchor + expansion)
Выход: /tmp/expand_pool/reels/_carousels_scored.json — все свежие карусели, скор↓ возраст↑
       /tmp/expand_pool/reels/_carousels_top.json     — top-N для визуального фильтра
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median as _median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_seen
import lib_paths
import lib_resolve

KEY = os.environ["HIKER_API_KEY"]
BASE = "https://api.instagrapi.com"
# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy paths.
OUT_DIR = lib_paths.pool_dir()
OUT_DIR.mkdir(exist_ok=True, parents=True)

SKILL_DIR = lib_paths.SKILL_DIR
WATCHLIST_FILE = lib_paths.config_file()
SCORED_FILE = OUT_DIR / "_carousels_scored.json"
TOP_FILE = OUT_DIR / "_carousels_top.json"

MEDIAN_SAMPLE_SIZE = 30
DEFAULT_CAROUSEL_HOURS = 120  # 5 дней

RETRY_HTTP = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


def load_cfg() -> dict[str, Any]:
    return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))


def watchlist_usernames(cfg: dict[str, Any]) -> list[str]:
    """Аккаунты для забора каруселей.

    carousel_accounts — ОТДЕЛЬНАЯ секция доноров, которые живут каруселями
    (владелец  «почему их мало и почему они такие слабые»).
    Замер того утра: общий список из 57 рилсовых аккаунтов дал за 72 часа
    64 карусели, порог в 100 лайков прошла ОДНА — карусели черпались из тех,
    кто каруселями не живёт. Секция читается ТОЛЬКО здесь, поэтому рилсовый
    пул (pull_reels.py) от неё не меняется. Ключа нет — поведение прежнее.
    """
    out: list[str] = []
    seen: set[str] = set()
    # Отклонённые владельцем не берём ни из одной секции. Без этого фильтра его
    # решение держалось только на том, что я не забыла вычистить донора руками
    # (: «бизнес пипл убери вообще из вач листа»).
    banned = {
        str(a.get("username") if isinstance(a, dict) else a).lower()
        for a in cfg.get("rejected", []) or []
        if (a.get("username") if isinstance(a, dict) else a)
    }
    for key in ("carousel_accounts", "anchor_accounts", "expansion_accounts"):
        for a in cfg.get(key, []) or []:
            u = a.get("username") if isinstance(a, dict) else a
            if not u:
                continue
            k = u.lower()
            if k in seen or k in banned:
                continue
            seen.add(k)
            out.append(u)
    return out


def call(path: str, params: dict[str, Any]) -> dict[str, Any]:
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


def get_user_id(username: str, log: list | None = None) -> str | None:
    """Устойчивый резолв username->uid (lib_resolve): кэш uid вытягивает аккаунт
    в throttle-день HikerAPI (by-username 404 UserNotFound). Общий кэш с
    pull_reels — cache/uid_cache.json."""
    uid, _followers = _RESOLVER.resolve(username, log)
    return uid


def get_user_medias(uid: str, username: str, log: list[str]) -> tuple[list[dict[str, Any]], bool]:
    """/v2/user/medias — все типы медиа (нужно для альбомов type 8).

    Возвращает (medias, first_page_failed). first_page_failed=True когда первая
    страница упала (ничего не собрано) — реальный сбой эндпоинта, не «нет медиа».
    """
    out: list[dict[str, Any]] = []
    page_id: str | None = None
    first_failed = False
    for _ in range(1, 5):
        params: dict[str, Any] = {"user_id": uid}
        if page_id:
            params["page_id"] = page_id
        data = call("/v2/user/medias", params)
        if "_error" in data:
            log.append(f"  [{username}] medias error: {data.get('_error')} {data.get('_body','')[:80]}")
            if not out:
                first_failed = True
            break
        items = data.get("response", {}).get("items") or data.get("items") or []
        for it in items:
            out.append(it.get("media") if "media" in it else it)
        page_id = data.get("next_page_id") or data.get("response", {}).get("next_page_id")
        if not page_id:
            break
        time.sleep(0.4)
    return out, first_failed


def likes(m: dict[str, Any]) -> int:
    return int(m.get("like_count") or 0)


def thumb_of(m: dict[str, Any]) -> str | None:
    # для альбома берём превью первого слайда
    carousel = m.get("carousel_media") or m.get("resources")
    target = carousel[0] if isinstance(carousel, list) and carousel else m
    cands = (target.get("image_versions2", {}) or {}).get("candidates", [])
    if cands:
        return cands[0].get("url")
    return target.get("thumbnail_url") or m.get("thumbnail_url")


# PROTECTED TOP-N для каруселей  — тот же принцип, что у
# рилсов (:<agent>::4a27cc8e): сильнейшая карусель дня входит в пак ВСЕГДА,
# иммунна к дедупу Блока А. Оси карусельные: комменты / лайки / скорость eng-час /
# ratio к медиане. Резерв лидера каждой оси первым, добор по (число осей, score), кап.
CAROUSEL_AXES = [
    ("comments", "комменты"),
    ("eng_per_hour", "скорость"),
    ("likes", "лайки"),
    ("viral_ratio", "ratio к медиане"),
]


def _c_lim_int(limits: dict[str, Any], key: str, default: int) -> int:
    try:
        v = int(limits.get(key, default))
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


def _c_axis_val(s: dict[str, Any], key: str) -> float:
    extras = s.get("extras")
    v = extras.get(key) if isinstance(extras, dict) else None
    return float(v) if isinstance(v, (int, float)) and v > 0 else 0.0


def _c_score_total(s: dict[str, Any]) -> float:
    try:
        return float(s.get("score_total") or 0)
    except (TypeError, ValueError):
        return 0.0


def mark_protected_carousels(pool: list[dict[str, Any]], limits: dict[str, Any]) -> list[dict[str, Any]]:
    """Помечает топ-N каруселей protected мульти-осево (резерв лидера оси первым)."""
    for s in pool:
        s["protected"] = False
        s["protected_reasons"] = []
    if not pool:
        return []
    top_n = _c_lim_int(limits, "protected_top_n", 6)
    per_axis = max(1, _c_lim_int(limits, "protected_per_axis", 3))
    if top_n == 0:
        return []
    reasons: dict[int, list[str]] = {}
    axis_leaders: list[dict[str, Any]] = []
    for key, label in CAROUSEL_AXES:
        ranked = sorted(
            (s for s in pool if _c_axis_val(s, key) > 0),
            key=lambda x: _c_axis_val(x, key), reverse=True,
        )
        for i, s in enumerate(ranked[:per_axis]):
            reasons.setdefault(id(s), []).append(label)
            if i == 0:
                axis_leaders.append(s)
    selected: list[dict[str, Any]] = []
    chosen: set[int] = set()
    for s in axis_leaders:
        if len(selected) >= top_n:
            break
        if id(s) not in chosen:
            selected.append(s)
            chosen.add(id(s))
    rest = [s for s in pool if id(s) in reasons and id(s) not in chosen]
    rest.sort(key=lambda x: (len(reasons[id(x)]), _c_score_total(x)), reverse=True)
    for s in rest:
        if len(selected) >= top_n:
            break
        selected.append(s)
        chosen.add(id(s))
    for s in selected:
        s["protected"] = True
        s["protected_reasons"] = reasons[id(s)]
    return selected


def score_account(acc_idx: int, username: str, window_h: int, since_ts: int,
                  now_ts: int, rules: dict[str, int], limits: dict[str, Any]) -> dict[str, Any]:
    """Per-account сбор + КОМПОЗИТНЫЙ скоринг каруселей. Выполняется в пуле потоков.

    Композит как у рилсов: главный вес — ОБЪЁМ КОММЕНТОВ
    (comment_volume_gt100/gt300), плюс СКОРОСТЬ набора (engagement/час, т.к. у
    альбомов нет views → метрика like+comment) и кратность к медиане автора по
    лайкам. Веса — те же scoring{} из watchlist.json, что у рилсов. БЕЗ лимита на
    автора («нужны вирусные, хоть 5 от одного»).

    Возвращает {"username", "records": [...], "error": None|str}. Пустой records
    с error=None = «у аккаунта нет свежих каруселей»; error!=None = сбой (API/
    исключение) — main() считает это failed-аккаунтом, не молчаливым нулём.
    acc_idx (позиция в watchlist) и m_idx (позиция медиа) кладутся в каждую
    запись для ДЕТЕРМИНИРОВАННОГО tie-break (порядок потоков на сорт не влияет).
    """
    log: list[str] = [f"\n=== {username} ==="]
    res: list[dict[str, Any]] = []
    err: str | None = None
    try:
        uid = get_user_id(username, log)
        if not uid:
            log.append("  no user_id")
            print("\n".join(log), flush=True)
            return {"username": username, "records": res, "error": "no_uid"}
        medias, fetch_failed = get_user_medias(uid, username, log)
        if fetch_failed:
            log.append("  medias первая страница упала → аккаунт помечен ошибкой")
            print("\n".join(log), flush=True)
            return {"username": username, "records": [], "error": "medias_fetch_failed"}
        log.append(f"  {len(medias)} medias fetched")

        # baseline: медиана лайков по последним ~30 альбомам автора
        album_likes = [likes(m) for m in medias if m.get("media_type") in (8, "8") and likes(m) > 0]
        median_likes = int(_median(album_likes[:MEDIAN_SAMPLE_SIZE])) if album_likes else None

        m_idx = -1
        for m in medias:
            if m.get("media_type") not in (8, "8"):
                continue
            m_idx += 1
            taken_at = m.get("taken_at") or 0
            if isinstance(taken_at, str):
                try:
                    taken_at = int(taken_at)
                except ValueError:
                    taken_at = 0
            if not taken_at or taken_at < since_ts:
                continue
            age_h = round((now_ts - taken_at) / 3600.0, 1)
            lk = likes(m)
            cm = int(m.get("comment_count") or 0)
            vr = round(lk / median_likes, 2) if median_likes and lk else None
            n_slides = len(m.get("carousel_media") or m.get("resources") or []) or None
            code = m.get("code") or m.get("shortcode")
            # СКОРОСТЬ: у альбомов нет views → темп набора = (лайки+комменты)/час
            eng_per_hour = int((lk + cm) / age_h) if age_h > 0 else 0

            # КОМПОЗИТНЫЙ скоринг (как рилсы): комменты (главный) + скорость + кратность
            # к медиане + свежесть + вовлечённость. Веса из watchlist.json scoring{}.
            sb = {"viral_likes_x3": 0, "comment_volume": 0, "speed": 0, "fresh": 0, "engagement": 0}
            # (1) кратность к СВОЕЙ норме по лайкам (как median_x3 у рилсов)
            if median_likes and lk > 3 * median_likes:
                sb["viral_likes_x3"] = rules.get("viewable_above_3x_median", 30)
            # (2) ГЛАВНЫЙ — сырой ОБЪЁМ комментов (вирус + воронка кодворда), не кумулятивно
            if cm > 300:
                sb["comment_volume"] = rules.get("comment_volume_gt300", 25)
            elif cm > 100:
                sb["comment_volume"] = rules.get("comment_volume_gt100", 15)
            # (3) СКОРОСТЬ набора engagement/час (карусельные пороги, не views/ч рилсов)
            eph_strong = float(limits.get("carousel_speed_strong_eph", 150))
            eph_moderate = float(limits.get("carousel_speed_moderate_eph", 50))
            if eng_per_hour >= eph_strong:
                sb["speed"] = rules.get("speed_strong", 20)
            elif eng_per_hour >= eph_moderate:
                sb["speed"] = rules.get("speed_moderate", 10)
            # (4) свежесть — новее 48ч приоритет (окно теперь 72ч)
            if 0 < age_h <= 48:
                sb["fresh"] = rules.get("fresh_under_48h", 20)
            # (5) вовлечённость cm/lk — вторичный бонус
            if lk > 0 and cm / lk > 0.02:
                sb["engagement"] = 15
            score = sum(sb.values())

            res.append({
                "username": username,
                "code": code,
                "url": f"https://www.instagram.com/p/{code}/" if code else None,
                "_sort": [acc_idx, m_idx],  # детерминированный tie-break, снимается перед записью
                "score_total": score,
                "score_breakdown": sb,
                "extras": {
                    "likes": lk, "comments": cm, "age_h": age_h, "eng_per_hour": eng_per_hour,
                    "median_likes": median_likes, "viral_ratio": vr, "slides": n_slides,
                },
                "raw": {
                    "code": code, "taken_at": taken_at, "like_count": lk, "comment_count": cm,
                    "caption": (m.get("caption_text") or (m.get("caption") or {}).get("text") or "")[:300],
                    "thumb_url": thumb_of(m),
                },
            })
        log.append(f"  {len(res)} свежих каруселей (<= {window_h}ч)")
        print("\n".join(log), flush=True)
    except Exception as e:
        err = f"exc:{type(e).__name__}:{e}"
        log.append(f"  EXC {type(e).__name__}: {e}")
        print("\n".join(log), flush=True)
    return {"username": username, "records": res, "error": err}


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Запись через temp + os.replace — потребители не поймают частичный файл."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    cfg = load_cfg()
    limits = cfg.get("limits", {})
    rules: dict[str, int] = cfg.get("scoring", {})  # те же веса, что у рилсов
    window_h = int(limits.get("carousel_lookback_hours", DEFAULT_CAROUSEL_HOURS))
    top_n = int(limits.get("thumbs_review_n", 15))
    workers = max(1, min(int(limits.get("scrape_workers", 8)), 24))
    since_ts = int(time.time()) - window_h * 3600
    now_ts = int(time.time())

    usernames = watchlist_usernames(cfg)
    print(f"workers={workers} accounts={len(usernames)} window={window_h}ч")

    scored: list[dict[str, Any]] = []
    failed: list[str] = []
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(score_account, i, u, window_h, since_ts, now_ts, rules, limits): u
                   for i, u in enumerate(usernames)}
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                r = fut.result()
            except Exception as e:
                failed.append(u)
                print(f"  [{u}] future error: {e}", flush=True)
                continue
            if r.get("error"):
                failed.append(u)
            else:
                ok += 1
            scored.extend(r.get("records", []))

    # SEEN-GATE (hard): уже показанные/взятые карусели не повторяем — общая
    # история reels_seen.json (пишет mark_shown.py). Окно свежести 5 дней →
    # показанная вчера карусель ещё «свежая» и всплыла бы снова без этого фильтра.
    seen_codes = lib_seen.load_seen_codes()
    before_seen = len(scored)
    scored = [s for s in scored if s.get("code") not in seen_codes]
    print(f"seen-gate: {len(seen_codes)} seen codes, "
          f"{before_seen - len(scored)} carousels dropped (already shown)")

    # сортировка: скор↓, возраст↑, затем ДЕТЕРМИНИРОВАННЫЙ tie-break по
    # (acc_idx, m_idx) — стабильно на границе top_n независимо от гонки потоков.
    scored.sort(key=lambda x: (-x["score_total"], x["extras"]["age_h"], x.get("_sort", [10**9, 0])))
    # _sort — внутреннее поле, не сериализуем
    for s in scored:
        s.pop("_sort", None)

    # АБСОЛЮТНЫЙ ПОЛ ПО ОТКЛИКУ (владелец  «очень слабая подборка»).
    # Скоринг выше весь относительный: свежесть плюс вовлечённость дают 35 баллов карусели
    # с двадцатью лайками, а «в три раза выше своей медианы» у аккаунта с медианой 19 лайков
    # срабатывает каждый день. Замер того утра: в пуле 55 каруселей, отклик от 100 лайков
    # набрали 4, остальные 11 мест пака занял один автор. Поэтому ниже пола карусель в обзор
    # не идёт вовсе, даже с высоким баллом.
    floor = _c_lim_int(limits, "carousel_min_likes", 100)
    below = [s for s in scored if int(s["extras"].get("likes") or 0) < floor]
    if below:
        print(f"floor-gate: {len(below)} каруселей отсеяно по порогу {floor} лайков "
              f"(осталось {len(scored) - len(below)})")
    scored = [s for s in scored if int(s["extras"].get("likes") or 0) >= floor]

    # КВОТУ НА АВТОРА НЕ СТАВЛЮ.  я её написала и тут же нашла прямое указание
    # владельца от , зашитое в daria-morning-trigger.sh строкой 214: «НЕ ограничивай
    # по автору, бери чисто по вирусности, хоть 5 каруселей от одного автора». Замер того же
    # утра показал, что квота и не нужна: пол по отклику убирает 42 карусели одного автора
    # сам, потому что у них 6-75 лайков, и после пола квота не отсекла НИ ОДНОЙ.

    # PROTECTED TOP-N: сильнейшие карусели дня иммунны к дедупу Блока А (мульти-осево).
    protected = mark_protected_carousels(scored, limits)
    print(f"protected: {len(protected)} каруселей (иммунны к дедупу): "
          + (", ".join(f"@{p['username']}/{p['code']}({'+'.join(p['protected_reasons'])})"
                       for p in protected) or "—"))

    _atomic_write_json(SCORED_FILE, scored)
    top = scored[:top_n]
    # protected обязаны попасть в обзор <agent>, даже если по score_total ниже top_n
    in_top = {id(s) for s in top}
    for s in scored:
        if s.get("protected") and id(s) not in in_top:
            top.append(s)
            in_top.add(id(s))
    _atomic_write_json(TOP_FILE, top)
    if len(top) < top_n:
        print(f"ПАК КОРОЧЕ ОБЫЧНОГО: порог прошли {len(top)} каруселей из {before_seen} "
              f"в пуле. Добивать слабыми не будем, длина пака переменная.")
    print(f"\n=== {len(scored)} свежих каруселей (<= {window_h}ч), top{len(top)} "
          f"(+{sum(1 for s in top[top_n:])} protected вне обзора) → {TOP_FILE} ===")
    print(f"accounts: ok={ok}/{len(usernames)} failed={len(failed)}"
          + (f" ({', '.join(failed)})" if failed else ""))
    for i, s in enumerate(top, 1):
        ex = s["extras"]
        prot = "🛡" if s.get("protected") else " "
        print(f"{prot}{i:2d}. @{s['username']:22} {s['code']}  score={s['score_total']:>3}  "
              f"cm={ex['comments']:>5}  likes={ex['likes']:>7}  eph={ex.get('eng_per_hour',0):>4}  "
              f"ratio={ex['viral_ratio']}  age={ex['age_h']}ч")
    # Полный провал (0 ok при непустом watchlist) = API/ключ битый → ненулевой код.
    # daily_morning_auto.sh трактует pull_carousels как WARN (не ABORT), но код
    # всё равно сигналит downstream'у/логу о тотальном сбое. Частичный → 0.
    if ok == 0 and usernames:
        print("FAIL signal: zero accounts scored successfully")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
