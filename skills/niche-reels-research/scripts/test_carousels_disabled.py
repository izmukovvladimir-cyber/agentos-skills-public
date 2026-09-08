#!/usr/bin/env python3
"""Инстанс БЕЗ каруселей: protected-бэкстоп не обязан кричать каждое утро.

Заявка <agent> : у клиентского инстанса без карусельных источников
`_carousels_scored.json` не существует и существовать не может, поэтому бэкстоп печатал
CHECK BROKEN каждый день, а guard минимума требовал добрать карусели неоткуда.

Набор НЕУБИВАЕМЫЙ: секция, умершая исключением, даёт FAIL, а не обрушение прогона.
Боевые каталоги не читаются и не пишутся: каждый сценарий живёт в своей песочнице через
NRR_CLIENT_DIR, сеть не трогается (--dry-run).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SENDER = HERE / "send_morning_digest.py"

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


def section(name, fn):
    global FAIL
    print(f"=== {name}")
    try:
        fn()
    except Exception as exc:                       # noqa: BLE001 — ради неубиваемости
        FAIL += 1
        print(f"FAIL секция «{name}» умерла исключением: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)


def sandbox(*, limits: dict | None = None, config_raw: str | None = None,
            scored: list | None = None, car_scored=None, packs: list | None = None) -> Path:
    """Клиентский инстанс в /tmp: config/watchlist.json, pool/, pool/packs/."""
    root = Path(tempfile.mkdtemp(prefix="nrr-car-", dir="/tmp/claude-1000"))
    (root / "config").mkdir()
    (root / "pool" / "packs").mkdir(parents=True)
    (root / "out").mkdir()
    if config_raw is not None:
        (root / "config" / "watchlist.json").write_text(config_raw, encoding="utf-8")
    else:
        cfg = {"anchor_accounts": [], "limits": limits if limits is not None else {}}
        (root / "config" / "watchlist.json").write_text(json.dumps(cfg), encoding="utf-8")
    if scored is not None:
        (root / "pool" / "_scored.json").write_text(json.dumps(scored), encoding="utf-8")
    if car_scored is not None:
        raw = car_scored if isinstance(car_scored, str) else json.dumps(car_scored)
        (root / "pool" / "_carousels_scored.json").write_text(raw, encoding="utf-8")
    for i, p in enumerate(packs or [], 1):
        (root / "pool" / "packs" / f"pack_{i:02d}.json").write_text(json.dumps(p), encoding="utf-8")
    return root


def load_sender(root: Path):
    """Свежий импорт модуля с НУЖНЫМ NRR_CLIENT_DIR: пути читаются на импорте."""
    os.environ["NRR_CLIENT_DIR"] = str(root)
    for mod in ("lib_paths", "send_morning_digest_under_test"):
        sys.modules.pop(mod, None)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("send_morning_digest_under_test", SENDER)
    m = importlib.util.module_from_spec(spec)
    sys.modules["send_morning_digest_under_test"] = m
    spec.loader.exec_module(m)
    return m


REEL = {"code": "AAA111", "username": "boshnikov", "protected": True,
        "url": "https://instagram.com/reel/AAA111/"}
CAR = {"code": "CCC222", "username": "vvedenskaya", "protected": True,
       "url": "https://instagram.com/p/CCC222/"}


def s1_flag():
    cases = [
        ("ключа нет — включено", {}, True),
        ("false — выключено", {"carousels_enabled": False}, False),
        ("true — включено", {"carousels_enabled": True}, True),
        ('строка "false" — включено (не JSON false)', {"carousels_enabled": "false"}, True),
        ("0 — включено (не bool false)", {"carousels_enabled": 0}, True),
        ("null — включено", {"carousels_enabled": None}, True),
    ]
    for name, limits, want in cases:
        m = load_sender(sandbox(limits=limits))
        check(f"флаг: {name}", m.carousels_enabled() is want)
    m = load_sender(sandbox(config_raw="{не json"))
    check("битый конфиг — включено", m.carousels_enabled() is True)
    m = load_sender(sandbox(config_raw='{"limits": "строка"}'))
    check("limits не объект — включено", m.carousels_enabled() is True)
    # Тот же кривой конфиг не должен ронять и соседний читатель того же ключа.
    check("limits не объект — минимум каруселей на fallback",
          m.carousel_min() == m.CAROUSEL_MIN_FALLBACK)
    root = sandbox(limits={})
    (root / "config" / "watchlist.json").unlink()
    m = load_sender(root)
    check("конфига нет — включено", m.carousels_enabled() is True)


def s2_protected_codes():
    root = sandbox(limits={}, scored=[REEL])
    m = load_sender(root)
    check("файла нет и он обязателен — None",
          m._protected_codes(root / "pool" / "_carousels_scored.json") is None)
    check("файла нет и он не обязателен — пусто",
          m._protected_codes(root / "pool" / "_carousels_scored.json", required=False) == {})
    check("файл есть — коды прочитаны",
          m._protected_codes(root / "pool" / "_scored.json") == {"AAA111": "boshnikov"})
    root2 = sandbox(limits={"carousels_enabled": False}, car_scored="{битый")
    m2 = load_sender(root2)
    check("нечитаемый файл — сбой даже при выключенных каруселях",
          m2._protected_codes(root2 / "pool" / "_carousels_scored.json", required=False) is None)
    # Валидный JSON не той формы: файл читается, но скрейп писал не список — тоже сбой,
    # иначе смена формы выдачи молча превратилась бы в «сильнейших сегодня нет».
    root3 = sandbox(limits={"carousels_enabled": False}, car_scored={"а": 1})
    m3 = load_sender(root3)
    check("JSON не-список — сбой при выключенных каруселях",
          m3._protected_codes(root3 / "pool" / "_carousels_scored.json", required=False) is None)
    root4 = sandbox(limits={}, scored={"а": 1})
    m4 = load_sender(root4)
    check("JSON не-список — сбой и при включённых",
          m4._protected_codes(root4 / "pool" / "_scored.json") is None)


def s3_backstop():
    pack = {"code": "AAA111", "url": "https://instagram.com/reel/AAA111/"}
    # выключено + файла каруселей нет + protected-рилс в паке = тишина
    m = load_sender(sandbox(limits={"carousels_enabled": False}, scored=[REEL]))
    res = m.protected_missing_warn([pack])
    check("выключено: нет CHECK BROKEN", "ПРОВЕРКА НЕ ОТРАБОТАЛА" not in res.text, res.text[:90])
    check("выключено: тишина при полном паке", res.text == "", res.text[:90])
    # включено (как было) — тот же вход даёт CHECK BROKEN, ровно жалоба заявителя
    m = load_sender(sandbox(limits={}, scored=[REEL]))
    res = m.protected_missing_warn([pack])
    check("включено: CHECK BROKEN на месте", "ПРОВЕРКА НЕ ОТРАБОТАЛА" in res.text, res.text[:90])
    check("включено: назван именно карусельный файл",
          "_carousels_scored.json" in res.text, res.text[:120])
    # выключено, но protected-рилс НЕ в паке — бэкстоп рилсов обязан работать
    m = load_sender(sandbox(limits={"carousels_enabled": False}, scored=[REEL]))
    res = m.protected_missing_warn([{"code": "ZZZ999", "url": ""}])
    check("выключено: рилсовый бэкстоп жив", "protected-виралка НЕ вошла" in res.text, res.text[:90])
    check("выключено: назван пропавший рилс", "boshnikov" in res.text, res.text[:120])
    # выключено, но файл каруселей ЕСТЬ — читаем его, выключатель не прячет данные
    m = load_sender(sandbox(limits={"carousels_enabled": False}, scored=[REEL], car_scored=[CAR]))
    res = m.protected_missing_warn([pack])
    check("выключено: существующий файл каруселей всё равно прочитан",
          "vvedenskaya" in res.text, res.text[:120])
    # выключено, файл каруселей битый — сбой называется вслух
    m = load_sender(sandbox(limits={"carousels_enabled": False}, scored=[REEL], car_scored="{битый"))
    res = m.protected_missing_warn([pack])
    check("выключено: битый файл каруселей = CHECK BROKEN",
          "ПРОВЕРКА НЕ ОТРАБОТАЛА" in res.text, res.text[:90])
    # рилсовый scored пропал — это сбой при любом флаге
    m = load_sender(sandbox(limits={"carousels_enabled": False}))
    res = m.protected_missing_warn([pack])
    check("пропавший _scored.json остаётся сбоем",
          "_scored.json" in res.text and "ПРОВЕРКА НЕ ОТРАБОТАЛА" in res.text, res.text[:90])


def _run_sender(root: Path) -> str:
    env = dict(os.environ, NRR_CLIENT_DIR=str(root))
    r = subprocess.run(
        [sys.executable, str(SENDER), "--dry-run", "--force",
         "--packs-dir", str(root / "pool" / "packs"), "--out-dir", str(root / "out"),
         "--chat-id", "1"],
        capture_output=True, text=True, env=env, timeout=120)
    return r.stdout + r.stderr


def s4_end_to_end():
    pack = {"code": "AAA111", "url": "https://instagram.com/reel/AAA111/",
            "kind": "РИЛС", "username": "boshnikov"}
    out_off = _run_sender(sandbox(limits={"carousels_enabled": False, "carousel_min": 3},
                                  scored=[REEL], packs=[pack]))
    check("сквозной выключено: нет требования добрать карусели",
          "КАРУСЕЛЕЙ" not in out_off.upper() or "МИНИМУМ" not in out_off.upper(),
          out_off[-300:])
    check("сквозной выключено: факт выключения назван в сводке",
          "carousels_enabled=false" in out_off, out_off[-300:])
    check("сквозной выключено: нет CHECK BROKEN про карусельный файл",
          "_carousels_scored.json" not in out_off, out_off[-300:])
    out_on = _run_sender(sandbox(limits={"carousel_min": 3}, scored=[REEL], packs=[pack]))
    check("сквозной включено: требование добрать на месте",
          "МИНИМУМ" in out_on.upper(), out_on[-300:])
    check("сквозной включено: строки про выключение нет",
          "carousels_enabled=false" not in out_on, out_on[-300:])


for name, fn in (("1. чтение флага limits.carousels_enabled", s1_flag),
                 ("2. protected-коды и обязательность файла", s2_protected_codes),
                 ("3. поведение бэкстопа", s3_backstop),
                 ("4. сквозной прогон отправителя (--dry-run)", s4_end_to_end)):
    section(name, fn)

print(f"\nPASS {PASS} FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
