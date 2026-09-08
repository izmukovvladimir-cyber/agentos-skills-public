#!/usr/bin/env python3
"""lib_embed.py — общий embedding-хелпер для theme-дедупа niche-reels.

Локальный FastEmbed (CPU, без внешних API-ключей). Модель multilingual (RU+EN),
имя берётся из config/watchlist.json:limits.theme_model. Запускать ТОЛЬКО через
.venv-embed/bin/python — в системном python3 fastembed не установлен.

Используется dedupe_filter.py (read-side: сравнение тем) и mark_shown.py
(write-side: эмбеддинг показанных тем в историю). Один и тот же модель-неймспейс
обязателен для обеих сторон — иначе косинус несравним.
"""
from __future__ import annotations

import logging
import math
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger("lib_embed")

# Маркер уже случившегося перезапуска: без него неверный путь к интерпретатору дал бы
# бесконечный exec самого себя.
_REEXEC_ENV = "NRR_EMBED_REEXEC"
VENV_PYTHON = Path(__file__).resolve().parent.parent / ".venv-embed" / "bin" / "python"


def _fatal(msg: str) -> None:
    """Ранний отказ с внятным текстом вместо трейсбека: сообщение читает агент, не человек."""
    log.error("%s", msg)
    raise SystemExit(1)


def reexec_in_venv(script: Path) -> None:
    """Перезапустить скрипт интерпретатором .venv-embed, если fastembed недоступен.

    Зачем: инструкция утреннего триггера и клиентские CLAUDE.md говорят «python3 mark_shown.py»,
    а fastembed стоит только в .venv-embed. Под системным python3 скрипт падал на импорте
    ВНУТРИ прогона, уже после того как подборка ушла клиенту, и история дедупа не обновлялась
    вовсе (ни коды, ни темы: эмбеддинги считаются ДО записи). На следующее утро агент выдавал
    те же ролики по второму кругу. Заявка <agent> 31.07.

    Чинить решено здесь, а не в тексте инструкций: команда «python3 <скрипт>» живёт в SKILL.md,
    в каноне формата и в CLAUDE.md семи агентов, и будет появляться снова. Самоперезапуск
    делает правильной ЛЮБУЮ из этих формулировок.

    Правило ровно одно: ОДИН автоматический переход в venv, а при любой невозможности туда
    попасть — немедленный отказ с кодом 1. Тихо продолжать нельзя: продолжение и есть та самая
    авария, ради которой всё чинится, просто отложенная до момента после доставки.

    script — путь к запускаемому файлу, передаётся явно (Path(__file__) вызывающего). Через
    sys.argv[0] контракт был бы верен только для прямого запуска из CLI.
    Вызывать ПЕРВОЙ строкой main(), до разбора аргументов и до любого чтения."""
    try:
        import fastembed  # noqa: F401
        return
    except ImportError as exc:
        why = exc
    if os.environ.get(_REEXEC_ENV):
        _fatal(f"fastembed недоступен даже после перезапуска через {VENV_PYTHON} ({why}). "
               f"Проверь venv: {VENV_PYTHON} -c 'import fastembed'")
    if not VENV_PYTHON.is_file():
        _fatal(f"fastembed недоступен, а интерпретатор {VENV_PYTHON} не найден ({why}). "
               f"Без него история дедупа не обновится, подборка завтра повторится")
    env = dict(os.environ, **{_REEXEC_ENV: "1"})
    target = str(Path(script).resolve())
    log.info("перезапуск через %s (fastembed нет в текущем интерпретаторе)", VENV_PYTHON)
    try:
        os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), target, *sys.argv[1:]], env)
    except OSError as exc:
        # is_file() не обещает исполнимость: битый симлинк, нет прав, сломанный loader.
        _fatal(f"не удалось запустить {VENV_PYTHON}: {exc}")

# multilingual-e5-large: 1024-dim, ~2.2GB. Выбрана за сильный кросс-язык RU<->EN
# (watchlist наполовину EN + мы переводим EN->RU). paraphrase-MiniLM на наших темах
# давал плохую разделимость (SAME-пары проваливались ниже DIFF-пар) — отвергнут.
DEFAULT_MODEL = "intfloat/multilingual-e5-large"
# e5-семейство требует префикс "query:"; paraphrase/MiniLM — нет.
_E5_PREFIX = "query: "


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    """Ленивая загрузка FastEmbed-модели (кэш по имени). Холодный старт ~3с для e5-small."""
    from fastembed import TextEmbedding  # импорт внутри: модуль есть только в .venv-embed

    log.info("loading FastEmbed model: %s", model_name)
    return TextEmbedding(model_name)


def _prep(text: str, model_name: str) -> str:
    """Нормализация темы: префикс (только для e5) + срез до 512 символов."""
    clean = (text or "").strip().replace("\n", " ")[:512]
    return (_E5_PREFIX + clean) if "e5" in model_name.lower() else clean


def embed_texts(texts: Sequence[str], model_name: str = DEFAULT_MODEL) -> list[list[float]]:
    """Эмбеддинги списка тем. Возвращает list[vector]. Пустой вход → []."""
    items = [_prep(t, model_name) for t in texts]
    if not items:
        return []
    model = _load_model(model_name)
    return [vec.tolist() for vec in model.embed(items)]


def embed_one(text: str, model_name: str = DEFAULT_MODEL) -> list[float]:
    """Эмбеддинг одной темы."""
    out = embed_texts([text], model_name)
    return out[0] if out else []


def is_vector(v: Any) -> bool:
    """True если v — непустой список/кортеж чисел (не bool). Защита от битых embedding в истории."""
    return (
        isinstance(v, (list, tuple))
        and len(v) > 0
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Косинусная близость двух векторов. 0.0 если любой пустой или нулевой нормы."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def max_cosine(vec: Sequence[float], pool: Sequence[Sequence[float]]) -> float:
    """Максимальный косинус vec против пула векторов. 0.0 для пустого пула."""
    best = 0.0
    for other in pool:
        c = cosine(vec, other)
        if c > best:
            best = c
    return best
