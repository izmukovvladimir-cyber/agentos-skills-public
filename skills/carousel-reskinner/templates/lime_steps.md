# lime_steps — body-слайды @donor_account-style в нашем lime-бренде

Использовать для каруселей формата «ШАГ N. Заголовок» (как @donor_account <post_code>). 100% PIL, без NB Pro — NB Pro ломает русский текст внутри UI-mockup'ов (см. `feedback_nb_pro_no_cyrillic_in_ui_mockup`).

## Когда использовать

The operator прислал референс @donor_account / @donor_account или другой формат «ШАГ 1. ... ШАГ 2. ...» где на каждом слайде:
- Лаймовый акцент-заголовок «ШАГ N.»
- Подзаголовок темы
- 2 чекмарка с инструментами
- UI-mockup карточка внутри (чат-bubble / image-grid / video player / avatars-grid / subtitle-timeline)
- Caption внизу

## Структура одного слайда (1080×1350)

```
@your_account (top-left, Inter Bold 26pt, grey)

         ШАГ N.            ← Inter Black 96pt, LIME_DARK (170,215,40)
       Подзаголовок         ← Inter Black 54pt, TEXT_DARK

  ✓ Инструмент1 — описание
  ✓ Инструмент2 — описание

  ┌───── card with shadow ─────┐
  │ ● Tool name      Badge     │  ← Inter Bold 22pt
  │ ───────────────────────── │
  │                            │
  │       MOCKUP CONTENT       │  ← варьируется per slide
  │                            │
  └────────────────────────────┘

      Caption внизу            ← Inter Regular 28pt, TEXT_GREY
```

## Палитра

```python
LIME = (200, 240, 60)
LIME_DARK = (170, 215, 40)
TEXT_DARK = (40, 44, 52)
TEXT_GREY = (110, 116, 124)
CARD_BG = (252, 252, 250)
CARD_BORDER = (228, 232, 238)
BUBBLE_USER = (240, 242, 246)
BUBBLE_BOT = (248, 249, 251)
WHITE = (255, 255, 255)
```

## Шрифты

```python
F_BLACK = "~/.fonts/Inter-Black.ttf"
F_BOLD  = "~/.fonts/Inter-Bold.ttf"
F_REG   = "~/.fonts/Inter-Regular.ttf"
```

Все три поддерживают полную кириллицу.

## 5 типов mockup-карточек (см. render_lime_steps_all.py)

1. **chat-bubbles** (ШАГ 1: тексты) — header «ChatGPT» + GPT-5 badge → user prompt справа → bot response слева → action chips «⌘ скопировать / ↻ перегенерировать / ↗ поделиться»
2. **image-grid** (ШАГ 2: картинки) — header «Midjourney v7» + prompt `/imagine ...` → 2×2 cell-grid с градиентными заливками (фейк-thumbnail'ы)
3. **video-player** (ШАГ 3: видео) — header «Sora 2 · 16s · 1080p» + prompt → ночной город silhouette + play-button + лаймовый progress bar
4. **avatars-grid** (ШАГ 4: аватары) — header «HeyGen · 4 такта» → 2×2 портретов-силуэтов с label-chips («Нейтральный / Улыбка / Серьёзный / Энергичный») + лаймовая кнопка «Сгенерировать видео»
5. **subtitle-timeline** (ШАГ 5: монтаж) — header «SubMagic · AI Captions» → таймлайн с waveform + playhead → стопка из 4 разноцветных subtitle-chips ALL CAPS

## CTA-слайд (финал)

Чистый текст в стиле @donor_account slide 7 (без выдуманной статистики):
- ALL CAPS hook 3 строки
- Value sub-line 2 строки regular weight
- Lime divider
- «Напиши в ком:ментариях»
- БОЛЬШОЕ лаймовое подчёркнутое «КОДВОРД»
- «пришлю в директ»

НЕ использовать DIY mockup stats с выдуманными цифрами (см. `feedback_cta_slide_with_dark_cards`). Чистый текст или РЕАЛЬНЫЕ IG-скрины.

## Pre-flight check

- Карточки не должны вылезать за H=1350 (overflow check)
- Caption всегда НИЖЕ карточки (не перекрывать)
- Без выдуманных метрик в любом слайде (правило `feedback_reel_rewrite_rules_strict`)
- В caption для IG — маскировка по `reference_caption_cta_statya`

## Скрипты

- `scripts/render_lime_step.py` — одиночный ШАГ 1 baseline (chat-bubble mockup)
- `scripts/render_lime_steps_all.py` — все 5 шагов + CTA в одном файле

Связано: [[feedback_nb_pro_no_cyrillic_in_ui_mockup]], [[feedback_reel_rewrite_rules_strict]], [[reference_caption_cta_statya]], [[feedback_cta_slide_with_dark_cards]].
