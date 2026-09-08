#!/usr/bin/env python3
"""style_check.py — PRE-FLIGHT проверка человеческого стиля текста для людей.

Назначение (владелец): человеческий стиль зашит
МЕХАНИЧЕСКИ, а не держится на памяти агента. Касается ЛЮБОГО русского текста
для людей, который пишет <agent>: посты, подписи, сторис/хайлайтс, present HTML,
ответы в чат.

Хард-флаги (exit 10 — переписать):
  1. Длинные тире «—»/«–»/«―» (U+2014/2013/2015). Обычный дефис «-» (compounds) ОК.
  2. Контраст «не X, а Y» (рекламный AI-почерк).
  3. Формулы-клише «дело не в тебе», «дело не в … а в …».
Мягкий флаг (тоже exit 10, но консервативно):
  4. Рваность — длинный run коротких предложений-обрубков подряд.

НЕ проверяет дословный телесуфлёр (там хук оригинала с его стилем, см.
hook_fidelity_check.py) — для речи запускать с --no-choppy и помнить, что
контраст из оригинала сохраняется. Цель скрипта — НАШ авторский текст
(пост/сторис/подпись/present/чат).

Вход: --draft-file PATH или stdin. Выход: verdict в stdout.
Exit 0 = чисто, 10 = есть флаги, 2 = пустой/нет ввода.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CONFIG = Path("~/.claude/skills/niche-reels-research/config/watchlist.json")

# дефолты эвристики рваности (в config/watchlist.json:limits можно переопределить)
CHOPPY_SHORT_WORDS = 4    # предложение < N слов считается «обрубком»
CHOPPY_RUN = 4            # столько обрубков ПОДРЯД = рваность
CHOPPY_MIN_SENTENCES = 6  # не судить рваность, если прозы меньше (короткая подпись)
CHOPPY_RATIO = 0.55       # либо доля обрубков среди прозы выше этой

DASH_RE = re.compile(r"[–—―]")             # –, —, ―; ASCII «-» (compounds) НЕ флагаем
# `\S+` used to swallow the sentence-ending dot, so "Он не пришёл. Позвонил, а
# потом ушёл" was flagged as a «не X, а Y» contrast across a sentence break.
# A false flag here is expensive: it blocks a whole delivery. Corpus check
# 26.08 (25 blog articles): 10 flags -> 7, and all 3 removed were this bug.
CONTRAST_RE = re.compile(r"\bне\s+[^\s.!?…]+[^.!?…\n]{0,30}?,\s+а\s+\S", re.IGNORECASE)
# Обратная форма того же запрета TOV: «X, а не Y» («это соглашение, а не функция»).
# Прямую форму ловит CONTRAST_RE, эта до  проходила мимо и доехала до живого магнита.
# NEG_TAIL снимает вопросительные обороты, где «а не» не противопоставление: «а не пора ли».
CONTRAST_REV_RE = re.compile(
    r",\s+а\s+не\s+(?!пора\b|лучше\s+ли\b|так\s+ли\b|то\b)\S", re.IGNORECASE)
FORMULA_RES = [
    re.compile(r"дело\s+не\s+в\b", re.IGNORECASE),
    re.compile(r"не\s+в\s+тебе\s+дело", re.IGNORECASE),
]
# корректный маркер списка = «-»/«•»/«*»/цифра; «—»/«–» как булет запрещены правилом
LIST_LINE_RE = re.compile(r"^\s*([-•*]|\d+[.)])\s+")
PARA_SPLIT_RE = re.compile(r"\n\s*\n+")     # абзац = пустая строка
SOFT_WRAP_RE = re.compile(r"\s*\n\s*")      # одиночный перенос внутри абзаца = пробел
SENT_SPLIT_RE = re.compile(r"[.!?…]+")
WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")   # слово = буквенно-цифровой токен (не emoji/URL-хвост)


def load_limits():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("limits", {})
    except (OSError, ValueError, TypeError):
        return {}


def _int(limits, key, default):
    try:
        v = int(limits.get(key, default))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _float(limits, key, default):
    try:
        v = float(limits.get(key, default))
        return v if 0.0 < v <= 1.0 else default
    except (TypeError, ValueError):
        return default


# Детектор не штрафует текст, который ЦИТИРУЕТ само правило: в гайдах по TOV строка
# «никаких конструкций вида "не X, а Y"» это объяснение запрета, а не его нарушение.
# 26 таких ложных находок по живому хабу на .
_RULE_CITE_RE = re.compile(r"(?:не\s+X\s*,\s*а\s+Y|X\s*,\s*а\s+не\s+Y)", re.IGNORECASE)


def _is_rule_citation(text, m):
    """True, если совпадение попало внутрь цитаты самого правила (метапеременные X и Y)."""
    return bool(_RULE_CITE_RE.search(text[max(0, m.start() - 40):m.end() + 40]))


def find_dashes(text):
    return [m.start() for m in DASH_RE.finditer(text)]


def snippet(text, pos, span=28):
    a = max(0, pos - span)
    b = min(len(text), pos + span)
    return text[a:b].replace("\n", " ").strip()


def prose_sentences(text):
    """Предложения только из ПРОЗЫ. Строки-списки исключаются (короткость там легитимна),
    одиночный перенос строки внутри абзаца — это вёрстка, склеиваем пробелом (НЕ конец
    предложения), границы предложений только по пунктуации [.!?…]."""
    prose_lines = [ln for ln in text.splitlines() if not LIST_LINE_RE.match(ln)]
    blob = "\n".join(prose_lines)
    out = []
    for para in PARA_SPLIT_RE.split(blob):
        para = SOFT_WRAP_RE.sub(" ", para).strip()
        if not para:
            continue
        for raw in SENT_SPLIT_RE.split(para):
            s = raw.strip()
            if s:
                out.append((s, len(WORD_RE.findall(s))))
    return out


def choppiness_flag(text, short_words, run_len, min_sents, ratio):
    sents = prose_sentences(text)
    if len(sents) < min_sents:
        return None
    shorts = [wc < short_words for _, wc in sents]
    # (a) длинный run обрубков подряд
    run = best = 0
    for is_short in shorts:
        run = run + 1 if is_short else 0
        best = max(best, run)
    frac = sum(shorts) / len(sents)
    # (a) явный run обрубков подряд, либо (b) высокая доля коротких ПРИ наличии хотя бы пары подряд
    if best >= run_len or (frac >= ratio and best >= 2):
        examples = [s for s, wc in sents if wc < short_words][:5]
        return {"run": best, "frac": round(frac, 2), "n": len(sents), "examples": examples}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft-file", type=Path, default=None)
    ap.add_argument("--no-choppy", action="store_true",
                    help="пропустить эвристику рваности (для речи/телесуфлёра/короткой подписи)")
    args = ap.parse_args()

    if args.draft_file:
        try:
            text = args.draft_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"ERR: не прочитать draft-file: {e}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()
    if not text or not text.strip():
        print("ERR: пустой ввод (нечего проверять)", file=sys.stderr)
        return 2

    limits = load_limits()
    short_words = _int(limits, "style_choppy_short_words", CHOPPY_SHORT_WORDS)
    run_len = _int(limits, "style_choppy_run", CHOPPY_RUN)
    min_sents = _int(limits, "style_choppy_min_sentences", CHOPPY_MIN_SENTENCES)
    ratio = _float(limits, "style_choppy_ratio", CHOPPY_RATIO)

    flags = []

    dashes = find_dashes(text)
    if dashes:
        flags.append(f"[ТИРЕ] длинных тире «—/–» {len(dashes)} шт. Замени на запятую или точку. "
                     f"Пример: «…{snippet(text, dashes[0])}…»")

    contrasts = [m for m in list(CONTRAST_RE.finditer(text)) + list(CONTRAST_REV_RE.finditer(text))
                 if not _is_rule_citation(text, m)]
    if contrasts:
        contrasts.sort(key=lambda m: m.start())
        flags.append(f"[КОНТРАСТ] конструкция «не X, а Y» / «X, а не Y» {len(contrasts)} шт. Перепиши "
                     f"простым утверждением. Пример: «…{snippet(text, contrasts[0].start())}…»")

    formula_hits = []
    for rx in FORMULA_RES:
        formula_hits += [m.start() for m in rx.finditer(text)]
    if formula_hits:
        flags.append(f"[ФОРМУЛА] клише «дело не в…» {len(formula_hits)} шт. Убери штамп, скажи по сути. "
                     f"Пример: «…{snippet(text, sorted(formula_hits)[0])}…»")

    if not args.no_choppy:
        ch = choppiness_flag(text, short_words, run_len, min_sents, ratio)
        if ch:
            ex = " / ".join(ch["examples"])
            flags.append(f"[РВАНОСТЬ] обрубков подряд до {ch['run']}, доля коротких {ch['frac']} из "
                         f"{ch['n']} предложений. Сшей в живые длинные фразы. Короткие: «{ex}»")

    if flags:
        print("СТИЛЬ: переписать (живой человеческий текст, без AI-почерка):")
        for f in flags:
            print("  " + f)
        print(f"\n=== флагов: {len(flags)} ===")
        return 10
    print("СТИЛЬ: чисто.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
