# Чёрный лист (Black Leaf)

Brand template for @your_account aphoristic single-slide posts.
Reference: @donor_account style (posts `<post_code>`, `<post_code>`).
Approved 2026-05-17 by the operator.

## Use case

- **Одиночный слайд** — афоризм / правда / список «N способов X». Низкая когнитивная нагрузка, высокий screenshot-rate.
- **Multi-slide карусель** (2026-05-17) — один параграф на слайд, естественная разбивка по структуре «хук → раскрытие → пейофф». Хорошо работает для рерайта абзацных постов из text-only референсов. Каждый слайд использует тот же `render_black_leaf.py` с массивом `paragraphs` длины 1.
- Подходит для cold-front виралок без портретного слайда.

## Canvas

- Size: **1080 × 1350** (Instagram portrait 4:5).
- Background: **`(0, 0, 0)`** — pure black.

## Typography (brand-fixed, never replaced by reference's font)

- Family: **DejaVu Serif Regular** (`/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf`) — the operator final pick 2026-05-17 (overrides earlier mid-session sans choice)
- Body size: **48pt**
- Watermark size: **34pt**
- Text colour: `(235, 235, 235)` — near-white
- Watermark colour: `(110, 110, 110)` — mid-grey

**Why serif:** the operator compared sans-version (his initial "как на прошлом" call) to serif-version (my very first render) and confirmed serif is the correct brand look for Чёрный лист. The Telegram code-block monospace was NOT a reference (he initially seemed to indicate it but it was a misread).

## Layout

- Left margin: **130px**
- Right margin: **130px** (max text width = **820px**)
- Word-wrap by words, line breaks at word boundaries
- Body vertical centring: block centered with **-40px upward offset** from canvas centre (visually balanced, leaves room for watermark below)
- Watermark: left-aligned with body, **20px below last line of body**
- Line gap (within paragraph): **14px**
- Paragraph gap: **38px**

## Two content sub-formats supported

1. **Numbered list** (e.g. «Самые легкие способы разбогатеть: 1. Продавать ... 2. ...»)
   - Hook line + items as separate paragraphs.
   - Items prefixed with `1.  `, `2.  ` (digit + dot + double space).

2. **Plain paragraphs** (e.g. «Если вы до сих пор не знаете, чем заняться в жизни — займитесь собой. Не работой, ... Станьте самой ...»)
   - 2-4 paragraphs of free text.
   - Em-dashes (`—`) for inline breaks, not hyphens.

## Caption template (works with Чёрный лист)

```
Пиши «<TRIGGER>» в ком:ментариях и забирай <CONCRETE_LEAD_MAGNET>, как с нуля <CONCRETE_OUTCOME>.

Именно таким способом за <TIMEFRAME> я <CONCRETE_RESULTS_with_masked_words> без <BARRIER_1>, без <BARRIER_2> и без <BARRIER_3>.
```

Active trigger word of the live funnel = `«КОДВОРД»` (verify via [[verify-active-funnel]] each time).

## How to render

```bash
python3 ~/.claude/skills/carousel-reskinner/scripts/render_black_leaf.py \
    --json /tmp/input.json --out /tmp/slide.jpg
```

Where `/tmp/input.json`:
```json
{
  "paragraphs": [
    "Hook line",
    "Body paragraph one.",
    "Body paragraph two."
  ],
  "watermark": "@your_account"
}
```

## Pre-flight checks (per `feedback_carousel_rendering_rules.md`)

- All text fits within max_w (820px) — script enforces via word-wrap
- No taboo words leaked through (slide content + watermark)
- Body block centred vertically
- Watermark visible and grey-toned (not full white)
- For numbered lists: digit + dot + double space, consistent alignment
