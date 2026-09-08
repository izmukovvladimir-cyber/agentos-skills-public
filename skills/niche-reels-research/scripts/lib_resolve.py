#!/usr/bin/env python3
"""lib_resolve.py — устойчивый резолв username->uid для niche-reels.

Проблема (06.07 выпал @donor_seven, топ-поставщик каруселей → 7 вместо 10):
HikerAPI /v1/user/by/username периодически отдаёт 404 UserNotFound —
замаскированный IG rate-limit для ОТДЕЛЬНОГО живого аккаунта. donor_seven
резолвился 10 дней из 12, donor_eight 8 из 28 — резолв flaky, аккаунт выпадает.

Фикс: персистентный кэш uid (uid у аккаунта неизменен) — cache/uid_cache.json.
  1. live /v1/user/by/username → success → кэшируем {uid, followers, verified, ts}.
  2. провал резолва → есть verified-кэш? берём его uid (клипы тянем по uid),
     followers освежаем best-effort через /v1/user/by/id, иначе last-known.
     uid из ЖИВОГО резолва уже подтверждён → доверяем даже если by-id throttled.
  3. провал + seed uid из watchlist (поле user_id) → verify by-id: username
     должен совпасть → тогда кэшируем и используем. Сид БЕЗ проверки не берём
     (анти-отравление: чужой аккаунт под тем же ником в пул не попадёт).

Анти-отравление и на ЖИВОМ пути: если live-резолв вернул uid, ОТЛИЧНЫЙ от
verified-кэша, ник сменил владельца (uid неизменен) → НЕ перетираем кэш чужим
аккаунтом, оставляем прежний uid и логируем (решает <agent>).

call() инжектит вызывающий скрипт (свой retry/ключ, тот же для by-id).
Потокобезопасно (Lock); запись сливается с диском (reload-merge) на случай
параллельных процессов. Ключи кэша/сидов нормализованы в lower-case.

Что НЕ лечит: день полного IG-блока аккаунта, когда 404 отдают ВСЕ эндпоинты
(by-username, by-id, clips) — редко, покрытие всё равно логируется в digest.
И аккаунты, не резолвившиеся НИ разу (renamed/приватность) — данные watchlist,
правит <agent>, а не баг резолва.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from pathlib import Path


def _to_int(v):
    """Безопасный парс числа: None/''/мусор -> None; '123'/123/123.0 -> 123."""
    if v is None:
        return None
    try:
        return int(float(v)) if isinstance(v, str) else int(v)
    except (TypeError, ValueError):
        return None


def load_watchlist_seeds(watchlist_file) -> dict:
    """username(lower) -> user_id из watchlist (аккаунты с известным uid)."""
    seeds: dict[str, str] = {}
    try:
        cfg = json.loads(Path(watchlist_file).read_text(encoding="utf-8"))
    except Exception:
        return seeds
    for key in ("anchor_accounts", "expansion_accounts"):
        for a in cfg.get(key, []) or []:
            if isinstance(a, dict) and a.get("username") and a.get("user_id"):
                seeds[str(a["username"]).lower()] = str(a["user_id"])
    return seeds


class Resolver:
    """Резолв username->uid с персистентным кэшем и fallback-цепочкой."""

    def __init__(self, call, cache_path, watchlist_seeds=None):
        self.call = call
        self.cache_path = Path(cache_path)
        self.seeds = {str(k).lower(): str(v) for k, v in (watchlist_seeds or {}).items()}
        self._lock = threading.Lock()
        self._cache = self._load()

    def _load(self) -> dict:
        try:
            d = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                return {}
            # ключи в lower-case (историческая совместимость)
            return {str(k).lower(): v for k, v in d.items() if isinstance(v, dict)}
        except Exception:
            return {}

    def _save_locked(self) -> None:
        """Атомарно записать кэш. reload-merge под МЕЖПРОЦЕССНЫМ flock (pull_reels
        и pull_carousels — отдельные процессы; в проде идут последовательно, но
        flock защищает и от ручного параллельного запуска). Temp — per-PID, чтобы
        писатели не топтали общий tmp. Кэш — runtime-state, <agent>-only."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        lock_path = self.cache_path.with_name(self.cache_path.name + ".lock")
        try:
            with open(lock_path, "w") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)  # снимается при закрытии файла
                # reload-merge под локом: диск мог обновить другой процесс
                disk = {}
                try:
                    raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        disk = {str(k).lower(): v for k, v in raw.items() if isinstance(v, dict)}
                except Exception:
                    disk = {}
                for k, v in disk.items():
                    cur = self._cache.get(k)
                    if cur is None:
                        self._cache[k] = v  # запись другого процесса, которой у нас нет
                    elif (_to_int(v.get("ts")) or 0) > (_to_int(cur.get("ts")) or 0):
                        self._cache[k] = v  # диск новее (наш свежий _put имеет ts=now → выиграет)
                tmp = self.cache_path.with_name(f"{self.cache_path.name}.{os.getpid()}.tmp")
                tmp.write_text(
                    json.dumps(self._cache, ensure_ascii=False, indent=0),
                    encoding="utf-8",
                )
                os.replace(tmp, self.cache_path)
        except Exception:
            pass

    def _put(self, key: str, uid, followers) -> None:
        with self._lock:
            prev = self._cache.get(key, {})
            fol = _to_int(followers)
            if fol is None:
                fol = prev.get("followers")
            self._cache[key] = {
                "uid": str(uid),
                "followers": fol,
                "verified": True,
                "ts": int(time.time()),
            }
            self._save_locked()

    def _by_id(self, uid) -> tuple[str | None, int | None]:
        """(username, followers) через /v1/user/by/id; (None, None) при сбое."""
        data = self.call("/v1/user/by/id", {"id": str(uid)})
        if not isinstance(data, dict) or data.get("_error"):
            return None, None
        un = data.get("username")
        return (un if un else None), _to_int(data.get("follower_count"))

    def resolve(self, username: str, log=None) -> tuple[str | None, int | None]:
        """(uid|None, followers|None). Источник резолва пишет в log (list|None)."""
        key = str(username).lower()
        with self._lock:
            cached = dict(self._cache.get(key, {}))

        # 1. Живой резолв — основной путь.
        data = self.call("/v1/user/by/username", {"username": username})
        pk = None
        if isinstance(data, dict):
            pk = data.get("pk") or data.get("id")
        if pk:
            pk = str(pk)
            fol = _to_int(data.get("follower_count")) if isinstance(data, dict) else None
            # Анти-отравление: если verified-кэш держит ДРУГОЙ uid, ник сменил
            # владельца (uid неизменен) — не перетираем чужим аккаунтом.
            if cached.get("verified") and cached.get("uid") and str(cached["uid"]) != pk:
                if log is not None:
                    log.append(
                        f"  ⚠ ник сменил владельца: live uid={pk} != кэш uid={cached['uid']}; "
                        f"оставляю прежний (проверь watchlist)"
                    )
                old = str(cached["uid"])
                self._put(key, old, cached.get("followers"))
                return old, cached.get("followers")
            self._put(key, pk, fol)
            return pk, fol

        # 2. Verified-кэш (uid из прежнего живого резолва → неизменен, доверяем).
        if cached.get("verified") and cached.get("uid"):
            uid = str(cached["uid"])
            un, fol = self._by_id(uid)
            if un and un.lower() == key:
                self._put(key, uid, fol if fol is not None else cached.get("followers"))
                if log is not None:
                    log.append(f"  resolve через кэш uid={uid} (by-username throttled)")
                return uid, (fol if fol is not None else cached.get("followers"))
            if un is None:
                # by-id тоже throttled — uid неизменен, followers last-known.
                if log is not None:
                    log.append(f"  resolve через кэш uid={uid} (by-id throttled, followers last-known)")
                return uid, cached.get("followers")
            # by-id вернул ДРУГОЙ username на этом uid — не доверяем, идём к seed.

        # 3. Seed из watchlist (user_id) — только после verify by-id.
        seed = self.seeds.get(key)
        if seed:
            un, fol = self._by_id(seed)
            if un and un.lower() == key:
                self._put(key, seed, fol)
                if log is not None:
                    log.append(f"  resolve через seed uid={seed} (verified by-id)")
                return str(seed), fol

        return None, None
