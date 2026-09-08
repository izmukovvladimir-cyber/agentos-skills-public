#!/usr/bin/env python3
"""Guard: /policy/ describes only the paths the owner actually runs.

Two independent things require a privacy policy, and they can be on separately:
  * site.analytics.yandex_metrika — the counter writes cookies and IP;
  * site.contacts_collection — the owner collects contact details OFF this site (a bot funnel
    asking for a phone number), and the consent line above that button needs a page to link to.

A page that claims a practice the owner does not run is as wrong as a missing page: it says
"we collect your phone" on a base that collects nothing, or stays silent about the phone while
the funnel asks for it. Hence every section is assembled per path, and this test checks both
directions for every combination.

The `where` field is FREE TEXT: a messenger, a phone call, a paper form, a CRM widget. So the
copy may not guess the channel. Codex found the first version guessing all four (phone number,
messengers, "in the same chat", "by pressing a button"), and the checks below pin that down.

Mechanism came from a live case: a client was asked for a phone number in a funnel and had no
privacy policy at all. Run: python3 test_policy_paths.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_draft_orphan import instance, registry, run  # noqa: E402  (same directory by design)

PASS = FAIL = 0

LEGAL = {"operator": "ИП Иванов Иван Иванович", "inn": "770000000000",
         "email": "mail@example.ru", "policy_date": "01.08.2026"}
CONTACTS = {
    "where": "Оператор собирает контактные данные в переписке в Telegram",
    "data": "номер телефона, имя, ник в мессенджере",
    "purpose": "Данные используются, чтобы связаться с вами и передать материалы.",
    "processors": ["Telegram", "ChatPlace"],
}
# a deliberately different channel: nothing about messengers, chats or phone numbers
BY_EMAIL = {
    "where": "Оператор принимает обращения по электронной почте",
    "data": "имя и адрес электронной почты",
    "purpose": "Данные используются, чтобы ответить на ваше обращение.",
}


def check(cond: bool, label: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def build(tmp: Path, name: str, *, metrika: bool, contacts: bool,
          legal: dict | None = LEGAL, cc: dict | None = None):
    inst = instance(tmp, name)

    def mutate(reg):
        site = reg["site"]
        if legal is not None:
            site["legal"] = dict(legal)
        if metrika:
            site["analytics"] = {"yandex_metrika": "12345678"}
        if contacts:
            site["contacts_collection"] = dict(CONTACTS) if cc is None else cc

    registry(inst, mutate)
    r = run(inst, "build.py")
    page = inst / "site" / "policy" / "index.html"
    return inst, r, (page.read_text(encoding="utf-8") if page.exists() else None)


def sections(html: str) -> dict[str, str]:
    """The page split by <h2>, so a check can say WHICH section carries a claim."""
    out = {}
    for m in re.finditer(r"<h2>(.*?)</h2>(.*?)(?=<h2>|</div>)", html, re.S):
        out[m.group(1)] = m.group(2)
    return out


def tree(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")} if root.exists() else set()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. ни счётчика, ни сбора: страницы нет вовсе, ссылки в подвале тоже
        inst, r, html = build(tmp, "none", metrika=False, contacts=False, legal=None)
        check(r.returncode == 0, f"чистая база не собралась: {r.stderr[-300:]}")
        check(html is None, "policy собралась там, где ничего не собирают")
        index = (inst / "site" / "index.html").read_text(encoding="utf-8")
        check("/policy/" not in index, "ссылка на политику стоит на базе без политики")

        # 2. только счётчик: страница про Метрику и БЕЗ обещаний про контакты
        inst, r, html = build(tmp, "metrika", metrika=True, contacts=False)
        check(r.returncode == 0, f"база со счётчиком не собралась: {r.stderr[-300:]}")
        check(html is not None, "счётчик есть, а политики нет")
        check("Яндекс.Метрика" in (html or ""), "политика не описывает счётчик")
        check("номер телефона" not in (html or ""),
              "политика обещает сбор телефона там, где его не собирают")
        check("обращаются к Оператору" not in (html or ""),
              "вводный абзац говорит об обращениях на базе без сбора контактов")
        check("обращаясь к Оператору" not in (html or ""),
              "согласие во вводном абзаце ссылается на несуществующий канал")
        index = (inst / "site" / "index.html").read_text(encoding="utf-8")
        check("/policy/" in index, "политика собрана, а ссылки на неё в подвале нет")

        # 3. только сбор контактов: страница про обращения и БЕЗ слова про Метрику
        inst, r, html = build(tmp, "contacts", metrika=False, contacts=True)
        check(r.returncode == 0, f"база со сбором контактов не собралась: {r.stderr[-300:]}")
        check(html is not None, "сбор контактов объявлен, а политики нет")
        sec = sections(html or "")
        check("номер телефона" in sec.get("Какие данные обрабатываются", ""),
              "состав собираемых данных не попал в свой раздел")
        check("Яндекс.Метрика" not in (html or ""),
              "политика описывает счётчик, которого на сайте нет")
        check("cookie" not in (html or "").lower(),
              "политика говорит о cookie на базе без веб-аналитики")
        check("ООО Яндекс" not in (html or ""),
              "политика называет обработчиком Яндекс на базе без счётчика")
        check("счётчиков веб-аналитики на нём нет" in (html or ""),
              "политика не сказала, что аналитики нет")
        check("Telegram" in sec.get("Передача данных", "")
              and "ChatPlace" in sec.get("Передача данных", ""),
              "обработчики из processors не попали в раздел о передаче")
        check("Используя сайт" not in (html or ""),
              "согласие выводится из посещения статического сайта")
        index = (inst / "site" / "index.html").read_text(encoding="utf-8")
        check("/policy/" in index, "политика собрана, а ссылки на неё в подвале нет")

        # 4. оба пути: обе темы на одной странице, разделы не задваиваются
        inst, r, html = build(tmp, "both", metrika=True, contacts=True)
        check(r.returncode == 0, f"база с обоими путями не собралась: {r.stderr[-300:]}")
        check("Яндекс.Метрика" in (html or "") and "номер телефона" in (html or ""),
              "на общей странице потерялся один из путей")
        check((html or "").count("<h2>Цели обработки</h2>") == 1, "раздел целей задвоился")
        check((html or "").count("<h2>Оператор и реквизиты</h2>") == 1,
              "раздел реквизитов задвоился")
        check("Используя сайт или обращаясь к Оператору" in (html or ""),
              "вводный абзац не собрал оба основания")
        #     союз именно «или»: согласие возникает от любого из двух действий, а «и» читалось бы
        #     как требование совершить оба сразу (Codex r2)
        check("Используя сайт и обращаясь" not in (html or ""),
              "вводный абзац требует совершить оба действия сразу")
        index = (inst / "site" / "index.html").read_text(encoding="utf-8")
        check("/policy/" in index, "политика собрана, а ссылки на неё в подвале нет")

        # 5. пустой раздел не печатается заголовком: обещание без текста хуже молчания
        _, _, html = build(tmp, "nocookies", metrika=False, contacts=True)
        check("<h2>Файлы cookie и Яндекс.Метрика</h2>" not in (html or ""),
              "печатается заголовок раздела, под которым ничего нет")

        # 6. канал сбора НЕ угадывается: у почтового сбора нет ни мессенджеров, ни телефона,
        #    ни «в той же переписке». Ровно тот дефект, который поймал Codex.
        _, r, html = build(tmp, "email-channel", metrika=False, contacts=True, cc=BY_EMAIL)
        check(r.returncode == 0, f"почтовый канал не собрался: {r.stderr[-300:]}")
        for word in ("мессендж", "переписк", "номер телефона", "нажатием кнопки"):
            check(word not in (html or "").lower(),
                  f"политика угадала канал сбора: в тексте {word!r}, а собирают по почте")
        check("адрес электронной почты" in (html or ""),
              "настоящий состав данных не попал на страницу")

        # 7. processors не названы: абсолютного обещания о непередаче быть не должно
        _, r, html = build(tmp, "noproc", metrika=False, contacts=True, cc=BY_EMAIL)
        check(r.returncode == 0, f"сценарий без processors не собрался: {r.stderr[-300:]}")
        check(html is not None, "сценарий без processors не дал страницы, отрицания проверять не на чем")
        check("не передаёт" not in (html or ""),
              "страница отрицает передачу данных, хотя обработчики не объявлены")
        check("государственным органам" in (html or ""),
              "раздел о передаче потерял оговорку про госорганы")
        #     а когда названы, отрицание сужено до «иных, кроме названных выше»: список
        #     обработчиков не объявляет себя исчерпывающим по всей вселенной получателей
        _, _, html = build(tmp, "withproc", metrika=False, contacts=True)
        check("Иным третьим лицам, кроме названных выше" in (html or ""),
              "при названных обработчиках пропало ограничение круга получателей")
        check("Другим третьим лицам Оператор данные не передаёт" not in (html or ""),
              "вернулось безусловное отрицание передачи данных")

        # 8. сбор объявлен, а реквизитов оператора нет: отказ ДО записи чего бы то ни было
        inst = instance(tmp, "nolegal")
        registry(inst, lambda reg: reg["site"].update(contacts_collection=dict(CONTACTS)))
        before = tree(inst / "site")
        r = run(inst, "build.py")
        check(r.returncode != 0, "сборка приняла сбор контактов без site.legal")
        check("contacts_collection" in (r.stdout + r.stderr),
              "отказ не назвал contacts_collection причиной")
        check(tree(inst / "site") == before, "сборка успела записать site/ до отказа")

        #     тот же отказ для счётчика без реквизитов: старая ветка не должна пострадать
        inst = instance(tmp, "nolegal-metrika")
        registry(inst, lambda reg: reg["site"].update(analytics={"yandex_metrika": "12345678"}))
        r = run(inst, "build.py")
        check(r.returncode != 0, "сборка приняла счётчик без site.legal")
        check("analytics counter" in (r.stdout + r.stderr),
              "отказ по счётчику перестал называть счётчик")

        # 9. кривой блок: каждая форма ошибки ловится своим внятным отказом
        for name, bad, expect in [
            ("notdict", "да", "expected an object"),
            ("nopurpose", {"where": "в Telegram", "data": "телефон"}, "incomplete"),
            ("emptydata", {"where": "в Telegram", "data": "  ", "purpose": "связаться"}, "incomplete"),
            ("proclist", dict(CONTACTS, processors="Telegram"), "expected a list"),
            ("procdict", dict(CONTACTS, processors=[{"name": "Telegram"}]), "expected names as strings"),
            ("procnum", dict(CONTACTS, processors=["Telegram", 42]), "expected names as strings"),
            ("nested", dict(CONTACTS, where={"a": 1}), "expected a string"),
            ("boolfield", dict(CONTACTS, purpose=True), "expected a string"),
            ("numfield", dict(CONTACTS, data=123), "expected a string"),
            ("typo", dict(BY_EMAIL, processor="Telegram"), "unknown keys"),
        ]:
            _, r, html = build(tmp, f"bad-{name}", metrika=False, contacts=True, cc=bad)
            check(r.returncode != 0, f"сборка приняла кривой contacts_collection ({name})")
            check(expect in (r.stdout + r.stderr), f"отказ на {name} не объяснил причину")
            check(html is None, f"страница записалась при кривом блоке ({name})")

        # 9a. чужой счётчик в site.analytics: движок его не ставит, а страница утверждает,
        #     что счётчиков нет вовсе. Молча принять такой ключ значит опубликовать неправду.
        inst = instance(tmp, "alien-counter")
        registry(inst, lambda reg: reg["site"].update(
            legal=dict(LEGAL), analytics={"google_analytics": "G-XXXX"}))
        r = run(inst, "build.py")
        check(r.returncode != 0, "сборка приняла неизвестный счётчик в site.analytics")
        check("unknown keys" in (r.stdout + r.stderr), "отказ не назвал неизвестный ключ")
        check(tree(inst / "site") == set(), "сборка успела записать site/ до отказа по счётчику")

        # 9b. пустое имя обработчика: список тихо схлопывался, а с ним пропадал целый абзац
        _, r, html = build(tmp, "blank-proc", metrika=False, contacts=True,
                           cc=dict(BY_EMAIL, processors=["   "]))
        check(r.returncode != 0, "сборка приняла пустое имя в processors")
        check("empty name" in (r.stdout + r.stderr), "отказ на пустое имя не объяснил причину")
        check(html is None, "страница записалась при пустом имени обработчика")

        # 9c. срок хранения не выдумывается: без retention страница называет законный предел,
        #     а не операционную практику, которой владелец не описывал
        _, _, html = build(tmp, "noretention", metrika=False, contacts=True, cc=BY_EMAIL)
        check("до достижения цели обработки" in (html or ""),
              "срок хранения по умолчанию перестал ссылаться на цель обработки")
        _, _, html = build(tmp, "retention", metrika=False, contacts=True,
                           cc=dict(BY_EMAIL, retention="Данные хранятся 6 месяцев."))
        check("Данные хранятся 6 месяцев." in (html or ""),
              "явно заданный срок хранения не дошёл до страницы")
        check("до достижения цели обработки" not in (html or ""),
              "рядом с заданным сроком напечатан ещё и дефолтный")

        # 10. длинное тире в тексте владельца: правило «без тире» держится и на этих полях,
        #     текст ложится на публичную страницу дословно
        _, r, _ = build(tmp, "dash", metrika=False, contacts=True,
                        cc=dict(CONTACTS, purpose="Связаться с вами — и передать материалы."))
        check(r.returncode != 0, "длинное тире прошло в текст политики")
        check("contacts_collection.purpose" in (r.stdout + r.stderr),
              "отказ по тире не назвал поле")

        # 11. готовая страница целиком свободна от длинных тире во всех комбинациях
        for name, m, c in (("d-m", True, False), ("d-c", False, True), ("d-b", True, True)):
            _, _, html = build(tmp, f"dashscan-{name}", metrika=m, contacts=c)
            found = [ch for ch in ("—", "–") if ch in (html or "")]
            check(not found, f"на готовой странице ({name}) длинные тире: {found}")

        # 11a. формулировки, за которые конфиг не отвечает, не должны вернуться ни в одной
        #      комбинации: «обезличенные» это результат отдельной процедуры, статус обработчика
        #      «по поручению» доказывается договором, а не строкой в конфиге, и срок уничтожения
        #      по 152-ФЗ не равен обещанным когда-то 10 рабочим дням (Codex, раунды 1 и 3)
        for name, m, c in (("c-m", True, False), ("c-c", False, True), ("c-b", True, True)):
            _, _, html = build(tmp, f"claims-{name}", metrika=m, contacts=c)
            low = (html or "").lower()
            for word in ("обезличен", "по поручению", "10 рабочих дней", "в его интересах"):
                check(word not in low, f"вернулось неподтверждённое утверждение ({name}): {word!r}")

        # 11b. вводный абзац это два предложения, и второе обязано начинаться с заглавной.
        #      На пути contacts-only оно начинается с деепричастия, поэтому дефект был виден
        #      ровно в одной комбинации из трёх и жил на живом домене.
        for name, m, c in (("l-m", True, False), ("l-c", False, True), ("l-b", True, True)):
            _, _, html = build(tmp, f"lead-{name}", metrika=m, contacts=c)
            lead = re.search(r'<p class="lead">(.*?)</p>', html or "", re.S)
            check(lead is not None, f"вводный абзац не найден ({name})")
            tail = (lead.group(1).split(". ", 1)[1] if lead and ". " in lead.group(1) else "")
            check(tail[:1].isupper(),
                  f"второе предложение вводного абзаца со строчной буквы ({name}): {tail[:40]!r}")

        # 12. сбор выключили после сборки: страница удаляется, старый URL перестаёт отвечать
        inst, r, html = build(tmp, "orphan", metrika=False, contacts=True)
        check(html is not None, "подготовка сценария сироты не собрала политику")
        registry(inst, lambda reg: reg["site"].pop("contacts_collection", None))
        r = run(inst, "build.py")
        check(r.returncode == 0, f"пересборка без сбора контактов упала: {r.stderr[-300:]}")
        check(not (inst / "site" / "policy").exists(),
              "политика осталась на диске после отключения сбора (rsync --delete её опубликует)")

        # 13. мутационный контроль А: без второго пути в policy_required страница не появится.
        #     Успешный выход проверяется отдельно: мутант, упавший по любой причине, тоже не
        #     оставил бы файла, и контроль оказался бы зелёным ни за что (Codex).
        mut = instance(tmp, "mutant-create")
        src = (mut / "build.py").read_text(encoding="utf-8")
        killed = src.replace("return bool(metrika_id(site)) or contacts_cfg(site) is not None",
                             "return bool(metrika_id(site))", 1)
        check(killed != src, "мутация не применилась: policy_required выглядит иначе")
        (mut / "build.py").write_text(killed, encoding="utf-8")
        registry(mut, lambda reg: reg["site"].update(legal=dict(LEGAL),
                                                     contacts_collection=dict(CONTACTS)))
        r = run(mut, "build.py")
        check(r.returncode == 0, f"мутант упал вместо тихой пропажи страницы: {r.stderr[-200:]}")
        check(not (mut / "site" / "policy").exists(),
              "мутант всё равно собрал политику — проверка 3 ничего не доказывает")

        # 14. мутационный контроль Б: без ветки удаления сирота переживает выключение пути.
        #     Проверка 12 иначе зелёная просто потому, что страницу никто не создавал заново.
        mut = instance(tmp, "mutant-prune")
        src = (mut / "build.py").read_text(encoding="utf-8")
        killed = src.replace("        shutil.rmtree(policy_dir)",
                             "        pass  # мутация: сироту не убираем", 1)
        check(killed != src, "мутация не применилась: ветка удаления выглядит иначе")
        (mut / "build.py").write_text(killed, encoding="utf-8")
        registry(mut, lambda reg: reg["site"].update(legal=dict(LEGAL),
                                                     contacts_collection=dict(CONTACTS)))
        r = run(mut, "build.py")
        check(r.returncode == 0, f"мутант не собрался: {r.stderr[-200:]}")
        registry(mut, lambda reg: reg["site"].pop("contacts_collection", None))
        r = run(mut, "build.py")
        check(r.returncode == 0, f"пересборка мутанта упала: {r.stderr[-200:]}")
        check((mut / "site" / "policy").exists(),
              "мутант тоже убрал сироту — проверка 12 ничего не доказывает")

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
