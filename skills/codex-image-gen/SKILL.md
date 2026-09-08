---
name: codex-image-gen
description: Free image generation via gpt-image-2 on the Codex/ChatGPT subscription (no API key, no Higgsfield credits) — SAME model ChatGPT uses. Use for backgrounds, story underlays, illustrations, YouTube/cover thumbnails, objects, trendy/abstract visuals, and carousel art. To get ChatGPT-quality results, READ the "Работать как ChatGPT" section first — the gap is prompt art-direction, not the model. For an EXACT face match use higgsfield-generate instead — gpt-image-2 only resembles, not 1:1.
---

# codex-image-gen — gpt-image-2 via the Codex subscription (free)

## Работать как ChatGPT (режиссура промпта) — ЧИТАЙ ПЕРВЫМ

Это **тот же gpt-image-2, что и в ChatGPT**. Если в самом ChatGPT картинка выходит
лучше, чем у нас — дело НЕ в модели, а в промпте. ChatGPT не отдаёт короткую фразу
пользователя прямо в рисовалку: внутри отдельный «мозг» (GPT) сначала **переписывает
её в подробный художественный промпт**, и только потом рисует, часто несколько раз и
показывает лучшее. Ты — Claude, ты этот «мозг» и есть. Поэтому:

1. **НЕ передавай в `--prompt` короткую фразу.** Сначала сам разверни её в детальный
   арт-промпт (англ. работает лучше для gpt-image). Опиши явно:
   - **Субъект**: кто, выражение лица (по умолчанию спокойное, без натянутой улыбки),
     одежда, поза, кадрирование. Если есть реф лица — добавь «keep the exact face from
     the reference image».
   - **Сцена/фон ПО ТЕМЕ**: конкретные объекты/люди/обстановка, иллюстрирующие тему
     (для «как понравиться с первой фразы» → пара общается, девушка смотрит на героя на
     вечернем приёме). Не абстракция.
   - **Свет и настроение**: golden-hour / rim light / cinematic, тёплое боке, shallow
     depth of field, dark moody premium tones.
   - **Стиль/формат**: «photorealistic, premium YouTube thumbnail, 16:9».
   - Если нужен текст В картинке — укажи точные строки + «spell exactly: <текст>».
2. **Сделай 2-3 варианта** (повтори вызов) — генерация случайная, бери лучший.
   Одинаково дважды не повторится (поэтому шрифт/лицо «гуляют» между генерациями).
3. **Реф лица** — `--ref-image` (resemblance, не 1:1; для строгого 1:1 — реальный кадр).
4. **Проверь глазами**: текст без опечаток, лицо ок, нет лишних пальцев/артефактов.
   Плохо → перегенери, не отдавай брак.

**Текст в картинке (важно):** свежий gpt-image-2 кириллицу часто рисует ХОРОШО — но
случайно (каждый раз чуть другой шрифт, изредка срывает букву). Два режима:
- **Разовая богатая обложка** → можно дать модели нарисовать и текст (быстро, цельно),
  но ОБЯЗАТЕЛЬНО проверь орфографию.
- **Бренд-консистентность** (один и тот же фирменный шрифт на ВСЕХ обложках, как у
  @reference_account) → генерируй сцену БЕЗ текста, заголовок накладывай настоящим шрифтом
  (PIL). Так шрифт идентичен везде и без опечаток. Готовый компоновщик для обложек
  клиента: `~/bin/thumbnail.py` (`--side center`, Montserrat Black).

Generates images with OpenAI's **gpt-image-2** by routing through the Codex
Responses `image_generation` tool, using the team Codex OAuth token. **No
OPENAI_API_KEY, no Higgsfield credits** — billed inside the existing Codex
subscription. Built in 2026-06 (technique from NousResearch/hermes-agent).

## Command

```
~/bin/codex-image-gen.py \
  --prompt "<image description>" \
  --quality low|medium|high \      # low ~15-35s, medium ~40-100s, high ~2min
  --aspect square|landscape|portrait \
  [--ref-image /path/face_or_style.jpg]   # repeatable (max 4) for image-to-image
```

- Prints the saved PNG path to **stdout** on success (exit 0). Errors → stderr, non-zero exit.
- Default output dir: `~/.claude/state/codex-images/`. Pass `--out PATH` to place it.
- Validates the result is a real PNG before declaring success (no silent junk files).

> ⚠️ **НЕ оборачивай вызов в короткий внешний `timeout` (`timeout 180 python3 ...`).**
> Скрипт сам делает до 5 попыток direct/proxy со своими внутренними таймаутами; полный
> цикл в плохом окне может занять несколько минут. Внешний `timeout 180` УБИВАЕТ процесс
> посреди 2-3 попытки, до того как proxy-fallback выгребет CF-burst — это даёт ровно
> симптом «attempt 1 direct пусто, attempt 2 proxy завис/не ответил». Если очень нужен
> внешний предохранитель — ставь `timeout 900` (покрывает все 5 попыток), а лучше не ставь:
> скрипт не висит вечно. Проверено 2026-07-19 на реальном кейсе другого агента.

## When to use gpt-image-2 (this) vs Higgsfield

| Need | Use |
|---|---|
| Backgrounds, story underlays, illustrations, objects, abstract/trendy art, carousel visuals | **codex-image-gen** (free, fast) |
| an EXACT face, close-up premium portrait, 1:1 recognizability | **higgsfield-generate** (golden_recipe — exact face lock) |
| Carousel that mixes both | hybrid: gpt-image for text/style/backgrounds, Higgsfield for the face slide |

**Face caveat (verified 2026-06-09):** gpt-image-2 with `--ref-image` produces a
person who *resembles* the reference (beard, build, vibe) but is **not** an exact
face match. For anything where the face must clearly be one specific person, use Higgsfield.
gpt-image-2 is great where the face isn't the point.

Face refs (for resemblance shots) are your own: put 2-3 photos of the person into `<face_refs>/`.
No reference photos ship with this skill.

## Tips

- **Pick the image to fit the text** — describe the scene/mood that matches the slide copy.
- gpt-image-2 text-in-image: modern model renders Cyrillic decently but **stochastically** (font wobbles, rare misspell) — for brand-consistent identical type, keep art text-free and overlay with PIL (stories_recipe / carousel-reskinner / thumbnail). See "Работать как ChatGPT" above.
- Quality `medium` is the default sweet spot; `high` for hero slides.
- **Visible progress (тишина = баг).** Generation runs 2-4 min and the native "печатает…" indicator GOES SILENT while it works (the turn ends; a backgrounded gen has no active turn) — the reader takes that silence for "agent hung". So BEFORE launching, send one short message: «🎨 Генерю картинку через gpt-image-2, ~2 мин — пришлю как будет». Then run the gen (foreground is fine; it returns the path), and reply with the image. The up-front notice makes the silent gap expected, not alarming.

### Face-prompt guidance (verified 2026-06-09 on owner feedback)

- **NO forced smile.** Do NOT add "smile / bright white teeth / closed-lip smile" — gpt-image-2 over-does it into a fake stretched grin with an oversized mouth. Default to **neutral / relaxed natural mouth**; add a smile ONLY if the owner asks.
- **Guard proportions.** gpt-image-2 tends to make the **head too big relative to the body** on portrait crops. Always include "realistic natural head-to-body proportions, head not oversized, shoulders/chest in frame" and frame a bit wider (waist-up, not face-only).
- **Beyond portraits:** works well for trendy locations + fashionable clothing (rooftop golden-hour, street, restaurant, travel) — owners tend to like these. Full upper-body fashion shots land better than tight face crops (face fidelity + proportions both improve).
- **Preferred style (owner feedback, 2026-06-09): candid full-length IN MOTION beats static posed.** His favourite was the full-height shot walking across a zebra crossing in a big city at golden hour — dynamic, visible city background, in-motion, candid (not posed). Bias toward: full body / shot-from-a-distance, walking or mid-action, readable big-city background, golden-hour/cinematic light.
- **Wardrobe taste (owner feedback, 2026-06-09): QUIET LUXURY / old-money / elegant, NOT edgy streetwear.** He liked the monochrome camel-and-cream quiet-luxury look (oversized camel coat, cream knit, wide tailored trousers, loafers) and rejected the black-leather-biker streetwear look. Default to refined, tonal, premium tailoring (camel/cream/beige/grey/navy, cashmere, wool, clean lines). Avoid biker leather, heavy black streetwear, loud logos, "edgy/urban" styling unless he asks.
- Use 3 refs (open-smile selfie + front + studio-build) from `<face_refs>/` for best resemblance. Still a resemblance, not 1:1 — Higgsfield for exact-face hero shots.
- **Reliability: the tool RETRIES across routes (updated 2026-07-19).** Both paths fail in bursts: the direct VPS IP hits an *intermittent* Cloudflare challenge (`HTTP 200 OK` + empty stream → old error `stream finished with no completed image_generation_call result`), and the residential proxy occasionally drops the long (1-2 min) stream (`httpx.RemoteProtocolError`). The script now retries automatically — **direct first, then the proxy as fallback, alternating** — default **5** attempts (`--retries N` or `CODEX_IMAGE_RETRIES`); at 5 that is direct→proxy→direct→proxy→direct. Transient failures (empty stream, dropped stream, HTTP 403/408/425/429/5xx, corrupt result) are retried; permanent ones (HTTP 400/401, bad/oversized ref image) fail fast. A stalled stream now fails fast at **180s** (read-timeout) instead of 300s, so a hung/dropped proxy stream cycles to the next route quickly rather than eating ~5 min per attempt.
  ```
  export CODEX_IMAGE_PROXY="socks5://user:pass@host:port"   # keep it in the environment, not in a file
  python3 ~/bin/codex-image-gen.py --prompt "..." --quality high --aspect portrait --out /path/out.png
  ```
  Direct alone works most of the time; **passing `CODEX_IMAGE_PROXY` is strongly recommended** so the fallback route exists when a CF burst hits. It is NOT strictly required (retries on the direct route alone still clear most transient CF hits), but with the proxy set a burst on either route is covered. The proxy secret is `socks5://...`; httpx needs `socksio`, installed in agent-user user-site (`~/.local`, alongside httpx) — no per-session install. If a fresh host misses it: `python3 -m pip install --user --break-system-packages socksio` (touches only `~/.local`). Use `CODEX_IMAGE_PROXY` (env), never `--proxy` on the command line, to keep proxy `user:pass` out of argv/ps.

## Notes

- Token read from `~/.codex/auth.json`; never printed. Reference images capped at 4 × 10MB, types png/jpg/jpeg/webp.
- Codex gpt-5.5 reviewed (APPROVE). Source: `~/bin/codex-image-gen.py`.
