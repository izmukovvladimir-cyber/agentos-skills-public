#!/usr/bin/env python3
"""Word-level Russian transcription of a short clip via Groq Whisper.

Karaoke subtitles need per-word timings, which the long-form helper
(`bin/groq-transcribe-long.py`) does not emit — it returns section markdown.
This is the short-clip companion: one request, `verbose_json` with word
granularity, straight to a JSON file the reel builder consumes.

Keep it for clips, not lectures: Groq caps the request body, so anything past a
few minutes belongs in the chunking helper instead.

The key comes from $GROQ_API_KEY (or a file passed with --key-file), never from
argv — argv is world-readable in /proc.
Cloudflare in front of Groq 403s the default urllib UA, so we send our own.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

MODEL = "whisper-large-v3-turbo"
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
KEY_ENV = "GROQ_API_KEY"  # export it before running; nothing is stored in this file
UA = "reels-montage/1.0"


def extract_audio(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Downmix to 16 kHz mono mp3 — whisper's input, and small on the wire."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)],
        check=True,
    )


def transcribe(audio: pathlib.Path, key: str, lang: str, timeout: int) -> dict:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; '
            f'name="{name}"\r\n\r\n{value}\r\n'.encode()
        )

    field("model", MODEL)
    field("language", lang)
    field("response_format", "verbose_json")
    field("timestamp_granularities[]", "word")
    field("timestamp_granularities[]", "segment")
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()
    )
    parts.append(audio.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        URL,
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=pathlib.Path, help="audio or video file")
    ap.add_argument("-o", "--out", type=pathlib.Path, required=True, help="words JSON output")
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--key-file", default=None,
                    help=f"file holding the key; default is ${KEY_ENV} from the environment")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"ERR: нет файла {args.input}", file=sys.stderr)
        return 2

    if args.key_file:
        key_path = pathlib.Path(args.key_file).expanduser()
        if not key_path.is_file():
            print(f"ERR: нет ключа {key_path}", file=sys.stderr)
            return 2
        key = key_path.read_text().strip()
    else:
        key = os.environ.get(KEY_ENV, "").strip()
        if not key:
            print(f"ERR: задай ${KEY_ENV} в окружении либо передай --key-file", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="reelsub-") as tmp:
        audio = pathlib.Path(tmp) / "audio.mp3"
        try:
            extract_audio(args.input, audio)
        except subprocess.CalledProcessError:
            print("ERR: ffmpeg не смог извлечь звук", file=sys.stderr)
            return 3
        try:
            data = transcribe(audio, key, args.lang, args.timeout)
        except urllib.error.HTTPError as exc:
            # the body carries Groq's reason (quota, size, bad audio); the key never appears in it
            print(f"ERR: Groq {exc.code}: {exc.read().decode()[:300]}", file=sys.stderr)
            return 4

    words = data.get("words") or []
    if not words:
        print("ERR: Groq не вернул пословных отметок", file=sys.stderr)
        return 5

    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"слов: {len(words)}, сегментов: {len(data.get('segments') or [])}, файл: {args.out}")
    print(f"текст: {data.get('text', '')[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
