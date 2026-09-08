#!/usr/bin/env python3
"""Render CTA-Stats — last/CTA slide of a carousel with two real IG screenshots side-by-side.

Spec: ../templates/cta_stats.md
Approved 2026-05-18 by the operator (after rejecting DIY dark-cards mockup; final = real screenshots).

Layout:
  - Top: CTA text (3-4 lines, DejaVu Serif)
  - Bottom: two real IG screenshots in equal-size white bbox side-by-side
  - Pure black canvas (matches Black Leaf carousel theme)

Usage:
    python3 render_cta_stats.py \\
        --json /tmp/cta_stats.json \\
        --out /tmp/cta_slide.jpg

cta_stats.json:
    {
      "cta_lines": [
        "Пиши «КОДВОРД» в ком:ментариях,",
        "и я пришлю гайд — как с нуля",
        "собрать первые 10к под:писчиков",
        "в Instagram."
      ],
      "screenshots": [
        "/path/to/screenshot1.jpg",
        "/path/to/screenshot2.jpg"
      ],
      "watermark": "@your_account",
      "crop_top_pct": [0.0, 0.10]   // optional per-screenshot top crop (status bar removal)
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
WM = (110, 110, 110)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

CTA_SIZE = 40
WM_SIZE = 30
CTA_TOP_Y = 110
BBOX_W, BBOX_H = 480, 600
GAP = 40
BBOX_TOP_Y = 660
BBOX_RADIUS = 18


def fit_into_bbox(img: Image.Image, bw: int, bh: int) -> Image.Image:
    iw, ih = img.size
    scale = min(bw / iw, bh / ih)
    return img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)


def render(data: dict, out: Path) -> Path:
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)

    cta_font = ImageFont.truetype(FONT, CTA_SIZE)
    wm_font = ImageFont.truetype(FONT, WM_SIZE)
    asc, desc = cta_font.getmetrics()
    line_h = asc + desc + 4

    # CTA top
    y = CTA_TOP_Y
    for line in data["cta_lines"]:
        bb = draw.textbbox((0, 0), line, font=cta_font)
        lw = bb[2] - bb[0]
        draw.text(((W - lw) // 2, y), line, fill=TEXT, font=cta_font)
        y += line_h

    # Two screenshots
    screenshots = data["screenshots"]
    crops = data.get("crop_top_pct", [0.0] * len(screenshots))
    if len(screenshots) != 2:
        raise ValueError("cta_stats expects exactly 2 screenshots")

    total_w = BBOX_W * 2 + GAP
    bbox_x0 = (W - total_w) // 2

    for i, path in enumerate(screenshots):
        img = Image.open(path).convert("RGB")
        if crops[i] > 0:
            sw, sh = img.size
            img = img.crop((0, int(sh * crops[i]), sw, int(sh * 0.97)))
        fit = fit_into_bbox(img, BBOX_W, BBOX_H)
        bx = bbox_x0 + i * (BBOX_W + GAP)
        # White bbox card
        draw.rounded_rectangle(
            [bx, BBOX_TOP_Y, bx + BBOX_W, BBOX_TOP_Y + BBOX_H],
            radius=BBOX_RADIUS, fill=(255, 255, 255),
        )
        x_off = bx + (BBOX_W - fit.size[0]) // 2
        y_off = BBOX_TOP_Y + (BBOX_H - fit.size[1]) // 2
        canvas.paste(fit, (x_off, y_off))

    # Watermark
    wm = data.get("watermark", "@your_account")
    wb = draw.textbbox((0, 0), wm, font=wm_font)
    ww = wb[2] - wb[0]
    draw.text(((W - ww) // 2, H - 55), wm, fill=WM, font=wm_font)

    canvas.save(out, "JPEG", quality=92)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    data = json.loads(args.json.read_text())
    out = render(data, args.out)
    print(f"saved -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
