#!/usr/bin/env python3
"""Тесты гейта дизайн-токенов carousel_lib: выбор блока, граница воркспейса, область гейта.

Сеть и Chrome не нужны, рендер не вызывается. Запуск:
    python3 ~/.claude/skills/carousel-reskinner/scripts/test_carousel_lib_brand.py

У КАЖДОЙ защиты есть мутационный контроль: тест обязан ПОКРАСНЕТЬ, если защиту снять.
Зелёный тест без такого контроля не доказывает, что он вообще исполняет проверяемый код.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import types

LIB = pathlib.Path(__file__).with_name("carousel_lib.py")
SRC = LIB.read_text(encoding="utf-8")

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="carousel-brand-test-"))


# --- инфраструктура ------------------------------------------------------


def load(name: str, *subs: tuple[str, str]) -> types.ModuleType:
    """Модуль из исходника, при желании с текстовыми мутациями.

    Мутация, не нашедшая цель, ПАДАЕТ: иначе негативный контроль молча перестаёт
    кусаться, когда код рядом переписали.
    """
    s = SRC
    for old, new in subs:
        assert old in s, f"мутация не нашла цель: {old[:60]!r}"
        s2 = s.replace(old, new, 1)
        assert s2 != s, f"мутация ничего не изменила: {old[:60]!r}"
        s = s2
    mod = types.ModuleType(name)
    mod.__file__ = str(LIB)
    exec(compile(s, str(LIB), "exec"), mod.__dict__)
    return mod


def ws(tokens_blocks: list[str], sub: str = "", name: str | None = None) -> pathlib.Path:
    """Воркспейс с .claude/design.md из готовых текстов блоков. Возвращает корень."""
    root = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix=(name or "ws") + "-"))
    (root / ".claude").mkdir()
    if sub:
        (root / sub).mkdir(parents=True)
    body = "# Дизайн-система\n\nТекст для человека.\n\n" + "\n\n".join(tokens_blocks) + "\n"
    (root / ".claude" / "design.md").write_text(body, encoding="utf-8")
    return root


def fence(obj: dict, lang: str = "json") -> str:
    return f"```{lang}\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


def toks(bg: str = "#0d0d0d", extra: dict | None = None, surfaces: dict | None = None) -> dict:
    d: dict = {
        "surfaces": surfaces if surfaces is not None
        else {"main": {"bg": bg, "text": "#ffffff", "accent": "#c8ff00"}},
        "type_scale": {"h2": 62, "body": 37},
        "canvas": {"footer_bottom": 64},
    }
    if extra:
        d.update(extra)
    return d


def raises(fn, kinds=Exception) -> Exception:
    try:
        fn()
    except kinds as e:
        return e
    raise AssertionError("ожидался отказ, его не было")


def no_raise(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — тест сам решает, что это провал
        raise AssertionError(f"неожиданный отказ: {type(e).__name__}: {e}") from None


# --- случаи -------------------------------------------------------------


def case_01_example_block_does_not_win(cl):
    """Пример для человека выше настоящих токенов НЕ становится палитрой молча."""
    example = toks(bg="#EXAMPLE")
    real = toks(bg="#0d0d0d")
    p = ws([fence(example), fence(real)]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("main", p), ValueError)
    assert "несколько" in str(e), f"причина отказа не про неоднозначность: {e}"
    assert cl.brand.__module__ or True


def case_02_jsonc_example_is_ignored(cl):
    """Пример, помеченный другим языком блока, не мешает: берутся настоящие токены."""
    p = ws([fence(toks(bg="#EXAMPLE"), lang="jsonc"), fence(toks(bg="#0d0d0d"))]) / ".claude" / "design.md"
    assert no_raise(lambda: cl.surface("main", p))["bg"] == "#0d0d0d"


def case_03_block_without_surfaces_is_skipped(cl):
    """Блок json без surfaces (например список шрифтов) не путается с токенами."""
    p = ws([fence({"fonts": ["Onest"]}), fence(toks(bg="#111111"))]) / ".claude" / "design.md"
    assert no_raise(lambda: cl.surface("main", p))["bg"] == "#111111"


def case_04_broken_json_next_to_valid(cl):
    """Битый блок рядом с валидным: берётся валидный, а не отказ на первом."""
    p = ws(["```json\n{ сломано\n```", fence(toks(bg="#222222"))]) / ".claude" / "design.md"
    assert no_raise(lambda: cl.surface("main", p))["bg"] == "#222222"


def case_05_all_blocks_broken_names_line(cl):
    """Все блоки битые: отказ называет строку и причину, а не молчит."""
    p = ws(["```json\n{ сломано\n```"]) / ".claude" / "design.md"
    e = raises(lambda: cl.brand(p), ValueError)
    assert "строка" in str(e), f"в отказе нет номера строки: {e}"


def case_06_no_block_at_all(cl):
    """design.md без блока токенов: внятный отказ."""
    root = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix="noblock-"))
    (root / ".claude").mkdir()
    (root / ".claude" / "design.md").write_text("# только текст\n", encoding="utf-8")
    raises(lambda: cl.brand(root / ".claude" / "design.md"), ValueError)


def case_07_placeholder_in_shared_block_blocks_build(cl):
    """Заглушка в ОБЩЕМ блоке (кегли) валит сборку: их использует любая поверхность."""
    t = toks()
    t["type_scale"]["h2"] = "TODO_H2"
    p = ws([fence(t)]) / ".claude" / "design.md"
    e = raises(lambda: cl.brand(p), ValueError)
    assert "type_scale.h2" in str(e), f"путь заглушки не назван: {e}"


def case_08_placeholder_in_used_surface_blocks_build(cl):
    """Заглушка в ИСПОЛЬЗУЕМОЙ поверхности валит сборку."""
    p = ws([fence(toks(surfaces={
        "main": {"bg": "TODO_BRAND_BG", "text": "#fff", "accent": "#c8ff00"},
    }))]) / ".claude" / "design.md"
    e = raises(lambda: cl.brand_css("main", p), ValueError)
    assert "bg" in str(e), f"путь заглушки не назван: {e}"


def case_09_placeholder_in_unused_surface_does_not_block(cl):
    """ГЛАВНОЕ: заглушка в поверхности, которой сборка не рисует, НЕ мешает."""
    p = ws([fence(toks(surfaces={
        "main": {"bg": "#0d0d0d", "text": "#ffffff", "accent": "#c8ff00"},
        "alt": {"bg": "TODO_BRAND_ALT_BG", "text": "#000000", "accent": "#000000"},
    }))]) / ".claude" / "design.md"
    css = no_raise(lambda: cl.brand_css("main", p))
    assert "#0d0d0d" in css, "палитра использованной поверхности не попала в css"
    raises(lambda: cl.surface("alt", p), ValueError)   # а её саму по-прежнему не даёт взять


def case_10_walk_stops_at_workspace_root(cl):
    """Подъём вверх не выходит за корень воркспейса: чужой design.md не берётся."""
    parent = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix="parent-"))
    (parent / ".claude").mkdir()
    (parent / ".claude" / "design.md").write_text(
        "```json\n" + json.dumps(toks(bg="#CHUJOY")) + "\n```\n", encoding="utf-8")
    client = parent / "client-x"
    (client / ".claude").mkdir(parents=True)          # корень воркспейса БЕЗ design.md
    work = client / "reels" / "scripts"
    work.mkdir(parents=True)
    old = os.getcwd()
    try:
        os.chdir(work)
        e = raises(cl._find_design_md, FileNotFoundError)
        assert "воркспейс" in str(e), f"отказ не про воркспейс: {e}"
        assert "CHUJOY" not in str(e)
    finally:
        os.chdir(old)


def case_11_own_workspace_design_is_found(cl):
    """Свой design.md из подкаталога сборки находится (ложного отказа нет)."""
    root = ws([fence(toks(bg="#333333"))], sub="reels/scripts")
    old = os.getcwd()
    try:
        os.chdir(root / "reels" / "scripts")
        assert cl._find_design_md() == root / ".claude" / "design.md"
        assert cl.surface("main")["bg"] == "#333333"
    finally:
        os.chdir(old)


def case_12_design_md_env_wins(cl):
    """DESIGN_MD побеждает подъём по каталогам."""
    a = ws([fence(toks(bg="#AAAAAA"))], sub="deep")
    b = ws([fence(toks(bg="#BBBBBB"))])
    old, oldenv = os.getcwd(), os.environ.get("DESIGN_MD")
    try:
        os.chdir(a / "deep")
        os.environ["DESIGN_MD"] = str(b / ".claude" / "design.md")
        assert cl.surface("main")["bg"] == "#BBBBBB"
    finally:
        os.chdir(old)
        if oldenv is None:
            os.environ.pop("DESIGN_MD", None)
        else:
            os.environ["DESIGN_MD"] = oldenv


def case_13_missing_required_surface_keys(cl):
    """Поверхность без bg/text/accent: внятный отказ вместо голого KeyError."""
    p = ws([fence(toks(surfaces={"main": {"bg": "#111111"}}))]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("main", p), ValueError)
    assert "text" in str(e) and "accent" in str(e), f"не названы недостающие ключи: {e}"


def case_14_unknown_surface_lists_available(cl):
    """Неизвестная поверхность: отказ перечисляет доступные."""
    p = ws([fence(toks())]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("lime", p), KeyError)
    assert "main" in str(e), f"доступные не перечислены: {e}"


def case_15_edit_of_design_md_is_seen(cl):
    """Правка design.md видна в том же процессе: кеш ключуется по mtime."""
    p = ws([fence(toks(bg="#111111"))]) / ".claude" / "design.md"
    assert cl.surface("main", p)["bg"] == "#111111"
    st = p.stat()
    p.write_text("```json\n" + json.dumps(toks(bg="#999999")) + "\n```\n", encoding="utf-8")
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert cl.surface("main", p)["bg"] == "#999999", "кеш отдал устаревшие токены"


def case_16_live_design_md_no_false_refusal(cl):
    """Живые design.md команды собираются: ложных отказов правка не даёт."""
    live = sorted(pathlib.Path("~/.claude/").glob("*/.claude/design.md"))
    if not live:
        return
    ok = 0
    for p in live:
        try:
            b = cl.brand(p)
        except Exception:      # noqa: BLE001 — файл без блока токенов это не наш регресс
            continue
        for n in sorted(b.get("surfaces", {})):
            no_raise(lambda n=n, p=p: cl.brand_css(n, p))
        ok += 1
    assert ok >= 6, f"живых собираемых design.md всего {ok}, ожидалось не меньше 6"


def case_17_cache_does_not_mix_clients(cl):
    """Кеш не путает двух клиентов: имя файла у всех одно, mtime может совпасть."""
    a = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix="cli-a-"))
    b = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix="cli-b-"))
    for d, bg in ((a, "#AAAAAA"), (b, "#BBBBBB")):
        (d / "design.md").write_text(
            "```json\n" + json.dumps(toks(bg=bg)) + "\n```\n", encoding="utf-8")
        os.utime(d / "design.md", ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    old = os.getcwd()
    try:
        os.chdir(a)
        first = cl.surface("main", "design.md")["bg"]
        os.chdir(b)
        second = cl.surface("main", "design.md")["bg"]
    finally:
        os.chdir(old)
    assert first == "#AAAAAA", f"первый клиент получил {first}"
    assert second == "#BBBBBB", f"кеш отдал второму клиенту палитру первого: {second}"


def case_18_empty_or_null_color_is_refused(cl):
    """Пустая строка, null и число это тоже незаполненный токен, просто без слова TODO_."""
    p = ws([fence(toks(surfaces={
        "main": {"bg": "", "text": None, "accent": 0},
    }))]) / ".claude" / "design.md"
    e = raises(lambda: cl.brand_css("main", p), ValueError)
    for k in ("bg", "text", "accent"):
        assert k in str(e), f"ключ {k} не назван в отказе: {e}"


def case_19_empty_surfaces_block_does_not_yield_example(cl):
    """Блок с пустым surfaces не выпадает из подсчёта: иначе пример остаётся один."""
    p = ws([fence({"surfaces": {}}), fence(toks(bg="#EXAMPLE"))]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("main", p), ValueError)
    assert "несколько" in str(e), f"неоднозначность не названа: {e}"


def case_20_crlf_file_parses(cl):
    """Файл с переводом строк Windows разбирается: иначе ложный отказ на верном файле."""
    root = pathlib.Path(tempfile.mkdtemp(dir=_TMP, prefix="crlf-"))
    (root / ".claude").mkdir()
    body = "# Дизайн\r\n\r\n```json\r\n" + json.dumps(toks(bg="#0d0d0d")) + "\r\n```\r\n"
    (root / ".claude" / "design.md").write_bytes(body.encode("utf-8"))
    p = root / ".claude" / "design.md"
    assert no_raise(lambda: cl.surface("main", p))["bg"] == "#0d0d0d"


def case_21_broken_token_like_block_refuses(cl):
    """Битый блок, похожий на токены, валит разбор даже при целом соседе: не угадываем."""
    p = ws(['```json\n{"surfaces": { сломано\n```', fence(toks(bg="#0d0d0d"))]) / ".claude" / "design.md"
    e = raises(lambda: cl.brand(p), ValueError)
    assert "не разбирается" in str(e), f"причина отказа другая: {e}"


def case_22_caller_cannot_poison_cache(cl):
    """Правка палитры у себя не меняет общий кеш: иначе следующий возьмёт чужой цвет."""
    p = ws([fence(toks(bg="#0d0d0d"))]) / ".claude" / "design.md"
    s = cl.surface("main", p)
    s["bg"] = "#FOREIGN"
    again = cl.surface("main", p)["bg"]
    assert again == "#0d0d0d", f"кеш отравлен вызывающим кодом: {again}"
    assert "#FOREIGN" not in cl.brand_css("main", p), "подменённый цвет доехал до css"


def case_23_indented_fence_counts(cl):
    """Ограда с отступом (Markdown разрешает до трёх пробелов) не выпадает из подсчёта."""
    real = "   ```json\n" + json.dumps(toks(bg="#0d0d0d"), ensure_ascii=False) + "\n   ```"
    p = ws([real, fence(toks(bg="#EXAMPLE"))]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("main", p), ValueError)
    assert "несколько" in str(e), f"отступ спрятал настоящий блок, взят пример: {e}"


def case_24_unterminated_block_does_not_swallow_real_tokens(cl):
    """Незакрытый блок не закрывается ОТКРЫВАЮЩЕЙ оградой следующего.

    Иначе настоящие токены выпадают из разбора целиком, а стоящий ниже пример
    остаётся единственным кандидатом и возвращается без единого предупреждения.
    """
    p = ws([
        "```json\n{ сломано",                      # ограда не закрыта
        fence(toks(bg="#0d0d0d")),                 # настоящие токены
        fence(toks(bg="#EXAMPLE")),                # пример ниже
    ]) / ".claude" / "design.md"
    e = raises(lambda: cl.surface("main", p), ValueError)
    assert "#EXAMPLE" not in str(e), "пример стал палитрой"
    assert "не разбирается" in str(e), f"причина отказа другая: {e}"


# --- прогон -------------------------------------------------------------

def case_25_top_level_colour_reaches_root(cl):
    """Цвет верхнего уровня токенов (accent_ink) доезжает до :root.

    Живой случай 26.08: роль «текст поверх акцента» лежит НЕ внутри поверхности,
    поэтому surface() её не отдавал, взять из design.md было нечем, и сборка
    хардкодила близкий цвет (#14180f вместо #1a1a1a). Правило «бери цвет из
    design.md» без этого неисполнимо, а неисполнимое правило хуже отсутствующего.
    """
    p = ws([fence(toks(bg="#0d0d0d", extra={"accent_ink": "#111111"}))]) / ".claude" / "design.md"
    css = cl.brand_css("main", p)
    assert "--accent-ink:#111111" in css, f"верхнеуровневый цвет не доехал до css: {css[:200]}"


def case_26_surface_key_beats_top_level(cl):
    """Одноимённый ключ ПОВЕРХНОСТИ перекрывает общий: поверхность конкретнее.

    Иначе общий токен молча перекрасил бы фон конкретной поверхности, и слайд
    вышел бы почти правильным — тот самый брак, который проходит мимо глаз.
    """
    p = ws([fence(toks(bg="#0d0d0d", extra={"accent": "#AAAAAA"}))]) / ".claude" / "design.md"
    css = cl.brand_css("main", p)
    assert "--accent:#c8ff00" in css, f"общий токен подменил акцент поверхности: {css[:200]}"
    assert "--accent:#AAAAAA" not in css, "общий акцент доехал вместо акцента поверхности"


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

# Негативный контроль: снимаем защиту и убеждаемся, что тест краснеет.
MUTATIONS: dict[str, tuple[str, str]] = {
    "case_01_example_block_does_not_win": ("if len(found) > 1:", "if False:"),
    "case_25_top_level_colour_reaches_root": (
        'top = {k: v for k, v in b.items() if isinstance(v, str) and v.startswith("#")}',
        'top = {}'),
    "case_24_unterminated_block_does_not_swallow_real_tokens": (
        r'_TOKENS_RE = re.compile(r"^[ ]{0,3}```json[ \t]*\n(.*?)^[ ]{0,3}```[ \t]*$", re.S | re.M)',
        r'_TOKENS_RE = re.compile(r"^[ ]{0,3}```json[ \t]*\n(.*?)^[ ]{0,3}```", re.S | re.M)'),
    "case_04_broken_json_next_to_valid": (
        r'_TOKENS_RE = re.compile(r"^[ ]{0,3}```json[ \t]*\n(.*?)^[ ]{0,3}```[ \t]*$", re.S | re.M)',
        r'_TOKENS_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)'),
    "case_09_placeholder_in_unused_surface_does_not_block": (
        '_require_filled({k: v for k, v in data.items() if k != "surfaces"},', "_require_filled(data,"),
    "case_08_placeholder_in_used_surface_blocks_build": (
        '_require_filled(s, p, f"поверхности «{name}»")', "pass"),
    "case_10_walk_stops_at_workspace_root": ('if (d / ".claude").is_dir():', "if False:"),
    "case_13_missing_required_surface_keys": ("if miss:", "if False:"),
    "case_15_edit_of_design_md_is_seen": (
        "key = (str(rp), st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)",
        "key = (str(rp),)"),
    "case_17_cache_does_not_mix_clients": (
        "key = (str(rp), st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)",
        "key = (str(p), st.st_mtime_ns)"),
    "case_18_empty_or_null_color_is_refused": (
        "miss = [k for k in _SURFACE_KEYS if not (isinstance(s.get(k), str) and s[k].strip())]",
        "miss = [k for k in _SURFACE_KEYS if k not in s]"),
    "case_19_empty_surfaces_block_does_not_yield_example": (
        'if isinstance(data, dict) and "surfaces" in data:',
        'if isinstance(data, dict) and isinstance(data.get("surfaces"), dict) and data["surfaces"]:'),
    # Мутация бьёт по настоящему механизму: \r снимает не регулярка, а чтение в
    # текстовом режиме. Сохрани перевод строк как есть — и файл Windows перестанет
    # разбираться. Мутация на саму регулярку тут НЕ кусалась бы, потому что до неё
    # символа \r уже нет; такую «защиту» я снял как мёртвую.
    # Читаем через open(newline=""), а НЕ read_text(newline=""): такого параметра у
    # read_text нет, и мутант краснел бы от TypeError, то есть не за то (нашёл Codex).
    "case_20_crlf_file_parses": (
        'text = p.read_text(encoding="utf-8")',
        'text = p.open("r", encoding="utf-8", newline="").read()'),
    "case_22_caller_cannot_poison_cache": (
        "return copy.deepcopy(_BRAND_CACHE[key])", "return _BRAND_CACHE[key]"),
    "case_23_indented_fence_counts": (
        r'_TOKENS_RE = re.compile(r"^[ ]{0,3}```json[ \t]*\n(.*?)^[ ]{0,3}```[ \t]*$", re.S | re.M)',
        r'_TOKENS_RE = re.compile(r"^```json[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)'),
    "case_21_broken_token_like_block_refuses": (
        'if "surfaces" in body:', "if False:"),
    "case_07_placeholder_in_shared_block_blocks_build": (
        "_require_filled({k: v for k, v in data.items()", "_require_filled({k: v for k, v in ({}).items()"),
}


def main() -> int:
    real = load("carousel_lib_real")
    fails: list[str] = []
    for fn in CASES:
        name = fn.__name__
        try:
            fn(real)
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
            fails.append(name)
    print()
    for name, sub in sorted(MUTATIONS.items()):
        fn = globals()[name]
        try:
            mutant = load("carousel_lib_mut_" + name, sub)
        except AssertionError as e:
            # Мутация, потерявшая цель, это НЕ повод пропустить остальные: код рядом
            # переписали, и негативный контроль молча перестал кусаться.
            print(f"  FAIL мутация потеряла цель: {name}: {e}")
            fails.append("mutation-target:" + name)
            continue
        try:
            fn(mutant)
        except AssertionError:
            print(f"  ok   мутация кусается: {name}")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ok   мутация кусается ({type(e).__name__}): {name}")
            continue
        print(f"  FAIL мутация НЕ кусается: {name} — защита без проверки")
        fails.append("mutation:" + name)
    shutil.rmtree(_TMP, ignore_errors=True)
    total = len(CASES) + len(MUTATIONS)
    print(f"\n{total - len(fails)}/{total} проверок пройдено")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
