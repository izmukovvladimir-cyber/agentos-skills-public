# LLM analysis prompts -- youtube-analyzer

Prompt scaffolds the calling agent uses on each video after `analyze.py`
produces `report.json`. The agent has title + description + transcript + metrics
for each video; the agent itself is the LLM, no separate model call needed
unless analysis is delegated to a subagent.

YouTube vs IG Reels differs in the surfaces that drive the click and the watch.
The 6-field per-video analysis below bakes those differences in.

| Factor | IG Reels | YouTube Shorts / Long |
|---|---|---|
| Title | none | **HUGE factor** -- visible in feed swipe + search + recommendations |
| Description first line | n/a | mini-hook visible above "...more" -- second hook surface |
| Thumbnail | n/a (autoplay) | matters for /shorts surfacing + recommendations panel |
| Video hook timing | first 3s | first 1-2s (Shorts feed swipes faster than IG) |
| CTA | comment trigger word (ChatPlace) | Subscribe + comment + bell + cards + end-screen + pinned comment |
| Algorithm currency | replays + saves | **watch-time + retention %** (drives both Shorts and Long) |

---

## Per-video analysis prompt (use as internal scaffold)

For each video object in `report.json["videos"]`, reason through:

```
INPUT:
  title: <v.title>
  description: <v.description>  (may be long; focus on first 2 lines + CTA placement)
  transcript: <v.transcript>  (or [NO TRANSCRIPT] if missing -- flag confidence)
  metrics: views=<v.view_count>, likes=<v.like_count>, comments=<v.comment_count>,
           ER=<v.er_pct>%, duration=<v.duration_s>s (<v.format>), upload=<v.upload_date>
  url: <v.url>

PRODUCE (markdown, exactly this structure):
  ### #<rank> · <view_count formatted> views · <duration>s (<Short|Long>) · <date>
  **«<title>»**
  [<url>](<url>)

  metrics line: ❤ <likes> · 💬 <comments> · ER <X.XX>%

  - **title strategy:** <what the title does>. Tactic: <curiosity-gap | numbers | brackets | emoji | contrarian | name-drop | listicle | question | shock-claim>. Length: <N chars / words>.

  - **description hook:** "<exact first 1-2 lines>". CTA placement: <top | middle | bottom | none>. Links/timestamps: <yes/no>.

  - **video hook (0-2s):** "<exact first sentence/visual from transcript>"
    Why it hooks: <1 line>. Tactic: <curiosity-gap | shock | loop | pattern-interrupt | specific-number | authority | contrarian | sensory>.

  - **retention engineering:** <pacing observation>. <B-roll cuts / pattern interrupts / loop construction / cliffhanger placement>. Estimated retention pattern: <front-loaded | even | spike-at-Y>.

  - **CTA architecture:** voice <yes/no/quote>, on-screen <yes/no>, description <yes/no>, pinned-comment <unknown but check>. Strength: <strong | medium | weak | absent>.

  - **тема / архетип:** <news-jacking | satisfying-process | hot-take | how-to | story | listicle | contrarian | demo | BTS | AI-generated | tutorial | reaction>. Topic: <one-liner>.

  - **вердикт:** **Скопировать формат** | **Адаптировать** | **Изучить и развить** | **Пропустить** -- <1 line why>.
```

---

## Executive summary prompt (top of report_final.md)

After all per-video analyses are written, prepend a 2-paragraph exec summary:

```
PARAGRAPH 1 -- Pattern across the top:
  - What's the dominant theme mix? (e.g. "4 of 5 are AI tool demos")
  - What's the dominant title style? (numbers? brackets? emoji? CAPS? length range?)
  - What's the dominant video-hook style? (e.g. "all open with a question + zoom-in")
  - Format mix: how many Shorts vs Long? Duration distribution.
  - CTA hit-rate: how many of N have a clear CTA in voice + description + pinned?

PARAGRAPH 2 -- Strategic gap (THE money paragraph):
  Identify 2-3 leverage points. Examples to look for on YouTube specifically:
    - viral video without subscribe CTA = lost funnel ("X views × 1% subs = N missed subs")
    - title undersells thumbnail (low CTR -- can A/B-test the title)
    - no end-screen / cards = no traffic to other videos = no session-time bonus
    - description is dead -- no first-line hook, no links, no timestamps
    - audience-product mismatch (theme attracts wrong demo for the offer)
    - over-dependence on news cycle (no evergreen content for SEO long-tail)
    - high-retention format underused (one video sustained 80%+, why isn't this scaled?)

  End with one concrete next-action ("the obvious 80/20 move is X").
```

---

## Verdict heuristics

To pick verdict consistently among 4 tiers:

**Operator strategy context (critical):** the owner runs a 2-layer funnel --
front-end is *cold-viral* (intentionally broad topics: news, politics,
relationships, esoterica, life-hacks) for maximum reach; back-end is
*warm-expert* (Telegram bot + tripwire + flagship). **Don't flag a viral
front-end video as Пропустить just because the topic isn't aligned with the
product.** Niche-product mismatch on front-end is a feature, not a bug --
that's exactly how he hit 39M views on the previous IG account, and the same
strategy translates to YT cold-viral.

**Скопировать формат** when:
- Title + format + topic are all transferable as-is
- Universal viral format (satisfying-process, demo, how-to) AND no
  celebrity / news / platform-risk dependency
- Strong CTA mechanic already present and on-brand

**Адаптировать** when (default for most cold-viral):
- Format transfers (title pattern, hook style, pacing, CTA shape) regardless
  of whether topic does or not
- Most viral cold-viral videos fall here -- topic doesn't need to match product

**Изучить и развить** when:
- The video has a unique mechanic (a novel hook construct, an unusual
  retention device, a CTA pattern not seen elsewhere on the owner's stack)
  worth a dedicated experiment, not just blind copy
- Use sparingly -- this is the "this deserves an A/B test" tier

**Пропустить** when (only legitimate reasons -- do NOT use "off-niche"):
- AI-deepfake of a recognizable public figure -- platform-risk, prior bans seen
- Depends on irreplaceable factor: live celebrity access, real breaking
  news with <24h relevance window, paid collab requiring disclosure
- Format requires real footage operator cannot capture (e.g., war zone)
- Ethical/legal risk specific to operator's verified-account status

When in doubt -- Адаптировать is the default. Пропустить requires a *real
reason* (platform-risk, irreplaceability, legal/ethical), not vibes and not
"wrong niche".

---

## Tone

- Russian for operator-facing report content (the owner's preference).
- Direct, no hedging. "Это слабый хук" not "Возможно, хук можно улучшить".
- Specific numbers when available ("2.75M views × 1% subs = 27.5K missed
  subscribers on the table") not abstract claims.
- Don't soften the strategic gap paragraph. Operator wants the leverage point,
  not flattery.
- If transcript is missing for a video, flag the lower confidence in the
  hook/retention sections and lean on title + description for verdict.
