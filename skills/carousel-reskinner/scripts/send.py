#!/usr/bin/env python3
"""Send a carousel run (slides + zip) to the owner's Telegram chat.

Usage:
    send.py <out_dir> [--caption "..."]

Credentials come from the environment, nothing is stored in this file:
    $TELEGRAM_BOT_TOKEN — bot token
    $TELEGRAM_CHAT_ID   — numeric chat id of the single allowed recipient
"""
from __future__ import annotations
import argparse
import http.client
import json
import logging
import os
import sys
import uuid
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

def get_token() -> str:
    """Bot token comes from the environment, never hard-coded here."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("set $TELEGRAM_BOT_TOKEN before running")
    return token


def get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        sys.exit("set $TELEGRAM_CHAT_ID before running")
    return chat_id


def multipart(fields: dict[str, str], files: list[tuple[str, str, bytes, str]]
              ) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for name, filename, data, ctype in files:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"{name}\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def post(token: str, method: str, fields: dict,
         files: list[tuple[str, str, bytes, str]]) -> dict:
    body, ctype = multipart(fields, files)
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=120)
    conn.request("POST", f"/bot{token}/{method}", body=body,
                 headers={"Content-Type": ctype})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return json.loads(data)


def build_zip(out_dir: Path) -> Path:
    zip_path = out_dir.parent / f"{out_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out_dir.glob("slide_*.jpg")):
            z.write(p, p.name)
    log.info("zip: %s (%d B)", zip_path, zip_path.stat().st_size)
    return zip_path


def send_album(token: str, out_dir: Path, caption: str) -> None:
    slides = sorted(out_dir.glob("slide_*.jpg"))
    if not slides:
        log.error("no slides in %s", out_dir)
        sys.exit(1)
    media = []
    files = []
    for i, p in enumerate(slides):
        attach = f"img{i}"
        item = {"type": "photo", "media": f"attach://{attach}"}
        if i == 0 and caption:
            item["caption"] = caption
        media.append(item)
        files.append((attach, p.name, p.read_bytes(), "image/jpeg"))
    r = post(token, "sendMediaGroup",
             {"chat_id": get_chat_id(), "media": json.dumps(media)}, files)
    log.info("album ok=%s", r.get("ok"))
    if not r.get("ok"):
        log.error("response: %s", r)


def send_zip(token: str, zip_path: Path, caption: str = "") -> None:
    r = post(token, "sendDocument",
             {"chat_id": get_chat_id(), "caption": caption},
             [("document", zip_path.name, zip_path.read_bytes(),
               "application/zip")])
    log.info("zip ok=%s", r.get("ok"))
    if not r.get("ok"):
        log.error("response: %s", r)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--caption", default="")
    ap.add_argument("--zip-caption", default="Слайды одним архивом")
    args = ap.parse_args()

    token = get_token()
    zp = build_zip(args.out_dir)
    send_album(token, args.out_dir, args.caption)
    send_zip(token, zp, args.zip_caption)


if __name__ == "__main__":
    main()
