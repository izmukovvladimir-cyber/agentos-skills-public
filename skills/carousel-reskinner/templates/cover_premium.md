# Cover Premium (slide 1 для карусели с фото)

Brand template for @your_account carousel COVER (slide 1) — photo background generated via FAL Nano Banana 2 edit + magazine-style text overlay.
Approved 2026-05-17 by the operator (final v5 with stroke + shadow), reference style: @donor_account.
Pair with `black_leaf.md` for slides 2..N.

## Use case

- **Slide 1 only** of a multi-slide carousel.
- Goal: stop the scroll, deliver hook, prompt swipe.
- Photo backdrop with the operator generated through FAL.
- Magazine cover composition — handle top, hook + tease left-aligned mid-bottom, "листай →" bottom-right corner.

## Canvas

- Size: **1080 × 1350** (IG portrait 4:5)
- Background: photorealistic generated photo (Nano Banana 2 edit, ~$0.12/iteration)
- Post-process: warm tone overlay (+8% blend with `(255,195,130)`), saturation +10%, contrast +5% — gives healthy tanned look
- Soft left-side darken (gradient 0-78% width × full height, max alpha 60) for text readability
- Top fade (140px, max alpha 110)

## Typography

ALL TEXT gets **stroke outline + drop shadow** for readability on any background:
- `stroke_width=4` for hook, `stroke_width=3` for sub, `stroke_width=2` for handle/swipe
- `stroke_fill=(0,0,0)`
- Drop shadow: Gaussian blur radius=4, offset (3-4, 5-6), alpha=200

### Handle (top center, ~36px from top)
- Font: `PlayfairDisplay.ttf` variable weight `Regular`, size **38pt**
- Colour: `(235, 235, 235)`
- Format: `@your_account` (no caps tracking — italic-feel via Playfair serif)
- **stroke + shadow APPLIED** (the operator feedback 2026-05-17: handle тоже выделить чтобы читался)

### Hook block (left-aligned, x=70, y≈580)
- Font: `Inter.ttf` variable axes `[opsz=14, weight=800]` (Inter Black-ish), size **64pt**
- Colour: `(255, 255, 255)`
- Lines: 2 typical. ONE WORD can be UPPERCASE for emphasis (e.g. «НАГЛЫМ»).
- `stroke_width=4` + drop shadow.

### Sub-hook / tease block (50px below hook)
- Font: `Inter.ttf` axes `[opsz=14, weight=700]`, size **50pt**
- Colour: `(245, 245, 245)`
- Lines: 2-4. **Ends with `:` (colon)** to cliffhanger-tease the swipe.
- `stroke_width=3` + drop shadow.

### Swipe prompt (bottom-right, ~50px margin)
- Font: `Inter.ttf` weight 500-600, size **28pt**
- Colour: `(220, 220, 220)`
- Text: `листай →`
- **stroke + shadow APPLIED** (the operator feedback 2026-05-17)

## Photo generation prompt template

```
A man with short dark brown hair styled up, full thick dark beard,
sun-tanned warm bronze skin tone, healthy summer complexion,
{POSE_AND_SETTING},
{COMPOSITION_AND_LIGHTING},
wearing {OUTFIT},
cinematic photo, photorealistic, shallow depth of field,
professional editorial photography, vertical 4:5 portrait composition
```

Pass via `image_urls=[face_frontal_url, face_profile_url]`. Face references are your own:
put 2-3 photos of the person you render into `<face_refs>/` (frontal + profile) and point the
URLs at them. No reference photos ship with this skill.

Endpoint: `fal-ai/nano-banana-2/edit` on queue.fal.run.
Aspect ratio param: `"aspect_ratio": "4:5"`.
Output ~928×1152 → resize+crop to 1080×1350 via PIL Lanczos.

## How to render

```bash
python3 ~/.claude/skills/carousel-reskinner/scripts/render_cover_premium.py \
    --photo /tmp/maybach_1080x1350.jpg \
    --json /tmp/cover_text.json \
    --out /tmp/cover.jpg
```

JSON:
```json
{
  "handle": "@your_account",
  "hook_block": ["НАГЛЫМ достаётся всё.", "Хорошим — ничего."],
  "sub_block": ["Мир награждает заметных", "и смелых, не скромных", "и не талантливых:"],
  "swipe": "листай →"
}
```

## Pre-flight checks

- Handle reads on top (stroke applied)
- Hook reads on any portion of photo (stroke + shadow)
- Sub-block ends with `:` (cliffhanger)
- Swipe prompt visible bottom-right
- Face is NOT fully obscured by text — text occupies left half, face mid-right
- Warm tone applied (look healthy, not pale)
