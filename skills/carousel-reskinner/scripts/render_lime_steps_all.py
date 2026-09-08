#!/usr/bin/env python3
"""Lime PIL render for ШАГ 2-5 + CTA Stats slides. Same layout, different mockup per step."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import random

W, H = 1080, 1350
WHITE = (255, 255, 255)
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


def font(p, s):
    return ImageFont.truetype(p, s)


def measure(d, t, f):
    bb = d.textbbox((0, 0), t, font=f)
    return bb[2] - bb[0], bb[3] - bb[1]


def rounded_rect(d, xy, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def shadow_card(img, xy, r, blur=18, alpha=40):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle(xy, radius=r, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(sh)


def checkmark(d, cx, cy, r, color=LIME_DARK, tick=(255, 255, 255)):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    w = max(4, r // 5)
    p1 = (cx - r * 0.45, cy + r * 0.02)
    p2 = (cx - r * 0.10, cy + r * 0.32)
    p3 = (cx + r * 0.48, cy - r * 0.32)
    d.line([p1, p2], fill=tick, width=w)
    d.line([p2, p3], fill=tick, width=w)


def wrap(d, text, f, max_w):
    words, lines, cur = text.split(), [], ""
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


def draw_header(d, img, step_num, subtitle):
    wmf = font(F_BOLD, 26)
    d.text((50, 40), "@your_account", font=wmf, fill=TEXT_GREY)
    hf = font(F_BLACK, 96)
    txt = f"ШАГ {step_num}."
    tw, _ = measure(d, txt, hf)
    d.text(((W - tw) // 2, 145), txt, font=hf, fill=LIME_DARK)
    sf = font(F_BLACK, 54)
    tw, _ = measure(d, subtitle, sf)
    d.text(((W - tw) // 2, 260), subtitle, font=sf, fill=TEXT_DARK)


def draw_bullets(d, bullets, y_start=380):
    bf = font(F_BOLD, 32)
    rf = font(F_REG, 32)
    y = y_start
    for brand, rest in bullets:
        checkmark(d, 130, y + 16, 26)
        bw, _ = measure(d, brand, bf)
        d.text((180, y), brand, font=bf, fill=TEXT_DARK)
        d.text((180 + bw, y), rest, font=rf, fill=TEXT_DARK)
        y += 64
    return y


def draw_caption(d, caption, y=None):
    cf = font(F_REG, 28)
    cw, _ = measure(d, caption, cf)
    d.text(((W - cw) // 2, y if y else H - 70), caption, font=cf, fill=TEXT_GREY)


# ====== MOCKUPS ======

def mockup_image_grid(img, d, y0):
    """ШАГ 2: Midjourney-like generation grid."""
    card_x0, card_x1 = 90, W - 90
    pad = 36
    # header in card
    chf = font(F_BOLD, 22)
    prompt_text = "/imagine футуристичный город закат киберпанк"
    pf = font(F_REG, 24)
    p_lines = wrap(d, prompt_text, pf, card_x1 - card_x0 - 80)

    # 4 squares grid — centered in card
    gap = 16
    cell = 250
    grid_h = cell * 2 + gap
    grid_x0_offset = (card_x1 - card_x0 - cell * 2 - gap) // 2

    head_h = 44
    prompt_h = len(p_lines) * 30 + 28
    card_h = pad + head_h + prompt_h + 20 + grid_h + pad
    card_y1 = y0 + card_h

    shadow_card(img, (card_x0 + 4, y0 + 8, card_x1 + 4, card_y1 + 12), r=32, blur=22, alpha=35)
    d = ImageDraw.Draw(img)
    rounded_rect(d, (card_x0, y0, card_x1, card_y1), 32,
                 fill=CARD_BG, outline=CARD_BORDER, width=2)

    # header
    label_y = y0 + 26
    d.ellipse((card_x0 + 36, label_y + 4, card_x0 + 50, label_y + 18), fill=(96, 102, 240))
    d.text((card_x0 + 60, label_y), "Midjourney", font=chf, fill=TEXT_DARK)
    badge = "v7"
    bbw, _ = measure(d, badge, chf)
    d.text((card_x1 - 36 - bbw, label_y), badge, font=chf, fill=TEXT_GREY)
    d.line((card_x0 + 36, label_y + 38, card_x1 - 36, label_y + 38), fill=CARD_BORDER, width=2)

    # prompt
    px = card_x0 + 40
    py = label_y + 56
    for ln in p_lines:
        d.text((px, py), ln, font=pf, fill=TEXT_DARK)
        py += 30

    # 4 generation squares — gradient placeholder with subtle colors
    grid_y0 = py + 18
    cell_colors = [
        [(80, 30, 130), (240, 90, 60)],   # purple→orange (cyberpunk sunset)
        [(20, 60, 130), (180, 120, 200)], # blue→lavender
        [(70, 20, 90), (250, 140, 90)],   # deep purple→peach
        [(40, 90, 160), (240, 200, 80)],  # blue→gold
    ]
    for i in range(4):
        cx = card_x0 + grid_x0_offset + (i % 2) * (cell + gap)
        cy = grid_y0 + (i // 2) * (cell + gap)
        # gradient fill (top→bottom interp)
        top, bot = cell_colors[i]
        cell_img = Image.new("RGB", (cell, cell), top)
        cd = ImageDraw.Draw(cell_img)
        for yy in range(cell):
            t = yy / cell
            r_ = int(top[0] * (1 - t) + bot[0] * t)
            g_ = int(top[1] * (1 - t) + bot[1] * t)
            b_ = int(top[2] * (1 - t) + bot[2] * t)
            cd.line([(0, yy), (cell, yy)], fill=(r_, g_, b_))
        # rounded mask
        mask = Image.new("L", (cell, cell), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, cell, cell), radius=18, fill=255)
        img.paste(cell_img, (cx, cy), mask)
    return card_y1


def mockup_video_player(img, d, y0):
    """ШАГ 3: Sora-like video preview."""
    card_x0, card_x1 = 90, W - 90
    pad = 36
    chf = font(F_BOLD, 22)
    prompt = "человек идёт по Манхэттену вечером, кинематографично"
    pf = font(F_REG, 24)
    p_lines = wrap(d, prompt, pf, card_x1 - card_x0 - 80)

    video_h = 280
    head_h = 44
    prompt_h = len(p_lines) * 30 + 28
    card_h = pad + head_h + prompt_h + 20 + video_h + 60 + pad
    card_y1 = y0 + card_h

    shadow_card(img, (card_x0 + 4, y0 + 8, card_x1 + 4, card_y1 + 12), r=32, blur=22, alpha=35)
    d = ImageDraw.Draw(img)
    rounded_rect(d, (card_x0, y0, card_x1, card_y1), 32,
                 fill=CARD_BG, outline=CARD_BORDER, width=2)

    label_y = y0 + 26
    d.ellipse((card_x0 + 36, label_y + 4, card_x0 + 50, label_y + 18), fill=(20, 20, 20))
    d.text((card_x0 + 60, label_y), "Sora 2", font=chf, fill=TEXT_DARK)
    badge = "16s · 1080p"
    bbw, _ = measure(d, badge, chf)
    d.text((card_x1 - 36 - bbw, label_y), badge, font=chf, fill=TEXT_GREY)
    d.line((card_x0 + 36, label_y + 38, card_x1 - 36, label_y + 38), fill=CARD_BORDER, width=2)

    px = card_x0 + 40
    py = label_y + 56
    for ln in p_lines:
        d.text((px, py), ln, font=pf, fill=TEXT_DARK)
        py += 30

    # video thumbnail — night city gradient
    vx0 = px
    vy0 = py + 18
    vx1 = card_x1 - 40
    vy1 = vy0 + video_h
    grad = Image.new("RGB", (vx1 - vx0, vy1 - vy0), (12, 18, 40))
    gd = ImageDraw.Draw(grad)
    for yy in range(vy1 - vy0):
        t = yy / (vy1 - vy0)
        r_ = int(12 * (1 - t) + 80 * t)
        g_ = int(18 * (1 - t) + 40 * t)
        b_ = int(40 * (1 - t) + 90 * t)
        gd.line([(0, yy), (vx1 - vx0, yy)], fill=(r_, g_, b_))
    # city silhouette
    random.seed(42)
    for i in range(14):
        bw = random.randint(40, 90)
        bh = random.randint(80, 220)
        bx = i * 70 + random.randint(-10, 10)
        gd.rectangle((bx, vy1 - vy0 - bh, bx + bw, vy1 - vy0), fill=(6, 10, 26))
        # tiny windows
        for wy in range(0, bh - 20, 24):
            for wx in range(0, bw - 12, 16):
                if random.random() > 0.5:
                    gd.rectangle((bx + wx + 4, vy1 - vy0 - bh + wy + 6,
                                  bx + wx + 12, vy1 - vy0 - bh + wy + 14),
                                 fill=(255, 220, 120))
    mask = Image.new("L", grad.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, grad.size[0], grad.size[1]), radius=22, fill=255)
    img.paste(grad, (vx0, vy0), mask)

    # play button
    d = ImageDraw.Draw(img)
    pcx, pcy = (vx0 + vx1) // 2, (vy0 + vy1) // 2
    d.ellipse((pcx - 40, pcy - 40, pcx + 40, pcy + 40), fill=(255, 255, 255, 230))
    d.polygon([(pcx - 12, pcy - 18), (pcx - 12, pcy + 18), (pcx + 20, pcy)],
              fill=(40, 44, 52))

    # progress bar below
    bar_y = vy1 + 22
    d.rounded_rectangle((vx0, bar_y, vx1, bar_y + 6), radius=3, fill=CARD_BORDER)
    d.rounded_rectangle((vx0, bar_y, vx0 + (vx1 - vx0) // 3, bar_y + 6),
                        radius=3, fill=LIME_DARK)
    tf = font(F_REG, 20)
    d.text((vx0, bar_y + 16), "0:05 / 0:16", font=tf, fill=TEXT_GREY)
    return card_y1


def mockup_avatars_grid(img, d, y0):
    """ШАГ 4: HeyGen 4-grid avatars."""
    card_x0, card_x1 = 90, W - 90
    pad = 36
    chf = font(F_BOLD, 22)

    cell = 230
    gap = 16
    grid_h = cell * 2 + gap

    head_h = 44
    sub_h = 38
    card_h = pad + head_h + sub_h + 16 + grid_h + 56 + pad
    card_y1 = y0 + card_h

    shadow_card(img, (card_x0 + 4, y0 + 8, card_x1 + 4, card_y1 + 12), r=32, blur=22, alpha=35)
    d = ImageDraw.Draw(img)
    rounded_rect(d, (card_x0, y0, card_x1, card_y1), 32,
                 fill=CARD_BG, outline=CARD_BORDER, width=2)

    label_y = y0 + 26
    d.ellipse((card_x0 + 36, label_y + 4, card_x0 + 50, label_y + 18), fill=(120, 100, 240))
    d.text((card_x0 + 60, label_y), "HeyGen", font=chf, fill=TEXT_DARK)
    badge = "4 такта"
    bbw, _ = measure(d, badge, chf)
    d.text((card_x1 - 36 - bbw, label_y), badge, font=chf, fill=TEXT_GREY)
    d.line((card_x0 + 36, label_y + 38, card_x1 - 36, label_y + 38), fill=CARD_BORDER, width=2)

    sub = "Выбери выражение лица твоего двойника"
    pf = font(F_REG, 24)
    d.text((card_x0 + 40, label_y + 56), sub, font=pf, fill=TEXT_GREY)

    # 4 avatar cells — abstract portrait silhouettes
    grid_x0 = (W - (cell * 2 + gap)) // 2
    grid_y0 = label_y + 56 + 40
    avatar_bgs = [(40, 60, 120), (180, 130, 80), (110, 80, 160), (60, 120, 110)]
    for i in range(4):
        cx = grid_x0 + (i % 2) * (cell + gap)
        cy = grid_y0 + (i // 2) * (cell + gap)
        # gradient bg
        bg_top = avatar_bgs[i]
        bg_bot = tuple(min(255, v + 60) for v in bg_top)
        cell_img = Image.new("RGB", (cell, cell), bg_top)
        cd = ImageDraw.Draw(cell_img)
        for yy in range(cell):
            t = yy / cell
            r_ = int(bg_top[0] * (1 - t) + bg_bot[0] * t)
            g_ = int(bg_top[1] * (1 - t) + bg_bot[1] * t)
            b_ = int(bg_top[2] * (1 - t) + bg_bot[2] * t)
            cd.line([(0, yy), (cell, yy)], fill=(r_, g_, b_))
        # silhouette: head circle + shoulders
        head_r = cell // 5
        head_cx = cell // 2
        head_cy = int(cell * 0.42)
        cd.ellipse((head_cx - head_r, head_cy - head_r,
                    head_cx + head_r, head_cy + head_r),
                   fill=(220, 195, 175))
        # shoulders
        sh_w = cell // 1.6
        sh_y = head_cy + head_r + 4
        cd.ellipse((int(head_cx - sh_w / 2), sh_y,
                    int(head_cx + sh_w / 2), int(sh_y + sh_w * 0.9)),
                   fill=(60, 65, 80))
        mask = Image.new("L", (cell, cell), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, cell, cell), radius=18, fill=255)
        img.paste(cell_img, (cx, cy), mask)
        # tiny badge label
        d = ImageDraw.Draw(img)
        labels = ["Нейтральный", "Улыбка", "Серьёзный", "Энергичный"]
        lf = font(F_BOLD, 18)
        lw, _ = measure(d, labels[i], lf)
        d.rounded_rectangle((cx + 8, cy + cell - 36, cx + 8 + lw + 16, cy + cell - 10),
                            radius=10, fill=(255, 255, 255, 220))
        d.text((cx + 16, cy + cell - 32), labels[i], font=lf, fill=TEXT_DARK)

    # bottom action
    d = ImageDraw.Draw(img)
    gen_y = grid_y0 + grid_h + 18
    btn_w = 220
    btn_x = (W - btn_w) // 2
    d.rounded_rectangle((btn_x, gen_y, btn_x + btn_w, gen_y + 40),
                        radius=20, fill=LIME_DARK)
    gtf = font(F_BOLD, 20)
    gt = "Сгенерировать видео"
    gw, _ = measure(d, gt, gtf)
    d.text((btn_x + (btn_w - gw) // 2, gen_y + 9), gt, font=gtf, fill=(20, 30, 10))
    return card_y1


def mockup_subtitle_timeline(img, d, y0):
    """ШАГ 5: SubMagic-like timeline with colorful captions."""
    card_x0, card_x1 = 90, W - 90
    pad = 36
    chf = font(F_BOLD, 22)

    cap_lines = [
        ("ВОТ КАК", (255, 215, 60)),
        ("ОДНА НЕЙРОСЕТЬ", (240, 90, 90)),
        ("ЗАМЕНИТ КАМЕРУ", (110, 220, 130)),
        ("И МОНТАЖЁРА", (90, 170, 255)),
    ]
    head_h = 44
    timeline_h = 64
    captions_h = len(cap_lines) * 60 + 20
    card_h = pad + head_h + 20 + timeline_h + 20 + captions_h + pad
    card_y1 = y0 + card_h

    shadow_card(img, (card_x0 + 4, y0 + 8, card_x1 + 4, card_y1 + 12), r=32, blur=22, alpha=35)
    d = ImageDraw.Draw(img)
    rounded_rect(d, (card_x0, y0, card_x1, card_y1), 32,
                 fill=CARD_BG, outline=CARD_BORDER, width=2)

    label_y = y0 + 26
    d.ellipse((card_x0 + 36, label_y + 4, card_x0 + 50, label_y + 18), fill=(255, 90, 140))
    d.text((card_x0 + 60, label_y), "SubMagic", font=chf, fill=TEXT_DARK)
    badge = "AI Captions"
    bbw, _ = measure(d, badge, chf)
    d.text((card_x1 - 36 - bbw, label_y), badge, font=chf, fill=TEXT_GREY)
    d.line((card_x0 + 36, label_y + 38, card_x1 - 36, label_y + 38), fill=CARD_BORDER, width=2)

    # timeline track
    tl_y = label_y + 70
    tx0, tx1 = card_x0 + 40, card_x1 - 40
    d.rounded_rectangle((tx0, tl_y, tx1, tl_y + 36), radius=10, fill=(232, 234, 240))
    # waveform-like blocks
    random.seed(7)
    bx = tx0 + 6
    while bx < tx1 - 6:
        bw = random.randint(4, 12)
        bh = random.randint(8, 28)
        d.rectangle((bx, tl_y + 18 - bh // 2, bx + bw, tl_y + 18 + bh // 2),
                    fill=(150, 156, 170))
        bx += bw + 3
    # playhead
    ph_x = tx0 + (tx1 - tx0) // 3
    d.line((ph_x, tl_y - 6, ph_x, tl_y + 42), fill=LIME_DARK, width=3)

    # caption stack
    cy = tl_y + 64
    cf_caps = font(F_BLACK, 36)
    for txt, color in cap_lines:
        tw, _ = measure(d, txt, cf_caps)
        # chip background
        bg_x0 = (W - tw - 40) // 2
        bg_x1 = bg_x0 + tw + 40
        d.rounded_rectangle((bg_x0, cy, bg_x1, cy + 50), radius=14, fill=color)
        d.text(((W - tw) // 2, cy + 5), txt, font=cf_caps, fill=(20, 20, 25))
        cy += 60
    return card_y1


# ====== STEP RENDERERS ======

def render_step(step_num, subtitle, bullets, mockup_fn, caption, dst):
    img = Image.new("RGBA", (W, H), WHITE + (255,))
    d = ImageDraw.Draw(img)
    draw_header(d, img, step_num, subtitle)
    draw_bullets(d, bullets)
    card_y1 = mockup_fn(img, d, 530)
    d = ImageDraw.Draw(img)
    draw_caption(d, caption, y=min(card_y1 + 30, H - 50))
    img.convert("RGB").save(dst, "JPEG", quality=94)
    print(f"saved {dst}")


def render_cta(dst):
    """Final CTA slide — Ilya-style clean text: hook question + value line + trigger word."""
    img = Image.new("RGBA", (W, H), WHITE + (255,))
    d = ImageDraw.Draw(img)

    wmf = font(F_BOLD, 26)
    d.text((50, 40), "@your_account", font=wmf, fill=TEXT_GREY)

    # Hook question (top-center, ALL CAPS like Ilya slide 7)
    title_lines = [
        "КАК СОБРАТЬ ВИРАЛЬНЫЙ",
        "РОЛИК БЕЗ КАМЕРЫ",
        "И МОНТАЖЁРА?",
    ]
    hf = font(F_BLACK, 56)
    y = 240
    for ln in title_lines:
        tw, _ = measure(d, ln, hf)
        d.text(((W - tw) // 2, y), ln, font=hf, fill=TEXT_DARK)
        y += 72

    # Value sub-line (mid-card, regular weight)
    sub_lines = [
        "Эти 10 нейросетей + готовые связки",
        "и промпты по триггерному слову ниже",
    ]
    sf = font(F_REG, 30)
    y = 580
    for ln in sub_lines:
        tw, _ = measure(d, ln, sf)
        d.text(((W - tw) // 2, y), ln, font=sf, fill=TEXT_GREY)
        y += 44

    # Divider line lime
    div_y = 740
    d.line(((W - 200) // 2, div_y, (W + 200) // 2, div_y),
           fill=LIME_DARK, width=3)

    # CTA trigger
    cta_top = 800
    line1 = "Напиши в ком:ментариях"
    f1 = font(F_BOLD, 36)
    tw, _ = measure(d, line1, f1)
    d.text(((W - tw) // 2, cta_top), line1, font=f1, fill=TEXT_DARK)

    # Big lime trigger word with underline
    trigger = "«КОДВОРД»"
    tf = font(F_BLACK, 96)
    tw, th = measure(d, trigger, tf)
    trig_y = cta_top + 60
    d.text(((W - tw) // 2, trig_y), trigger, font=tf, fill=LIME_DARK)
    # underline
    d.line(((W - tw) // 2 + 10, trig_y + th + 10,
            (W + tw) // 2 - 10, trig_y + th + 10),
           fill=LIME_DARK, width=4)

    # CTA bottom
    bot = "пришлю в директ"
    bf = font(F_BOLD, 36)
    bw, _ = measure(d, bot, bf)
    d.text(((W - bw) // 2, trig_y + th + 50), bot, font=bf, fill=TEXT_DARK)

    img.convert("RGB").save(dst, "JPEG", quality=94)
    print(f"saved {dst}")


# ====== MAIN ======

OUT = Path("/tmp/carousel_palette/out")

# ШАГ 2
render_step(
    2, "Картинки",
    [("Midjourney", " — обложки, иллюстрации"),
     ("Nano Banana Pro", " — фото и сцены")],
    mockup_image_grid,
    "Не нужна камера — снимает нейросеть",
    OUT / "step2_lime_pil.jpg",
)

# ШАГ 3
render_step(
    3, "Видео",
    [("Sora 2", " — реалистичные сцены до 60 сек"),
     ("Seedance", " — короткие виральные клипы")],
    mockup_video_player,
    "Из одной строчки — готовый ролик",
    OUT / "step3_lime_pil.jpg",
)

# ШАГ 4
render_step(
    4, "Аватар и голос",
    [("HeyGen", " — говорящий двойник"),
     ("ElevenLabs", " — клонирует твой голос")],
    mockup_avatars_grid,
    "Снимаешь себя один раз — потом записывает нейросеть",
    OUT / "step4_lime_pil.jpg",
)

# ШАГ 5
render_step(
    5, "Монтаж",
    [("CapCut AI", " — автомонтаж и нарезка"),
     ("SubMagic", " — анимированные субтитры")],
    mockup_subtitle_timeline,
    "30 минут сырья → 5 готовых роликов за час",
    OUT / "step5_lime_pil.jpg",
)

# CTA
render_cta(OUT / "cta_lime_pil.jpg")
