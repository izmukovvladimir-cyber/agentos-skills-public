#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты предупреждения о неподключённом шрифте (font_warnings в build.py).

    python3 scripts/test_font_warnings.py

Сеть и клиентские данные не нужны. Проверка нужна потому, что молчащая подмена
шрифта не видна ни в Chromium, ни на снимках Playwright: на iPhone она ломала
набор чисел в .story-sum (пробелы склеивались, запятая уезжала к соседнему
слову), и нашёл это заказчик на своём телефоне, а не наши проверки.

Запуск build.py целиком тут не нужен: проверяем саму функцию, поэтому тесты
не зависят от content.py конкретного лендинга.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import time
import types

HERE = pathlib.Path(__file__).resolve().parent

GOOGLE_LINK = (
    "<link href='https://fonts.googleapis.com/css2?"
    "family=Playfair+Display:wght@400;500&family=Manrope:wght@300;400;500;600"
    "&display=swap' rel='stylesheet'>"
)


class _AnyContent(types.ModuleType):
    """Заглушка content.py: отдаёт что угодно на любой запрос атрибута.

    build.py импортирует `content` на уровне модуля, поэтому без заглушки тест
    падал бы на ImportError ещё до первой проверки — и, что хуже, «красный»
    прогон выглядел бы как сработавший мутационный контроль, ничего не проверив.
    Сами тексты лендинга тут не нужны: проверяется только font_warnings.
    """

    def __getattr__(self, name: str) -> str:  # pragma: no cover - тривиально
        return f"<{name}>"


def load_build():
    """Импортировать build.py без запуска сборки (он собирает только под __main__)."""
    sys.modules.setdefault("content", _AnyContent("content"))
    spec = importlib.util.spec_from_file_location("_build_under_test", HERE / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_build_under_test"] = module
    spec.loader.exec_module(module)
    # Если функции нет, тест обязан упасть внятно, а не «пройти» на пустом месте.
    assert hasattr(module, "font_warnings"), "в build.py нет font_warnings"
    return module


def font_face(family: str, url: str) -> str:
    return f"@font-face{{font-family:'{family}';src:url('{url}') format('woff');}}"


def run() -> int:
    build = load_build()
    warn = build.font_warnings
    failures: list[str] = []
    # Счётчик, а не число руками: ручное число один раз уже разошлось с составом
    # проверок, и тогда прогон рапортовал больше, чем исполнял.
    done = [0]

    def check(name: str, html: str, out_dir: pathlib.Path, expect_warning: bool) -> None:
        done[0] += 1
        warnings = warn(html, out_dir)
        got = len(warnings) > 0
        if got != expect_warning:
            failures.append(
                f"{name}: ожидали {'предупреждение' if expect_warning else 'тишину'}, "
                f"получили {warnings or 'тишину'}"
            )

    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp)

        # ── Молчащая подмена: то, из-за чего заявка и появилась ────────────
        check(
            "шрифт в токене без всякого подключения (живой случай: 'Onest')",
            GOOGLE_LINK + "<style>:root{--sans:'Onest',-apple-system,'Segoe UI',sans-serif}</style>",
            out,
            True,
        )
        check(
            "@font-face объявлен, а ФАЙЛА на диске нет",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva','Playfair Display',Georgia,serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff")
            + "</style>",
            out,
            True,
        )

        # ── Рабочие конфигурации: предупреждать не о чем ───────────────────
        check(
            "оба токена на шрифтах из ссылки Google Fonts",
            GOOGLE_LINK
            + "<style>:root{--serif:'Playfair Display',Georgia,serif;--sans:'Manrope',sans-serif}</style>",
            out,
            False,
        )
        check(
            "системные семейства подключения не требуют",
            "<style>:root{--sans:Georgia,serif;--serif:serif}</style>",
            out,
            False,
        )
        check(
            "системный шрифт ПЕРВЫМ: подключать нечего, предупреждать не о чем",
            GOOGLE_LINK + "<style>:root{--sans:system-ui,'Onest',sans-serif}</style>",
            out,
            False,
        )
        check(
            "запасные семейства после первого не проверяются (они и есть запас)",
            GOOGLE_LINK
            + "<style>:root{--serif:'Playfair Display','Совсем Другой Шрифт',serif}</style>",
            out,
            False,
        )

        # Файл на месте — как в собранном живом лендинге, где шрифт реально
        # отдаётся по HTTP 200. Тут проверяется, что гейт НЕ шумит на здоровой
        # сборке: ложное предупреждение обесценивает настоящее.
        (out / "fonts").mkdir(parents=True, exist_ok=True)
        (out / "fonts" / "anticva-regular.woff").write_bytes(b"wOFF-stub")
        check(
            "@font-face с СУЩЕСТВУЮЩИМ файлом (как в живом лендинге)",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva','Playfair Display',Georgia,serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff")
            + "</style>",
            out,
            False,
        )
        check(
            "регистр имени не мешает: 'ANTICVA' в токене против 'Anticva' в @font-face",
            GOOGLE_LINK
            + "<style>:root{--serif:'ANTICVA','Playfair Display',serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff")
            + "</style>",
            out,
            False,
        )

        # ── Формы записи, на которых гейт давал ЛОЖНОЕ срабатывание ────────
        # (все три поймал Codex; файл существует, страница рабочая)
        check(
            "ДВОЙНЫЕ кавычки в @font-face — тоже законный CSS",
            GOOGLE_LINK
            + '<style>:root{--serif:"Anticva",serif}'
            + '@font-face{font-family:"Anticva";src:url("fonts/anticva-regular.woff")}'
            + "</style>",
            out,
            False,
        )
        check(
            "кавычек нет вовсе — тоже законный CSS",
            GOOGLE_LINK
            + "<style>:root{--serif:Anticva,serif}"
            + "@font-face{font-family:Anticva;src:url(fonts/anticva-regular.woff)}"
            + "</style>",
            out,
            False,
        )
        check(
            "версионный '?v=1' у существующего файла: query не часть имени",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff?v=1")
            + "</style>",
            out,
            False,
        )
        check(
            "'#iefix' у существующего файла: fragment не часть имени",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff#iefix")
            + "</style>",
            out,
            False,
        )
        check(
            "шрифт с внешнего адреса грузит браузер, файла в сборке и не надо",
            "<style>:root{--serif:'Cdn Face',serif}"
            + font_face("Cdn Face", "https://cdn.example.com/f.woff")
            + "</style>",
            out,
            False,
        )
        check(
            "data: — шрифт лежит внутри самой страницы",
            "<style>:root{--serif:'Inline Face',serif}"
            + font_face("Inline Face", "data:font/woff;base64,d09G")
            + "</style>",
            out,
            False,
        )

        # ── Корневой web-URL: '/' это корень САЙТА, а не файловой системы ───
        check(
            "'/fonts/...' у существующего файла — законная запись, не жалоба",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + font_face("Anticva", "/fonts/anticva-regular.woff")
            + "</style>",
            out,
            False,
        )
        check(
            "'/fonts/...' у ОТСУТСТВУЮЩЕГО файла — жалоба по делу",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nomanflow',serif}"
            + font_face("Nomanflow", "/fonts/nomanflow.woff")
            + "</style>",
            out,
            True,
        )
        # ── Формы CSS, где регистр и пробелы законны, а гейт их не читал ────
        check(
            "верхний регистр и пробелы у двоеточий — валидный CSS, файл есть",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + "@FONT-FACE { FONT-FAMILY : 'Anticva' ; SRC : URL('fonts/anticva-regular.woff') }"
            + "</style>",
            out,
            False,
        )
        check(
            "перенос строк внутри @font-face не мешает",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + "@font-face{\n  font-family: 'Anticva';\n  src: url('fonts/anticva-regular.woff')"
            + " format('woff');\n}"
            + "</style>",
            out,
            False,
        )

        # ── Обходы, на которых гейт выдавал чужое за подключённое ───────────
        check(
            "'local(' в КОММЕНТАРИИ рядом с отсутствующим файлом — это не источник",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nomanflow',serif}"
            + "@font-face{font-family:'Nomanflow';src:url('fonts/no.woff'); /* local( */ }"
            + "</style>",
            out,
            True,
        )
        check(
            "'local(' в комментарии ВНУТРИ значения src — тоже не источник",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nomanflow',serif}"
            + "@font-face{font-family:'Nomanflow';src:url('fonts/no.woff') /* local( */ }"
            + "</style>",
            out,
            True,
        )
        check(
            "url() в СОСЕДНЕМ свойстве шрифта не подключает",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nomanflow',serif}"
            + "@font-face{font-family:'Nomanflow';src:bogus;"
            + "foo:url('fonts/anticva-regular.woff')}"
            + "</style>",
            out,
            True,
        )

        # ── Патологический CSS: гейт не должен ни падать, ни выдавать чужое ──
        check(
            "data-URI с '}' внутри строки не обрывает блок — шрифт рабочий",
            "<style>:root{--serif:'Braceface',serif}"
            + "@font-face{font-family:'Braceface';src:url('data:font/woff;base64,abc}def')}"
            + "</style>",
            out,
            False,
        )
        check(
            "экранированная кавычка в имени файла не проглатывает соседнее свойство",
            GOOGLE_LINK
            + "<style>:root{--serif:'Escface',serif}"
            + "@font-face{font-family:'Escface';src:url('fonts/mis\\'sing.woff');"
            + "foo:url('fonts/anticva-regular.woff')}"
            + "</style>",
            out,
            True,
        )
        check(
            "целиком закомментированный @font-face объявлением не является",
            GOOGLE_LINK
            + "<style>:root{--serif:'Commentface',serif}"
            + "/* @font-face{font-family:'Commentface';src:url('fonts/anticva-regular.woff')} */"
            + "</style>",
            out,
            True,
        )
        check(
            "незакрытая url( — сломанный CSS, шрифта не даёт",
            GOOGLE_LINK
            + "<style>:root{--serif:'Brokenface',serif}"
            + "@font-face{font-family:'Brokenface';src:url(https://cdn.example/x.woff}"
            + "</style>",
            out,
            True,
        )
        check(
            "незакрытая local( — тоже сломанный CSS",
            GOOGLE_LINK
            + "<style>:root{--serif:'Brokenlocal',serif}"
            + "@font-face{font-family:'Brokenlocal';src:local('X'}"
            + "</style>",
            out,
            True,
        )

        # Пробел в имени файла экранируется обратным слэшем — штатный CSS.
        (out / "fonts" / "my font.woff").write_bytes(b"wOFF-stub")
        check(
            "экранированный пробел в имени: файл есть, жаловаться не на что",
            GOOGLE_LINK
            + "<style>:root{--serif:'Spaceface',serif}"
            + "@font-face{font-family:'Spaceface';src:url(fonts/my\\ font.woff)}"
            + "</style>",
            out,
            False,
        )

        # ── Пустой и отсутствующий адрес: шрифта не будет, молчать нельзя ───
        check(
            "url('') — по синтаксису законно, шрифта не даёт",
            GOOGLE_LINK
            + "<style>:root{--serif:'Emptyface',serif}"
            + "@font-face{font-family:'Emptyface';src:url('')}"
            + "</style>",
            out,
            True,
        )
        check(
            "src без url() вовсе — тоже не даёт шрифта",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nosrc',serif}"
            + "@font-face{font-family:'Nosrc';font-weight:400}"
            + "</style>",
            out,
            True,
        )
        check(
            "список источников: woff2 нет, woff есть — шрифт будет, жаловаться не на что",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + "@font-face{font-family:'Anticva';src:url('fonts/anticva.woff2') format('woff2'),"
            + "url('fonts/anticva-regular.woff') format('woff')}"
            + "</style>",
            out,
            False,
        )
        check(
            "список источников: НИ ОДНОГО файла нет — жалоба по делу",
            GOOGLE_LINK
            + "<style>:root{--serif:'Nomanflow',serif}"
            + "@font-face{font-family:'Nomanflow';src:url('fonts/no.woff2') format('woff2'),"
            + "url('fonts/no.woff') format('woff')}"
            + "</style>",
            out,
            True,
        )
        check(
            "src: local('X') — законно, шрифт берётся у читателя",
            GOOGLE_LINK
            + "<style>:root{--serif:'Localface',serif}"
            + "@font-face{font-family:'Localface';src:local('Localface')}"
            + "</style>",
            out,
            False,
        )

        # ── Абсолютный путь: файл ЕСТЬ у сборщика, но в раздачу не попадёт ──
        # Ровно тот случай, где pathlib отдавал сам абсолютный путь и проверка
        # уходила на чужой файл, а гейт молчал.
        abs_font = out / "fonts" / "anticva-regular.woff"
        check(
            "абсолютный путь к существующему файлу сборщика = в сборке шрифта нет",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + font_face("Anticva", str(abs_font))
            + "</style>",
            out,
            True,
        )
        check(
            "file:// к существующему файлу сборщика = в сборке шрифта нет",
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva',serif}"
            + font_face("Anticva", f"file://{abs_font}")
            + "</style>",
            out,
            True,
        )

    # Выход за пределы сборки. Файл НАРОЧНО создаётся снаружи out_dir: без
    # проверки границы он нашёлся бы и гейт промолчал, а в раздачу такой файл
    # не попадает. Внутри общего tmp, чтобы каталог сборки был вложенным.
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        out = root / "out"
        (out / "fonts").mkdir(parents=True, exist_ok=True)
        (root / "fonts").mkdir(parents=True, exist_ok=True)
        (root / "fonts" / "outside.woff").write_bytes(b"wOFF-stub")
        check(
            "'..' уводит за пределы сборки: файл снаружи не считается подключённым",
            GOOGLE_LINK
            + "<style>:root{--serif:'Outside',serif}"
            + font_face("Outside", "../fonts/outside.woff")
            + "</style>",
            out,
            True,
        )

    # Предупреждение не должно печатать абсолютный путь: в логе сборки это
    # раскрывало бы имя пользователя и проекта. Источников пути ДВА: каталог
    # сборки и сам URL внутри CSS. Второй Codex поймал отдельно.
    with tempfile.TemporaryDirectory() as tmp:
        secret_dir = pathlib.Path(tmp) / "home-of-someone" / "out"
        secret_dir.mkdir(parents=True, exist_ok=True)
        msgs = warn(
            GOOGLE_LINK
            + "<style>:root{--serif:'Anticva','Playfair Display',serif}"
            + font_face("Anticva", "fonts/anticva-regular.woff")
            + "</style>",
            secret_dir,
        )
        done[0] += 1
        if not msgs:
            failures.append("путь: ожидали предупреждение об отсутствующем файле, получили тишину")
        elif any(str(secret_dir) in m or "home-of-someone" in m for m in msgs):
            failures.append(f"путь: абсолютный каталог утёк в предупреждение: {msgs}")

        # expect_name=False там, где имени файла в адресе нет по определению: тогда
        # проверяется только отсутствие утечки, а имя требовать неоткуда.
        for label, url, expect_name in (
            ("абсолютный путь", "/someone-else/private/font-regular.woff", True),
            ("file://", "file:///someone-else/private/font-regular.woff", True),
            # Обратные слэши: путь с машины Windows тоже не должен утечь в лог.
            ("windows-путь", "C:\\Users\\of-someone\\private\\anticva-regular.woff", True),
            # Адрес без имени файла: подставлять вместо него последний каталог нельзя.
            ("каталог без файла", "/someone-else/private/", False),
        ):
            msgs = warn(
                GOOGLE_LINK
                + "<style>:root{--serif:'Anticva',serif}"
                + font_face("Anticva", url)
                + "</style>",
                secret_dir,
            )
            done[0] += 1
            if not msgs:
                failures.append(f"путь в CSS ({label}): ожидали предупреждение, получили тишину")
            elif any("of-someone" in m or "private" in m for m in msgs):
                failures.append(f"путь в CSS ({label}): каталог утёк в предупреждение: {msgs}")
            elif expect_name and not any("anticva-regular.woff" in m for m in msgs):
                failures.append(f"путь в CSS ({label}): в тексте нет имени файла: {msgs}")

    # Время на повреждённом входе. Проверка не про скорость как таковую, а про
    # КВАДРАТИЧНОСТЬ: пока следующее объявление src искалось от начала блока, 2000
    # повторов «src:(;» считались 23 секунды, то есть гейт подвешивал сборку на кривом
    # CSS. Порог щедрый нарочно, чтобы тест не краснел от загрузки машины: линейный
    # проход укладывается в доли секунды, квадратичный не уложится и в минуту.
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp)
        evil = "<style>:root{--serif:'Evilface',serif}@font-face{font-family:'Evilface';" + "src:(;" * 4000 + "}</style>"
        started = time.monotonic()
        warn(evil, out)
        spent = time.monotonic() - started
        done[0] += 1
        if spent > 5.0:
            failures.append(
                f"время: 4000 повторов «src:(;» обработаны за {spent:.1f} c, "
                "похоже на квадратичный проход"
            )

    total = done[0]
    if failures:
        print(f"ПРОВАЛОВ {len(failures)} из {total}:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {total} проверок пройдено")
    return 0


if __name__ == "__main__":
    sys.exit(run())
