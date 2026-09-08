#!/usr/bin/env python3
"""Тесты бюджета времени на шаг комментов в score.py (заявка <agent>, ).

Набор НЕУБИВАЕМЫЙ: секция, умершая исключением, даёт FAIL, а не трейсбек — иначе
мутационный прогон считает пойманным мутанта, который просто уронил набор.
Запуск: python3 test_comments_budget.py
"""
from __future__ import annotations
import os

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

PASS = 0
FAIL = 0
_failed_names: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        _failed_names.append(name)
        print(f"  FAIL: {name} {extra}")


def section(fn):
    """Секция, упавшая исключением, засчитывается как FAIL, а не рушит прогон."""
    def wrapper():
        global FAIL
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            FAIL += 1
            _failed_names.append(f"{fn.__name__}:EXC")
            print(f"  FAIL: секция {fn.__name__} умерла исключением: {e!r}")
    wrapper.__name__ = fn.__name__
    return wrapper


class LogCapture:
    """Захват журнала на БОЕВОМ уровне: подмена log.warning на log.debug должна ловиться."""

    def __init__(self, level=logging.INFO):
        self.level = level
        self.records: list[tuple[str, str]] = []

    def __enter__(self):
        cap = self

        class H(logging.Handler):
            def emit(self, rec):
                cap.records.append((rec.levelname, rec.getMessage()))

        self.h = H(level=self.level)
        score.log.addHandler(self.h)
        self.prev = score.log.level
        score.log.setLevel(self.level)
        return self

    def __exit__(self, *a):
        score.log.removeHandler(self.h)
        score.log.setLevel(self.prev)

    def has(self, needle: str, level: str | None = None) -> bool:
        return any(needle in m and (level is None or lv == level) for lv, m in self.records)


# ---------------------------------------------------------------- бюджет из env
@section
def t_budget_constants_are_sane():
    """Мутант, обнуливший дефолт, проходил проверки «равно дефолту»: они сравнивали
    константу с ней же. Нулевой или крошечный дефолт означает, что комменты не
    фетчатся вовсе — весь шаг пропускается молча, а прогон выглядит нормальным."""
    d = score.COMMENTS_BUDGET_DEFAULT_S
    m = score.COMMENTS_BUDGET_MAX_S
    check("дефолт положителен", isinstance(d, float) and d > 0, f"d={d}")
    check("дефолта хватает хотя бы на десяток медленных рилсов", d >= 60.0, f"d={d}")
    check("дефолт не абсурдно велик", d <= 1800.0, f"d={d}")
    check("потолок выше дефолта", m > d, f"m={m} d={d}")
    check("потолок конечен и не абсурден", 60.0 <= m <= 24 * 3600.0, f"m={m}")


@section
def t_budget_default():
    check("нет env -> дефолт", score.comments_budget_s({}) == score.COMMENTS_BUDGET_DEFAULT_S)
    check("пустая строка -> дефолт",
          score.comments_budget_s({score.COMMENTS_BUDGET_ENV: ""}) == score.COMMENTS_BUDGET_DEFAULT_S)
    check("пробелы -> дефолт",
          score.comments_budget_s({score.COMMENTS_BUDGET_ENV: "   "}) == score.COMMENTS_BUDGET_DEFAULT_S)


@section
def t_budget_valid():
    check("120 -> 120", score.comments_budget_s({score.COMMENTS_BUDGET_ENV: "120"}) == 120.0)
    check("дробное 45.5 -> 45.5",
          score.comments_budget_s({score.COMMENTS_BUDGET_ENV: "45.5"}) == 45.5)
    check("с пробелами по краям",
          score.comments_budget_s({score.COMMENTS_BUDGET_ENV: " 200 "}) == 200.0)
    check("ровно потолок проходит",
          score.comments_budget_s({score.COMMENTS_BUDGET_ENV: str(score.COMMENTS_BUDGET_MAX_S)})
          == score.COMMENTS_BUDGET_MAX_S)


@section
def t_budget_broken_falls_back_loudly():
    """Отключения нет намеренно: любое непонятое значение = дефолт, и это слышно."""
    for bad in ("abc", "0", "-5", "nan", "inf", "-inf", "None", "300s"):
        with LogCapture() as cap:
            got = score.comments_budget_s({score.COMMENTS_BUDGET_ENV: bad})
        check(f"{bad!r} -> дефолт", got == score.COMMENTS_BUDGET_DEFAULT_S, f"got={got}")
        check(f"{bad!r} назван вслух WARNING", cap.has(score.COMMENTS_BUDGET_ENV, "WARNING"))


@section
def t_budget_over_max_clipped_loudly():
    with LogCapture() as cap:
        got = score.comments_budget_s({score.COMMENTS_BUDGET_ENV: "99999"})
    check("выше потолка -> потолок", got == score.COMMENTS_BUDGET_MAX_S)
    check("срез назван вслух", cap.has("потолка", "WARNING"))


@section
def t_budget_reads_real_environ():
    import os
    prev = os.environ.get(score.COMMENTS_BUDGET_ENV)
    try:
        os.environ[score.COMMENTS_BUDGET_ENV] = "77"
        check("без аргумента читает os.environ", score.comments_budget_s() == 77.0)
    finally:
        if prev is None:
            os.environ.pop(score.COMMENTS_BUDGET_ENV, None)
        else:
            os.environ[score.COMMENTS_BUDGET_ENV] = prev


# ------------------------------------------------------- дедлайн в fetch_comments
@section
def t_fetch_stops_before_any_call_when_deadline_passed():
    calls = []

    def fake(path, params, timeout=None):
        calls.append(params)
        return {"response": {"comments": [{"pk": "1", "text": "ПРИВЕТ"}]}}

    orig = score.hiker_call
    score.hiker_call = fake
    try:
        out, hit = score.fetch_comments("123", "CODE", deadline=time.monotonic() - 1)
    finally:
        score.hiker_call = orig
    check("истёкший дедлайн: ни одного запроса", calls == [], f"calls={len(calls)}")
    check("истёкший дедлайн: пустая выборка", out == [])
    check("истёкший дедлайн: усечение названо", hit is True)


@section
def t_fetch_stops_mid_pagination():
    """Дедлайн истекает после первой страницы — собранное отдаётся, вторая не берётся."""
    state = {"n": 0}
    box = {}

    def fake(path, params, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            box["expire"] = True
            return {"response": {"comments": [{"pk": "1", "text": "СЛОВО"}]},
                    "next_page_id": "p2"}
        return {"response": {"comments": [{"pk": "2", "text": "ВТОРАЯ"}]},
                "next_page_id": "p3"}

    fake_now = {"t": 1000.0}

    def mono():
        # время идёт только после первого ответа: первая страница успевает, вторая нет
        if box.get("expire"):
            return 2000.0
        return fake_now["t"]

    orig_call, orig_mono, orig_sleep = score.hiker_call, time.monotonic, time.sleep
    score.hiker_call = fake
    time.monotonic = mono
    time.sleep = lambda *_: None
    try:
        out, hit = score.fetch_comments("123", "CODE", deadline=1500.0)
    finally:
        score.hiker_call = orig_call
        time.monotonic = orig_mono
        time.sleep = orig_sleep
    check("остановка после первой страницы", state["n"] == 1, f"страниц={state['n']}")
    check("собранное отдано", out == ["слово"], f"out={out}")
    check("частичная выборка ПОМЕЧЕНА усечённой", hit is True,
          "иначе «бонуса нет» неотличимо от «слова не было»")


@section
def t_call_timeout_is_clipped_by_remaining_budget():
    """Находка Codex R2 (critical): проверка ТОЛЬКО перед запросом оставляла шагу
    возможность висеть внутри вызова ещё HIKER_TIMEOUT_S сверх бюджета, восьмикратно."""
    seen: list[float] = []
    now = {"t": 1000.0}

    def fake(path, params, timeout=score.HIKER_TIMEOUT_S):
        seen.append(timeout)
        return {"response": {"comments": [], "comment_count": 0}}

    orig_call, orig_mono = score.hiker_call, time.monotonic
    score.hiker_call = fake
    time.monotonic = lambda: now["t"]
    try:
        score.fetch_comments("123", "CODE", deadline=now["t"] + 3.0)
    finally:
        score.hiker_call = orig_call
        time.monotonic = orig_mono
    check("запрос сделан", len(seen) == 1, f"seen={seen}")
    check("таймаут срезан остатком бюджета", seen and seen[0] <= 3.0, f"timeout={seen}")

    seen.clear()
    orig_call = score.hiker_call
    score.hiker_call = fake
    try:
        score.fetch_comments("123", "CODE")
    finally:
        score.hiker_call = orig_call
    check("без дедлайна таймаут штатный",
          seen and seen[0] == score.HIKER_TIMEOUT_S, f"timeout={seen}")


@section
def t_fetch_without_deadline_unchanged():
    """Без дедлайна поведение прежнее — правка не меняет старый путь."""
    state = {"n": 0}

    def fake(path, params, timeout=None):
        state["n"] += 1
        return {"response": {"comments": [{"pk": str(state["n"]), "text": "ТЕКСТ"}],
                             "comment_count": 1}}

    orig_call, orig_sleep = score.hiker_call, time.sleep
    score.hiker_call = fake
    time.sleep = lambda *_: None
    try:
        out, hit = score.fetch_comments("123", "CODE")
    finally:
        score.hiker_call = orig_call
        time.sleep = orig_sleep
    check("без дедлайна запрос сделан", state["n"] >= 1)
    check("без дедлайна тексты собраны", out == ["текст"], f"out={out}")
    check("без дедлайна усечения нет", hit is False)


# --------------------------------------------------- поведение цикла кандидатов
def _run_candidate_loop(budget: float, per_call_cost: float, n_candidates: int):
    """Прогон ровно той логики, что стоит в main: бюджет, пометка, громкая строка.

    Держим копию цикла в тесте НЕ ДЛЯ ТОГО, чтобы проверять копию: ниже секция
    t_main_loop_source_matches сверяет, что боевой main несёт те же условия.
    """
    now = {"t": 0.0}
    orig_mono, orig_sleep = time.monotonic, time.sleep
    time.monotonic = lambda: now["t"]
    time.sleep = lambda *_: None

    def fake(path, params, timeout=None):
        now["t"] += per_call_cost
        return {"response": {"comments": [], "comment_count": 0}}

    orig_call = score.hiker_call
    score.hiker_call = fake
    try:
        candidates = [{"code": f"C{i}", "media_pk": str(i),
                       "score_base": 40, "score_total": 40,
                       "score_breakdown": {"extras": {}}} for i in range(n_candidates)]
        deadline = now["t"] + budget
        skipped = 0
        for s in candidates:
            if time.monotonic() >= deadline:
                skipped += 1
                s["score_breakdown"]["extras"]["trigger_comments_n"] = 0
                s["score_breakdown"]["extras"]["comments_sampled"] = 0
                s["score_breakdown"]["extras"]["trigger_share"] = 0.0
                s["score_breakdown"]["extras"]["comments_skipped"] = True
                continue
            _texts, hit = score.fetch_comments(s["media_pk"], s["code"], deadline=deadline)
            s["score_breakdown"]["extras"]["comments_skipped"] = bool(hit)
        return candidates, skipped
    finally:
        score.hiker_call = orig_call
        time.monotonic = orig_mono
        time.sleep = orig_sleep


@section
def t_loop_marks_skipped():
    cands, skipped = _run_candidate_loop(budget=10.0, per_call_cost=4.0, n_candidates=6)
    check("часть пропущена", skipped > 0, f"skipped={skipped}")
    check("часть обработана", skipped < len(cands), f"skipped={skipped}")
    for c in cands:
        ex = c["score_breakdown"]["extras"]
        check(f"{c['code']}: пометка есть всегда", "comments_skipped" in ex)
    sk = [c for c in cands if c["score_breakdown"]["extras"]["comments_skipped"]]
    for c in sk:
        ex = c["score_breakdown"]["extras"]
        check(f"{c['code']}: нулевые поля у пропущенного",
              ex["trigger_comments_n"] == 0 and ex["comments_sampled"] == 0
              and ex["trigger_share"] == 0.0)


@section
def t_loop_full_budget_skips_nothing():
    cands, skipped = _run_candidate_loop(budget=1000.0, per_call_cost=1.0, n_candidates=5)
    check("щедрый бюджет: пропусков нет", skipped == 0, f"skipped={skipped}")
    check("все помечены как непропущенные",
          all(c["score_breakdown"]["extras"]["comments_skipped"] is False for c in cands))


# ------------------------------------------- боевой main несёт те же условия
@section
def t_main_loop_source_matches():
    """Копия цикла в тесте ничего не доказывает про бой — сверяем ИСХОДНИК main."""
    src = Path(score.__file__).read_text(encoding="utf-8")
    check("main зовёт comments_budget_s", "budget_s = comments_budget_s()" in src)
    check("main строит deadline", "deadline = time.monotonic() + budget_s" in src)
    check("main сверяет дедлайн в цикле кандидатов",
          "if time.monotonic() >= deadline:" in src)
    check("main передаёт дедлайн в fetch_comments",
          "fetch_comments(s[\"media_pk\"], s[\"code\"], deadline=deadline)" in src)
    check("main разбирает признак усечения",
          "texts, budget_hit = fetch_comments(" in src)
    check("усечённый идёт в тот же счёт",
          '"comments_skipped"] = bool(budget_hit)' in src and "comments_partial += 1" in src)
    check("итог считает и частичные",
          "if comments_skipped or comments_partial:" in src)
    check("итог называет оба числа",
          "не проверены вовсе %d, проверены" in src and "частично %d" in src)
    check("таймаут запроса режется остатком",
          "call_timeout = HIKER_TIMEOUT_S if left is None else min(HIKER_TIMEOUT_S, left)" in src)
    check("main помечает пропущенного", '"comments_skipped"] = True' in src)
    check("main помечает обработанного признаком усечения",
          '"comments_skipped"] = bool(budget_hit)' in src)
    check("main обнуляет поля пропущенного",
          '"trigger_comments_n"] = 0' in src and '"comments_sampled"] = 0' in src)
    # Наличие log.warning ГДЕ-ТО в файле громкости этой строки не доказывает:
    # мутант переводил на log.info только её, а warning оставался в чтении env.
    idx = src.find("БЮДЖЕТ КОММЕНТОВ ИСЧЕРПАН")
    check("строка про исчерпание есть", idx > 0)
    head = src[max(0, idx - 200):idx]
    check("именно она идёт через log.warning",
          "log.warning(" in head and "log.info(" not in head.split("log.warning(")[-1],
          f"head={head[-80:]!r}")
    check("fetch_comments сверяет дедлайн перед страницей",
          "if deadline is not None and time.monotonic() >= deadline:" in src)
    # отключения бюджета быть не должно
    check("флага отключения бюджета нет",
          "BUDGET_DISABLE" not in src and "budget_off" not in src)


@section
def t_warning_text_names_the_consequence():
    """Строка обязана говорить, что отсутствие бонуса у пропущенных — непроверенное."""
    src = Path(score.__file__).read_text(encoding="utf-8")
    check("названо число из скольких", "всего кандидатов %d" in src)
    check("названо, что это непроверенное", "непроверенное" in src)
    check("названа ручка подъёма", "%s=<секунды>" in src)


@section
def t_resolve_pk_respects_budget():
    """Резолв pk стоит ДО цикла, значит бюджет обязан судить и его (находка Codex R3)."""
    calls = []

    def fake(path, params, timeout=None):
        calls.append((path, timeout))
        return {"response": {"comments": [{"pk": "1", "text": "ПРИВЕТ"}]}, "pk": "999"}

    orig = score.hiker_call
    score.hiker_call = fake
    try:
        # без pk и с истёкшим бюджетом резолв не оплачивается вовсе
        out, hit = score.fetch_comments("", "CODE", deadline=time.monotonic() - 1)
        check("истёкший бюджет: резолв не вызывался", calls == [], f"calls={calls}")
        check("истёкший бюджет: выборка пуста", out == [])
        check("истёкший бюджет до резолва: усечение названо", hit is True)

        # живой бюджет: резолв идёт, но его таймаут урезан остатком
        calls.clear()
        out, hit = score.fetch_comments("", "CODE", deadline=time.monotonic() + 2)
        check("живой бюджет: резолв вызван", bool(calls), f"calls={calls}")
        check("таймаут резолва урезан остатком",
              calls and calls[0][1] is not None and calls[0][1] <= 2.01,
              f"timeout={calls[0][1] if calls else None}")
        check("резолв без бюджета не трогается",
              score.resolve_pk_from_code.__defaults__[0] == score.HIKER_TIMEOUT_S)
    finally:
        score.hiker_call = orig


@section
def t_failed_resolve_on_spent_budget_is_marked():
    """Резолв, не уложившийся в бюджет, не имеет права выглядеть проверкой."""

    def fake(path, params, timeout=None):
        # резолв «съедает» остаток бюджета и возвращает ошибку
        time.sleep(0.05)
        return {"_error": "HTTP 504", "_body": "gateway timeout"}

    orig = score.hiker_call
    score.hiker_call = fake
    try:
        out, hit = score.fetch_comments("", "CODE", deadline=time.monotonic() + 0.01)
    finally:
        score.hiker_call = orig
    check("неудачный резолв на исчерпанном бюджете: пусто", out == [])
    check("неудачный резолв на исчерпанном бюджете: помечен", hit is True)


@section
def t_error_after_budget_spent_is_marked():
    """Отказ запроса на исчерпанном бюджете это усечение бюджетом, а не «проверено»."""

    def fake(path, params, timeout=None):
        time.sleep(0.05)
        return {"_error": "HTTP 429", "_body": "rate limited"}

    orig = score.hiker_call
    score.hiker_call = fake
    try:
        out, hit = score.fetch_comments("123", "CODE", deadline=time.monotonic() + 0.01)
    finally:
        score.hiker_call = orig
    check("отказ на исчерпанном бюджете: пусто", out == [])
    check("отказ на исчерпанном бюджете: помечен усечением", hit is True)


@section
def t_error_with_budget_left_is_not_a_budget_hit():
    """Обратная сторона: настоящий отказ при живом бюджете бюджетом не объявляется."""

    def fake(path, params, timeout=None):
        return {"_error": "HTTP 500", "_body": "boom"}

    orig = score.hiker_call
    score.hiker_call = fake
    try:
        out, hit = score.fetch_comments("123", "CODE", deadline=time.monotonic() + 60)
    finally:
        score.hiker_call = orig
    check("отказ при живом бюджете: пусто", out == [])
    check("отказ при живом бюджете: усечением НЕ зовётся", hit is False)



@section
def t_sleep_is_not_spent_after_budget_is_gone():
    """Пауза между страницами тоже тратит бюджет: спать после исчерпания нельзя.

    Проверяем ФАКТ вызова sleep, а не наличие строки в исходнике: прежняя сверка
    доказывала порядок строк и мутанта, снявшего условие, не ловила.
    """
    slept = []
    pages = [
        {"response": {"comments": [{"pk": "1", "text": "РАЗ"}], "comment_count": 99},
         "next_page_id": "p2"},
        {"response": {"comments": [{"pk": "2", "text": "ДВА"}], "comment_count": 99},
         "next_page_id": "p3"},
    ]
    seq = list(pages)

    def fake(path, params, timeout=None):
        return seq.pop(0) if seq else {"response": {"comments": []}}

    # Время идёт так, что бюджет исчерпан РОВНО после первой страницы.
    # 1-й тик: остаток бюджета в начале итерации (живой). 2-й: проверка перед паузой,
    # бюджет уже исчерпан — спать нельзя.
    ticks = iter([0.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    last = [0.0]

    def mono():
        try:
            last[0] = next(ticks)
        except StopIteration:
            pass
        return last[0]

    orig_call, orig_mono, orig_sleep = score.hiker_call, time.monotonic, time.sleep
    score.hiker_call = fake
    time.monotonic = mono
    time.sleep = lambda d: slept.append(d)
    try:
        out, hit = score.fetch_comments("123", "CODE", deadline=5.0)
    finally:
        score.hiker_call = orig_call
        time.monotonic = orig_mono
        time.sleep = orig_sleep
    check("после исчерпания бюджета не спим", slept == [], f"slept={slept}")
    check("собранное отдано", out == ["раз"], f"out={out}")
    check("усечение названо", hit is True)


@section
def t_empty_partial_counts_as_not_checked_at_all():
    """Пустая выборка с пометкой бюджета это НЕ «частично» (находка Codex R5).

    Бюджет, кончившийся на резолве или первой странице, не даёт ни одного коммента.
    Считать такого кандидата частично проверенным значит завышать покрытие.
    """
    src = Path(score.__file__).read_text(encoding="utf-8")
    check("частично считается только при непустой выборке",
          "if sampled:\n                comments_partial += 1" in src, "")
    check("пустая выборка идёт в «не проверены вовсе»",
          "else:\n                comments_skipped += 1" in src, "")
    check("пауза не тратится после исчерпания бюджета в цикле кандидатов",
          "if deadline is not None and time.monotonic() >= deadline:\n            continue\n"
          "        time.sleep(0.4)" in src, "")


def main() -> int:
    for fn in (t_budget_constants_are_sane, t_budget_default, t_budget_valid, t_budget_broken_falls_back_loudly,
               t_budget_over_max_clipped_loudly, t_budget_reads_real_environ,
               t_fetch_stops_before_any_call_when_deadline_passed,
               t_fetch_stops_mid_pagination, t_call_timeout_is_clipped_by_remaining_budget,
               t_fetch_without_deadline_unchanged,
               t_loop_marks_skipped, t_loop_full_budget_skips_nothing,
               t_main_loop_source_matches, t_warning_text_names_the_consequence,
               t_resolve_pk_respects_budget, t_failed_resolve_on_spent_budget_is_marked,
               t_error_after_budget_spent_is_marked,
               t_error_with_budget_left_is_not_a_budget_hit,
               t_sleep_is_not_spent_after_budget_is_gone,
               t_empty_partial_counts_as_not_checked_at_all):
        fn()
    print(f"\nPASS={PASS} FAIL={FAIL}")
    if _failed_names:
        print("упало:", ", ".join(_failed_names))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
