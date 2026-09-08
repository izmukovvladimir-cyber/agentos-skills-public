#!/usr/bin/env python3
"""ПОСТ-SHIP ГЕЙТ: третье касание ветки B обязано вести на СТАТЬЮ, а не в финал.

Зачем. В форме fundament билдер жёстко ставит на `fund_b_texts[2]` кнопку финала (у клиента это
кнопка продукта на finish_url). Правило: ветка «не открыл» добивает ТОЛЬКО на статью. Значит после
каждой сборки кнопку надо перевешивать, а ручная память защитой не является. Этот гейт читает ЖИВОЙ
кабинет и падает, если дефект вернулся.

Три условия, без которых гейт сам стал бы ложным нулём:
1. ЗНАМЕНАТЕЛЬ ИЗ СПИСКА. Проверяем ровно те воронки, что перечислены в FUNNELS, а не те, что
   «нашлись» в кабинете. Не нашли воронку из списка — падаем.
2. НЕНАЙДЕННЫЙ УЗЕЛ ЭТО ПАДЕНИЕ. Нет сообщения ветки B с ожидаемым текстом или нет кнопки на нём —
   падаем, а не «пропускаем».
3. НЕГАТИВНЫЙ ТЕСТ ВНУТРИ. Перед проверкой живого прогоняем сам детектор на подсунутом узле с
   finish_url и убеждаемся, что он его ловит. Детектор, который ничего не ловит, бесполезен.

Запуск (сначала заполни блок «ПРАВИТЬ ТОЛЬКО ЭТОТ БЛОК» ниже):
    export CHATPLACE_API_KEY="<ключ кабинета ChatPlace>"   # либо CHATPLACE_KEY_FILE с путём к файлу ключа
    python3 tools/check_b3_button.py            # проверить
    python3 tools/check_b3_button.py --fix      # проверить и перевесить кнопку на статью

Обкатан на живом клиентском кабинете: на четырёх воронках поймал два свежих дефекта сразу после
сборки.

Код возврата: 0 всё чисто, 1 дефект найден (или не найден узел, или сорвался негативный тест).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# ─────────────────────────── ПРАВИТЬ ТОЛЬКО ЭТОТ БЛОК ───────────────────────────
# SPEC_DIR: папка со спеками воронок ТВОЕГО клиента (там же, откуда ты запускаешь ship).
SPEC_DIR = Path("~/.claude/assets/kb").expanduser()

# TG_BOT: uuid телеграм-бота клиента (bots_list покажет).
TG_BOT = "<uuid-телеграм-бота-клиента>"

# FUNNELS: знаменатель проверки. Кодворд как в имени автоматики плюс файл спеки в SPEC_DIR.
# Добавил воронку — добавь строку здесь, иначе она в проверку НЕ ПОПАДЁТ.
FUNNELS: list[tuple[str, str]] = [
    ("ПОЗИТИВ", ".funnel-spec-pozitiv.json"),
]

# FINISH_BOT_MARKER: кусок финальной ссылки клиента (ник бота или домен продукта), по которому
# детектор узнаёт кнопку финала. Заполняется под конкретный кабинет.
FINISH_BOT_MARKER = "<ник-финального-бота>"

# Ключ кабинета берётся из окружения, как у билдера:
#   export CHATPLACE_API_KEY="<ключ кабинета ChatPlace>"
#   (или CHATPLACE_KEY_FILE с путём к файлу, где лежит ключ)
# ────────────────────────── КОНЕЦ ПРАВИМОГО БЛОКА ──────────────────────────────

KB = SPEC_DIR
ARTICLE_TAG = "открыл-статью-v2"
READ_BUTTON = "📖 Читать статью"


@dataclass
class Defect:
    codeword: str
    message_id: str
    button_id: str
    url: str
    reason: str


sys.path.insert(0, str(Path("~/bin").expanduser()))
import cp_funnel_builder as cfb  # noqa: E402  (тот же клиент кабинета, что у билдера)

_CP = cfb.CpClient()


def mcp(tool: str, args: dict):
    """Вызов инструмента ChatPlace клиентом билдера: та же авторизация, те же ретраи на 5xx."""
    return _CP.call(tool, args)


def b3_text(spec_file: str) -> str:
    """Первые слова третьего касания ветки B: по ним ищем узел в кабинете.

    Ищем по НАЧАЛУ текста намеренно: вывод чтения обрезается, а неразрывные пробелы внутри фразы
    ломают поиск по середине (обе граблю поймали 05.08)."""
    spec = json.loads((KB / spec_file).read_text(encoding="utf-8"))
    body = spec["fund_b_texts"][2]
    plain = body.replace("<p>", "").replace("</p>", " ").replace("<b>", "").replace("</b>", "")
    return " ".join(plain.split())[:40]


def is_defect(button: dict, finish_url: str) -> bool:
    """Сам детектор. Отдельной функцией, чтобы его можно было прогнать негативным тестом."""
    url = button.get("url") or ""
    return url.startswith(finish_url.split("?")[0]) or FINISH_BOT_MARKER in url


def self_test() -> None:
    """Условие 3: детектор обязан ловить подсунутый финальный url."""
    finish_url = f"https://t.me/{FINISH_BOT_MARKER}?start=stat_bot-test"
    fake_finish = {"url": finish_url}
    fake_article = {"url": "https://your-domain.ru/article/?from=bot-test"}
    if not is_defect(fake_finish, finish_url):
        raise SystemExit("НЕГАТИВНЫЙ ТЕСТ ПРОВАЛЕН: детектор не поймал финальный url, гейт слепой")
    if is_defect(fake_article, finish_url):
        raise SystemExit("НЕГАТИВНЫЙ ТЕСТ ПРОВАЛЕН: детектор считает дефектом ссылку на статью")
    print("негативный тест детектора: ОК")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="перевесить найденные кнопки на статью")
    args = ap.parse_args()

    self_test()

    automations = mcp("automations_list", {"botId": TG_BOT})
    items = automations if isinstance(automations, list) else (automations.get("data") or automations.get("result"))
    # НЕ складываем в dict по имени: у ретайренных копий имя ТО ЖЕ САМОЕ, и словарь оставил бы
    # только последнюю (у меня на этом гейт сказал «активных 0» при живой воронке). Идём списком.

    defects: list[Defect] = []
    checked = 0
    for codeword, spec_file in FUNNELS:
        spec = json.loads((KB / spec_file).read_text(encoding="utf-8"))
        live = [a for a in items
                if (a.get("name") or "").startswith(f"{codeword} AUTO") and a.get("statusName") == "Active"]
        if len(live) != 1:
            raise SystemExit(f"{codeword}: активных воронок {len(live)}, ожидалась ровно одна (знаменатель нарушен)")
        detail = mcp("automations_get_detail", {"automationId": live[0]["id"]})
        needle = b3_text(spec_file)
        nodes = [m for s in detail.get("steps", []) for m in s.get("messages", [])]
        target = [m for m in nodes if needle and needle in " ".join((m.get("text") or "").replace("<p>", "").replace("</p>", " ").replace("<b>", "").replace("</b>", "").split())]
        if not target:
            raise SystemExit(f"{codeword}: узел третьего касания ветки B не найден по началу текста "
                             f"{needle!r}. Это падение, а не пропуск: либо текст спеки разошёлся с живым, "
                             f"либо воронка собрана иначе")
        node = target[0]
        buttons = node.get("inlineButtons") or []
        if not buttons:
            raise SystemExit(f"{codeword}: на узле {node['id']} нет ни одной кнопки, проверять нечего "
                             f"(падение по условию 2)")
        checked += 1
        for b in buttons:
            if is_defect(b, spec["finish_url"]):
                defects.append(Defect(codeword, node["id"], b["id"], b.get("url") or "", "кнопка ведёт в финал"))

    print(f"проверено воронок: {checked} из {len(FUNNELS)}")
    if not defects:
        print("ГЕЙТ ЧИСТ: у всех третье касание ветки B ведёт на статью")
        return 0

    for d in defects:
        print(f"ДЕФЕКТ {d.codeword}: узел {d.message_id}, кнопка {d.button_id} -> {d.url}")
    if not args.fix:
        print("запусти с --fix, чтобы перевесить кнопки на статью")
        return 1

    tag_list = mcp("tags_list", {})
    tags = tag_list if isinstance(tag_list, list) else (tag_list.get("data") or tag_list.get("result"))
    tag_id = next((t["id"] for t in tags if t.get("name") == ARTICLE_TAG), None)
    if not tag_id:
        raise SystemExit(f"тег {ARTICLE_TAG} не найден в кабинете, перевешивать нельзя")

    for d in defects:
        spec = json.loads((KB / dict(FUNNELS)[d.codeword]).read_text(encoding="utf-8"))
        article = spec["article_url"]
        mcp("automations_inline_buttons_setup", {"buttonId": d.button_id, "subtype": "url", "url": article,
                                                 "trackClicks": True, "tagIds": [tag_id]})
        mcp("automations_inline_buttons_update", {"buttonId": d.button_id, "text": READ_BUTTON, "url": article})
        print(f"перевешено {d.codeword}: {d.button_id} -> {article}")
    print("повторный прогон обязателен: python3 assets/kb/check_b3_button.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
