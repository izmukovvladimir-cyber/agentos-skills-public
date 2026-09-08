#!/usr/bin/env python3
"""Render Cover Premium — slide 1 of a multi-slide carousel with photo backdrop.

Spec: ../templates/cover_premium.md
Approved 2026-05-17 by the operator.

Usage:
    python3 render_cover_premium.py \
        --photo /tmp/maybach_1080x1350.jpg \
        --json /tmp/cover_text.json \
        --out /tmp/cover.jpg

cover_text.json:
    {
      "handle": "@your_account",
      "hook_block": ["Line 1 of hook", "Line 2 of hook"],
      "sub_block": ["Sub line 1", "Sub line 2:"],
      "swipe": "листай →"
    }
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

W, H = 1080, 1350

FONT_HANDLE = "/tmp/fonts/PlayfairDisplay.ttf"
FONT_BODY = "/tmp/fonts/Inter.ttf"

HANDLE_SIZE = 38
HOOK_SIZE = 64
SUB_SIZE = 50
SWIPE_SIZE = 28

STROKE_HOOK = 4
STROKE_SUB = 3
STROKE_HANDLE = 2
STROKE_SWIPE = 2

SHADOW_BLUR = 4
SHADOW_OFFSET_HOOK = (4, 6)
SHADOW_OFFSET_SUB = (3, 5)
SHADOW_OFFSET_SMALL = (2, 3)
SHADOW_ALPHA = 200

LEFT_TEXT = 70
HOOK_TOP_Y = 580
BLOCKS_GAP = 50


def warm_treat(img: Image.Image) -> Image.Image:
    warm = Image.new("RGB", img.size, (255, 195, 130))
    img = Image.blend(img.convert("RGB"), warm, 0.08)
    img = ImageEnhance.Color(img).enhance(1.10)
    img = ImageEnhance.Contrast(img).enhance(1.05)
    return img


def darken(img_rgba: Image.Image) -> Image.Image:
    return img_rgba


def render(photo: Path, data: dict, out: Path) -> Path:
    img = Image.open(photo).convert("RGB").resize((W, H), Image.LANCZOS)
    img = warm_treat(img)
    img_rgba = darken(img.convert("RGBA"))

    handle_font = ImageFont.truetype(FONT_HANDLE, HANDLE_SIZE)
    handle_font.set_variation_by_name(b"Regular")
    hook_font = ImageFont.truetype(FONT_BODY, HOOK_SIZE)
    hook_font.set_variation_by_axes([14, 800])
    sub_font = ImageFont.truetype(FONT_BODY, SUB_SIZE)
    sub_font.set_variation_by_axes([14, 700])
    swipe_font = ImageFont.truetype(FONT_BODY, SWIPE_SIZE)
    swipe_font.set_variation_by_axes([14, 600])

    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)
    sd = ImageDraw.Draw(shadow_layer)

    # Handle top-center
    handle = data.get("handle", "@your_account")
    hb = td.textbbox((0, 0), handle, font=handle_font)
    hw = hb[2] - hb[0]
    hx = (W - hw) // 2
    hy = 36
    sd.text((hx + SHADOW_OFFSET_SMALL[0], hy + SHADOW_OFFSET_SMALL[1]),
            handle, fill=(0, 0, 0, SHADOW_ALPHA), font=handle_font,
            stroke_width=STROKE_HANDLE, stroke_fill=(0, 0, 0, SHADOW_ALPHA))
    td.text((hx, hy), handle, fill=(235, 235, 235), font=handle_font,
            stroke_width=STROKE_HANDLE, stroke_fill=(0, 0, 0))

    # Hook block
    asc, desc = hook_font.getmetrics()
    line_h_hook = asc + desc
    asc2, desc2 = sub_font.getmetrics()
    line_h_sub = asc2 + desc2

    y = HOOK_TOP_Y
    for ln in data["hook_block"]:
        sd.text((LEFT_TEXT + SHADOW_OFFSET_HOOK[0], y + SHADOW_OFFSET_HOOK[1]),
                ln, fill=(0, 0, 0, SHADOW_ALPHA), font=hook_font,
                stroke_width=STROKE_HOOK, stroke_fill=(0, 0, 0, SHADOW_ALPHA))
        td.text((LEFT_TEXT, y), ln, fill=(255, 255, 255), font=hook_font,
                stroke_width=STROKE_HOOK, stroke_fill=(0, 0, 0))
        y += line_h_hook
    y += BLOCKS_GAP
    for ln in data["sub_block"]:
        sd.text((LEFT_TEXT + SHADOW_OFFSET_SUB[0], y + SHADOW_OFFSET_SUB[1]),
                ln, fill=(0, 0, 0, SHADOW_ALPHA), font=sub_font,
                stroke_width=STROKE_SUB, stroke_fill=(0, 0, 0, SHADOW_ALPHA))
        td.text((LEFT_TEXT, y), ln, fill=(245, 245, 245), font=sub_font,
                stroke_width=STROKE_SUB, stroke_fill=(0, 0, 0))
        y += line_h_sub

    # Swipe bottom-right
    swipe = data.get("swipe", "листай →")
    sb = td.textbbox((0, 0), swipe, font=swipe_font)
    sw_w = sb[2] - sb[0]
    sw_x = W - sw_w - 50
    sw_y = H - 55
    sd.text((sw_x + SHADOW_OFFSET_SMALL[0], sw_y + SHADOW_OFFSET_SMALL[1]),
            swipe, fill=(0, 0, 0, SHADOW_ALPHA), font=swipe_font,
            stroke_width=STROKE_SWIPE, stroke_fill=(0, 0, 0, SHADOW_ALPHA))
    td.text((sw_x, sw_y), swipe, fill=(220, 220, 220), font=swipe_font,
            stroke_width=STROKE_SWIPE, stroke_fill=(0, 0, 0))

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=SHADOW_BLUR))
    img_rgba = Image.alpha_composite(img_rgba, shadow_layer)
    img_rgba = Image.alpha_composite(img_rgba, text_layer)

    img_rgba.convert("RGB").save(out, "JPEG", quality=92)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    data = json.loads(args.json.read_text())
    out = render(args.photo, data, args.out)
    print(f"saved -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
