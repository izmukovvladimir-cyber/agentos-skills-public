#!/usr/bin/env python3
"""digest_format_check.py — механическая проверка «формат <agent> 1 в 1».

владелец HARD: все агентские боты выдают утреннюю подборку
одинаково — как <agent>, от дизайна до каждой буквы карточки. Канон:
references/digest_format_canon.md. Этот скрипт — зубы канона: гоняется агентом
перед выдачей И автоматически из send_morning_digest.py (⚠️-блок в сводке).

Проверяет pack_*.json + meta.json в packs-dir:
  reel-pack:  ключи author_username/topic/url/card/teleprompter/caption/editor_brief
              непустые; topic содержит «(кодворд …)»; card начинается с
              «МЕТРИКИ ОРИГИНАЛА (@», несёт score= и блоки ПОЧЕМУ/ФОРМАТ
              ОРИГИНАЛА; editor_brief с таймкодами и строкой РЕФЕРЕНС.
              «ratio=» НЕ проверяется намеренно: <agent> легитимно пишет
              «ратио=speed-driven» или опускает при «под:писчиков=n/a» (канон §2);
  транскрипт: у рилса с телесуфлёром обязан быть транскрипт на диске (work/<code>/transcript.*
              либо сводный *transcript*.json пула). Без него телесуфлёр написан по капшену,
              то есть выдуман. Исключения: РЕФЕРЕНС-ONLY и явная пометка 'no_speech': true
              (или «БЕЗ РЕЧИ» в editor_brief) для ролика без речи;
  carousel:   type=="carousel", card с МЕТРИКИ/ВЕРДИКТ/ПОЧЕМУ, кодворд в topic|card;
  meta.json:  присутствует, date_label YYYY-MM-DD, intro/final непустые;
  стиль:      длинное тире «—» в teleprompter/caption/intro/final = флаг.

Exit: 0 = формат по канону; 10 = есть флаги (исправь паки, НЕ выдавай) — сюда же
намеренно попадают битый pack_*.json и пустая packs-dir: pack пишет сам агент,
это дефект подборки, а не окружения; 2 = ошибка входа (нет папки packs-dir).
Fail-open вызов из digest: любые исключения там глотаются.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

CANON = "references/digest_format_canon.md"
DASH_RE = re.compile(r"[—–―]")  # — – ―
TIMECODE_RE = re.compile(r"\d:\d\d")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHORTCODE_RE = re.compile(r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]{5,})")

REEL_KEYS = ("author_username", "topic", "url", "card",
             "teleprompter", "caption", "editor_brief")
CAROUSEL_KEYS = ("author_username", "topic", "url", "card")


def _s(pack: dict, key: str) -> str:
    v = pack.get(key)
    return v.strip() if isinstance(v, str) else ""


def _codeword_ok(*texts: str) -> bool:
    return any("кодворд" in t.lower() for t in texts)


def pack_shortcode(pack: dict) -> str:
    """Shortcode рилса: явный ключ, иначе вытащить из url/link."""
    code = pack.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    for key in ("url", "link"):
        m = SHORTCODE_RE.search(_s(pack, key))
        if m:
            return m.group(1)
    return ""


@lru_cache(maxsize=1)
def _aggregate_transcript_codes() -> frozenset[str]:
    """Коды из сводных файлов транскриптов пула (_pack6_transcripts.json и его датированные
    предшественники). Форма записи у всех одна: список объектов с code и text."""
    codes: set[str] = set()
    try:
        files = sorted(lib_paths.pool_dir().glob("*transcript*.json"))
    except OSError:
        return frozenset()
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for rec in data:
            if not isinstance(rec, dict):
                continue
            code = rec.get("code")
            text = rec.get("text") or rec.get("transcript")
            if isinstance(code, str) and isinstance(text, str) and text.strip():
                codes.add(code.strip())
    return frozenset(codes)


def has_transcript(code: str) -> bool:
    """Есть ли на диске РЕЧЬ этого ролика. Сначала per-work файл, затем сводный:
    у разных клиентов исторически прижились оба варианта."""
    if not code:
        return False
    work = lib_paths.pool_dir() / "work" / code
    txt = work / "transcript.txt"
    try:
        if txt.is_file() and txt.read_text(encoding="utf-8", errors="ignore").strip():
            return True
    except OSError:
        pass
    js = work / "transcript.json"
    try:
        if js.is_file():
            data = json.loads(js.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                text = data.get("text")
                if isinstance(text, str) and text.strip():
                    return True
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return code in _aggregate_transcript_codes()


def check_reel(pack: dict, name: str, notes: list[str] | None = None) -> list[str]:
    p: list[str] = []
    brief = _s(pack, "editor_brief")
    # Канонное исключение <agent>: REFERENCE-ONLY рилс (off-niche виралка для полноты
    # картины) идёт без телесуфлёра/капшена/таймкодов, brief честно говорит об этом.
    reference_only = "РЕФЕРЕНС-ONLY" in brief.upper() or "REFERENCE-ONLY" in brief.upper()
    required = REEL_KEYS if not reference_only else CAROUSEL_KEYS + ("editor_brief",)
    for k in required:
        if not _s(pack, k) and not (k == "url" and _s(pack, "link")):
            p.append(f"{name}: пустой/нет ключ '{k}'")
    card = _s(pack, "card")
    if card:
        if not card.startswith("МЕТРИКИ ОРИГИНАЛА (@"):
            p.append(f"{name}: card не начинается с «МЕТРИКИ ОРИГИНАЛА (@handle):»")
        if "score=" not in card:
            p.append(f"{name}: в card нет «score=N»")
        if "ПОЧЕМУ" not in card:
            p.append(f"{name}: в card нет блока «ПОЧЕМУ ВЗЯЛА:»")
        if "ФОРМАТ ОРИГИНАЛА" not in card and not reference_only:
            p.append(f"{name}: в card нет блока «ФОРМАТ ОРИГИНАЛА:»")
    if _s(pack, "topic") and not reference_only and not _codeword_ok(_s(pack, "topic")):
        p.append(f"{name}: в topic нет «(кодворд X)»")
    if brief:
        if not reference_only and not TIMECODE_RE.search(brief):
            p.append(f"{name}: editor_brief без таймкодов «0:00-0:03 …»")
        if "РЕФЕРЕНС" not in brief:
            p.append(f"{name}: editor_brief без строки «РЕФЕРЕНС: <url оригинала>»")
    for k in ("teleprompter", "caption"):
        if DASH_RE.search(_s(pack, k)):
            p.append(f"{name}: длинное тире «—» в {k} (запрещено, замени запятой/точкой)")
    p.extend(check_transcript(pack, name, reference_only, notes))
    return p


def no_speech_marked(pack: dict) -> bool:
    """Пак заявляет, что речи в ролике нет («no_speech»: true либо «БЕЗ РЕЧИ» в editor_brief).

    Условие ДУБЛИРУЕТСЯ в hook_fidelity_check.py (там свой пропуск по той же пометке). Свести
    в один импорт стоит, но это правка соседнего гейта, сюда её не тащу; пока держим тексты
    условий побуквенно одинаковыми, расхождение канона будет тихим.
    Пометку ставит ТОТ ЖЕ агент, который пишет телесуфлёр, то есть это его слово, а не замер.
    Отличить немой ролик от говорящего по тексту транскрипта нельзя: ASR на музыке всегда
    выдаёт непустой мусор. Поэтому пропуск оставляет СЛЕД (см. check_packs → notes): ошибочная
    пометка на говорящем ролике ловится глазами на ревью, а молчаливый пропуск неотличим от
    «проверено и чисто» и невидим навсегда. Решение куратора 31.07, доска #362."""
    return pack.get("no_speech") is True or "БЕЗ РЕЧИ" in _s(pack, "editor_brief").upper()


def check_transcript(pack: dict, name: str, reference_only: bool,
                     notes: list[str] | None = None) -> list[str]:
    """Гейт: телесуфлёр обязан опираться на РЕЧЬ ролика, а не на капшен.

    Повод: `transcribe.py` без стадии `stage_audio.py` печатает «NO MP3, skip» и выходит с
    нулевым кодом, то есть выглядит успешным прогоном. Агент видит зелёный конвейер, речи не
    видит и пишет телесуфлёр по подписи к ролику. Это выдуманный текст вместо рерайта чужой
    виралки. За 22-25.07 так ушли 4 дня у троих клиентов, и никакая проверка этого не поймала.

    Исключения: пак без телесуфлёра и ролик без речи, который агент обязан пометить явно
    (`no_speech: true` в паке либо «БЕЗ РЕЧИ» в editor_brief).

    РЕФЕРЕНС-ONLY считается только когда так помечен САМ телесуфлёр: по живой практике агенты
    кладут в это поле не сценарий, а строку «РЕФЕРЕНС-ONLY, телесуфлёр не готовила …», и пустым
    поле не бывает. Метки в editor_brief при написанном сценарии НЕДОСТАТОЧНО, иначе гейт
    обходился бы одной строкой в ТЗ монтажу.
    """
    tele = _s(pack, "teleprompter")
    if not tele or "РЕФЕРЕНС-ONLY" in tele.upper() or "REFERENCE-ONLY" in tele.upper():
        return []
    if no_speech_marked(pack):
        # След пишем ЗДЕСЬ, а не выше по стеку: только в этой точке проверка транскрипта
        # действительно пропущена ИМЕННО по пометке. У пака без телесуфлёра и у
        # РЕФЕРЕНС-ONLY проверки нет по другой причине, и след про «без речи» там соврал бы.
        if notes is not None:
            notes.append(f"{name}: проверка транскрипта пропущена, пак помечен «без речи»")
        return []
    code = pack_shortcode(pack)
    if not code:
        return [f"{name}: не определить shortcode (ни 'code', ни url) — транскрипт не проверить"]
    if has_transcript(code):
        return []
    return [f"{name}: телесуфлёр есть, транскрипта рилса {code} нет. Сначала "
            f"stage_audio.py --codes {code}, потом transcribe.py --codes {code}. "
            f"Телесуфлёр по капшену это выдуманный текст, а не рерайт. "
            f"Ролик реально без речи, пометь 'no_speech': true в паке"]


def check_carousel(pack: dict, name: str) -> list[str]:
    p: list[str] = []
    for k in CAROUSEL_KEYS:
        if not _s(pack, k) and not (k == "url" and _s(pack, "link")):
            p.append(f"{name}: пустой/нет ключ '{k}' (карусель)")
    card = _s(pack, "card")
    if card:
        if not card.startswith("МЕТРИКИ ОРИГИНАЛА (@"):
            p.append(f"{name}: card карусели не начинается с «МЕТРИКИ ОРИГИНАЛА (@handle):»")
        if "ВЕРДИКТ" not in card:
            p.append(f"{name}: в card карусели нет «ВЕРДИКТ: адаптировать|уникализировать|референс»")
        if "ПОЧЕМУ" not in card:
            p.append(f"{name}: в card карусели нет «ПОЧЕМУ ПОКАЗЫВАЮ:»")
    # Канонное исключение <agent>, то же что у рилсов: РЕФЕРЕНС-ONLY карусель несёт ПРИЁМ,
    # а не тему, магнита под неё нет, поэтому кодворд там был бы ложным обещанием.
    ref_only = "РЕФЕРЕНС-ONLY" in (_s(pack, "topic") + card + _s(pack, "editor_brief")).upper() \
        or "REFERENCE-ONLY" in (_s(pack, "topic") + card + _s(pack, "editor_brief")).upper()
    if not ref_only and not _codeword_ok(_s(pack, "topic"), card):
        p.append(f"{name}: у карусели нет кодворда ни в topic, ни в card")
    if DASH_RE.search(_s(pack, "caption")):
        p.append(f"{name}: длинное тире «—» в caption карусели")
    return p


def check_meta(meta: dict | None, has_reels: bool) -> list[str]:
    p: list[str] = []
    if meta is None:
        return ["meta.json отсутствует (обязателен: date_label + intro + final, скелет в каноне)"]
    if not isinstance(meta, dict):
        return ["meta.json не объект"]
    dl = meta.get("date_label")
    if not (isinstance(dl, str) and DATE_RE.match(dl.strip())):
        p.append("meta.json: date_label не в формате YYYY-MM-DD")
    intro = meta.get("intro")
    if not (isinstance(intro, str) and intro.strip()):
        p.append("meta.json: intro пустой (скелет: счёт, PROTECTED, отсевы, ТОП ДНЯ, ПОКРЫТИЕ, CTA)")
    else:
        if has_reels and "ТОП РИЛС ДНЯ" not in intro:
            p.append("meta.json: в intro нет строки «ТОП РИЛС ДНЯ: @handle …»")
        if DASH_RE.search(intro):
            p.append("meta.json: длинное тире «—» в intro")
    final = meta.get("final")
    if not (isinstance(final, str) and final.strip()):
        p.append("meta.json: final пустой («Это весь пак. Какие берёшь, напиши номера…»)")
    elif DASH_RE.search(final):
        p.append("meta.json: длинное тире «—» в final")
    return p


def load_meta(packs_dir: Path) -> dict | None:
    mp = packs_dir / "meta.json"
    if not mp.exists():
        return None
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}  # битый = объект без полей → флаги по полям
    return data if isinstance(data, dict) else {}


def check_packs(packs: list[dict], meta: dict | None,
                notes: list[str] | None = None) -> list[str]:
    """Importable ядро: паки уже загружены (как в send_morning_digest).

    notes — необязательный список, куда складываются НЕблокирующие следы (сейчас: пропуск
    проверки транскрипта по пометке «без речи»). Отдельный канал нужен потому, что любой
    элемент возвращаемого списка это ДОКАЗАННОЕ нарушение, оно блокирует выдачу клиенту.
    След обязан быть видимым и при этом безобидным, иначе честный немой ролик снова
    перестанет доезжать. Параметр необязателен ради обратной совместимости вызовов."""
    # Кэш сводных транскриптов живёт ровно один прогон проверки. Агент часто дотранскрибирует
    # недостающий ролик и зовёт проверку повторно в ТОМ ЖЕ процессе: бессрочный кэш продолжал бы
    # флагать уже готовый транскрипт и заблокировал бы выдачу живому клиенту на ровном месте.
    _aggregate_transcript_codes.cache_clear()
    problems: list[str] = []
    reels = 0
    for pack in packs:
        if not isinstance(pack, dict):
            problems.append("pack не объект JSON")
            continue
        name = Path(str(pack.get("_file", "pack"))).name
        if pack.get("type") == "carousel":
            problems.extend(check_carousel(pack, name))
        else:
            reels += 1
            problems.extend(check_reel(pack, name, notes))
    problems.extend(check_meta(meta, has_reels=reels > 0))
    return problems


def check_packs_dir(packs_dir: Path, notes: list[str] | None = None,
                    seen: list[str] | None = None) -> list[str]:
    files = sorted(packs_dir.glob("pack_*.json"))
    if seen is not None:
        # Охват судимого. Без него чистый прогон печатал уверенное «OK: формат по канону <agent>»
        # и на урезанной или несвежей папке (нашёл агент Натали ). Молчащий охват
        # читается как «проверено всё».
        seen.extend(f.name for f in files)
    if not files:
        return [f"в {packs_dir} нет pack_*.json"]
    packs: list[dict] = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            packs.append({"_file": f.name, "_broken": str(e)})
            continue
        if isinstance(d, dict):
            d["_file"] = f.name
            packs.append(d)
        else:
            packs.append({"_file": f.name, "_broken": "not a dict"})
    problems: list[str] = []
    for p in packs:
        if "_broken" in p:
            problems.append(f"{p['_file']}: битый JSON ({p['_broken']})")
    ok_packs = [p for p in packs if "_broken" not in p]
    problems.extend(check_packs(ok_packs, load_meta(packs_dir), notes))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка паков на канон «формат <agent>»")
    ap.add_argument("--packs-dir", type=Path,
                    default=lib_paths.packs_dir())  # board #56: same canonical packs the digest ships
    args = ap.parse_args()
    if not args.packs_dir.is_dir():
        print(f"ERROR: нет папки {args.packs_dir}", file=sys.stderr)
        return 2
    notes: list[str] = []
    seen: list[str] = []
    problems = check_packs_dir(args.packs_dir, notes, seen)
    newest = ""
    if seen:
        try:
            from datetime import datetime, timezone, timedelta
            ts = max((args.packs_dir / n).stat().st_mtime for n in seen)
            msk = datetime.fromtimestamp(ts, timezone(timedelta(hours=3)))
            newest = f", свежайший {msk:%d.%m %H:%M} МСК"
        except OSError:
            newest = ""
    scope = f"судил {len(seen)} паков в {args.packs_dir}{newest}"
    # Заметки печатаем ВСЕГДА, в том числе на чистом прогоне: их смысл ровно в том, чтобы
    # пропуск проверки было видно. На код возврата они не влияют.
    for nt in notes:
        print(f"  ~ {nt}")
    print(scope)
    if not problems:
        print(f"OK: формат по канону <agent> ({CANON})")
        return 0
    print(f"ФОРМАТ НЕ ПО КАНОНУ ({CANON}) — {len(problems)} флагов:")
    for pr in problems:
        print(f"  · {pr}")
    return 10


if __name__ == "__main__":
    sys.exit(main())
