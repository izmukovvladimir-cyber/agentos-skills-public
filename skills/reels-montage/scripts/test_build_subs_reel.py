#!/usr/bin/env python3
"""Tests for build_subs_reel.py. Run: python3 test_build_subs_reel.py

Every section is wrapped so that a section dying of an exception counts as a
FAIL rather than killing the run — a suite that aborts silently reads as
"nothing to report" to a mutation runner.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import traceback

HERE = pathlib.Path(__file__).resolve().parent
TARGET = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "build_subs_reel.py"

spec = importlib.util.spec_from_file_location("bsr", TARGET)
bsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsr)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {name} {detail}")


def section(fn) -> None:
    try:
        fn()
    except Exception:
        global FAIL
        FAIL += 1
        print(f"FAIL: секция {fn.__name__} умерла исключением")
        traceback.print_exc()


def w(word: str, start: float, end: float) -> dict:
    return {"word": word, "start": start, "end": end}


# ---------------------------------------------------------------- group_lines
def t_group() -> None:
    words = [w(f"сл{i}", i, i + 1) for i in range(9)]
    lines = bsr.group_lines(words, max_words=4, max_chars=999)
    check("group: по 4 слова", [len(x) for x in lines] == [4, 4, 1], str([len(x) for x in lines]))
    check("group: ничего не потеряно", sum(len(x) for x in lines) == 9)
    check("group: порядок сохранён",
          [x["word"] for ln in lines for x in ln] == [x["word"] for x in words])

    lines = bsr.group_lines([w("а" * 40, 0, 1), w("б", 1, 2)], max_words=4, max_chars=10)
    check("group: слово длиннее лимита не теряется и не зацикливает",
          sum(len(x) for x in lines) == 2 and len(lines) == 2, str(lines))

    lines = bsr.group_lines([w("аб", 0, 1), w("вг", 1, 2), w("де", 2, 3)], max_words=99, max_chars=6)
    check("group: режет по символам", len(lines) == 2, str([[x['word'] for x in l] for l in lines]))

    check("group: пустой вход", bsr.group_lines([], 4, 30) == [])


# ---------------------------------------------------------------- timed_lines
def t_timed() -> None:
    # whisper spans overlap: line 0 ends at 3.22 but line 1 starts at 3.16
    lines = [[w("а", 0.0, 3.22)], [w("б", 3.16, 5.0)]]
    rows = bsr.timed_lines(lines, duration=10.0)
    check("timed: две строки", len(rows) == 2)
    _, s0, e0, _ = rows[0]
    _, s1, e1, _ = rows[1]
    check("timed: строка держится ДО начала следующей", abs(e0 - s1) < 1e-9, f"{e0} vs {s1}")
    check("timed: перекрытия нет", e0 <= s1 + 1e-9, f"{e0} > {s1}")
    check("timed: последняя тянется до конца ролика", abs(e1 - 5.12) < 1e-9, str(e1))

    rows = bsr.timed_lines([[w("а", 0.0, 1.0)], [w("б", 9.9, 20.0)]], duration=10.0)
    check("timed: хвост обрезан длительностью", rows[-1][2] <= 10.0, str(rows[-1][2]))

    rows = bsr.timed_lines([[w("а", 0.0, 1.0)], [w("б", 30.0, 31.0)]], duration=10.0)
    check("timed: строка целиком за концом отброшена", len(rows) == 1, str(rows))

    rows = bsr.timed_lines([[w("а", 5.0, 5.0)], [w("б", 5.0, 6.0)]], duration=10.0)
    check("timed: нулевое окно отброшено", all(e > s for _, s, e, _ in rows), str(rows))

    rows = bsr.timed_lines([], duration=10.0)
    check("timed: пустой вход", rows == [])

    # индексы строк переживают отбрасывание — id не должны схлопнуться
    rows = bsr.timed_lines([[w("а", 30.0, 31.0)], [w("б", 1.0, 2.0)]], duration=10.0)
    check("timed: индекс уцелевшей строки прежний", rows and rows[0][0] == 1, str(rows))


# ---------------------------------------------------------------- render_html
def build(words=None, duration=10.0, hook="Хук", **kw) -> str:
    words = words or [w("раз", 0.0, 1.0), w("два", 1.0, 2.0), w("три", 2.0, 3.0)]
    p = dict(hook_until=4.5, accent="#c8ff2e", width=1080, height=1920,
             max_words=4, max_chars=30, band_top=1360)
    p.update(kw)
    return bsr.render_html(words, duration, hook, p["hook_until"], p["accent"],
                           p["width"], p["height"], p["max_words"], p["max_chars"], p["band_top"])


def t_contract() -> None:
    doc = build()
    # судим САМ корневой тег: data-start="0" стоит и у video/audio, и подстрока
    # по всему документу «доказывала» бы атрибут, которого у корня нет
    root = re.search(r"<div id=\"root\"[^>]*>", doc)
    check("contract: корневой тег найден", root is not None)
    root_tag = root.group(0) if root else ""
    check("contract: у корня data-composition-id", 'data-composition-id="main"' in root_tag, root_tag)
    check("contract: у корня data-start=0", 'data-start="0"' in root_tag, root_tag)
    check("contract: у корня заданы размеры",
          'data-width=' in root_tag and 'data-height=' in root_tag, root_tag)
    check("contract: одна пауз-таймлиния", doc.count("gsap.timeline({ paused: true })") == 1)
    check("contract: таймлиния зарегистрирована под id корня", 'window.__timelines["main"] = tl;' in doc)
    check("contract: видео muted+inline", 'muted playsinline' in doc)
    check("contract: звук отдельным элементом", '<audio id="a-roll-audio"' in doc)
    check("contract: нет br в тексте", "<br" not in doc)
    check("contract: нет repeat: -1", "repeat: -1" not in doc)
    check("contract: длительность корня из аргумента", 'data-duration="10.00"' in doc)


def t_ids() -> None:
    doc = build()
    timed = re.findall(r"<(\w+)([^>]*data-start=[^>]*)>", doc)
    for tag, attrs in timed:
        if 'data-composition-id' in attrs:
            continue  # root
        check(f"ids: у тайм-элемента <{tag}> есть id", 'id="' in attrs, attrs[:90])
    ids = re.findall(r'id="([^"]+)"', doc)
    check("ids: уникальны", len(ids) == len(set(ids)),
          str([i for i in ids if ids.count(i) > 1]))


def t_words() -> None:
    doc = build()
    check("words: подсветка каждого слова", doc.count('color: "#c8ff2e"') == 3, str(doc.count('color: "#c8ff2e"')))
    doc = build(words=[w("раз", 0.0, 1.0), w("поздно", 99.0, 100.0)], duration=10.0)
    check("words: слово за концом не твинится", doc.count('color: "#c8ff2e"') == 1)
    doc = build(words=[w("<b>&amp;", 0.0, 1.0)])
    check("words: html экранирован", "&lt;b&gt;" in doc and "<b>" not in doc)
    check("words: акцент подставляется", 'color: "#ff0000"' in build(accent="#ff0000"))


def t_hook() -> None:
    doc = build(hook="")
    check("hook: пустой — нет карточки", 'id="hook"' not in doc and "hook-card" not in doc)
    doc = build(hook="Привет")
    check("hook: есть карточка", 'id="hook-card"' in doc)
    check("hook: экранирован", "&lt;" in build(hook="<x>"))
    check("hook: длительность из hook_until", 'data-duration="4.30"' in build(hook="х", hook_until=4.5), "")
    check("hook: не уходит в ноль", 'data-duration="0.50"' in build(hook="х", hook_until=0.1))


def t_geometry() -> None:
    doc = build(width=720, height=1280, band_top=900)
    check("geom: ширина корня", 'data-width="720"' in doc and 'data-height="1280"' in doc)
    check("geom: полоса на заданной высоте", "top: 900px" in doc)
    check("geom: полоса уже кадра", "max-width: 580px" in doc)


def t_no_overlap_in_html() -> None:
    words = [w("а", 0.0, 3.22), w("б", 3.16, 4.0), w("в", 4.0, 5.0), w("г", 5.0, 6.0),
             w("д", 5.9, 7.0), w("е", 7.0, 8.0)]
    doc = build(words=words, duration=10.0, max_words=2, max_chars=99)
    spans = [(float(s), float(s) + float(d)) for s, d in
             re.findall(r'class="clip subs" data-start="([\d.]+)" data-duration="([\d.]+)"', doc)]
    check("html: полос больше одной", len(spans) >= 3, str(spans))
    overlaps = [(a, b) for a, b in zip(spans, spans[1:]) if a[1] > b[0] + 1e-9]
    check("html: полосы не наезжают", not overlaps, str(overlaps))


# --------------------------------------------------------------- place_source
def t_place_source() -> None:
    import subprocess as sp
    import tempfile

    have_ffmpeg = sp.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
    if not have_ffmpeg:
        check("place: ffmpeg доступен для проверки", False, "ffmpeg не найден — секция ничего не проверила")
        return

    with tempfile.TemporaryDirectory(prefix="bsr-test-") as tmp:
        d = pathlib.Path(tmp)
        mp4 = d / "in.mp4"
        sp.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", str(mp4)], check=True)

        out = d / "a.mp4"
        note = bsr.place_source(mp4, out)
        check("place: mp4 копируется как есть", "как есть" in note, note)
        check("place: файл на месте", out.is_file() and out.stat().st_size > 0)
        check("place: байты не изменились", out.read_bytes() == mp4.read_bytes())

        mov = d / "in.MOV"
        sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-c", "copy", str(mov)], check=True)
        out2 = d / "b.mp4"
        note2 = bsr.place_source(mov, out2)
        check("place: MOV переупакован, а не скопирован", "переупакован" in note2, note2)
        check("place: результат читается ffprobe", sp.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", str(out2)],
            capture_output=True).returncode == 0)
        # регистр расширения не должен решать судьбу файла: .MP4 это тот же mp4.
        # (проверять это подстрокой «перекодирован» нельзя — она сидит внутри
        #  слова «перекодирования» в сообщении об успешной переупаковке)
        upper = d / "in.MP4"
        upper.write_bytes(mp4.read_bytes())
        out_u = d / "u.mp4"
        note_u = bsr.place_source(upper, out_u)
        check("place: .MP4 в верхнем регистре копируется как есть", "как есть" in note_u, note_u)

        # ffmpeg с кодом 0 и без файла: пустой source.mp4 даёт чёрный рендер,
        # который читается как ошибка вёрстки, а не как несобранный исходник
        import os
        fake = d / "fakebin"
        fake.mkdir()
        (fake / "ffmpeg").write_text("#!/bin/sh\nexit 0\n")
        (fake / "ffmpeg").chmod(0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{fake}:{old_path}"
        try:
            raised = False
            try:
                bsr.place_source(mov, d / "empty.mp4")
            except RuntimeError:
                raised = True
            check("place: пустой выход ffmpeg — отказ, а не успех", raised)
        finally:
            os.environ["PATH"] = old_path

        # контейнер, который «-c copy» в mp4 не переживает → путь перекодирования
        ogg = d / "in.ogv"
        sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-c:v", "libtheora",
                "-c:a", "libvorbis", str(ogg)], capture_output=True)
        if ogg.is_file() and ogg.stat().st_size > 0:
            out3 = d / "c.mp4"
            note3 = bsr.place_source(ogg, out3)
            check("place: неподходящий контейнер перекодируется", "перекодирован" in note3, note3)
            check("place: перекодированный файл валиден", sp.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", str(out3)],
                capture_output=True).returncode == 0)


for fn in (t_group, t_timed, t_contract, t_ids, t_words, t_hook, t_geometry, t_no_overlap_in_html, t_place_source):
    section(fn)

print(f"PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
