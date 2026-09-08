# Web image search — proven queries

How to find supporting visuals for carousels via Claude `WebSearch` + `curl`/`WebFetch`.

## Real Instagram analytics screenshots

Need a real "ring chart with metric number" — the kind Instagram shows for reel views/reach. Queries that work:

- `instagram reels analytics screenshot views million` — finds influencer flex posts that include their own metric screenshots
- `instagram insights просмотры миллион скриншот` — Russian variant, better for cyrillic-text rings
- `instagram reel reach circle screenshot mobile` — narrower, mobile UI specifically
- `instagram insights overview reach views screenshot 2024` — recent UI revisions

Useful sources (high signal):
- Russian Telegram channels of growth experts — they post their own metric screens often
- Twitter/X creator economy posts — same pattern
- LinkedIn growth-marketing posts
- Substack newsletters about creator economy

**Pick screens that match the operator's brand**: purple/pink ring (matches his lime+pink palette), large bold number, "Просмотры" label in Russian if possible. Avoid screenshots that show the source creator's name (legal/cred attribution).

## Stock photography (body slide visuals)

Use Unsplash via WebSearch:

- `site:unsplash.com phone instagram screen` — for phone-in-hand mockups
- `site:unsplash.com creator content studio` — for studio/setup shots
- `site:unsplash.com mobile creator dark` — moody dark phone photos

Download direct from Unsplash URL — `https://images.unsplash.com/photo-XXXXXX?w=1080&q=80`.

## Carousel mockups

For body slides that need "this is what a good carousel looks like" visuals, prefer **the operator's own previously-rendered slides** over stock. Path `/tmp/carousel_v1/out_v8/slide_*.jpg`. This keeps consistency with his existing posted carousels and shows real КОДВОРД CTA in context.

## Download patterns

```bash
# direct curl with browser UA — works for most CDNs
curl -L -o "$RAW/img.jpg" -A "Mozilla/5.0" "<url>"

# Unsplash with size param
curl -L -o "$RAW/img.jpg" "https://images.unsplash.com/photo-XXXX?w=1080&q=80"
```

If the page blocks direct curl, use Claude's `WebFetch` tool to download via the rendered page.

## Quality bar before use

Before pasting any web-sourced image into the carousel:

1. Resolution — width ≥ 600px for circles, ≥ 1080 for full-bleed bg
2. No watermark or attribution text visible
3. No competitor brand/logo in frame
4. Numbers/text legible at the size it'll be rendered
5. For circles: white inner area large enough for the metric number to be readable after our `:` masking

If none of the candidates pass — fall back to a clean drawn ring + real metric number the account owner gave (`<число просмотров>`).

## Cache

Save downloaded images under `/tmp/carousel_run/<timestamp>/raw/web_<n>.<ext>`. Keep across runs only if the operator confirmed the image was good — promote those into `~/.claude/skills/carousel-reskinner/examples/`.
