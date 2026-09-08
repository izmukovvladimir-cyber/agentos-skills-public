# CTA-Stats (последний/CTA-слайд карусели со статистикой)

Brand template for @your_account carousel CTA slide — real IG-statistics
screenshots side-by-side + CTA text above, on pure black canvas.
Approved 2026-05-18 by the operator после отвержения DIY dark-cards mockup-варианта.
Reference style: @donor_account.

## Use case

- **ФИНАЛЬНЫЙ слайд карусели** — «Карусель пусть заканчивается призывом. И призыв, где белые искренние» (= белые bbox + настоящие скрины). После CTA-Stats ничего не идёт.
- Цель: дать social proof через реальные IG-скрины + дожать CTA с активным триггер-словом.
- Pair с любым другим шаблоном для верхних слайдов (Cover Premium + Black Leaf body, или Black Leaf-only).
- **Не ставить фото-слайд после CTA** (2026-05-18 «зачем он? Он не нужен такой слайд» про cafe-фото после CTA). Лишние фото — для следующих каруселей, не в хвост текущей.

## Canvas

- Size: **1080 × 1350** (IG portrait 4:5)
- Background: **`(0, 0, 0)`** — pure black, как Black Leaf.

## Layout

```
┌─────────────────────────────────────┐
│                                     │  y=0
│                                     │
│     CTA text (3-4 lines)            │  y=110, DejaVu Serif 40pt
│     centered, white                 │
│                                     │
│                                     │
│  ┌──────────┐    ┌──────────┐       │  y=660
│  │          │    │          │       │
│  │ Screen 1 │    │ Screen 2 │       │  bbox 480×600 each
│  │ (white   │    │ (white   │       │  gap 40px
│  │  card)   │    │  card)   │       │  rounded radius=18
│  │          │    │          │       │
│  └──────────┘    └──────────┘       │  y=1260
│                                     │
│         @your_account             │  y=H-55, grey
└─────────────────────────────────────┘
```

## Typography

- CTA font: **DejaVu Serif** (`/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf`), **40pt**, colour `(235, 235, 235)`
- Watermark: same font, **30pt**, colour `(110, 110, 110)`

## CTA structure

3-4 строки serif, centered. Pattern:

```
Пиши «<TRIGGER>» в ком:ментариях,
и я пришлю <TRIGGER> — как с нуля
<OUTCOME>.
```

Текущая активная воронка → trigger = `«КОДВОРД»` (verify via [[verify-active-funnel]]
each session).

**CRITICAL — `<LEAD_MAGNET>` MUST equal `<TRIGGER>` буквально.** Обещание в CTA называет
ровно тот материал, который лежит за кодовым словом. НЕ подменять триггер-слово синонимами
(«гайд», «схема», «чек-лист», «шпаргалка») — это подрыв доверия и нарушение
caption truth-check rule из [[post-rewrite-workflow]].

- ✅ «Пиши "<КОДВОРД>" → пришлю **<то, что реально лежит за словом>**»
- ❌ «Пиши "<КОДВОРД>" → пришлю гайд / схему / план / шпаргалку», когда там другое
- ❌ В caption «забирай **схему**», когда за словом не схема

## Screenshots rules

- **РЕАЛЬНЫЕ скрины IG-статистики владельца аккаунта** — НЕ DIY mockup через PIL.
  Mockup отвергнут оператором 2026-05-18: «У тебя получилось не настоящие скрины».
- Equal size: **480×600 bbox каждый**, gap 40px между ними, total 1000×600.
- Each screenshot fits within bbox preserving aspect ratio (white padding по краям).
- **White rounded_rectangle background** (radius=18, fill=255,255,255) под каждым скрином —
  integrating light IG-UI in dark canvas, не выглядит как floating fragment.
- **Crop top status bar:** для iPhone-скринов передать `crop_top_pct: [0.10]` —
  убрать часы / иконки сети / батареи. Для desktop-cropped скринов передать 0.0.
- **Stop-words рискованны:** реальные цифры в скринах (`млн`, `тыс`, `подписчиков`)
  не маскированы — владелец аккаунта принимает риск, это social proof. См. [[instagram-operator]].

## Dark theme нюанс

Если хочется dark look для скринов (как у @donor_account):
- **Не обрабатывать через PIL** (invert даёт магента-зелёные стрелки → магента-фуксия).
- Попросить владельца аккаунта переснять скрины в **IG Dark Mode** (Settings → Theme → Dark).
- DIY dark-cards mockup ОТВЕРГНУТ 2026-05-18, не возвращаться к этому подходу.

## How to render

```bash
python3 ~/.claude/skills/carousel-reskinner/scripts/render_cta_stats.py \
    --json /tmp/cta_stats.json \
    --out /tmp/cta_slide.jpg
```

`cta_stats.json`:
```json
{
  "cta_lines": [
    "Пиши «КОДВОРД» в ком:ментариях,",
    "и я пришлю гайд — как с нуля",
    "собрать первые 10к под:писчиков",
    "в Instagram."
  ],
  "screenshots": [
    "~/gateway/media-inbound/<screenshot1>.jpg",
    "~/gateway/media-inbound/<screenshot2>.jpg"
  ],
  "watermark": "@your_account",
  "crop_top_pct": [0.0, 0.10]
}
```

## Pre-flight checks (per `feedback_carousel_rendering_rules.md`)

- CTA текст помещается в ширину (max ~960px), не вылетает за края canvas
- Trigger word — актуальный для текущей воронки ([[verify-active-funnel]])
- Оба скрина — real IG screenshots, не DIY mockup
- Status bar обрезан (часы / индикаторы не видны)
- White bbox обоих скринов одинакового размера (480×600)
- Watermark `@your_account` виден внизу
- Caption (Telegram) проходит [[instagram-operator]] стоп-слов фильтр
