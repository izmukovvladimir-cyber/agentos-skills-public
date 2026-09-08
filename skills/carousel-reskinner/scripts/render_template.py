"""Carousel v2 — 5-slide variant in @donor_account format.

Theme: «Алгоритмы Instagram изменились. Вот новая формула рилсов.»
CTA: КОДВОРД + save + share.
Layout: 1080×1350, white bg, lime accent, uppercase blue-replaced-by-lime titles.
"""
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).parent
RAW = Path("/tmp/carousel_v1/raw")
RAW2 = Path("/tmp/carousel_v2/raw")
OUT = ROOT / "out_final"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1350
PAD = 80

WHITE = (255, 255, 255)
BG_LIGHT = (250, 250, 248)
DARK = (12, 12, 12)
DIM = (130, 130, 130)
ACCENT = (200, 240, 60)        # lime — the operator's brand color
ACCENT_DARK = (170, 215, 40)
CIRCLE_A = (110, 50, 200)      # purple
CIRCLE_B = (235, 65, 165)      # pink
TXT_LIGHT = (240, 240, 240)

FONT_DIR = Path("/tmp/fonts/Inter/extras/ttf")
F_DISPLAY = str(FONT_DIR / "InterDisplay-Black.ttf")
F_BOLD = str(FONT_DIR / "Inter-Bold.ttf")
F_SEMI = str(FONT_DIR / "Inter-SemiBold.ttf")
F_MED = str(FONT_DIR / "Inter-Medium.ttf")
F_REG = str(FONT_DIR / "Inter-Regular.ttf")


def F(p, s):
    return ImageFont.truetype(p, s)


def wrap(text, fnt, max_w, draw):
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=fnt) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if not words:
            lines.append("")
    return lines


def draw_block(d, x, y, text, fnt, fill, max_w, line_gap=10):
    """Draw wrapped text starting at (x, y). Returns end y."""
    lines = wrap(text, fnt, max_w, d)
    lh = fnt.size + line_gap
    for ln in lines:
        d.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def base_white():
    return Image.new("RGB", (W, H), WHITE)


# ───────────── footer ─────────────
def footer(img, page_num, total=5, dark_bg=False):
    d = ImageDraw.Draw(img)
    line_col = (60, 60, 60) if dark_bg else (200, 200, 200)
    text_col = TXT_LIGHT if dark_bg else DARK
    dim_col = (160, 160, 160) if dark_bg else (140, 140, 140)
    d.line([(PAD, H - 110), (W - PAD, H - 110)], fill=line_col, width=1)
    fH = F(F_SEMI, 26)
    d.text((PAD, H - 88), "@your_account ✓", font=fH, fill=text_col)
    fS = F(F_MED, 24)
    pn = f"{page_num} / {total}"
    pw = d.textlength(pn, font=fS)
    d.text((W - PAD - pw, H - 84), pn, font=fS, fill=dim_col)


# ───────────── view-count circle ─────────────
def draw_metric_circle(img, cx, cy, r, number_text, label="Просмотры"):
    """Draw a gradient-ringed circle with a metric number inside (like @donor_account style)."""
    # background filled white-ish ellipse first
    overlay = Image.new("RGBA", (r * 2 + 60, r * 2 + 60), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # filled white inner disc with subtle shadow
    od.ellipse([30, 30, 30 + 2 * r, 30 + 2 * r], fill=(255, 255, 255, 230))

    # gradient ring — draw arc segments by stepping degrees
    steps = 360
    for i in range(steps):
        a = i / steps
        # blend lime ↔ pink
        rch = int(CIRCLE_A[0] * (1 - a) + CIRCLE_B[0] * a)
        gch = int(CIRCLE_A[1] * (1 - a) + CIRCLE_B[1] * a)
        bch = int(CIRCLE_A[2] * (1 - a) + CIRCLE_B[2] * a)
        od.arc(
            [30, 30, 30 + 2 * r, 30 + 2 * r],
            start=i - 90,
            end=i + 2 - 90,
            fill=(rch, gch, bch, 255),
            width=16,
        )

    # paste onto img
    img.paste(overlay, (cx - r - 30, cy - r - 30), overlay)

    # text inside circle: label + number
    d = ImageDraw.Draw(img)
    fLab = F(F_MED, 22)
    fNum = F(F_BOLD, 48)
    lw = d.textlength(label, font=fLab)
    nw = d.textlength(number_text, font=fNum)
    d.text((cx - lw / 2, cy - 50), label, font=fLab, fill=(80, 80, 80))
    d.text((cx - nw / 2, cy - 10), number_text, font=fNum, fill=DARK)


# ───────────── SLIDE 1: HOOK ─────────────
def slide_1():
    img = base_white()
    d = ImageDraw.Draw(img)

    # background: studio cover photo the operator (v1 baseline he confirmed)
    try:
        bg = Image.open(RAW / "cover.png").convert("RGB")
        # center-crop to 1080x1350
        bw, bh = bg.size
        target_ratio = W / H
        bg_ratio = bw / bh
        if bg_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            bg = bg.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = max(0, (bh - new_h) // 3)  # bias toward top so face stays visible
            bg = bg.crop((0, y0, bw, y0 + new_h))
        bg = bg.resize((W, H))
        # subtle darken bottom half for text legibility
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        # gradient dark to bottom
        for i in range(H):
            alpha = 0
            if i > H * 0.55:
                t = (i - H * 0.55) / (H * 0.45)
                alpha = int(180 * t)
            od.line([(0, i), (W, i)], fill=(0, 0, 0, alpha))
        bg = bg.convert("RGBA")
        bg.alpha_composite(overlay)
        img.paste(bg.convert("RGB"), (0, 0))
        d = ImageDraw.Draw(img)
    except Exception as e:
        print("portrait err", e)

    # solid black panel covering bottom 50% — hides Higgsfield fake-text
    d.rectangle([0, 720, W, H], fill=(8, 8, 8))

    # Real Instagram-analytics circle cutout — small, left shoulder (like @donor_account ref_01)
    try:
        circ = Image.open(RAW2 / "circle_55m.png").convert("RGBA")
        # white background → transparent; dark text → white (for legibility over dark bg)
        px = circ.load()
        for yy in range(circ.height):
            for xx in range(circ.width):
                r, g, b, a = px[xx, yy]
                if r > 235 and g > 235 and b > 235:
                    px[xx, yy] = (0, 0, 0, 0)
                elif r < 90 and g < 90 and b < 90:
                    px[xx, yy] = (255, 255, 255, 255)
        target_w = 340
        ratio_c = circ.height / circ.width
        target_h = int(target_w * ratio_c)
        circ = circ.resize((target_w, target_h))
        # left side, shoulder level — does not cover face
        img.paste(circ, (-30, 430), circ)
    except Exception as e:
        print("circle paste err", e)
    d = ImageDraw.Draw(img)

    # headline — close to @donor_account verbatim
    d = ImageDraw.Draw(img)
    fH = F(F_DISPLAY, 50)
    lines = [
        "АЛГОРИТМЫ INSTAGRAM",
        "ПОМЕНЯЛИСЬ —",
        "СТАРЫЕ КАРУСЕЛИ",
        "НЕ РАБОТАЮТ.",
    ]
    y = 770
    for ln in lines:
        tw = d.textlength(ln, font=fH)
        d.text(((W - tw) / 2, y), ln, font=fH, fill=WHITE)
        y += 58

    d.line([(W // 2 - 60, y + 22), (W // 2 + 60, y + 22)], fill=WHITE, width=3)
    y += 56

    fSub = F(F_DISPLAY, 32)
    sub_lines = ["ВОТ НОВАЯ СТРУКТУРА", "ДЛЯ ТАКИХ ОХВАТОВ"]
    for ln in sub_lines:
        tw = d.textlength(ln, font=fSub)
        d.text(((W - tw) / 2, y), ln, font=fSub, fill=WHITE)
        y += 42

    footer(img, 1, dark_bg=True)
    img.save(OUT / "slide_01.jpg", "JPEG", quality=93)
    print("✓ slide_01")


# ───────────── Body slide template (S2, S3, S4) ─────────────
def body_slide(n, title_lines, bullets, bottom_visual_fn=None, page_num=None):
    img = base_white()
    d = ImageDraw.Draw(img)

    # title — uppercase, accent-lime, top
    fT = F(F_DISPLAY, 56)
    y = 100
    for ln in title_lines:
        tw = d.textlength(ln, font=fT)
        d.text(((W - tw) / 2, y), ln, font=fT, fill=ACCENT_DARK)
        y += 70

    # bullets
    y += 50
    fBul = F(F_MED, 30)
    for b in bullets:
        # accent disc with check
        disc_r = 22
        cx = PAD + disc_r
        cy = y + 20
        d.ellipse([cx - disc_r, cy - disc_r, cx + disc_r, cy + disc_r], fill=ACCENT)
        d.text((cx - 12, cy - 20), "✓", font=F(F_BOLD, 32), fill=DARK)
        # text wrapped
        end_y = draw_block(d, PAD + 64, y, b, fBul, DARK, max_w=W - PAD - 64 - PAD, line_gap=8)
        y = end_y + 18

    # bottom visual area (optional)
    if bottom_visual_fn:
        bottom_visual_fn(img, d)

    footer(img, page_num or n)
    img.save(OUT / f"slide_{(page_num or n):02d}.jpg", "JPEG", quality=93)
    print(f"✓ slide_{(page_num or n):02d}")


# ───────────── helper: paste real carousel slide as phone-mockup ─────────────
V1 = Path("/tmp/carousel_v1/out_v8")

def paste_mockup(img, src_path, x, y, target_w, radius=24, border_color=(220, 220, 220)):
    """Paste a real carousel slide as a phone-shape rounded mockup at (x, y)."""
    try:
        m = Image.open(src_path).convert("RGB")
        mw, mh = m.size
        target_h = int(target_w * mh / mw)
        m = m.resize((target_w, target_h))
        # rounded mask
        mask = Image.new("L", (target_w, target_h), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, target_w, target_h], radius=radius, fill=255)
        img.paste(m, (x, y), mask)
        # subtle border
        d2 = ImageDraw.Draw(img)
        d2.rounded_rectangle([x, y, x + target_w, y + target_h], radius=radius,
                             outline=border_color, width=2)
    except Exception as e:
        print("mockup err", src_path, e)


# ───────────── SLIDE 2 ─────────────
def visual_s2(img, d):
    # Two real owner carousel covers as phone-mockups (cover + предпоследний)
    bw = 380
    by = 760
    gap = 60
    total = bw * 2 + gap
    bx = (W - total) // 2
    paste_mockup(img, V1 / "slide_01.jpg", bx, by, bw)
    paste_mockup(img, V1 / "slide_11.jpg", bx + bw + gap, by, bw)


def slide_2():
    body_slide(
        2,
        ["1. СТРУКТУРА КАРУСЕЛЕЙ", "ОБНОВИЛАСЬ"],
        [
            "Самое важное в каруселях — это первый слайд, от него зависит будут ли охваты.",
            "Обязательно используй визуальные элементы: стрелочки, мокапы, акценты.",
            "Самая полезная информация — на предпоследнем слайде, чтобы дошли до призыва.",
        ],
        bottom_visual_fn=visual_s2,
        page_num=2,
    )


# ───────────── SLIDE 3 ─────────────
def visual_s3(img, d):
    # Two design-focused mockups: clean cover + bold-typo slide
    bw = 380
    by = 760
    gap = 60
    total = bw * 2 + gap
    bx = (W - total) // 2
    paste_mockup(img, V1 / "slide_01.jpg", bx, by, bw)
    paste_mockup(img, V1 / "slide_12.jpg", bx + bw + gap, by, bw)


def slide_3():
    body_slide(
        3,
        ["2. НОВЫЙ ДИЗАЙН", "КАРУСЕЛЕЙ"],
        [
            "Правило «одного экрана». Не пишите больше 4 коротких тезисов на слайд.",
            "Используйте жирные шрифты для заголовков и тонкие для пояснений.",
            "Не располагайте текст слишком близко к краям, иначе алгоритмы не считают его.",
        ],
        bottom_visual_fn=visual_s3,
        page_num=3,
    )


# ───────────── SLIDE 4 ─────────────
def visual_s4(img, d):
    # Real КОДВОРД hero slide as left mockup + comment-mockup on right
    bw = 380
    by = 760
    gap = 60
    total = bw * 2 + gap
    bx = (W - total) // 2
    paste_mockup(img, V1 / "slide_12.jpg", bx, by, bw)

    # right side: small comment-mockup panel (real, IG-style)
    px_ = bx + bw + gap
    py_ = by
    pw_ = bw
    ph_ = int(bw * 1.32)
    d.rounded_rectangle([px_, py_, px_ + pw_, py_ + ph_],
                        radius=24, fill=(20, 20, 22))
    fHd = F(F_BOLD, 22)
    d.text((px_ + 22, py_ + 18), "Комментарии", font=fHd, fill=TXT_LIGHT)
    rows = [
        ("user_one", "КОДВОРД"),
        ("user_two", "КОДВОРД"),
        ("user_three", "КОДВОРД"),
        ("user_four", "КОДВОРД"),
    ]
    yy = py_ + 70
    for username, msg in rows:
        d.ellipse([px_ + 22, yy, px_ + 22 + 28, yy + 28], fill=(120, 120, 120))
        fU = F(F_SEMI, 20)
        d.text((px_ + 62, yy - 2), username, font=fU, fill=TXT_LIGHT)
        fM = F(F_BOLD, 22)
        d.text((px_ + 62, yy + 24), msg, font=fM, fill=ACCENT)
        fR = F(F_REG, 16)
        d.text((px_ + 62, yy + 52), "Автор: В директ ✓", font=fR, fill=(150, 200, 150))
        yy += 80


def slide_4():
    body_slide(
        4,
        ["3. ПРИЗЫВ К", "ДЕЙСТВИЮ"],
        [
            "Призыв по кодовому слову — работает лучше всего. Слово в коммент = польза в директ.",
            "Чем больше однотипных комментариев в первые часы — тем больше охваты.",
        ],
        bottom_visual_fn=visual_s4,
        page_num=4,
    )


# ───────────── SLIDE 5: CTA ─────────────
def slide_5():
    img = base_white()
    d = ImageDraw.Draw(img)

    # Real Instagram circle screenshot — hero metric
    try:
        circ = Image.open(RAW2 / "circle_55m.png").convert("RGBA")
        # remove white bg
        px = circ.load()
        for yy in range(circ.height):
            for xx in range(circ.width):
                r, g, b, a = px[xx, yy]
                if r > 235 and g > 235 and b > 235:
                    px[xx, yy] = (0, 0, 0, 0)
        target_w = 720
        ratio_c = circ.height / circ.width
        target_h = int(target_w * ratio_c)
        circ = circ.resize((target_w, target_h))
        img.paste(circ, ((W - target_w) // 2, 80), circ)
    except Exception as e:
        print("circle paste err on slide_5", e)
    d = ImageDraw.Draw(img)

    # "Пиши в комментариях"
    fSub = F(F_SEMI, 30)
    sub = "↓ Пиши в комментариях"
    sw = d.textlength(sub, font=fSub)
    d.text(((W - sw) / 2, 720), sub, font=fSub, fill=(80, 80, 80))

    # «КОДВОРД» — big underline link style
    fPak = F(F_DISPLAY, 100)
    pak = "«КОДВОРД»"
    pw = d.textlength(pak, font=fPak)
    pak_x = (W - pw) / 2
    pak_y = 780
    d.text((pak_x, pak_y), pak, font=fPak, fill=ACCENT_DARK)
    d.line([(pak_x, pak_y + 118), (pak_x + pw, pak_y + 118)], fill=ACCENT_DARK, width=4)

    # reward sentence
    fR = F(F_BOLD, 24)
    reward = "и забирай промпт Content GPT — он пишет\nрилсы и карусели твоим голосом, чтобы\nблог рос ещё быстрее."
    y = 920
    for ln in reward.split("\n"):
        tw = d.textlength(ln, font=fR)
        d.text(((W - tw) / 2, y), ln, font=fR, fill=DARK)
        y += 32

    # mini secondary CTAs
    y_sec = 1010
    fSec = F(F_SEMI, 22)
    rows = [
        "Сохрани пост, чтобы вернуться к правилам.",
        "Поделись с другом-блогером, который ноет про охваты.",
    ]
    for txt in rows:
        d.ellipse([PAD + 14, y_sec + 10, PAD + 14 + 14, y_sec + 10 + 14], fill=ACCENT)
        d.text((PAD + 46, y_sec + 4), txt, font=fSec, fill=(60, 60, 60))
        y_sec += 40

    footer(img, 5)
    img.save(OUT / "slide_05.jpg", "JPEG", quality=93)
    print("✓ slide_05")


if __name__ == "__main__":
    slide_1()
    slide_2()
    slide_3()
    slide_4()
    slide_5()
    print("\nDone:", sorted(p.name for p in OUT.iterdir()))
