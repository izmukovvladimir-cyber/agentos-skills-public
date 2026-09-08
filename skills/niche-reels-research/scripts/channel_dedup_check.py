#!/usr/bin/env python3
"""channel_dedup_check.py — PRE-FINALIZE анти-повтор смыслов для постов @your_channel.

Назначение (отдельное от theme-дедупа niche-reels): перед отправкой владелец на
review прогнать черновик поста против последних N постов канала и свежего архива
ниши. Цель — НЕ выпустить смысл или кейс, который уже выходил в канале. Правило
владельца простое: один смысл выходит один раз.

Две проверки:
  A. CHANNEL REPEAT — семантика (e5 cosine) + литеральное пересечение сущностей
     (имена кейсов, отличительные числа) черновика против истории канала.
  B. STALE CASE — кейсы берутся ТОЛЬКО из свежего архива ниши. Имена и числа
     из черновика, которых нет в источнике за последние RILS_DAYS дней,
     помечаются как подозрительные. Явный блок-лист уже использованных кейсов
     (config/used_cases.json) — жёсткий флаг.

Это ФЛАГ, не хард-блок: финальное решение за <agent> + владелец (review). Ложный
DROP хорошего поста дороже ложного KEEP — пороги консервативные.

Запуск ТОЛЬКО через .venv-embed/bin/python (нужен fastembed из lib_embed).
Вход: черновик через --draft-file PATH или stdin.
Выход: человекочитаемый verdict в stdout. Exit 0 = чисто, 10 = есть флаги.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import lib_embed

log = logging.getLogger("channel_dedup_check")

# Свой канал: числовой id без префикса -100, задаётся переменной OWNER_CHANNEL_ID.
CHANNEL_CHAT_ID = os.environ.get("OWNER_CHANNEL_ID", "")
CHIP_URL = f"http://127.0.0.1:18080/chats/{CHANNEL_CHAT_ID}/messages"
CHANNEL_LIMIT = 60
# Архив ниши: выгрузка чата или канала, по файлу <дата>.jsonl на день.
# Свой путь задаётся переменной NICHE_ARCHIVE_DIR.
RILS_DIR = Path(os.environ.get("NICHE_ARCHIVE_DIR", "~/niche-archive"))
RILS_DAYS = 5
HTTP_TIMEOUT = 12

# e5-large даёт высокий within-domain baseline (CTA-boilerplate ~0.84-0.85, см.
# decisions.md). Порог повтора СМЫСЛА поста консервативный: ловит парафраз темы,
# не режет разные посты с общим CTA-хвостом.
COSINE_FLAG = 0.90
# Отличительное число: >=3 цифр (счётчики подписчиков, просмотров). Короткие (дни, %) шумят.
MIN_DIGITS = 3

# Уже использованные кейсы владельца: годятся только для лендинга, НЕ для
# постов канала. Жёсткий флаг при появлении в черновике. Список свой у каждого,
# ведётся в config/used_cases.json рядом со скиллом. Файла нет — проверка молчит.
def _load_used_cases() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read the owner's own list of already-spent cases. Empty when absent."""
    cfg = Path(__file__).resolve().parent.parent / "config" / "used_cases.json"
    if not cfg.is_file():
        return (), ()
    with cfg.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return tuple(data.get("names", ())), tuple(str(n) for n in data.get("numbers", ()))


USED_CASE_NAMES, USED_CASE_NUMBERS = _load_used_cases()

MSK = timezone(timedelta(hours=3))

_NAME_RE = re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+")
_NUM_RE = re.compile(r"\d[\d\s.,]*\d|\d")


@dataclass
class Verdict:
    """Итог проверки. flags непустой → возможный повтор, нужен взгляд <agent>."""

    channel_posts: int = 0
    rils_msgs: int = 0
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalize_number(raw: str) -> str:
    """Срезать пробелы/разделители тысяч, оставить только цифры."""
    return re.sub(r"[\s.,]", "", raw)


def extract_numbers(text: str) -> set[str]:
    """Отличительные числа (>=MIN_DIGITS цифр) из текста."""
    out: set[str] = set()
    for m in _NUM_RE.finditer(text):
        n = _normalize_number(m.group(0))
        if len(n) >= MIN_DIGITS:
            out.add(n)
    return out


def extract_names(text: str) -> set[str]:
    """Кандидаты в имена кейсов: «Имя Фамилия» (две заглавных-строчных группы)."""
    return {m.group(0) for m in _NAME_RE.finditer(text)}


def fetch_channel_posts() -> list[str]:
    """Последние посты канала через telegram-chip. Возвращает список тел сообщений.

    Raises:
        RuntimeError: если chip недоступен или ответ невалиден — пайплайн должен
            знать, что проверка не отработала (fail-loud), а не молча пропустить.
    """
    url = f"{CHIP_URL}?limit={CHANNEL_LIMIT}"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"telegram-chip недоступен ({url}): {exc}") from exc

    if not payload.get("success"):
        raise RuntimeError(f"telegram-chip вернул success=false: {payload.get('error')}")

    data = payload.get("data") or ""
    parts = re.split(r"(?m)^(?=ID:\s*\d+\s*\|)", data)
    msgs: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.search(r"\|\s*Message:\s*(.*)\Z", part, re.S)
        if m:
            body = m.group(1).strip()
            if body:
                msgs.append(body)
    return msgs


def load_niche_archive_recent(days: int = RILS_DAYS) -> list[str]:
    """Тексты сообщений архива ниши за последние `days` дней (по имени файла <date>.jsonl)."""
    if not RILS_DIR.is_dir():
        log.warning("niche archive dir missing: %s", RILS_DIR)
        return []
    cutoff = (datetime.now(MSK) - timedelta(days=days)).date()
    texts: list[str] = []
    for fp in sorted(RILS_DIR.glob("*.jsonl")):
        try:
            file_date = datetime.strptime(fp.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        try:
            with fp.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    txt = (rec.get("text") or "").strip()
                    if txt:
                        texts.append(txt)
        except OSError as exc:
            log.warning("niche archive file unreadable, skip: %s (%s)", fp, exc)
            continue
    return texts


def check_channel_repeat(draft: str, posts: list[str], verdict: Verdict) -> None:
    """CHECK A — семантический + литеральный повтор черновика против истории канала."""
    if not posts:
        verdict.notes.append("Канал пуст или chip ничего не вернул — проверку A пропускаю.")
        return

    draft_nums = extract_numbers(draft)
    draft_names = extract_names(draft)

    # Литеральное пересечение: общее имя кейса или отличительное число = сильный сигнал.
    for idx, post in enumerate(posts, 1):
        shared_names = draft_names & extract_names(post)
        shared_nums = draft_nums & extract_numbers(post)
        if shared_names or shared_nums:
            bits = []
            if shared_names:
                bits.append(f"имена={sorted(shared_names)}")
            if shared_nums:
                bits.append(f"числа={sorted(shared_nums)}")
            verdict.flags.append(
                f"[A/литерал] пост канала #{idx} делит с черновиком {', '.join(bits)} "
                f"— возможный повтор кейса. Пост: «{post[:120]}…»"
            )

    # Семантика: cosine черновика против каждого поста. Модель может упасть
    # (загрузка/OOM/битые векторы) — не роняем весь чек, помечаем флагом.
    try:
        vecs = lib_embed.embed_texts([draft, *posts])
    except Exception as exc:  # fastembed внутр. ошибки не типизированы
        verdict.flags.append(f"[A/ОШИБКА] embedding не отработал ({exc}). Проверь смыслы вручную.")
        return
    if not vecs or not lib_embed.is_vector(vecs[0]):
        verdict.notes.append("Embedding черновика пуст/битый — семантическую часть A пропускаю.")
        return
    draft_vec = vecs[0]
    for idx, vec in enumerate(vecs[1:], 1):
        if not lib_embed.is_vector(vec):
            continue
        c = lib_embed.cosine(draft_vec, vec)
        if c >= COSINE_FLAG:
            verdict.flags.append(
                f"[A/смысл] пост канала #{idx} близок по смыслу (cosine={c:.3f} ≥ {COSINE_FLAG}) "
                f"— возможный повтор. Пост: «{posts[idx - 1][:120]}…»"
            )


def check_stale_case(draft: str, rils_texts: list[str], verdict: Verdict) -> None:
    """CHECK B — кейсы только из свежего архива ниши + блок-лист использованных."""
    draft_names = extract_names(draft)
    draft_nums = extract_numbers(draft)

    # Жёсткий блок-лист: явно использованные кейсы.
    for name in USED_CASE_NAMES:
        if name.lower() in draft.lower():
            verdict.flags.append(
                f"[B/использован] кейс «{name}» уже выходил (только для лендинга, НЕ для поста)."
            )
    for num in USED_CASE_NUMBERS:
        if num in draft_nums:
            verdict.flags.append(
                f"[B/использован] число {num} принадлежит использованному кейсу "
                f"(Анна/Кристина/Анастасия) — вероятно стале-память."
            )

    # Soft: имя ИЛИ метрика-число из черновика, которых нет в свежем архиве ниши →
    # не подтверждённый кейс (ловит стале-кейс и без ФИО — только по старому числу).
    if rils_texts:
        rils_blob = "\n".join(rils_texts)
        rils_nums = extract_numbers(rils_blob)
        for name in draft_names:
            if name not in rils_blob:
                verdict.notes.append(
                    f"[B/проверь] имя «{name}» из черновика НЕ найдено в свежем архиве ниши "
                    f"(последние {RILS_DAYS} дней). Если это кейс — подтверди, что он свежий, "
                    f"а не из памяти/TOV."
                )
        # Метрика-число: >=4 цифр, не год (19xx/20xx). Год-подобные шумят, исключаем.
        metric_nums = {
            n for n in draft_nums
            if len(n) >= 4 and not (len(n) == 4 and n.startswith(("19", "20")))
        }
        unconfirmed = sorted(metric_nums - rils_nums)
        if unconfirmed:
            verdict.notes.append(
                f"[B/проверь] числа {unconfirmed} из черновика НЕ найдены в свежем архиве ниши. "
                f"Если это метрики кейса — подтверди свежесть, иначе вероятна стале-память."
            )
    else:
        verdict.notes.append(
            f"Архив ниши за {RILS_DAYS} дней пуст — не могу подтвердить свежесть кейсов из черновика."
        )


def run(draft: str) -> Verdict:
    """Полная проверка черновика. Никогда не падает молча — chip-ошибка как нота/flag."""
    verdict = Verdict()
    try:
        posts = fetch_channel_posts()
    except RuntimeError as exc:
        verdict.flags.append(f"[A/ОШИБКА] не смог прочитать канал: {exc}. Проверь смыслы вручную.")
        posts = []
    verdict.channel_posts = len(posts)

    rils_texts = load_niche_archive_recent()
    verdict.rils_msgs = len(rils_texts)

    check_channel_repeat(draft, posts, verdict)
    check_stale_case(draft, rils_texts, verdict)
    return verdict


def format_report(verdict: Verdict) -> str:
    """Verdict → текст для <agent>."""
    lines = [
        "=== CHANNEL DEDUP CHECK (@your_channel) ===",
        f"Проверено постов канала: {verdict.channel_posts} | сообщений архива ниши: {verdict.rils_msgs}",
    ]
    if verdict.flags:
        lines.append("")
        lines.append(f"⚠ ВОЗМОЖНЫЙ ПОВТОР СМЫСЛА — {len(verdict.flags)} флаг(ов), проверь ДО отправки владельцу:")
        lines.extend(f"  • {f}" for f in verdict.flags)
    else:
        lines.append("")
        lines.append("✓ Повторов смысла против канала не найдено.")
    if verdict.notes:
        lines.append("")
        lines.append("Заметки (не блок, к сведению):")
        lines.extend(f"  - {n}" for n in verdict.notes)
    lines.append("")
    lines.append(
        "ВЕРДИКТ: " + ("ПРОВЕРЬ ФЛАГИ перед отправкой." if verdict.flags else "чисто, можно финализировать.")
    )
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="PRE-FINALIZE анти-повтор смыслов для @your_channel.")
    parser.add_argument("--draft-file", type=Path, help="Путь к файлу с черновиком поста. Иначе stdin.")
    args = parser.parse_args()

    if args.draft_file:
        if not args.draft_file.is_file():
            print(f"missing: {args.draft_file}", file=sys.stderr)
            return 2
        draft = args.draft_file.read_text(encoding="utf-8").strip()
    else:
        draft = sys.stdin.read().strip()

    if not draft:
        print("пустой черновик — нечего проверять", file=sys.stderr)
        return 2

    verdict = run(draft)
    print(format_report(verdict))
    return 10 if verdict.flags else 0


if __name__ == "__main__":
    raise SystemExit(main())
