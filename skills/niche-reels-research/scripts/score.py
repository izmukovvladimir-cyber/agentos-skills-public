#!/usr/bin/env python3
"""score.py — композитный скоринг рилсов.

Вход:  /tmp/expand_pool/reels/_top3_per_account.json (от pull_reels.py)
       config/watchlist.json (формула скоринга + триггер-слова)
Выход: /tmp/expand_pool/reels/_scored.json — все рилсы отсортированы по композитному скору
       /tmp/expand_pool/reels/_top10.json   — top-10 для визуального фильтра

Формула (из watchlist.json.scoring + criteria.md):
  +30 viewable_above_3x_median  — просмотры > 3× медианы автора (последние 30 клипов)
  +25 comment_with_trigger_word_gt10 — >10 комментариев с триггер-словом
  +20 views_gt_1M
  +20 fresh_under_48h
  +15 er_gt_5pct (likes/views)
  +10 duration_24_60s
  -25 dead_cta — призыв в капшене есть, а откликаться на него не идут (порог от медианы пула)

Опт: comments-fetch (дорогой) делаем ТОЛЬКО для рилсов с базовым скором >=30.

Зависимости: HikerAPI Lite (для median + comments).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_seen
import lib_paths

log = logging.getLogger("score")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

SKILL_DIR = lib_paths.SKILL_DIR
WATCHLIST_FILE = lib_paths.config_file()
HIKER_KEY = os.environ["HIKER_API_KEY"]
HIKER_BASE = "https://api.instagrapi.com"

# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy paths.
POOL_DIR = lib_paths.pool_dir()
INPUT_FILE = POOL_DIR / "_top3_per_account.json"
SCORED_FILE = POOL_DIR / "_scored.json"
TOP10_FILE = POOL_DIR / "_top10.json"

MEDIAN_SAMPLE_SIZE = 30  # клипов автора для медианы
COMMENT_FETCH_LIMIT = 50  # комментов на один рилс

# Бюджет времени на ВЕСЬ шаг комментов, секунды. Повод: , заявка
# <agent>. HikerAPI отвечал по 30 с и отдавал HTTP 500, кандидатов 76,
# цикл последовательный и без общего дедлайна — оба прогона (600 с и 1500 с) были
# убиты ВНЕШНИМ таймаутом ДО записи _top10.json. Снаружи это выглядит успешным
# прогоном, а файлы при этом вчерашние. Файл общий для всех клиентских отделов,
# поэтому в медленный день без бюджета это ловит каждого.
COMMENTS_BUDGET_DEFAULT_S = 300.0
COMMENTS_BUDGET_MAX_S = 3600.0
COMMENTS_BUDGET_ENV = "NRR_COMMENTS_BUDGET_S"


def comments_budget_s(env: dict[str, str] | None = None) -> float:
    """Бюджет шага комментов. Отключения нет НАМЕРЕННО: неограниченный шаг — ровно
    тот дефект, который здесь чинится, поэтому опечатка в env не должна его вернуть.
    Любое непонятое значение даёт дефолт и говорит об этом вслух."""
    src = os.environ if env is None else env
    raw = src.get(COMMENTS_BUDGET_ENV)
    if raw is None or str(raw).strip() == "":
        return COMMENTS_BUDGET_DEFAULT_S
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        log.warning("%s=%r не число, беру дефолт %.0f с",
                    COMMENTS_BUDGET_ENV, raw, COMMENTS_BUDGET_DEFAULT_S)
        return COMMENTS_BUDGET_DEFAULT_S
    if not math.isfinite(val) or val <= 0:
        log.warning("%s=%r вне разумного (нужно положительное число), беру дефолт %.0f с",
                    COMMENTS_BUDGET_ENV, raw, COMMENTS_BUDGET_DEFAULT_S)
        return COMMENTS_BUDGET_DEFAULT_S
    if val > COMMENTS_BUDGET_MAX_S:
        log.warning("%s=%r выше потолка, срезаю до %.0f с",
                    COMMENTS_BUDGET_ENV, raw, COMMENTS_BUDGET_MAX_S)
        return COMMENTS_BUDGET_MAX_S
    return val


# КОМПОЗИТНАЯ ФОРМУЛА (владелец/<agent> , уточнение): ни один сигнал не
# «ворота» — всё складывается, окно 24ч в приоритете (freshness-gate ниже). Пять
# сигналов: (1) median_x3 — ГЛАВНЫЙ, выше СВОЕЙ нормы (работает и на крупных, где
# абсолют < подписчиков); (2) speed — views/час с момента выхода (крупный за сутки
# не наберёт 100к, но темп виден); (3) воронка — trigger-слово в комментах + объём
# комментов; (4) views_over_followers — ТОЛЬКО бонус (ломается на крупных аккаунтах);
# (5) порог снизу по просмотрам (мягкий, в extras). Плюс прежние вторичные бонусы
# (views_1m, fresh_48h, er_5pct, duration_24_60s) — тоже аддитивны. Веса — watchlist.json scoring{}.
@dataclass
class ScoreBreakdown:
    median_x3: int = 0              # (1) ГЛАВНЫЙ: просмотры > 3× своей медианы
    speed: int = 0                  # (2) views/час — темп набора (чинит «крупный за сутки»)
    trigger_comments_gt10: int = 0  # (3a) воронка: кодовое слово в комментах
    comment_volume: int = 0         # (3b) абсолютный объём комментов (>100 / >300)
    views_over_followers: int = 0   # (4) бонус, НЕ доминанта (ломается на крупных)
    views_1m: int = 0
    fresh_48h: int = 0
    er_5pct: int = 0
    duration_24_60s: int = 0
    dead_cta: int = 0                # (6) ШТРАФ: призыв в капшене есть, а откликаться на него не идут
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.median_x3
            + self.speed
            + self.trigger_comments_gt10
            + self.comment_volume
            + self.views_over_followers
            + self.views_1m
            + self.fresh_48h
            + self.er_5pct
            + self.duration_24_60s
            + self.dead_cta
        )


# PROTECTED TOP-N (владелец/<agent> , косяк 27.06: бэнгер дня mavgpt
# DaDfKmuqRyW 114к показов / 5013 комментов срезан author/theme-дедупом Блока А).
# Самый сильный ролик дня ОБЯЗАН войти в пак — soft-фильтры не имеют права ронять
# выстрел. Помечаем protected МУЛЬТИ-ОСЕВО (топ по комментам / показам / скорости /
# ratio к медиане — union по осям), НЕПРЕРЫВНО, без порогов: пороговый comment_volume
# уравнивает 350 и 5013 комментов, поэтому бэнгер ранжируем по сырым осям, не по cap'у.
# В Блоке А author-dedup/theme-dedup применяются ТОЛЬКО к protected:false.
PROTECT_AXES = [
    ("comments", "комменты"),
    ("views", "показы"),
    ("views_per_hour", "скорость"),
    ("viral_ratio", "ratio к медиане"),
]


# КОНВЕРТНОСТЬ ДОНОРА (<agent> , поручение владельца от 22.08,
# карточка #797). Повод: у одной из клиенток отбор доноров переведён с просмотров на
# конвертность (комментарии на 1000 просмотров). Замер на нашем пуле 26.08 (74 рилса,
# 53 аккаунта) показал, что ГЛАВНЫМ ключом её признак нам не годится: в нашей нише он
# меряет не силу формата, а наличие кодворда в капшене (медиана 17.33 против 0.64 без
# призыва, в топ-10 по конвертности 10 роликов из 10 с призывом). Жёсткий отбор по нему
# вырезал бы русский виральный сегмент целиком, включая ролики на 385к, 272к и 229к
# просмотров, то есть ровно тот холодный охват, ради которого фронт-энд и существует.
#
# Поэтому конвертность работает УЗКО и только там, где она честная: если автор ЗОВЁТ в
# комментарии, а идти на призыв не идут, копировать у него нечего. Формат с мёртвым
# призывом получает штраф и уходит вниз, а не выбрасывается: виралка с испорченным
# капшеном всё равно пройдёт по охвату. Ролики БЕЗ призыва правило не трогает вовсе.
# Замер порога: cr<5 помечает 5 роликов из 34 с призывом и НИ ОДНОГО из 10 взятых в пак
# 26.08; cr<8 убил бы главную виралку дня (1.3 млн показов, 7x медианы автора).
# Признак призыва снят УЗКО и в два условия сразу, потому что широкий шаблон ловит
# обычную речь: проверка 26.08 по семи клиентским пулам поймала «Запишите ребенка на
# курс» (подстрока «пишите ребенка») и «пишите помощнице» из вакансии Бони на 1.6 млн
# показов. Оба получили бы штраф ни за что. Поэтому нужен глагол письма НА ГРАНИЦЕ
# слова И рядом либо сам кодворд (капсом или в кавычках), либо прямое указание места
# (комментарии, директ, личные).
_CTA_VERB = r'(?i:(?<![а-яёa-z])(?:напиш\w*|пиши\w*|оставь\w*|скинь\w*|comment|DM\s+me|drop))'
# Кодворд узнаётся ЗАГЛАВНЫМИ или кавычками, поэтому регистр здесь значим и общий флаг
# IGNORECASE тут стоять НЕ может: с ним класс [A-ZА-ЯЁ] ловит любые буквы, и «Пишите
# ваше мнение» становится призывом. Проверено на себе 26.08, три ложных из четырнадцати.
_CTA_WORD = r'(?:[«"\u201c\u2018\'][^»"\u201d\u2019\'\n]{2,24}[»"\u201d\u2019\']|\b[A-ZА-ЯЁ]{3,}\b)'
_CTA_PLACE = r'(?i:ком:?мент\w*|директ\w*|в\s+личн\w*|в\s+л\.?с\.?|below|comments?)'
CTA_RE = re.compile(
    _CTA_VERB + r'[^.!?\n]{0,40}?(?:' + _CTA_WORD + r'|' + _CTA_PLACE + r')'
)


def comment_rate_per_1k(comments: int, views: int) -> float:
    """Конвертность: комментариев на 1000 просмотров. 0 просмотров -> 0.0."""
    if views <= 0:
        return 0.0
    return round(comments * 1000.0 / views, 2)


def has_cta(caption: str | None) -> bool:
    """Есть ли в капшене прямой призыв писать слово. Призыв со СЛАЙДА сюда не попадает
    по построению, поэтому отсутствие призыва в капшене доказывает только капшен."""
    return bool(CTA_RE.search(caption or ""))


def _lim_int(limits: dict[str, Any], key: str, default: int) -> int:
    try:
        v = int(limits.get(key, default))
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


def _axis_val(s: dict[str, Any], key: str) -> float:
    # fail-open на битой вложенности: score_breakdown/extras может быть None/не-dict.
    bd = s.get("score_breakdown")
    extras = bd.get("extras") if isinstance(bd, dict) else None
    v = extras.get(key) if isinstance(extras, dict) else None
    return float(v) if isinstance(v, (int, float)) and v > 0 else 0.0


def _score_total(s: dict[str, Any]) -> float:
    try:
        return float(s.get("score_total") or 0)
    except (TypeError, ValueError):
        return 0.0


def mark_protected(pool: list[dict[str, Any]], limits: dict[str, Any]) -> list[dict[str, Any]]:
    """Помечает топ-N виралок дня protected (иммунны к author/theme-дедупу Блока А).

    Мульти-осевой: РЕЗЕРВИРУЕМ лидера (#1) каждой оси (комменты/показы/скорость/ratio)
    первым — лидер любой оси не имеет права выпасть из-за капа top_n; затем добиваем
    остаток слотов по (число осей, score_total). Так бэнгер, ведущий хоть по ОДНОЙ оси,
    всегда внутри. Возвращает список protected (для лога). pool мутируется: s['protected']
    + s['protected_reasons']."""
    for s in pool:
        s["protected"] = False
        s["protected_reasons"] = []
    if not pool:
        return []
    top_n = _lim_int(limits, "protected_top_n", 6)
    per_axis = max(1, _lim_int(limits, "protected_per_axis", 3))
    if top_n == 0:
        return []
    reasons: dict[int, list[str]] = {}
    axis_leaders: list[dict[str, Any]] = []  # #1 каждой оси в порядке PROTECT_AXES
    for key, label in PROTECT_AXES:
        ranked = sorted(
            (s for s in pool if _axis_val(s, key) > 0),
            key=lambda x: _axis_val(x, key), reverse=True,
        )
        for i, s in enumerate(ranked[:per_axis]):
            reasons.setdefault(id(s), []).append(label)
            if i == 0:
                axis_leaders.append(s)
    # 1) резервируем лидеров осей (гарантия: сильнейший по любой оси защищён)
    selected: list[dict[str, Any]] = []
    chosen: set[int] = set()
    for s in axis_leaders:
        if len(selected) >= top_n:
            break
        if id(s) not in chosen:
            selected.append(s)
            chosen.add(id(s))
    # 2) добиваем остаток по (число осей, score_total)
    rest = [s for s in pool if id(s) in reasons and id(s) not in chosen]
    rest.sort(key=lambda x: (len(reasons[id(x)]), _score_total(x)), reverse=True)
    for s in rest:
        if len(selected) >= top_n:
            break
        selected.append(s)
        chosen.add(id(s))
    for s in selected:
        s["protected"] = True
        s["protected_reasons"] = reasons[id(s)]
    return selected


HIKER_TIMEOUT_S = 30


def hiker_call(path: str, params: dict[str, Any],
               timeout: float = HIKER_TIMEOUT_S) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{HIKER_BASE}{path}?{qs}",
        headers={"x-access-key": HIKER_KEY, "accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode()[:200]}
    except Exception as e:
        return {"_error": str(e)}


def fetch_author_median_views(user_id: str, username: str) -> float | None:
    """Median play_count за последние ~30 клипов автора."""
    items: list[dict[str, Any]] = []
    page_id: str | None = None
    for page in range(1, 4):
        params: dict[str, Any] = {"user_id": user_id}
        if page_id:
            params["page_id"] = page_id
        data = hiker_call("/v2/user/clips", params)
        if "_error" in data:
            log.warning("median fetch fail %s: %s", username, data["_error"])
            break
        raw = data.get("response", {}).get("items") or data.get("items") or []
        for it in raw:
            media = it.get("media") if "media" in it else it
            items.append(media)
        page_id = data.get("next_page_id") or data.get("response", {}).get("next_page_id")
        if not page_id or len(items) >= MEDIAN_SAMPLE_SIZE:
            break
        time.sleep(0.4)
    if not items:
        return None
    views_list = [
        (c.get("play_count") or c.get("view_count") or c.get("ig_play_count") or 0)
        for c in items[:MEDIAN_SAMPLE_SIZE]
    ]
    views_list = [v for v in views_list if v > 0]
    if not views_list:
        return None
    return median(views_list)


def _normalize_pk(media_pk: str) -> str:
    """HikerAPI comments требует ЧИСТЫЙ числовой pk; 'pk_userid' → pk.

    Не-числовое значение (shortcode, 'None', пробелы) трактуем как отсутствие pk
    → вызывающий уйдёт в resolve_pk_from_code, а не словит 404 на v2.
    """
    s = str(media_pk or "")
    if "_" in s:
        s = s.split("_", 1)[0]
    s = s.strip()
    return s if s.isdigit() else ""


def resolve_pk_from_code(code: str, timeout: float = HIKER_TIMEOUT_S) -> str:
    """pk по shortcode через /v1/media/by/code (рилсы из pull_reels часто без pk).

    Таймаут параметром (находка Codex, раунд 3): резолв стоит ПЕРЕД циклом страниц, то есть
    вне его проверки дедлайна, и при остатке бюджета в секунду висел свои 30 с сверх.
    """
    if not code:
        return ""
    data = hiker_call("/v1/media/by/code", {"code": code}, timeout=timeout)
    if isinstance(data, dict) and "_error" not in data:
        return str(data.get("pk") or "")
    return ""


def fetch_comments(media_pk: str, code: str,
                   deadline: float | None = None) -> tuple[list[str], bool]:
    """Достаём до COMMENT_FETCH_LIMIT комментов рилса. Возвращаем тексты (lower).

    HikerAPI: рабочий эндпоинт — /v2/media/comments?id=<numeric pk>. Отдаёт
    response.comments (список) + response.comment_count (всего) + next_page_id
    (пагинация через page_id). pk резолвим из code, если в данных только code
    (pull_reels часто без pk). Старый /v1/media/comments/by/code = 404,
    response.items (старый парс) у v2 нет — коменты лежат в response.comments.
    Страницы перекрываются → дедуп по pk комментария.

    Возвращает (тексты, усечено_бюджетом). Второй элемент — находка Codex, раунд 2:
    частичная выборка, отданная как обычный список, делала «бонуса нет» неотличимым от
    «слова в комментах не было». Усечённый рилс обязан помечаться наравне с пропущенным.
    """
    pk = _normalize_pk(media_pk)
    if not pk:
        # Бюджет судится ДО резолва и ограничивает его (находка Codex, раунд 3). Прежде
        # исчерпанный бюджет всё равно оплачивался резолвом, а его неудача возвращала
        # «проверено, комментов нет» — то есть молчаливое занижение ровно там, где мы
        # не проверили ничего.
        left = None if deadline is None else deadline - time.monotonic()
        if left is not None and left <= 0:
            log.debug("comments: бюджет исчерпан до резолва pk для %s", code)
            return [], True
        pk = resolve_pk_from_code(
            code, timeout=HIKER_TIMEOUT_S if left is None else min(HIKER_TIMEOUT_S, left))
        if not pk and left is not None and time.monotonic() >= deadline:
            log.debug("comments: резолв pk для %s не уложился в бюджет", code)
            return [], True
    if not pk:
        log.warning("comments: no pk resolved for %s", code)
        return [], False
    texts: list[str] = []
    seen: set[str] = set()
    page_id: str | None = None
    total: int | None = None
    budget_hit = False
    for _ in range(8):
        # Дедлайн общий на весь шаг: один медленный рилс не имеет права съесть бюджет
        # остальных. Уже собранные страницы отдаём, это честная частичная выборка,
        # но помеченная — иначе она читается как полная проверка.
        left = None if deadline is None else deadline - time.monotonic()
        if left is not None and left <= 0:
            budget_hit = True
            log.debug("comments: бюджет исчерпан на %s, отдаю собранное (%d)", code, len(texts))
            break
        # Сам запрос тоже ограничен остатком бюджета (находка Codex, раунд 2): проверка
        # ТОЛЬКО перед запросом оставляла шагу возможность висеть внутри одного вызова
        # ещё HIKER_TIMEOUT_S секунд сверх бюджета, а при восьми страницах — восьмикратно.
        call_timeout = HIKER_TIMEOUT_S if left is None else min(HIKER_TIMEOUT_S, left)
        params: dict[str, Any] = {"id": pk}
        if page_id:
            params["page_id"] = page_id
        data = hiker_call("/v2/media/comments", params, timeout=call_timeout)
        if isinstance(data, dict) and "_error" in data:
            body = str(data.get("_body") or "")
            # HikerAPI отдаёт 404 "Entries not found"/NotFoundError для рилса БЕЗ комментов
            # (pk уже резолвнулся — пост живой, это не сбой и не rate-limit, просто нет комментов).
            # Benign: бонуса за комменты нет по факту, логируем тихо, а не как "fetch fail".
            empty_comments = (not texts
                              and data["_error"] == "HTTP 404"
                              and ("NotFoundError" in body or "Entries not found" in body))
            if empty_comments:
                log.debug("comments: none for %s (HikerAPI 404 Entries not found)", code)
            elif not texts:
                # первая страница упала на РЕАЛЬНОЙ ошибке (429/5xx/сеть/иной 4xx) — это шум важный
                log.warning("comments fetch fail %s: %s (%s)", code, data["_error"], body[:120])
            else:
                # курсор протух после уже собранных страниц — не шум
                log.debug("comments pagination stop %s: %s", code, data["_error"])
            # Отказ, случившийся на ИСЧЕРПАННОМ бюджете, это и есть усечение бюджетом
            # (находка Codex, раунд 3): таймаут вызова урезан остатком, значит запрос
            # умер от нашего же потолка. Без пометки кандидат уходил как проверенный.
            if deadline is not None and time.monotonic() >= deadline:
                budget_hit = True
            break
        resp = data.get("response", {}) if isinstance(data, dict) else {}
        comments = resp.get("comments") or []
        if total is None:
            total = resp.get("comment_count")
        new = 0
        for c in comments:
            if not isinstance(c, dict):
                continue
            t = c.get("text") or c.get("comment_text") or ""
            cpk = str(c.get("pk") or c.get("id") or "")
            # дедуп по pk; если pk нет — по тексту (страницы v2 перекрываются)
            key = cpk or ("t:" + t)
            if key in seen:
                continue
            seen.add(key)
            new += 1
            if t:
                texts.append(t.lower())
        page_id = data.get("next_page_id") if isinstance(data, dict) else None
        if (not page_id or new == 0 or len(texts) >= COMMENT_FETCH_LIMIT
                or (isinstance(total, int) and len(seen) >= total)):
            break
        if deadline is not None and time.monotonic() >= deadline:
            # Пауза между страницами тоже тратит бюджет: спать после его исчерпания
            # значит гарантированно выйти за заявленный потолок (находка Codex, раунд 2).
            budget_hit = True
            break
        time.sleep(0.3)
    return texts[:COMMENT_FETCH_LIMIT], budget_hit


def count_trigger_comments(texts: list[str], variants: list[str]) -> int:
    vs = [v.lower() for v in variants]
    hit = 0
    for t in texts:
        if any(v in t for v in vs):
            hit += 1
    return hit


def base_score(
    reel: dict[str, Any],
    median_views: float | None,
    now_ts: int,
    rules: dict[str, int],
    limits: dict[str, Any] | None = None,
) -> ScoreBreakdown:
    limits = limits or {}
    sb = ScoreBreakdown()
    views = int(reel.get("play_count") or 0)
    duration = float(reel.get("duration") or 0)
    likes = int(reel.get("like_count") or 0)
    comments = int(reel.get("comment_count") or 0)
    taken_at = int(reel.get("taken_at") or 0)
    age_h = (now_ts - taken_at) / 3600.0 if taken_at else 9999

    # (1) ГЛАВНЫЙ — выше СВОЕЙ нормы. Работает и на крупных аккаунтах, где сильный
    # ролик по абсолюту меньше аудитории, но кратно выше медианы автора.
    if median_views and views and views > 3 * median_views:
        sb.median_x3 = rules.get("viewable_above_3x_median", 30)

    # (2) СКОРОСТЬ — views/час с момента выхода. Чинит «крупный за сутки не набрал
    # 100к»: судим по ТЕМПУ, а не по абсолюту. Тиры (порог в limits, вес в scoring),
    # не кумулятивно. age_h<=0 (нет taken_at / будущее) → темп не считаем.
    views_per_hour = (views / age_h) if age_h > 0 and views else 0.0
    vph_strong = float(limits.get("speed_strong_vph", 10000))
    vph_moderate = float(limits.get("speed_moderate_vph", 3000))
    if views_per_hour >= vph_strong:
        sb.speed = rules.get("speed_strong", 20)
    elif views_per_hour >= vph_moderate:
        sb.speed = rules.get("speed_moderate", 10)

    # (4) views_over_followers — ТОЛЬКО бонус (не доминанта): ломается на крупных
    # (500к подписчиков → сильный суточный ролик по абсолюту < аудитории, но виралка).
    # Доверяем готовому флагу pull_reels; если его нет — считаем сами.
    followers = reel.get("follower_count")
    followers = int(followers) if isinstance(followers, (int, float)) and followers > 0 else None
    vof = reel.get("views_over_followers")
    if vof is None and followers and views:
        vof = views > followers
    if vof:
        sb.views_over_followers = rules.get("views_over_followers", 15)

    if views >= 1_000_000:
        sb.views_1m = rules.get("views_gt_1M", 20)
    if 0 < age_h <= 48:
        sb.fresh_48h = rules.get("fresh_under_48h", 20)
    if views > 0 and likes / views > 0.05:
        sb.er_5pct = rules.get("er_gt_5pct", 15)
    if 24 <= duration <= 60:
        sb.duration_24_60s = rules.get("duration_24_60s", 10)
    # (3b) Абсолютный объём комментов — сырой отклик. Не кумулятивно: верхний порог.
    if comments > 300:
        sb.comment_volume = rules.get("comment_volume_gt300", 25)
    elif comments > 100:
        sb.comment_volume = rules.get("comment_volume_gt100", 15)

    # (6) Конвертность: комментариев на 1000 просмотров плюс факт призыва в капшене.
    # Сам вердикт «призыв мёртвый» ставится ВТОРЫМ проходом (mark_dead_cta), потому что
    # порог берётся от медианы ЭТОГО пула, а один ролик своей ниши не знает.
    cr_1k = comment_rate_per_1k(comments, views)
    cta = has_cta(reel.get("caption"))
    is_dead_cta = False

    # (5) Порог снизу по просмотрам — МЯГКИЙ (только флаг в extras, не ворота):
    # отметка «ролик прошёл минимальный охват», чтобы топ можно было фильтровать
    # отдельно, не выкидывая сигнал из скоринга. min_views_floor=0 → флаг всегда True.
    floor = int(limits.get("min_views_floor", 0))
    above_floor = views >= floor

    vpf = reel.get("views_per_follower")
    sb.extras = {
        "views": views,
        "likes": likes,
        "comments": comments,
        "duration": duration,
        "age_h": round(age_h, 1),
        "views_per_hour": int(views_per_hour),
        "followers": followers,
        "views_over_followers": bool(vof),
        "views_per_follower": (round(float(vpf), 2) if isinstance(vpf, (int, float))
                               else (round(views / followers, 2) if followers and views else None)),
        "median_views": int(median_views) if median_views else None,
        "viral_ratio": round(views / median_views, 2) if median_views and views else None,
        "above_views_floor": above_floor,
        "comment_rate_per_1k": cr_1k,
        "has_cta": cta,
        "dead_cta": is_dead_cta,
    }
    return sb


def mark_dead_cta(scored: list[dict[str, Any]],
                  rules: dict[str, int],
                  limits: dict[str, Any]) -> list[dict[str, Any]]:
    """Второй проход: помечает доноров, чей призыв в капшене люди игнорируют.

    Порог ОТНОСИТЕЛЬНЫЙ, доля от медианы конвертности среди призывных роликов этого же
    пула. Фиксированного порога тут быть не может: замер 26.08 по восьми пулам показал
    разброс медианы в двадцать раз (AI 17.45, отношения 0.84, психология 0.82, ипотека
    0.73). Порог 5, снятый с ниши AI, пометил бы мёртвыми 87-94 процента ВСЕХ призывов у
    трёх клиентов, то есть выродился бы в наказание за сам призыв. Доля 1/3 на моём пуле
    даёт 5.8 и сходится с порогом, который до того был подобран на моих данных руками.

    Возвращает список помеченных. Штраф пишется в score_breakdown и в score_base.
    """
    min_views = int(limits.get("dead_cta_min_views", 1000))
    share = float(limits.get("dead_cta_median_share", 1.0 / 3.0))
    min_sample = int(limits.get("dead_cta_min_sample", 8))
    penalty = abs(int(rules.get("dead_cta_penalty", 25)))

    cta_rates = [s["score_breakdown"]["extras"].get("comment_rate_per_1k", 0.0)
                 for s in scored
                 if s["score_breakdown"]["extras"].get("has_cta")
                 and (s["score_breakdown"]["extras"].get("views") or 0) >= min_views]
    if len(cta_rates) < min_sample:
        # Выборки нет — судить не о чем. Молчать тут нельзя: ноль помеченных при живом
        # правиле и ноль при отсутствии выборки снаружи выглядят одинаково.
        log.info("мёртвый призыв: пропуск, призывных роликов %d при минимуме %d",
                 len(cta_rates), min_sample)
        return []
    floor = median(cta_rates) * share
    marked: list[dict[str, Any]] = []
    for s in scored:
        ex = s["score_breakdown"]["extras"]
        if not ex.get("has_cta"):
            continue
        if (ex.get("views") or 0) < min_views:
            continue
        if ex.get("comment_rate_per_1k", 0.0) >= floor:
            continue
        ex["dead_cta"] = True
        s["score_breakdown"]["dead_cta"] = -penalty
        s["score_base"] = s["score_base"] - penalty
        s["score_total"] = s["score_total"] - penalty
        marked.append(s)
    log.info("мёртвый призыв: порог %.2f (медиана призывных %.2f × %.2f), помечено %d из %d призывных | %s",
             floor, median(cta_rates), share, len(marked), len(cta_rates),
             ", ".join(f"@{s['username']}/{s['code']}"
                       f"(cr={s['score_breakdown']['extras'].get('comment_rate_per_1k')})"
                       for s in marked) or "—")
    return marked


def main() -> int:
    if not INPUT_FILE.exists():
        log.error("missing input %s — run pull_reels.py first", INPUT_FILE)
        return 1
    watchlist = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    rules: dict[str, int] = watchlist.get("scoring", {})
    limits: dict[str, Any] = watchlist.get("limits", {})
    trigger_variants: list[str] = watchlist.get("trigger_word_variants_for_comment_signal", [])
    bonus_trigger: int = rules.get("comment_with_trigger_word_gt10", 25)

    input_data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    now_ts = int(time.time())

    # 1) median per author — берём готовый из pull_reels.py; ре-фетчим только если его нет
    median_by_user: dict[str, float | None] = {}
    for acc in input_data:
        uid = acc.get("user_id")
        uname = acc.get("username", "?")
        pre = acc.get("median_views")
        if isinstance(pre, (int, float)) and pre > 0:
            median_by_user[uname] = float(pre)
            continue
        if not uid:
            median_by_user[uname] = None
            continue
        log.info("median fetch (fallback): %s", uname)
        median_by_user[uname] = fetch_author_median_views(str(uid), uname)
        time.sleep(0.5)

    # 2) базовый скор для всех рилсов
    scored: list[dict[str, Any]] = []
    for acc in input_data:
        uname = acc.get("username", "?")
        med = median_by_user.get(uname)
        for r in acc.get("reels", []):
            sb = base_score(r, med, now_ts, rules, limits)
            scored.append(
                {
                    "username": uname,
                    "code": r.get("code"),
                    "url": r.get("url"),
                    "media_pk": r.get("pk") or r.get("id"),
                    "score_breakdown": asdict(sb),
                    "score_base": sb.total,
                    "score_total": sb.total,  # обновим после комментов
                    "raw": r,
                }
            )

    # 2b) мёртвый призыв — ДО отбора кандидатов на дорогой фетч комментов: донор, чей
    # призыв игнорируют, не должен ни занимать бюджет запросов, ни всплывать в обзоре.
    mark_dead_cta(scored, rules, limits)

    # 3) трэкер триггер-комментов только для рилсов с базовым >= 30
    threshold = 30
    candidates = [s for s in scored if s["score_base"] >= threshold]
    budget_s = comments_budget_s()
    deadline = time.monotonic() + budget_s
    log.info("comments fetch: %d candidates (base >= %d), бюджет %.0f с",
             len(candidates), threshold, budget_s)
    comments_skipped = 0
    comments_partial = 0
    for s in candidates:
        if time.monotonic() >= deadline:
            # Пропуск помечается НА САМОМ рилсе: без пометки «бонуса нет» неотличимо
            # от «бонус не заслужен», и в выдаче это молчаливое занижение скора.
            comments_skipped += 1
            s["score_breakdown"]["extras"]["trigger_comments_n"] = 0
            s["score_breakdown"]["extras"]["comments_sampled"] = 0
            s["score_breakdown"]["extras"]["trigger_share"] = 0.0
            s["score_breakdown"]["extras"]["comments_skipped"] = True
            continue
        texts, budget_hit = fetch_comments(s["media_pk"], s["code"], deadline=deadline)
        trig_n = count_trigger_comments(texts, trigger_variants)
        sampled = len(texts)
        share = trig_n / sampled if sampled else 0.0
        s["score_breakdown"]["extras"]["trigger_comments_n"] = trig_n
        s["score_breakdown"]["extras"]["comments_sampled"] = sampled
        s["score_breakdown"]["extras"]["trigger_share"] = round(share, 3)
        # Усечённый бюджетом рилс идёт в тот же счёт, что и вовсе не тронутый (находка
        # Codex, раунд 2). Иначе последний кандидат, оборванный на середине выборки,
        # оставлял итог зелёным: «все N проверены» при непроверенном хвосте.
        s["score_breakdown"]["extras"]["comments_skipped"] = bool(budget_hit)
        if budget_hit:
            # «Частично» означает, что часть комментов мы всё-таки прочитали. Бюджет,
            # кончившийся на резолве или на ПЕРВОЙ странице, не даёт ни одного коммента —
            # такой кандидат не проверен ВОВСЕ, и звать это частичной проверкой значит
            # завышать покрытие (находка Codex, раунд 5).
            if sampled:
                comments_partial += 1
            else:
                comments_skipped += 1
        # Калибровка  (<agent>, после фикса pk-фетча <agent>): абсолют >10
        # ловит только giveaway-рилсы. Добавлен пропорциональный сигнал — триггер-
        # слово как доля выборки: >=15% при >=3 упоминаниях = реальный паттерн
        # "слово в комменты", даже если абсолют скромный при выборке до 50.
        if trig_n > 10 or (trig_n >= 3 and share >= 0.15):
            s["score_breakdown"]["trigger_comments_gt10"] = bonus_trigger
            s["score_total"] = s["score_base"] + bonus_trigger
        # Пауза между кандидатами тоже тратит бюджет, и после ПОСЛЕДНЕГО она не нужна
        # никому (находка Codex, раунд 5): прежде шаг выходил за заявленный потолок уже
        # после того, как все запросы в него уложились.
        if deadline is not None and time.monotonic() >= deadline:
            continue
        time.sleep(0.4)

    if comments_skipped or comments_partial:
        log.warning(
            "БЮДЖЕТ КОММЕНТОВ ИСЧЕРПАН (%.0f с): не проверены вовсе %d, проверены "
            "частично %d, всего кандидатов %d. У них отсутствие бонуса НЕ означает "
            "отсутствия слова в комментах, это непроверенное. Поднять бюджет: "
            "%s=<секунды> (потолок %.0f).",
            budget_s, comments_skipped, comments_partial, len(candidates),
            COMMENTS_BUDGET_ENV, COMMENTS_BUDGET_MAX_S)
    else:
        log.info("comments fetch: все %d кандидатов проверены в бюджет %.0f с",
                 len(candidates), budget_s)

    # 4) FRESHNESS-GATE (hard). Стале НИКОГДА не попадает в выгрузку.
    #    Тиринг: primary <=lookback_hours (24), fallback <=fallback_lookback_hours (48).
    #    Если в 24ч-окне набралось >= min_primary роликов — используем только их,
    #    иначе расширяемся до 48ч. Дальше 48ч — отсекается полностью.
    primary_h = int(limits.get("lookback_hours", 24))
    fallback_h = int(limits.get("fallback_lookback_hours", 48))
    min_primary = int(limits.get("min_primary_for_strict", 6))

    def age_of(s: dict[str, Any]) -> float:
        a = s["score_breakdown"]["extras"].get("age_h")
        return a if isinstance(a, (int, float)) and a >= 0 else 9999.0

    primary = [s for s in scored if age_of(s) <= primary_h]
    fallback = [s for s in scored if age_of(s) <= fallback_h]
    if len(primary) >= min_primary:
        fresh_pool, window_used = primary, primary_h
    else:
        fresh_pool, window_used = fallback, fallback_h
    dropped = len(scored) - len(fresh_pool)
    log.info("freshness-gate: %d in <=%dh window, %d stale dropped (>%dh)",
             len(fresh_pool), window_used, dropped, window_used)

    # SEEN-GATE (hard): уже показанные/взятые/отклонённые рилсы не возвращаем —
    # свежий по возрасту (<=48ч) ролик мог быть показан вчера. reels_seen.json
    # пишет mark_shown.py. Фильтруем ДО записи _scored.json, чтобы и download_thumbs,
    # и _top10 (визуальный фильтр <agent>) уже были без повторов.
    seen_codes = lib_seen.load_seen_codes()
    before_seen = len(fresh_pool)
    fresh_pool = [s for s in fresh_pool if s.get("code") not in seen_codes]
    log.info("seen-gate: %d seen codes loaded, %d reels dropped (already shown)",
             len(seen_codes), before_seen - len(fresh_pool))

    # PROTECTED TOP-N: помечаем сильнейшие ролики дня иммунными к author/theme-дедупу
    # Блока А (фильтруем мульти-осево по сырым комментам/показам/скорости/ratio).
    protected = mark_protected(fresh_pool, limits)
    log.info("protected: %d виралок (иммунны к author/theme-дедупу): %s",
             len(protected),
             ", ".join(f"@{p['username']}/{p['code']}({'+'.join(p['protected_reasons'])})"
                       for p in protected) or "—")

    # сортировка: выше скор, при равенстве — младший ролик первым
    fresh_pool.sort(key=lambda x: (-x["score_total"], age_of(x)))
    SCORED_FILE.write_text(json.dumps(fresh_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    review_n = _lim_int(limits, "thumbs_review_n", 15)
    top10 = fresh_pool[:review_n]
    # protected ОБЯЗАНЫ попасть в обзорный набор <agent>, даже если по score_total ниже
    # review_n (порог обзора не должен тихо прятать бэнгер до глаз <agent>).
    in_top = {id(s) for s in top10}
    for s in fresh_pool:
        if s.get("protected") and id(s) not in in_top:
            top10.append(s)
            in_top.add(id(s))
    TOP10_FILE.write_text(json.dumps(top10, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("saved %d fresh scored (window=%dh), top%d (+%d protected вне обзора) → %s",
             len(fresh_pool), window_used, len(top10),
             sum(1 for s in top10[review_n:]), TOP10_FILE)

    print("\n=== TOP 10 ===")
    for i, s in enumerate(top10, 1):
        ex = s["score_breakdown"]["extras"]
        vof = "V>F" if ex.get("views_over_followers") else "   "
        prot = "🛡" if s.get("protected") else " "
        print(
            f"{prot}{i:2d}. @{s['username']:25s} {s['code']}  "
            f"score={s['score_total']:>3d}  "
            f"views={ex.get('views', 0):>9d}  "
            f"vph={ex.get('views_per_hour', 0):>7d}  "
            f"{vof} f={ex.get('followers')}  "
            f"cmts={ex.get('comments', 0):>5d}  "
            f"viral_x={ex.get('viral_ratio')}  "
            f"age={ex.get('age_h')}h"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
