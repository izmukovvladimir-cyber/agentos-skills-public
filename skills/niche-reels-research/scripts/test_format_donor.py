#!/usr/bin/env python3
"""Тесты признака «донор формата» (заявка <agent> ).

Проверяются обе стороны: гейт хука (`hook_fidelity_check.py`) и печать причины в сводку
(`send_morning_digest.py`). Сеть не трогается, паки и транскрипты кладутся во временный
каталог, боевые каталоги подборок не читаются и не пишутся.

    python3 .../scripts/test_format_donor.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "hook_fidelity_check.py"
SENDER = HERE / "send_morning_digest.py"

PASS = FAIL = 0
# хук донора: чужие марки и диагноз, ровно случай @pediatr_nauruzova
DONOR_SPEECH = ("Несичка и Урьяш Атодерм это интенсив бальзам при атопическом дерматите "
                "и его надо мазать каждый день")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


HFC = load(CHECKER, "hook_fidelity_check")


def check(name: str, cond: bool, got=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {name}" + (f" (получили {got!r})" if got is not None else ""),
              file=sys.stderr)


def pack(**over) -> dict:
    p = {"author_username": "pediatr_nauruzova", "type": "reel",
         "url": "https://www.instagram.com/reel/DcHBjmsMRm-/",
         "editor_brief": "обычное ТЗ монтажу",
         "teleprompter": "Своя речь на позициях клиента, хук по конструкции донора",
         "card": "карточка"}
    p.update(over)
    return p


def run_checker(tmp: Path, packs: list[dict], speech: str = DONOR_SPEECH) -> tuple[int, str]:
    pd, rd = tmp / "packs", tmp / "pool"
    for d in (pd, rd):
        d.mkdir(parents=True, exist_ok=True)
    for f in pd.glob("pack_*.json"):
        f.unlink()
    for i, p in enumerate(packs):
        (pd / f"pack_{i:02d}.json").write_text(json.dumps(p, ensure_ascii=False),
                                              encoding="utf-8")
    # транскрипт кладётся ровно туда, откуда его читает гейт: work/<shortcode>/transcript.txt
    wd = rd / "work" / "DcHBjmsMRm-"
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "transcript.txt").write_text(speech, encoding="utf-8")
    r = subprocess.run([sys.executable, str(CHECKER), "--packs-dir", str(pd),
                        "--reels-dir", str(rd), "--min", "0.50"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    # ── признак сам по себе: заявлен + названа причина
    R = HFC.format_donor_reason
    D = HFC.declares_format_donor
    check("а1 ключ с причиной распознан",
          R({"hook_source": "format_donor", "hook_source_reason": "чужие марки"}, "")
          == "чужие марки")
    check("а2 регистр и пробелы ключа не мешают",
          R({"hook_source": "  Format_Donor ", "hook_source_reason": "марки"}, "") == "марки")
    check("а3 ключ БЕЗ причины донором не делает",
          R({"hook_source": "format_donor"}, "") == "")
    check("а3a но заявка видна отдельно", D({"hook_source": "format_donor"}, "") is True)
    check("а4 строка ТЗ монтажу с причиной распознана",
          R({}, "ДОНОР ФОРМАТА: речь оригинала это чужие марки") == "речь оригинала это чужие марки")
    check("а4a пометка списком тоже", R({}, "- ДОНОР ФОРМАТА — прайс конкурента")
          == "прайс конкурента")
    check("а4b пометка не первой строкой тоже",
          R({}, "первая строка\nДОНОР ФОРМАТА: диагнозы") == "диагнозы")
    check("а5 обычный пак донором не считается", R(pack(), "обычное ТЗ") == "")
    check("а6 чужое значение ключа не проходит", R({"hook_source": "original"}, "") == "")

    # ГЛАВНОЕ ПО РЕВЬЮ: свободное вхождение подстроки гейт НЕ снимает
    for name, brief in (
            ("отрицание", "НЕ ДОНОР ФОРМАТА, хук переносим дословно"),
            ("запрет в инструкции", "не ставь ДОНОР ФОРМАТА без нужды"),
            ("упоминание в середине", "тут был бы ДОНОР ФОРМАТА, но нет"),
            ("английская фраза", "FORMAT DONOR: brand names"),
            ("пометка без причины", "ДОНОР ФОРМАТА"),
            ("отрицание ПОСЛЕ пометки", "ДОНОР ФОРМАТА НЕ СТАВИТЬ"),
            ("склейка со словом", "ДОНОР ФОРМАТАМИ пользуемся редко"),
            ("склейка без пробела", "ДОНОР ФОРМАТА-НЕТ"),
            # пометка ПОСРЕДИ строки: замер показал, что при поиске подстрокой такая строка
            # снимала бы гейт (смещение 13 символов попадает ровно на разделитель)
            ("пометка посреди строки", "ВАЖНО-ПОМЕТКА: ДОНОР ФОРМАТА — марки")):
        check(f"а7 {name} гейт не снимает", R({}, brief) == "", (brief, R({}, brief)))
    check("а7a но заявка без причины ВИДНА (её не проглотят молча)",
          D({}, "ДОНОР ФОРМАТА") is True)
    check("а7b а отрицание заявкой не считается",
          D({}, "НЕ ДОНОР ФОРМАТА, хук переносим") is False)
    check("а7c отрицание после пометки — тоже не заявка",
          D({}, "ДОНОР ФОРМАТА НЕ СТАВИТЬ") is False)
    check("а7d склейка со словом — не заявка",
          D({}, "ДОНОР ФОРМАТАМИ пользуемся редко") is False)
    check("а7f пометка посреди строки заявкой не считается",
          D({}, "ВАЖНО-ПОМЕТКА: ДОНОР ФОРМАТА — марки") is False)
    check("а7e тире как разделитель работает",
          R({}, "ДОНОР ФОРМАТА - чужие марки") == "чужие марки")

    # ── обрезка причины: по границе слова, но с потолком (наблюдение <agent> 17.08)
    C = HFC._clip
    check("и1 короткая причина не трогается", C("чужие марки") == "чужие марки")
    check("и2 ровно по лимиту не трогается", C("а" * 160) == "а" * 160, C("а" * 160))
    # строка собрана так, чтобы 160-й символ падал ВНУТРИ слова: иначе жёсткая резка
    # случайно совпала бы с границей и мутант «режется посреди слова» остался бы не пойман
    long_reason = "слово " * 26 + "разорванноепродолжение и ещё хвост"
    got = C(long_reason)
    check("и3 длинная причина укорочена, многоточие ВНУТРИ лимита",
          len(got) <= 160, (len(got), got))
    check("и4 и обрезана многоточием", got.endswith("…"), got)
    check("и5 слово не разорвано посередине",
          long_reason.startswith(got[:-1]) and got[:-1].split()[-1] in long_reason.split(),
          got)
    # осознанный размен: одно слово длиннее лимита режется жёстко, потолок важнее
    check("и6 одно длинное слово режется жёстко, но упирается в потолок",
          len(C("я" * 400)) == 160 and C("я" * 400).endswith("…"), C("я" * 400)[-5:])
    check("и7 хвостовая пунктуация не остаётся перед многоточием",
          not C("слово " * 30 + ", хвост").rstrip("…").endswith(","),
          C("слово " * 30 + ", хвост"))
    check("и8 не строка даёт пустую строку", C(None) == "" and C(12) == "")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # ── БЕЗ пометки карточка блокируется: это исходная жалоба заявителя
        rc, out = run_checker(tmp, [pack()])
        check("б1 без пометки гейт блокирует (порог недостижим)", rc == 10, (rc, out[-200:]))
        check("б2 и называет потерянные слова", "потеряны слова хука" in out, out[-200:])

        # ── С пометкой ключом: штатный пропуск, причина напечатана
        rc, out = run_checker(tmp, [pack(hook_source="format_donor", hook_source_reason="речь это чужие марки")])
        check("в1 с ключом прогон чистый", rc == 0, (rc, out[-300:]))
        check("в2 напечатан токен для отправителя", HFC.DONOR_SKIP_TOKEN in out, out[-300:])
        check("в3 причина автора напечатана",
              "перенос хука не проверялся" in out and "чужие марки" in out, out[-300:])
        check("в4 в итоге посчитаны доноры", "доноров формата: 1" in out, out[-300:])

        # ── С пометкой в ТЗ монтажу: то же самое
        rc, out = run_checker(tmp, [pack(editor_brief="ДОНОР ФОРМАТА: берём конструкцию, речь оригинала это марки")])
        check("г1 пометка в ТЗ работает так же", rc == 0, (rc, out[-300:]))
        check("г2 и тоже с токеном", HFC.DONOR_SKIP_TOKEN in out, out[-300:])

        # ── ГРАНИЦА: пометка означает «телесуфлёр написан с нуля», а не «его нет»
        rc, out = run_checker(tmp, [pack(hook_source="format_donor", teleprompter="",
                                         hook_source_reason="речь это чужие марки")])
        check("д1 донор без телесуфлёра всё равно флаг", rc == 10, (rc, out[-300:]))
        check("д2 и причина названа прямо", "но телесуфлёра нет" in out, out[-300:])

        # ── заявка без причины: не пропуск и не молчание, а понятный флаг
        rc, out = run_checker(tmp, [pack(hook_source="format_donor")])
        check("д4 донор без причины блокирует", rc == 10, (rc, out[-300:]))
        check("д5 и объясняет, чего не хватает", "без причины" in out, out[-300:])
        check("д3 донором такой пак не объявлен",
              HFC.DONOR_SKIP_TOKEN not in out, out[-300:])

        # ── соседей пометка не трогает: чужая карточка судится как раньше
        other = pack(author_username="someone", hook_source=None,
                     teleprompter="Совсем другая речь без единого слова оригинала")
        rc, out = run_checker(tmp, [pack(hook_source="format_donor", hook_source_reason="речь это чужие марки"), other])
        check("е1 сосед без пометки по-прежнему судится", rc == 10, (rc, out[-300:]))
        check("е2 а донор остался пропущенным", HFC.DONOR_SKIP_TOKEN in out, out[-300:])

        # ── ОТПРАВИТЕЛЬ: токен читается и причина уходит в сводку
        SND = load(SENDER, "send_morning_digest")
        check("ж1 токен у обоих файлов один",
              SND.HOOK_DONOR_TOKEN == HFC.DONOR_SKIP_TOKEN,
              (SND.HOOK_DONOR_TOKEN, HFC.DONOR_SKIP_TOKEN))

        class FakeRun:
            def __init__(self, rc_: int, out_: str) -> None:
                self.returncode, self.stdout, self.stderr = rc_, out_, ""

        saved = SND.subprocess.run
        donor_line = (f"{HFC.DONOR_SKIP_TOKEN} pack_00.json (@pediatr_nauruzova): "
                      f"{HFC.FORMAT_DONOR_MARK} — хук оригинала не переносится")
        try:
            SND.subprocess.run = lambda *a, **kw: FakeRun(0, donor_line + "\n")
            res = SND.hook_fidelity_warn(tmp / "packs")
            check("з1 чистый прогон с донором не блокирует", res.violated is False, res)
            check("з2 но причина видна в сводке", "ДОНОР ФОРМАТА" in res.text, res.text)
            check("з2a сводка не утверждает непроверенного",
                  "написан с нуля" not in res.text and "Гейт этого не подтверждал" in res.text,
                  res.text)
            check("з3 названа карточка", "pack_00.json" in res.text, res.text)
            check("з4 и число карточек", "1 шт." in res.text, res.text)

            SND.subprocess.run = lambda *a, **kw: FakeRun(0, "")
            res = SND.hook_fidelity_warn(tmp / "packs")
            check("з5 без доноров сводка молчит как раньше", res.text == "", res.text)

            flag_out = donor_line + "\n[FLAG] pack_01.json @someone retention=0.10\n"
            SND.subprocess.run = lambda *a, **kw: FakeRun(10, flag_out)
            res = SND.hook_fidelity_warn(tmp / "packs")
            check("з6 донор не глушит настоящее нарушение", res.violated is True, res)
            check("з7 в сводке обе части",
                  "ДОНОР ФОРМАТА" in res.text and "pack_01.json" in res.text, res.text)

            SND.subprocess.run = lambda *a, **kw: FakeRun(2, "traceback")
            res = SND.hook_fidelity_warn(tmp / "packs")
            check("з8 сбой проверки по-прежнему не выдаётся за чистоту",
                  "НЕ ОТРАБОТАЛА" in res.text.upper(), res.text)
        finally:
            SND.subprocess.run = saved

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
