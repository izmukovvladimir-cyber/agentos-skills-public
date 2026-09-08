#!/usr/bin/env python3
"""send_morning_digest.py — утренний пакет niche-reels как ДВЕ HTML-презентации.

владелец  (HARD, 3-й повтор → эскалация): НЕ поток из 20-30 сообщений,
а ДВЕ отдельные HTML-презентации (рилсы + карусели) + короткая сводка в чат +
оба .html через sendDocument. См. память feedback-morning-pack-as-html-presentations.

Вход: --packs-dir (default = lib_paths.packs_dir(): owner→SKILL_DIR/packs,
  client→<NRR_CLIENT_DIR>/pool/packs) с файлами pack_*.json.
  reel-pack:     keys author_username, topic, url|link, card, teleprompter, editor_brief, [caption]
  carousel-pack: те же + "type" == "carousel".
Опционально meta.json в той же папке: {"date_label": "...", ...}.

Выход (в OUT_DIR, по умолчанию assets/montage):
  reels_<YYYYMMDD>.html, carousels_<YYYYMMDD>.html
Доставка владельцу:
  короткая сводка (plain) -> sendDocument(reels.html) -> sendDocument(carousels.html).

--dry-run: только собрать HTML и напечатать пути, без отправки.
--force:   отправить вопреки блокирующему нарушению (только с ведома владельца).

Exit: 0 = отправлено (или собрано в --dry-run); 1 = нет токена/паков; 2 = часть отправки
не прошла; 10 = ОТПРАВКА ЗАБЛОКИРОВАНА: переписан хук оригинала либо формат не по канону.
Гейт работает и в --dry-run: это и есть сигнал агенту «так выдавать нельзя».
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

log = logging.getLogger("digest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Токен бота и chat id получателя читаются из окружения:
#   export TELEGRAM_BOT_TOKEN=...   export TELEGRAM_CHAT_ID=...
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy paths
# (shared /tmp pool + <agent> assets), so <agent>'s flow is byte-identical.
DEFAULT_PACKS_DIR = lib_paths.packs_dir()  # board #56: owner reads SKILL_DIR/packs (where gen_packs writes), not the stale /tmp/expand_pool/reels/packs; clients unchanged (their pool/packs)
DEFAULT_OUT_DIR = lib_paths.out_dir()
MSK = timezone(timedelta(hours=3))
SEND_GAP_SEC = 0.8

# Единый источник правды по объёму пакета (см. daria-morning-trigger.sh):
# config/watchlist.json:limits. Минимум каруселей — механический guard ниже.
CONFIG_FILE = lib_paths.config_file()
CAROUSEL_MIN_FALLBACK = 5

# PROTECTED-виралки (флаг пишут score.py → _scored.json, pull_carousels.py →
# _carousels_scored.json). Бэкстоп: если сильнейший рилс/карусель дня не вошёл в
# пак — громкий WARN (<agent> видит, даже если LLM Блока А срезал дедупом).
SCORED_FILE = lib_paths.pool_dir() / "_scored.json"
CAROUSELS_SCORED_FILE = lib_paths.pool_dir() / "_carousels_scored.json"

# Покрытие скрейпа (пишет pull_reels.py). Для строки «X из N аккаунтов».
COVERAGE_FILE = lib_paths.pool_dir() / "_coverage.json"
ACCOUNT_SUMMARY_FILE = lib_paths.pool_dir() / "_top3_per_account.json"
# Старше окна = данные не от текущего скрейпа (ручной запуск дайджеста без свежего
# прогона). Не показываем устаревшие цифры как актуальные — лучше без строки.
COVERAGE_MAX_AGE_SEC = 8 * 3600


# Тексты нарушений живут в константах ради единообразия сообщений агентам.
# РЕШЕНИЕ «не отправлять» принимается НЕ по тексту: сообщение о сбое проверки может содержать
# чужой stderr с этими же словами и заблокировало бы живого клиента на пустом месте.
HOOK_VIOLATION_MARK = "переписан ХУК"
FORMAT_VIOLATION_MARK = "ФОРМАТ НЕ ПО КАНОНУ"


class CheckResult(NamedTuple):
    """text — что показать агенту, violated — ДОКАЗАННОЕ нарушение (только оно блокирует)."""
    text: str
    violated: bool = False


def check_broken_warn(name: str, reason: str) -> CheckResult:
    """Проверка не отработала — это НЕ то же самое, что «замечаний нет».

    все бэкстопы ниже fail-open, то есть при любом сбое возвращали пустую строку.
    Сводка выглядела чистой и когда всё в порядке, и когда проверка упала или не запустилась.
    Ровно этот класс дыр стоил нам 4 дней выдуманных телесуфлёров. Доставку по-прежнему не
    ломаем, но молчать о неотработавшей проверке нельзя."""
    log.error("CHECK BROKEN: %s (%s)", name, reason)
    return CheckResult(
        f"⚠️⚠️ ПРОВЕРКА НЕ ОТРАБОТАЛА: {name} ({reason}). Это НЕ «замечаний нет»: "
        f"подборка НЕ проверена, проверь руками ДО отправки и скажи <agent>.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n",
        violated=False,      # сбой проверки НЕ равен нарушению: доставку не блокируем
    )


# Токен строки пропуска по донору формата. Контракт с hook_fidelity_check.DONOR_SKIP_TOKEN:
# два процесса, общий литерал; менять только в обоих файлах сразу (тест это проверяет).
HOOK_DONOR_TOKEN = "[skip:format_donor]"


def hook_fidelity_warn(packs_dir: Path) -> CheckResult:
    """Бэкстоп: телесуфлёр обязан хранить хук оригинала.
    Прогоняет hook_fidelity_check.py; если по рилсу хук переписан — громкий WARN в сводку.
    Доставку не ломает, но о собственном сбое сообщает (check_broken_warn)."""
    try:
        checker = Path(__file__).resolve().parent / "hook_fidelity_check.py"
        if not checker.exists():
            return check_broken_warn("hook_fidelity_check", f"нет файла {checker.name}")
        r = subprocess.run(
            [sys.executable, str(checker),
             # reels-dir = the POOL dir (transcripts + work/ live there), NOT packs_dir.parent:
             # since board #56 the owner's packs sit in SKILL_DIR/packs whose parent is NOT the pool,
             # so deriving from packs_dir would point the transcript scan at the wrong tree and the
             # (fail-open) backstop would silently go quiet. pool_dir() is correct for owner+client.
             "--packs-dir", str(packs_dir), "--reels-dir", str(lib_paths.pool_dir())],
            capture_output=True, text=True, timeout=120,
        )
        # 0 = чисто, 10 = есть флаги. Всё остальное это сбой самой проверки, а не «чисто»:
        # раньше упавший чекер (код 1/2, трейсбек) читался как «хук на месте».
        if r.returncode not in (0, 10):
            tail = ((r.stderr or r.stdout or "").strip().splitlines() or ["без вывода"])[-1]
            return check_broken_warn("hook_fidelity_check",
                                     f"код возврата {r.returncode}: {tail[:160]}")
        # Донор ФОРМАТА: гейт такую карточку НЕ судит (правило куратора 27.07, речь
        # оригинала это чужие марки). Молчать об этом нельзя — снятие гейта обязано быть
        # видно в сводке, поэтому причина печатается и при чистом прогоне. Токен — контракт
        # с hook_fidelity_check.py (DONOR_SKIP_TOKEN), менять только в обоих файлах сразу.
        donors = [ln.split(maxsplit=1)[1].strip()
                  for ln in (r.stdout or "").splitlines()
                  if ln.startswith(HOOK_DONOR_TOKEN) and len(ln.split(maxsplit=1)) > 1]
        donor_note = ""
        if donors:
            log.info("FORMAT DONOR (гейт хука не судит): %s", "; ".join(donors))
            donor_note = (
                f"ℹ️ ДОНОР ФОРМАТА — перенос хука НЕ проверялся у {len(donors)} шт.: "
                + "; ".join(donors)
                + "\nСнято по пометке в паке (правило куратора 27.07), причина названа автором "
                  "карточки. Гейт этого не подтверждал.\n"
                  "━━━━━━━━━━━━━━━━━━━━\n\n")
        if r.returncode == 0:
            return CheckResult(donor_note)
        flagged = [ln.split()[1] for ln in (r.stdout or "").splitlines()
                   if ln.startswith("[FLAG]") and len(ln.split()) > 1]
        names = ", ".join(flagged) if flagged else "см. лог"
        log.warning("HOOK REWRITTEN in: %s", names)
        return CheckResult(
            donor_note +
            f"⚠️⚠️ ВНИМАНИЕ: в телесуфлёре {HOOK_VIOLATION_MARK} ({names}) — верни хук оригинала "
            f"почти дословно (рерайт ≤25%, меняй только табу/ники/кодворд), пересобери ДО отправки.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n",
            violated=True,
        )
    except Exception as exc:  # бэкстоп НИКОГДА не должен ронять доставку дайджеста
        return check_broken_warn("hook_fidelity_check", f"{type(exc).__name__}: {exc}"[:160])


def _code_from_url(url) -> str:
    # рилсы /reel/CODE/, карусели /p/CODE/
    m = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", str(url or ""))
    return m.group(1) if m else ""


def _protected_codes(scored_file: Path, *, required: bool = True) -> dict[str, str] | None:
    """{code: username} из protected-записей scored-файла.

    None = файл не прочитан или не той формы (проверка не отработала). Пустой словарь =
    файл прочитан, protected-элементов в нём нет. Раньше оба случая давали {} и сбой чтения
    был неотличим от честного «сильнейших сегодня нет».

    required=False (инстанс без каруселей): ОТСУТСТВИЕ файла — норма, а не сбой. Битая форма
    существующего файла остаётся сбоем: раз файл написан, его писал скрейп."""
    if not scored_file.exists():
        return None if required else {}   # ручной прогон без свежего скрейпа
    try:
        data = json.loads(scored_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    out: dict[str, str] = {}
    for s in data:
        if isinstance(s, dict) and s.get("protected"):
            code = s.get("code") or _code_from_url(s.get("url"))
            if code:
                out[code] = s.get("username") or "?"
    return out


def protected_missing_warn(packs: list[dict]) -> CheckResult:
    """Бэкстоп (владелец/<agent> , косяк 27.06): сильнейший рилс/карусель дня
    обязан войти в пак. Берёт protected-коды из _scored.json (score.py) и
    _carousels_scored.json (pull_carousels.py); если protected-элемент НЕ в паке —
    громкий WARN (<agent> видит, даже если LLM Блока А его срезал дедупом). Зеркало
    carousel/hook warn. Доставку не ломает, но о собственном сбое сообщает: нечитаемый
    scored-файл больше не выглядит как честное «сильнейших сегодня нет»."""
    try:
        car_required = carousels_enabled()
        reels_prot = _protected_codes(SCORED_FILE)
        car_prot = _protected_codes(CAROUSELS_SCORED_FILE, required=car_required)
        unread = [f.name for f, v in ((SCORED_FILE, reels_prot),
                                      (CAROUSELS_SCORED_FILE, car_prot)) if v is None]
        if unread:
            return check_broken_warn("protected-бэкстоп",
                                     f"не прочитан {', '.join(unread)} — сильнейшее дня не сверено")
        prot = {**reels_prot, **car_prot}
        if not prot:
            return CheckResult("")
        pack_codes = {c for p in packs if isinstance(p, dict)
                      for c in [p.get("code") or _code_from_url(p.get("url"))] if c}
        missing = [(c, u) for c, u in prot.items() if c not in pack_codes]
        if not missing:
            return CheckResult("")
        names = ", ".join(f"@{u} {c}" for c, u in missing)
        log.warning("PROTECTED items missing from packs: %s", names)
        # Совещательный бэкстоп: это про полноту отбора, а не про негодный материал.
        # Отправку НЕ блокирует намеренно.
        return CheckResult(
            f"⚠️⚠️ ВНИМАНИЕ: protected-виралка НЕ вошла в пак ({names}) — это сильнейший "
            f"рилс/карусель дня (иммунен к author/theme-дедупу). Верни в пак ДО отправки владельцу.\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )
    except Exception as exc:  # бэкстоп НИКОГДА не должен ронять доставку дайджеста
        return check_broken_warn("protected-бэкстоп", f"{type(exc).__name__}: {exc}"[:160])


def format_canon_warn(packs: list[dict], meta: dict, bad: list[str]) -> CheckResult:
    """Гейт «формат <agent> 1 в 1» : паки/meta
    обязаны соответствовать канону references/digest_format_canon.md — иначе
    громкий WARN в сводку (агент видит и чинит ДО выдачи клиенту, без напоминаний).
    Механика — digest_format_check.py. Доставку не ломает, о собственном сбое сообщает."""
    try:
        import digest_format_check as dfc
        # Проверяем ТОТ ЖЕ снимок, из которого собран HTML (без повторного чтения диска),
        # плюс явные проблемы чтения из load_packs: нечитаемый пак это дефект подборки,
        # а не «его просто нет».
        # notes — НЕблокирующие следы (пропуск проверки транскрипта по пометке «без речи»).
        # Показываем их и на чистом прогоне: молчаливый пропуск снаружи неотличим от
        # «проверено и чисто», а ошибочная пометка на говорящем ролике ловится только глазами.
        notes: list[str] = []
        problems = list(bad) + dfc.check_packs(
            [p for p in packs if isinstance(p, dict)], meta, notes)
        trace = ""
        if notes:
            trace = ("ℹ️ Пропущена проверка транскрипта (пометка «без речи»), это НЕ нарушение:\n"
                     + "\n".join(f"  ~ {x}" for x in notes[:10])
                     + (f"\n  … и ещё {len(notes) - 10}" if len(notes) > 10 else "")
                     + "\nЕсли речь в ролике всё же есть, сними пометку и пересобери.\n"
                     + "━━━━━━━━━━━━━━━━━━━━\n\n")
        if not problems:
            return CheckResult(trace)
        log.warning("FORMAT canon violated (%d flags)", len(problems))
        shown = "\n".join(f"  · {x}" for x in problems[:10])
        more = f"\n  … и ещё {len(problems) - 10}" if len(problems) > 10 else ""
        return CheckResult(
            f"{trace}"
            f"⚠️⚠️ {FORMAT_VIOLATION_MARK} КАНОНА ({len(problems)} флагов) — исправь паки и "
            f"пересобери ДО отправки клиенту. Канон: references/digest_format_canon.md\n"
            f"{shown}{more}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n",
            violated=True,
        )
    except Exception as exc:  # бэкстоп НИКОГДА не должен ронять доставку дайджеста
        return check_broken_warn("digest_format_check", f"{type(exc).__name__}: {exc}"[:160])


def carousels_enabled() -> bool:
    """False = инстанс не собирает карусели вовсе (pull_carousels.py не в его цепочке).

    Заявка <agent> : у клиентского инстанса без каруселей protected-бэкстоп
    падал КАЖДЫЙ день («не прочитан _carousels_scored.json»), и его предупреждение перестало
    что-либо значить. Разделяем два случая: файла нет, потому что каруселей тут нет (норма,
    сверяем по рилсам) и файла нет, потому что скрейп упал (поломка, кричим).

    Выключается ТОЛЬКО явным limits.carousels_enabled = false (JSON false, не строка).
    Отсутствие ключа, мусор в значении, нечитаемый конфиг — всё даёт True: неизвестность
    обязана ОСТАВЛЯТЬ проверку включённой, иначе опечатка в конфиге молча снимает бэкстоп
    сильнейшего дня. Существующий, но битый scored-файл остаётся сбоем при любом значении."""
    try:
        limits = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("limits", {})
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return True
    if not isinstance(limits, dict):
        return True
    return limits.get("carousels_enabled") is not False


def carousel_min() -> int:
    """Минимум каруселей из config; при любой ошибке — безопасный fallback (5)."""
    try:
        limits = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("limits", {})
        return int(limits.get("carousel_min", CAROUSEL_MIN_FALLBACK))
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return CAROUSEL_MIN_FALLBACK

def _fresh(path: Path) -> bool:
    """Файл существует и обновлён в пределах окна (mtime) — данные текущего прогона."""
    try:
        return (time.time() - path.stat().st_mtime) <= COVERAGE_MAX_AGE_SEC
    except OSError:
        return False


def _str_list(v) -> list[str]:
    return [x for x in v if isinstance(x, str) and x] if isinstance(v, list) else []


def coverage_line() -> str:
    """Строка покрытия скрейпа для сводки: «X из N аккаунтов; упали: …».

    Источник правды — _coverage.json (pull_reels.py). Фоллбэк — per-account summary
    (_top3_per_account.json). Любая ошибка / отсутствие / устаревшие данные (старше
    COVERAGE_MAX_AGE_SEC) / битая структура → пустая строка: <agent> может гонять
    дайджест вручную без свежего скрейпа — не ломаем его и не показываем stale-цифры.
    """
    ok = total = None
    failed: list[str] = []
    recovered: list[str] = []
    try:
        if not _fresh(COVERAGE_FILE):
            raise ValueError("stale or missing coverage")
        cov = json.loads(COVERAGE_FILE.read_text(encoding="utf-8"))
        if not isinstance(cov, dict):
            raise ValueError("coverage not a dict")
        total = int(cov["total"])
        ok = int(cov["ok"])
        fl = cov.get("failed", [])
        failed = [f.get("username") for f in fl
                  if isinstance(f, dict) and f.get("username")] if isinstance(fl, list) else []
        recovered = _str_list(cov.get("recovered_on_retry", []))
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError):
        failed, recovered = [], []
        try:
            if not _fresh(ACCOUNT_SUMMARY_FILE):
                return ""
            summ = json.loads(ACCOUNT_SUMMARY_FILE.read_text(encoding="utf-8"))
            if not isinstance(summ, list):
                return ""
            total = len(summ)
            ok = sum(1 for s in summ if isinstance(s, dict) and not s.get("error"))
            failed = [s.get("username") for s in summ
                      if isinstance(s, dict) and s.get("error") and s.get("username")]
        except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return ""
    if total is None or ok is None:
        return ""
    line = f"📡 Скрейп: {ok} из {total} аккаунтов"
    if failed:
        shown = ", ".join(failed[:20])
        more = f" (+{len(failed) - 20})" if len(failed) > 20 else ""
        line += f"; упали: {shown}{more}"
    else:
        line += ", все успешно"
    if recovered:
        line += f"\n   ↻ добраны ретраем: {', '.join(recovered[:20])}"
    return line


RU_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# --- HTML (форк утверждённого стиля morning_pack ) -------------------

HEAD = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root {{ --bg:#0f1115; --card:#171a21; --line:#262b35; --txt:#e8ebf0; --mut:#9aa3b2; --acc:#d8b24a; --acc2:#5fb0ff; }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; background:var(--bg); color:var(--txt); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:24px; }}
.wrap {{ max-width:820px; margin:0 auto; }}
h1 {{ font-size:24px; margin:0 0 6px; }}
.sub {{ color:var(--mut); font-size:14px; margin:0 0 20px; }}
.toc {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 20px; margin-bottom:26px; }}
.toc-h {{ font-size:12px; font-weight:700; letter-spacing:.6px; text-transform:uppercase; color:var(--acc); margin-bottom:10px; }}
.toc a {{ display:block; color:var(--acc2); text-decoration:none; font-size:14px; padding:6px 0; border-bottom:1px solid var(--line); }}
.toc a:last-child {{ border-bottom:none; }}
.toc a:hover {{ color:var(--acc); }}
.up {{ display:inline-block; margin-top:14px; font-size:12px; color:var(--mut); text-decoration:none; }}
.sec {{ font-size:13px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:var(--acc); margin:32px 0 14px; border-top:1px solid var(--line); padding-top:18px; }}
.reel {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:22px 24px; margin-bottom:22px; }}
.tag {{ display:inline-block; font-size:12px; font-weight:700; letter-spacing:.4px; color:#0f1115; background:var(--acc); padding:3px 10px; border-radius:6px; }}
h2 {{ font-size:18px; margin:12px 0 4px; }}
a.ref {{ color:var(--acc2); font-size:13px; word-break:break-all; }}
.block {{ margin-top:16px; }}
.label {{ font-size:12px; font-weight:700; letter-spacing:.5px; color:var(--acc); text-transform:uppercase; margin-bottom:6px; }}
.hook {{ background:#1f2330; border-left:3px solid var(--acc); padding:12px 14px; border-radius:8px; font-size:15px; white-space:pre-wrap; }}
.brief {{ white-space:pre-wrap; background:#12151c; border:1px dashed var(--line); border-radius:8px; padding:12px 14px; font-size:14px; color:#cfd6e2; }}
.empty {{ color:var(--mut); font-style:italic; }}
@media print {{ body{{background:#fff;color:#000;padding:0;}} .reel{{border-color:#ccc;background:#fff;}} .hook,.brief{{background:#f5f5f5;}} a.ref{{color:#0a58ca;}} .label,.sec{{color:#000;}} }}
</style></head><body><div class="wrap">
<h1>{h1}</h1>
<p class="sub">{sub}</p>
"""
FOOT = "</div></body></html>"


def esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


# Ссылки внутри карточек (строка РЕФЕРЕНС в ТЗ монтажу, ссылки в «почему взяла») шли
# простым текстом: esc() экранирует всё подряд, тега <a> не возникало. владелец :
# «сделай чтобы референсы ссылки были кликабельные». Линкуем ПОСЛЕ экранирования, поэтому
# ВАЖНО, ПОЧЕМУ ЭТО БЕЗОПАСНО: защищает РОВНО порядок вызовов _linkify(esc(content)).
# К моменту линковки чужие скобки и кавычки уже сущности, поэтому живой тег не соберётся,
# а href не закроется. Список исключённых символов в _URL_RE к безопасности отношения НЕ имеет,
# он только режет хвосты вида «точка в конце предложения». Поменяете два вызова местами,
# и чужой тег из текста пака оживёт. Текст пака пишет посторонний человек из чужого аккаунта.
# Контроль на этот порядок стоит в ~/bin/test_digest_linkify.py (мутационный тест,
# <agent> ). Правите этот блок, прогоните тест.
_URL_RE = re.compile(r'(https?://[^\s<>"\')]+)')


def _linkify(safe: str) -> str:
    return _URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>',
        safe)


def block(label: str, content: str, cls: str = "brief") -> str:
    if not content:
        return ""
    return (f'<div class="block"><div class="label">{esc(label)}</div>'
            f'<div class="{cls}">{_linkify(esc(content))}</div></div>')


def card_html(p: dict, idx: int, kind: str) -> str:
    author = p.get("author_username", "?")
    topic = p.get("topic", "")
    url = p.get("url") or p.get("link") or ""
    parts = [f'<div class="reel" id="item{idx}"><span class="tag">{kind} {idx} · @{esc(author)}</span>',
             f'<h2>{esc(topic)}</h2>']
    if url:
        parts.append(f'<a class="ref" href="{esc(url)}">{esc(url)}</a>')
    is_carousel = p.get("type") == "carousel"
    parts.append(block("Вердикт + метрики виральности", p.get("card", ""), "hook"))
    # Карусель = только референс + виральность + почему выбрана :
    # ни телесуфлёра, ни ТЗ монтажу — карусель не снимают и не монтируют.
    if not is_carousel:
        parts.append(block("Телесуфлёр", p.get("teleprompter", "")))
    if p.get("caption"):
        parts.append(block("Капшен под пост (IG)", p.get("caption", "")))
    if not is_carousel:
        parts.append(block("ТЗ монтажу", p.get("editor_brief", "")))
    parts.append('<a class="up" href="#toc">↑ к содержанию</a>')
    parts.append("</div>")
    return "".join(parts)


def toc_html(items: list[dict], kind: str) -> str:
    """Оглавление с быстрым переходом на каждый ролик/карусель :
    жмёшь пункт — сразу прыгаешь к нужной карточке, не листаешь весь пак."""
    rows = [f'<div class="toc" id="toc"><div class="toc-h">Содержание · жми для перехода</div>']
    for i, p in enumerate(items, 1):
        author = esc(p.get("author_username", "?"))
        topic = esc((p.get("topic", "") or "")[:70])
        rows.append(f'<a href="#item{i}">{i}. @{author} · {topic}</a>')
    rows.append("</div>")
    return "".join(rows)


def build_html(items: list[dict], title: str, h1: str, sub: str, kind: str) -> str:
    body = HEAD.format(title=esc(title), h1=esc(h1), sub=esc(sub))
    if items:
        body += toc_html(items, kind)
        for i, p in enumerate(items, 1):
            body += card_html(p, i, kind)
    else:
        body += '<p class="empty">Сегодня ничего не отобрано.</p>'
    return body + FOOT


# --- packs --------------------------------------------------------------------

def load_packs(packs_dir: Path) -> tuple[list[dict], list[str]]:
    """Читает паки ОДИН раз и возвращает (годные, список проблем).

    раньше нечитаемый pack_*.json просто писался в лог и выбрасывался, рилс
    исчезал из выдачи, и ни одна проверка этого не видела. Теперь проблемы возвращаются
    наверх и становятся флагом формата, то есть блокируют отправку. Читаем один раз, чтобы
    проверялось ровно то содержимое, из которого собран отправляемый HTML."""
    packs: list[dict] = []
    bad: list[str] = []
    for f in sorted(packs_dir.glob("pack_*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error("bad pack %s: %s", f, e)
            bad.append(f"{f.name}: не прочитан ({type(e).__name__}: {e})")
            continue
        if not isinstance(p, dict):
            log.error("bad pack %s: не объект JSON (%s)", f, type(p).__name__)
            bad.append(f"{f.name}: не объект JSON ({type(p).__name__})")
            continue
        p["_file"] = f.name
        packs.append(p)
    return packs, bad


def load_meta(packs_dir: Path) -> dict:
    mf = packs_dir / "meta.json"
    if not mf.exists():
        return {}
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("bad meta.json: %s", e)
        return {}


# --- Telegram -----------------------------------------------------------------

def tg_send_message(token: str, chat_id: int, text: str, dry_run: bool) -> bool:
    if dry_run:
        sys.stdout.write(f"\n----- [MESSAGE] -----\n{text}\n")
        return True
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode())
        if not res.get("ok"):
            log.error("sendMessage error: %s", res)
            return False
        return True
    except urllib.error.HTTPError as e:
        log.error("sendMessage HTTP %d: %s", e.code, e.read().decode()[:200])
        return False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.error("sendMessage exc: %s", e)  # ValueError = битый JSON, не падать
        return False


def tg_send_document(token: str, chat_id: int, path: Path, caption: str, dry_run: bool) -> bool:
    if dry_run:
        sys.stdout.write(f"\n----- [DOCUMENT] {path} caption={caption!r} -----\n")
        return True
    try:
        file_bytes = path.read_bytes()
    except OSError as e:
        log.error("cannot read %s: %s", path, e)
        return False
    boundary = uuid.uuid4().hex
    pre = []
    for k, v in (("chat_id", str(chat_id)), ("caption", caption)):
        pre.append(f"--{boundary}\r\n"
                   f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    head = ("".join(pre) +
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
            f"Content-Type: text/html\r\n\r\n").encode()
    body = head + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode())
        if not res.get("ok"):
            log.error("sendDocument error: %s", res)
            return False
        return True
    except urllib.error.HTTPError as e:
        log.error("sendDocument HTTP %d: %s", e.code, e.read().decode()[:200])
        return False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.error("sendDocument exc: %s", e)  # ValueError = битый JSON, не падать
        return False


# --- main ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Утренний пакет niche-reels как 2 HTML-презентации")
    ap.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--chat-id", type=int, default=DEFAULT_CHAT_ID)
    ap.add_argument("--date", help="YYYY-MM-DD (по умолчанию сегодня МСК)")
    ap.add_argument("--dry-run", action="store_true", help="собрать HTML, не отправлять")
    ap.add_argument("--force", action="store_true",
                    help="отправить ВОПРЕКИ блокирующим нарушениям (переписанный хук, формат "
                         "не по канону). Только осознанно и с ведома владельца")
    args = ap.parse_args()

    if not args.packs_dir.exists():
        log.error("packs dir not found: %s", args.packs_dir)
        return 1
    packs, bad_packs = load_packs(args.packs_dir)
    if not packs:
        # Все паки нечитаемы — это ДЕФЕКТ ПОДБОРКИ, а не пустое окружение: код 10, как у любого
        # доказанного нарушения формата. Пустая папка без файлов вообще остаётся кодом 1.
        if bad_packs:
            log.error("ВСЕ pack_*.json нечитаемы в %s: %s", args.packs_dir, "; ".join(bad_packs))
            print(f"ОТПРАВКА ЗАБЛОКИРОВАНА ({FORMAT_VIOLATION_MARK}): ни один pack_*.json не "
                  f"прочитан.\n  · " + "\n  · ".join(bad_packs), file=sys.stderr)
            return 10
        log.error("no pack_*.json found in %s", args.packs_dir)
        return 1
    meta = load_meta(args.packs_dir)

    if args.date:
        try:
            d = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            log.error("bad --date %r (need YYYY-MM-DD)", args.date)
            return 1
    else:
        d = datetime.now(MSK)
    stamp = d.strftime("%Y%m%d")
    raw_label = (meta.get("date_label") or "").strip()
    # board #56 freshness guard: meta.json carries a machine date_label written by
    # the daily gen_packs. If it is a valid YYYY-MM-DD and does NOT match the target
    # day, the packs are stale (a previous run's leftovers) → abort loudly instead of
    # shipping yesterday's digest as today's. --date is honoured: a backfill run whose
    # label matches --date passes; only a valid-but-mismatched label aborts (a missing
    # or free-text label never blocks, keeping legacy behaviour).
    if raw_label and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_label):
        target_ymd = d.strftime("%Y-%m-%d")
        if raw_label != target_ymd:
            log.error(
                "STALE PACKS: meta date_label=%s != target %s (dir %s). "
                "Aborting so a stale digest is not shipped. "
                "Re-run gen_packs for today, or pass --date %s to build this label deliberately.",
                raw_label, target_ymd, args.packs_dir, raw_label,
            )
            return 1
    if raw_label and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_label):
        dd = datetime.strptime(raw_label, "%Y-%m-%d")
        label = f"{dd.day} {RU_MONTHS[dd.month]}"
    else:
        label = raw_label or f"{d.day} {RU_MONTHS[d.month]}"

    reels = [p for p in packs if p.get("type") != "carousel"]
    carousels = [p for p in packs if p.get("type") == "carousel"]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    reels_path = args.out_dir / f"reels_{stamp}.html"
    carousels_path = args.out_dir / f"carousels_{stamp}.html"

    reels_path.write_text(build_html(
        reels,
        title=f"Рилсы {label}",
        h1=f"Утренние рилсы · {label}",
        sub=f"{len(reels)} рилсов. Вердикт + формула виральности, телесуфлёр, "
            f"капшен, ТЗ монтажу. Отбери, что берёшь в работу.",
        kind="РИЛС",
    ), encoding="utf-8")
    carousels_path.write_text(build_html(
        carousels,
        title=f"Карусели {label}",
        h1=f"Утренние карусели · {label}",
        sub=f"{len(carousels)} каруселей. Вердикт (адаптировать / уникализировать), "
            f"разбор слайдов, метрики.",
        kind="КАРУСЕЛЬ",
    ), encoding="utf-8")

    log.info("built reels=%d carousels=%d -> %s | %s",
             len(reels), len(carousels), reels_path, carousels_path)

    # Механический guard: карусели минимум N — если меньше,
    # печатаем громкий WARN в сводку, чтобы <agent> ФИЗИЧЕСКИ видела недобор до отправки.
    # Сводка шлётся без parse_mode → не HTML-bold, а CAPS+⚠️ (видно в чате и в --dry-run).
    cmin = carousel_min()
    car_on = carousels_enabled()
    # Инстанс без каруселей добирать неоткуда: guard там шумел бы каждое утро (заявка
    # <agent> 19.08). Факт выключения называется в сводке строкой ниже, не молчанием.
    carousel_short = car_on and len(carousels) < cmin
    if carousel_short:
        log.warning("CAROUSELS UNDER MINIMUM: %d < %d — добери перед отправкой",
                    len(carousels), cmin)
    warn_line = (
        f"⚠️⚠️ ВНИМАНИЕ: КАРУСЕЛЕЙ {len(carousels)} < {cmin} (МИНИМУМ) — ДОБЕРИ "
        f"из топ-15 ДО отправки владельцу. HARD-правило, недобор не отправлять.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n" if carousel_short else ""
    )

    hook_res = hook_fidelity_warn(args.packs_dir)
    prot_res = protected_missing_warn(packs)
    fmt_res = format_canon_warn(packs, meta, bad_packs)
    hook_warn, prot_warn, fmt_warn = hook_res.text, prot_res.text, fmt_res.text

    # БЛОКИРУЮЩИЙ ГЕЙТ («хук вообще никогда не должен меняться,
    # как и ядро смыслов»). До этого дня переписанный хук и сломанный формат были ТЕКСТОМ в
    # сводке: предупреждение можно было прочитать и выдать пак всё равно, что 26.07 и произошло
    # (9 рилсов из 9 у одного клиента). Теперь такая подборка не отправляется вообще.
    # Границу держу осознанно: «ПРОВЕРКА НЕ ОТРАБОТАЛА» НЕ блокирует — иначе сбой одного чекера
    # оставит клиента без утренней подборки. Он остаётся громким блоком в сводке.
    blocking = ([HOOK_VIOLATION_MARK] if hook_res.violated else []) + \
               ([FORMAT_VIOLATION_MARK] if fmt_res.violated else [])
    if blocking and not args.force:
        log.error("BLOCKED: %s — подборка НЕ отправлена", ", ".join(blocking))
        print(hook_warn + fmt_warn, end="")
        print(f"ОТПРАВКА ЗАБЛОКИРОВАНА ({', '.join(blocking)}). Почини паки и запусти снова. "
              f"HTML собран: {reels_path}\n"
              f"Отправить вопреки нарушению можно только с --force и с ведома владельца.",
              file=sys.stderr)
        return 10

    cov = coverage_line()
    cov_block = f"{cov}\n\n" if cov else ""
    # Молчащая проверка неотличима от прошедшей — тот же класс, что чистый проход предполёта.
    car_off_line = ("" if car_on else
                    "ℹ️ Карусели в этом инстансе выключены (limits.carousels_enabled=false): "
                    "скрейп каруселей не запускался, бэкстоп сильнейшего дня сверял только рилсы.\n\n")

    summary = (
        f"{fmt_warn}"
        f"{prot_warn}"
        f"{hook_warn}"
        f"{warn_line}"
        f"🌅 Утренний пакет niche-reels · {label}\n\n"
        f"{car_off_line}"
        f"{cov_block}"
        f"📹 Рилсы: {len(reels)} — вердикт + формула виральности + телесуфлёр + ТЗ монтажу\n"
        f"🎠 Карусели: {len(carousels)} — вердикт + разбор слайдов + метрики\n\n"
        f"Два файла ниже — открой, отбери что берёшь в работу."
    )

    token = "<dry>" if args.dry_run else BOT_TOKEN.strip()
    if not token and not args.dry_run:
        log.error("empty $TELEGRAM_BOT_TOKEN")
        return 1

    ok = True
    if not tg_send_message(token, args.chat_id, summary, args.dry_run):
        log.error("summary send failed")
        ok = False
    time.sleep(SEND_GAP_SEC)

    if not tg_send_document(token, args.chat_id, reels_path, f"📹 Рилсы · {label}", args.dry_run):
        log.error("reels doc send failed")
        ok = False
    time.sleep(SEND_GAP_SEC)

    if carousels:
        if not tg_send_document(token, args.chat_id, carousels_path,
                                f"🎠 Карусели · {label}", args.dry_run):
            log.error("carousels doc send failed")
            ok = False
    else:
        log.info("no carousels — карусельный .html собран, но не отправлен (пусто)")

    log.info("done%s: reels=%d carousels=%d ok=%s",
             " [DRY-RUN]" if args.dry_run else "", len(reels), len(carousels), ok)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
