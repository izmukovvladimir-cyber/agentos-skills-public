#!/usr/bin/env python3
"""Render «Чёрный лист» single-slide brand template for @your_account.

Spec: ../templates/black_leaf.md
Reference posts: @donor_account <post_code> (numbered list), <post_code> (paragraphs).
Approved 2026-05-17 by the operator.

Usage:
    python3 render_black_leaf.py --json input.json --out slide.jpg

input.json:
    {
      "paragraphs": ["Hook line", "Body line 1", "Body line 2"],
      "watermark": "@your_account"
    }
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG = (0, 0, 0)
TEXT = (235, 235, 235)
WATERMARK = (110, 110, 110)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
BODY_SIZE = 48
WM_SIZE = 34

LEFT = 130
RIGHT = 130
MAX_W = W - LEFT - RIGHT

LINE_GAP = 14
PARA_GAP = 38
WM_GAP = 20
VCENTER_OFFSET = -40


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = font.getbbox(trial)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render(paragraphs: list[str], watermark: str, out_path: Path) -> Path:
    font = ImageFont.truetype(FONT_PATH, BODY_SIZE)
    wm_font = ImageFont.truetype(FONT_PATH, WM_SIZE)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + LINE_GAP

    wrapped = [wrap(p, font, MAX_W) for p in paragraphs]
    total_h = sum(len(lines) * line_h for lines in wrapped)
    total_h += (len(wrapped) - 1) * PARA_GAP
    total_h -= LINE_GAP

    block_y0 = (H - total_h) // 2 + VCENTER_OFFSET

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    y = block_y0
    for lines in wrapped:
        for line in lines:
            draw.text((LEFT, y), line, fill=TEXT, font=font)
            y += line_h
        y += PARA_GAP

    wm_y = y + WM_GAP
    draw.text((LEFT, wm_y), watermark, fill=WATERMARK, font=wm_font)

    img.save(out_path, "JPEG", quality=95)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, required=True, help="input JSON file")
    ap.add_argument("--out", type=Path, required=True, help="output JPG path")
    args = ap.parse_args()

    data = json.loads(args.json.read_text())
    paragraphs = data["paragraphs"]
    watermark = data.get("watermark", "@your_account")

    out = render(paragraphs, watermark, args.out)
    print(f"saved -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
