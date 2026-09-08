#!/usr/bin/env python3
"""Транскрибируем через curl чтобы обойти Cloudflare 1010.

Коды рилсов НЕ захардкожены: по умолчанию берём коды из свежих топ-файлов пула
(_top10.json / _carousels_top.json), метаданные (автор/заметка) подтягиваем из
отобранных паков. Изоляция через env NRR_CLIENT_DIR (lib_paths): клиентский прогон
пишет только в свою папку, легаси-файлы <agent> не затираются.

Usage: python3 transcribe.py [--codes CODE1,CODE2,...] [--all]
  дефолт     = только коды из свежих _top10.json / _carousels_top.json (что нужно
               для сегодняшнего дайджеста), а НЕ весь накопленный work/ (task #76).
  --codes    = явный список shortcode'ов.
  --all      = легаси: весь work/<code>/audio.mp3 (может упереться в RPM Groq).
429/5xx от Groq ретраятся с экспоненциальным backoff (ключ общий на всех клиентов).
"""
import argparse
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

GROQ_KEY = os.environ["GROQ_API_KEY"]
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy path.
OUT = lib_paths.pool_dir()
WORK = OUT / "work"

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
# Groq whisper RPM limit is 20/min and the API key is SHARED by all client bots — at 08:05 the
# morning digests fire together and burst past it. Retry with exponential backoff + jitter so a
# 429 (or transient 5xx) is ridden out instead of silently dropping the reel (task #76).
MAX_RETRIES = 5
BASE_BACKOFF = 5.0   # seconds; doubled each retry up to BACKOFF_CAP
BACKOFF_CAP = 60.0   # RPM window is 60s, so cap the wait there


def _s(v) -> str:
    """Поле пака может прийти числом/списком/None — безопасно к строке."""
    return v if isinstance(v, str) else ""


def _code_from_pack(p: dict) -> str:
    """Shortcode пака: поле code или последний сегмент url/link."""
    code = _s(p.get("code"))
    if code:
        return code
    m = re.search(r"/reel/([A-Za-z0-9_-]+)", _s(p.get("url") or p.get("link", "")))
    return m.group(1) if m else ""


def discover_codes(work_dir: Path) -> list[str]:
    """Все коды, для которых уже скачано audio.mp3 (что и надо транскрибировать)."""
    if not work_dir.is_dir():
        return []
    return sorted(
        d.name for d in work_dir.iterdir()
        if d.is_dir() and (d / "audio.mp3").exists()
    )


def load_top_codes(pool_dir: Path) -> list[str]:
    """Коды из СВЕЖИХ топ-файлов (_top10.json + _carousels_top.json) — то, что реально нужно
    для сегодняшнего дайджеста. Дефолт раньше брал ВЕСЬ work/ (~240 накопленных папок) и упирался
    в RPM Groq (task #76). Карусели без audio.mp3 отсеются проверкой ниже (транскрибировать нечего)."""
    codes: list[str] = []
    seen: set[str] = set()
    for fn in ("_top10.json", "_carousels_top.json"):
        f = pool_dir / fn
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = data if isinstance(data, list) else (data.get("items") if isinstance(data, dict) else [])
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            c = _s(it.get("code")) or _code_from_pack(it)
            if c and c not in seen:
                seen.add(c)
                codes.append(c)
    return codes


def load_pack_meta(packs_dir: Path) -> dict:
    """code -> {username, note} из отобранных паков (best-effort, без хардкода)."""
    meta: dict[str, dict] = {}
    if not packs_dir.is_dir():
        return meta
    for pf in sorted(packs_dir.glob("pack_*.json")):
        try:
            p = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(p, dict):
            continue
        code = _code_from_pack(p)
        if code:
            meta[code] = {
                "username": _s(p.get("author_username")) or "?",
                "note": (_s(p.get("title")) or _s(p.get("hook")))[:80],
            }
    return meta


def _rate_limited(status: str, data: dict) -> bool:
    """HTTP 429, либо тело ошибки Groq говорит про rate limit (на случай если статус не 429)."""
    if status == "429":
        return True
    err = data.get("error")
    if isinstance(err, dict):
        return "rate_limit" in _s(err.get("code")).lower() or "rate limit" in _s(err.get("message")).lower()
    return False


def _retry_after_hint(data: dict) -> "float | None":
    """Groq пишет «Please try again in Xs» в message — используем как подсказку паузы."""
    err = data.get("error")
    msg = _s(err.get("message")) if isinstance(err, dict) else _s(data.get("_raw"))
    m = re.search(r"try again in ([\d.]+)s", msg, re.I)   # seconds only; «500ms» falls back to backoff
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _curl_once(audio_path: Path) -> "tuple[int, str, str]":
    """(returncode, http_status, body). curl -w печатает http-код последней строкой stdout."""
    cmd = [
        "curl", "-s", "-X", "POST", GROQ_URL,
        "-H", f"Authorization: Bearer {GROQ_KEY}",
        "-H", "User-Agent: curl/8.5.0",
        "-F", "model=whisper-large-v3",
        "-F", "response_format=verbose_json",
        "-F", f"file=@{audio_path}",
        "-w", "\n%{http_code}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return r.returncode, "", (r.stderr or r.stdout)
    body, _, status = r.stdout.rpartition("\n")   # last line = %{http_code}; JSON body has no trailing NL
    return 0, status.strip(), body


def transcribe(audio_path: Path) -> dict:
    """Один рилс → transcript dict. Ретраит 429/5xx с экспоненциальным backoff + джиттер,
    чтобы burst общего Groq-ключа (все клиентские боты в 08:05) не терял файл молча."""
    delay = BASE_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            rc, status, body = _curl_once(audio_path)
        except subprocess.TimeoutExpired:
            # TimeoutExpired.__str__ embeds the full cmd (incl. the Bearer key) → generic msg only.
            return {"_error": "curl таймаут (>180s)"}
        except (subprocess.SubprocessError, OSError) as e:
            return {"_error": f"curl не запустился: {e}"}
        if rc != 0:
            return {"_error": f"curl rc={rc}", "_raw": body[:300]}   # сетевой сбой, не HTTP — не ретраим
        try:
            data = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError as e:
            data = {"_error": str(e), "_raw": body[:300]}
        if not isinstance(data, dict):
            return {"_error": "ответ Groq не JSON-объект", "_raw": body[:300]}
        transient = _rate_limited(status, data) or status.startswith("5")
        if transient and attempt < MAX_RETRIES:
            wait = (_retry_after_hint(data) or delay) + random.uniform(0, 3)   # джиттер расфазирует ботов
            kind = "429 rate limit" if _rate_limited(status, data) else f"HTTP {status}"
            print(f"    {kind}, попытка {attempt}/{MAX_RETRIES} не прошла, жду {wait:.0f}s и повторяю...")
            time.sleep(wait)
            delay = min(delay * 2, BACKOFF_CAP)
            continue
        if transient:   # попытки исчерпаны
            kind = "429 rate limit" if _rate_limited(status, data) else f"HTTP {status}"
            return {"_error": f"Groq {kind} не прошёл за {MAX_RETRIES} попыток", "_raw": body[:300]}
        return data


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", default="",
                    help="shortcodes через запятую (явный список; игнорирует топ-файлы и --all)")
    ap.add_argument("--all", action="store_true",
                    help="транскрибировать ВЕСЬ work/<code>/audio.mp3 (легаси; может упереться в RPM Groq)")
    args = ap.parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.all:
        codes = discover_codes(WORK)
    else:
        # DEFAULT (task #76): ТОЛЬКО свежий топ, никогда не весь накопленный work/. Если топ-файлов
        # нет/пусты — НЕ откатываемся на обход всех ~240 папок (это и был баг с RPM Groq): выходим
        # и требуем явного --codes или осознанного --all. Полный обход work/ живёт только за --all.
        top_codes = load_top_codes(OUT)
        if not top_codes:
            print(f"нет свежих _top10.json/_carousels_top.json в {OUT} — по умолчанию транскрибировать "
                  f"нечего. Передай --codes <...> явно или --all для всего work/ (осознанно, риск RPM Groq).",
                  file=_sys.stderr)
            return 2
        codes = [c for c in top_codes if (WORK / c / "audio.mp3").exists()]
        no_audio = len(top_codes) - len(codes)
        if no_audio:
            print(f"  (из {len(top_codes)} топ-кодов {no_audio} без audio.mp3 — карусели/нескачанные, пропускаю)")
    if not codes:
        print(f"нет аудио для транскрипции в {WORK} (стадия скачивания не запускалась?) "
              f"— выхожу, {OUT}/_pack6_transcripts.json не трогаю", file=_sys.stderr)
        return 2

    pack_meta = load_pack_meta(lib_paths.packs_dir())  # board #56: packs live in the canonical dir (owner→SKILL_DIR/packs), not OUT/packs
    results = []
    no_mp3: list[str] = []          # : считаем пропуски, чтобы прогон не выглядел удачным
    failed: list[str] = []
    for code in codes:
        work_dir = WORK / code
        mp3 = work_dir / "audio.mp3"
        if not mp3.exists():
            print(f"  {code}: NO MP3, skip")
            no_mp3.append(code)
            continue
        print(f"  {code} transcribing...")
        result = transcribe(mp3)
        if not isinstance(result, dict):
            print(f"    ERR: ответ Groq не JSON-объект, skip")
            failed.append(code)
            continue
        err = result.get("_error") or result.get("error")
        if err:
            print(f"    ERR: {err} raw={_s(result.get('_raw'))[:120]}")
            failed.append(code)
            continue
        text = _s(result.get("text"))
        if not text.strip():
            print(f"    ERR: Groq вернул пустой transcript, skip")
            failed.append(code)
            continue
        (work_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        (work_dir / "transcript.txt").write_text(text)
        print(f"    ok, {len(text)} chars: {text[:120]}")
        m = pack_meta.get(code, {})
        results.append({
            "code": code,
            "username": m.get("username", "?"),
            "note": m.get("note", ""),
            "text": text,
            "language": result.get("language"),
            "duration": result.get("duration"),
        })

    if not results:
        print(f"ни один код не дал транскрипт (нет mp3 или ошибки Groq) "
              f"— {OUT}/_pack6_transcripts.json не трогаю", file=_sys.stderr)
        if no_mp3:
            print(f"  ни у одного кода нет audio.mp3. Пропущен шаг скачивания: "
                  f"python3 stage_audio.py --codes {','.join(no_mp3)}", file=_sys.stderr)
        return 2

    # Мержим с тем, что уже лежит, а не перезаписываем: повторный прогон на ОДНОМ коде
    # (доснять пропущенный ролик, переделать сбойный) иначе стирал транскрипты остальных,
    # и агент собирал телесуфлёр по капшену вместо рерайта. Свежий результат по тому же
    # коду побеждает старый; порядок прежний — сначала то, что было, потом новое.
    out_file = OUT / "_pack6_transcripts.json"

    # Дедуп свежих: `--codes A,A` иначе даёт две записи A и «победитель» неоднозначен.
    by_code: dict[str, dict] = {}
    for r in results:
        by_code[r["code"]] = r                            # last wins
    results = list(by_code.values())
    fresh_codes = set(by_code)

    def _rescue(reason: str) -> None:
        """Отложить непонятный файл рядом вместо того, чтобы затереть его молча."""
        spare = out_file.with_name(f"{out_file.stem}.{reason}-{int(time.time())}.json")
        try:
            out_file.replace(spare)
            print(f"  ⚠ прежний {out_file.name} сохранён как {spare.name}", file=_sys.stderr)
        except OSError as exc:
            print(f"  ⚠ прежний {out_file.name} не удалось отложить: {exc}", file=_sys.stderr)

    merged: list[dict] = []
    if out_file.exists():
        try:
            prev = json.loads(out_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ⚠ {out_file.name} не прочитан ({exc})", file=_sys.stderr)
            _rescue("broken")
            prev = []
        if isinstance(prev, list):
            # Записи неожиданной формы не выбрасываем молча: сначала откладываем оригинал.
            if any(not isinstance(r, dict) for r in prev):
                print(f"  ⚠ в {out_file.name} есть записи неожиданной формы", file=_sys.stderr)
                _rescue("odd")
            merged = [r for r in prev
                      if isinstance(r, dict) and r.get("code") not in fresh_codes]
        elif prev:
            print(f"  ⚠ {out_file.name} не список", file=_sys.stderr)
            _rescue("odd")

    kept = len(merged)
    merged.extend(results)

    # Атомарная запись: write_text сначала обрезает файл, и обрыв на этом месте оставил бы
    # пустой _pack6_transcripts.json, то есть потерю ВСЕХ транскриптов дня.
    tmp = out_file.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(out_file)

    print(f"\n=== SAVED {len(results)} transcripts"
          + (f" (+{kept} прежних сохранено)" if kept else "")
          + f" → {out_file} ===")

    # Частичный прогон раньше выглядел удачным: часть кодов уходила в «NO MP3, skip», а код
    # возврата оставался нулевым. Агент делал вывод «у ролика нет речи» и писал телесуфлёр по
    # капшену. Теперь недобор виден и в выводе, и в коде возврата.
    if no_mp3 or failed:
        print("\n⚠ БЕЗ ТРАНСКРИПТА:", file=_sys.stderr)
        if no_mp3:
            print(f"  нет audio.mp3 ({len(no_mp3)}): {','.join(no_mp3)}\n"
                  f"  → python3 stage_audio.py --codes {','.join(no_mp3)}  и повтори transcribe.py",
                  file=_sys.stderr)
        if failed:
            print(f"  Groq не дал текст ({len(failed)}): {','.join(failed)}", file=_sys.stderr)
        print("  Телесуфлёр по капшену без речи ролика писать НЕЛЬЗЯ: это выдуманный текст, "
              "а не рерайт. Ролик действительно без речи — помечай 'no_speech': true в паке.",
              file=_sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    _sys.exit(main())
