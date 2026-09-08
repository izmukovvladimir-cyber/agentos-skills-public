#!/usr/bin/env python3
"""ШАГ 1 — lime palette, pure PIL render with embedded ChatGPT mockup card."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

W, H = 1080, 1350
WHITE = (255, 255, 255)
BG = WHITE
LIME = (200, 240, 60)
LIME_DARK = (170, 215, 40)
TEXT_DARK = (40, 44, 52)
TEXT_GREY = (110, 116, 124)
CARD_BG = (252, 252, 250)
CARD_BORDER = (228, 232, 238)
BUBBLE_USER = (240, 242, 246)
BUBBLE_BOT = (248, 249, 251)

F_BLACK = "~/.fonts/Inter-Black.ttf"
F_BOLD = "~/.fonts/Inter-Bold.ttf"
F_REG = "~/.fonts/Inter-Regular.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def measure(d, text, f):
    bb = d.textbbox((0, 0), text, font=f)
    return bb[2] - bb[0], bb[3] - bb[1]


def rounded_rect(d, xy, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def shadow_card(img, xy, r, blur=18, alpha=40):
    """Draw soft drop shadow under a rounded card."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle(xy, radius=r, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(sh)


def checkmark(d, cx, cy, r, color=LIME, tick=(255, 255, 255)):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # тонкая галочка
    w = max(4, r // 5)
    p1 = (cx - r * 0.45, cy + r * 0.02)
    p2 = (cx - r * 0.10, cy + r * 0.32)
    p3 = (cx + r * 0.48, cy - r * 0.32)
    d.line([p1, p2], fill=tick, width=w)
    d.line([p2, p3], fill=tick, width=w)


def wrap_text(d, text, f, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if measure(d, cand, f)[0] <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render(dst):
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)

    # 1) watermark
    wmf = font(F_BOLD, 26)
    d.text((50, 40), "@your_account", font=wmf, fill=TEXT_GREY)

    # 2) header "ШАГ 1."
    hf = font(F_BLACK, 96)
    h_text = "ШАГ 1."
    tw, th = measure(d, h_text, hf)
    d.text(((W - tw) // 2, 145), h_text, font=hf, fill=LIME_DARK)

    # 3) subtitle "Тексты и идеи"
    sf = font(F_BLACK, 54)
    s_text = "Тексты и идеи"
    tw, th = measure(d, s_text, sf)
    d.text(((W - tw) // 2, 260), s_text, font=sf, fill=TEXT_DARK)

    # 4) two checkmark bullets
    bf = font(F_BOLD, 32)
    bullets = [
        ("ChatGPT", " — сценарии, хуки, идеи"),
        ("Claude", " — длинные тексты, прогревы"),
    ]
    y = 380
    bullet_x = 130
    for brand, rest in bullets:
        checkmark(d, bullet_x, y + 16, 26, color=LIME_DARK)
        # bold brand + regular rest
        bx = bullet_x + 50
        bw, _ = measure(d, brand, bf)
        d.text((bx, y), brand, font=bf, fill=TEXT_DARK)
        d.text((bx + bw, y), rest, font=font(F_REG, 32), fill=TEXT_DARK)
        y += 64

    # 5) ChatGPT mockup card — two-pass: compute layout, then draw
    card_x0, card_x1 = 90, W - 90
    card_y0 = 560
    pad = 36

    # --- pre-compute bubble dimensions to size card ---
    chf = font(F_BOLD, 22)
    pf = font(F_REG, 26)
    rf = font(F_REG, 26)
    icf = font(F_REG, 22)

    prompt = "Напиши 5 виральных хуков про нейросети для коротких роликов"
    p_max_w = card_x1 - card_x0 - 200
    p_lines = wrap_text(d, prompt, pf, p_max_w)
    p_h = len(p_lines) * 36 + 30

    bot_lines = [
        "1. Эта одна нейросеть заменит SMM-щика",
        "2. Я не снимал 30 дней — выросло в 2 раза",
        "3. Один промпт = 100 идей для роликов",
    ]
    bot_max_w = card_x1 - card_x0 - 200
    real_lines = []
    for ln in bot_lines:
        real_lines.extend(wrap_text(d, ln, rf, bot_max_w))
    b_h = len(real_lines) * 38 + 36

    head_h = 60  # label + divider
    actions_h = 50  # mini icon row under response
    card_h = pad + head_h + p_h + 28 + b_h + actions_h + pad
    card_y1 = card_y0 + card_h

    # --- draw card frame ---
    shadow_card(img, (card_x0 + 4, card_y0 + 8, card_x1 + 4, card_y1 + 12),
                r=32, blur=22, alpha=35)
    d = ImageDraw.Draw(img)
    rounded_rect(d, (card_x0, card_y0, card_x1, card_y1), 32,
                 fill=CARD_BG, outline=CARD_BORDER, width=2)

    # card header
    label_y = card_y0 + 26
    d.ellipse((card_x0 + 36, label_y + 4, card_x0 + 50, label_y + 18),
              fill=(34, 197, 94))
    d.text((card_x0 + 60, label_y), "ChatGPT", font=chf, fill=TEXT_DARK)
    badge = "GPT-5"
    bbw, _ = measure(d, badge, chf)
    d.text((card_x1 - 36 - bbw, label_y), badge, font=chf, fill=TEXT_GREY)
    d.line((card_x0 + 36, label_y + 38, card_x1 - 36, label_y + 38),
           fill=CARD_BORDER, width=2)

    # user prompt bubble (right)
    p_w = max(measure(d, ln, pf)[0] for ln in p_lines) + 40
    p_x1 = card_x1 - 40
    p_x0 = p_x1 - p_w
    p_y0 = label_y + 70
    p_y1 = p_y0 + p_h
    rounded_rect(d, (p_x0, p_y0, p_x1, p_y1), 22, fill=BUBBLE_USER)
    py = p_y0 + 15
    for ln in p_lines:
        lw, _ = measure(d, ln, pf)
        d.text((p_x1 - 20 - lw, py), ln, font=pf, fill=TEXT_DARK)
        py += 36

    # bot response bubble (left)
    b_w = max(measure(d, ln, rf)[0] for ln in real_lines) + 40
    b_x0 = card_x0 + 40
    b_x1 = b_x0 + b_w
    b_y0 = p_y1 + 28
    b_y1 = b_y0 + b_h
    rounded_rect(d, (b_x0, b_y0, b_x1, b_y1), 22, fill=BUBBLE_BOT,
                 outline=CARD_BORDER, width=1)
    by = b_y0 + 18
    for ln in real_lines:
        d.text((b_x0 + 20, by), ln, font=rf, fill=TEXT_DARK)
        by += 38

    # mini action row under response (copy / 👍 / 👎 / regen) — text-only chips
    chip_y = b_y1 + 14
    chips = ["⌘ скопировать", "↻ перегенерировать", "↗ поделиться"]
    cx = b_x0 + 4
    for chip in chips:
        cw_, _ = measure(d, chip, icf)
        d.text((cx, chip_y), chip, font=icf, fill=TEXT_GREY)
        cx += cw_ + 26

    # 6) bottom caption
    cf = font(F_REG, 28)
    caption = "Тот же запрос в Claude — для длинных постов и прогревов"
    cw, _ = measure(d, caption, cf)
    cap_y = min(card_y1 + 50, H - 80)
    d.text(((W - cw) // 2, cap_y), caption, font=cf, fill=TEXT_GREY)

    img.convert("RGB").save(dst, "JPEG", quality=94)
    print(f"saved {dst}")


if __name__ == "__main__":
    render("/tmp/carousel_palette/out/step1_lime_pil.jpg")
