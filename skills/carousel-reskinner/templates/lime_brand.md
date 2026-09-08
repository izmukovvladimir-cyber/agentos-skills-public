# Lime brand — default template for @your_account

The operator's recognizable carousel look. Default when no reference URL is given. Survives Mode B reference dubl (the accent stays lime, never the reference color).

## Canvas

- Size: 1080×1350 (5-slide) or 1080×1440 (12-slide). Padding `PAD = 80`.
- Output: JPEG quality 93, sRGB.

## Color palette

| Name | RGB | Use |
|------|-----|-----|
| WHITE | (255, 255, 255) | body slide bg |
| BG_LIGHT | (250, 250, 248) | secondary panels |
| DARK | (12, 12, 12) | body text |
| DIM | (130, 130, 130) | secondary text, hints |
| ACCENT (lime) | (200, 240, 60) | titles, checkmark discs, «КОДВОРД», key accents |
| ACCENT_DARK (lime dark) | (170, 215, 40) | underlines, dark variant |
| TXT_LIGHT | (240, 240, 240) | text on dark bg |
| CIRCLE_A | (110, 50, 200) | nominal purple for drawn circles (use real screenshots when possible) |
| CIRCLE_B | (235, 65, 165) | nominal pink (same — real circles preferred) |

**Reference (Mode B) override rule:** if the reference uses a different accent, ignore — keep lime. Memory: `feedback_carousel_reskin_protocol.md`.

## Typography (Inter family)

- `F_DISPLAY` = InterDisplay-Black.ttf — slide titles, hero numbers
- `F_BOLD` = Inter-Bold.ttf — emphasized body
- `F_SEMI` = Inter-SemiBold.ttf — subtitles
- `F_MED` = Inter-Medium.ttf — body
- `F_REG` = Inter-Regular.ttf — captions

Path: `/tmp/fonts/Inter/extras/ttf/`.

## Slide patterns

### Slide 1 (cover / hook)
- Studio black-bg portrait of the operator (full-bleed top half).
- ONE real IG-analytics ring cutout placed off-side at shoulder level (not on face).
- Bottom 50% solid black panel `(8,8,8)` covering Higgsfield potential fake-text on shirt.
- Title in WHITE uppercase F_DISPLAY 50, 3-4 short lines.
- Thin separator line.
- Subtitle in WHITE F_DISPLAY 32, 2 lines, sometimes lime instead of white.
- Footer `@your_account ✓` left, page `1/N` right.

### Body slides (2 … N-1)
- White bg.
- Title at top — F_DISPLAY 56, ACCENT lime color, 2 lines uppercase. Prefix `1.`, `2.`, etc.
- Bullets — lime disc (radius 22) with dark checkmark, body F_MED 30 DARK.
- Optional bottom visual: real carousel mockup thumbnails OR real IG screenshot. NEVER abstract "ХУК/ХОЛОДНО"-style fake cards.

### Final slide (CTA)
- White bg.
- Real IG analytics circle, large, centered at top (~y=80 — y=720).
- "↓ Пиши в комментариях" hint in DIM F_SEMI 30, centered.
- «КОДВОРД» in F_DISPLAY 100 ACCENT_DARK with underline, centered.
- Reward sentence: "и забирай промпт Content GPT — он пишет рилсы и карусели твоим голосом, чтобы блог рос ещё быстрее." centered, F_BOLD 24.
- 2 secondary CTA bullets with lime dots: «Сохрани пост …», «Поделись с другом-блогером …».
- Footer same as body slides.

## Footer (every slide)

- Top separator line at y = H - 110 (light grey on white, dark grey on dark).
- Left: `@your_account ✓` in F_SEMI 26.
- Right: page indicator `N / total` in F_MED 22.

## CTA word

Always «КОДВОРД» (Russian, brackets «»). The reward unlocks the Content GPT prompt that writes owner-voice carousels + reels.

## What to keep / what to drop

KEEP across versions:
- Lime accent
- Studio black-bg portrait on slide 1
- Real IG ring cutout (not drawn) — single, off-face
- White body slides with lime title prefix
- Final «КОДВОРД» CTA in lime with reward + 2 bullets

DROP / NEVER use:
- "1 аккаунт / Без ферм" or any redundant secondary metric — single big metric is enough
- The operator's face thumbnail above the metric circle on final slide (looks bolted-on)
- Abstract "ХУК/ХОЛОДНО" / "0:00.6" cards as body visuals
- Blue or any non-lime accent
