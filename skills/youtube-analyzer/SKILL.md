---
name: youtube-analyzer
description: Full YouTube channel viral-analysis pipeline (Shorts and long-form). Pulls a target channel's top-N videos by views via yt-dlp (no API key needed), grabs metadata + captions (manual subs > auto-captions > Groq Whisper fallback), and produces a structured report with metrics + title + description + transcript ready for LLM analysis of title-strategy / description-hook / video-hook / retention / CTA architecture / verdict. Use this skill whenever the operator asks to "проанализируй YouTube-канал", "разобрать YT Shorts", "что у конкурента на ютубе", "вытащить хуки с YouTube", "повторить формат у блогера на ютубе", "research AI Shorts channel", or pastes a youtube.com/@handle or youtube.com/channel/UC... URL with analysis intent. Skip when the task is a one-shot transcript pull for a single video (use `youtube-transcript` skill) or video re-skinning (use `reel-reskinner` after extending it for YT).
---

# YouTube Analyzer -- viral channel deep-dive

End-to-end pipeline that turns a YouTube handle into a structured viral-analysis
report. Built on:

- **`yt-dlp`** -- channel listing, per-video metadata, captions (no API key)
- **`groq-voice`** -- Whisper Large v3 Turbo fallback (key in
  `$GROQ_API_KEY`), only when no captions exist
- **`ffmpeg`** -- audio extraction for the Groq fallback path

Hardcoded path: `YT_DLP = "~/.local/bin/yt-dlp"` (version 2026.03.17).

---

## When to use

Trigger on any of these (Russian and English):

- "проанализируй YouTube-канал @...", "разбери YT Shorts у ...", "сделай разбор канала на ютубе"
- "что у конкурента на ютубе", "повторить формат у блогера на ютубе", "вытащить хуки с YouTube"
- "research AI Shorts channel", "deep dive YouTube channel", "что залетает на ютубе у X"
- bare `youtube.com/@handle` or `youtube.com/channel/UC...` URL + analysis intent
- "почему у него такие просмотры на ютубе"

Skip when:

- Task is one-shot transcript of a single video -> use `youtube-transcript` skill.
- Task is video re-skinning (rewrite script from a YT video) -> use
  `reel-reskinner` (extend if needed for YT).
- Task is content creation from scratch (write titles, generate ideas) -> not this skill.
- Operator wants to upload to YouTube -> read-only, scrape only.

---

## Cost model (rough, per run)

This is the key advantage over reels-analyzer ($0.35-0.55 per IG run): YouTube
provides captions for free for most channels.

| Item | Per top-5 run |
|---|---|
| yt-dlp listing + metadata + captions | **$0** (no API key, just bandwidth) |
| Groq Whisper fallback (only when no captions, ~10-30% of cases) | ~$0.005 per fallback video |
| LLM-analysis (Opus on operator's subscription) | **$0** |
| **Total cash** | **~$0** for channels with EN/RU captions |

For a typical 5-video run on an English/Russian channel, expect $0 in cash cost.
Worst case (no captions on any video): ~$0.025 cumulative Groq cost.

---

## Two-phase workflow

### Phase 1: data collection (deterministic, scripted)

Run the bundled orchestrator. It does: handle resolve (try `/videos`, fallback
to `/shorts`, merge if both exist) → flat-playlist listing (all videos with
view counts in one call) → sort by views → top-N → per-video full metadata via
`yt-dlp -j` → captions priority chain (ru-manual → en-manual → ru-auto → en-auto
→ Groq fallback) → emit `report.json` + draft `report.md`.

```bash
python3 ~/.claude/skills/youtube-analyzer/scripts/analyze.py \
    --handle @your_account --top 5 --verbose
# or via full URL:
python3 ... --handle "https://www.youtube.com/@your_account"
# or via channel ID:
python3 ... --handle "UCxxxxxxxxxxxxx"
# debug without captions/Groq:
python3 ... --no-transcribe
```

Output goes to `/tmp/youtube-analyzer/<handle>/`:
```
report.json             -- full structured payload (read this)
report.md               -- draft report with LLM-analysis fields blank
videos/<id>.mp3         -- only if Groq fallback triggered (audio only)
transcripts/<id>.txt    -- captions or Whisper output
```

### Phase 2: LLM analysis (you, the agent)

Read `report.json`, then for each video produce 6 fields by reasoning over
title + description + transcript + metrics. Write the full report back as
`<out>/report_final.md`.

**See `references/prompts.md` for the analysis prompt template.**

The 6 fields (YouTube-specific, differs from reels-analyzer):

1. **title strategy** -- curiosity gap, numbers, brackets, emoji, length.
   Why this title hooks in feed/search.
2. **description hook** -- first 2 lines (visible above "...more"), CTA placement.
3. **video hook (0-2s)** -- exact opening line/visual, why it hooks.
   Shorts are 1-2s opener (faster swipe than IG).
4. **retention engineering** -- pacing, B-roll cuts, pattern interrupts,
   loop construction.
5. **CTA architecture** -- voice + on-screen + description + pinned comment.
   YouTube has more native CTA surfaces than IG.
6. **вердикт** -- exactly one of:
   - **Скопировать формат** -- format and topic both transferable as-is.
   - **Адаптировать** -- format works, topic needs swap (default for cold-viral).
   - **Изучить и развить** -- has a unique mechanic worth a deeper experiment.
   - **Пропустить** -- format depends on factors operator can't replicate
     (celebrity access, breaking news, paid ads, ethical risk).

   Each verdict needs a 1-line *why*.

---

## Strategic layer

After per-video analysis, write a **2-paragraph executive summary** at the top
of `report_final.md` covering:

1. **Pattern across the top** -- what's common (theme mix, title style, hook
   style, length distribution, Shorts vs long-form mix, CTA hit-rate).
2. **Strategic gap** -- where is this channel losing money? Common ones:
   viral videos with no CTA (lost subscribe funnel), title undersells thumbnail,
   no end-screen / cards, audience-product mismatch, dependency on news cycles.
   Be direct, not diplomatic.

The operator hires this skill to find **leverage points**, not for cute reports.

**Critical:** the owner runs a 2-layer funnel where front-end (cold viral)
content is intentionally broad and decoupled from the product. **DO NOT
critique videos as "off-niche"** -- that's the same rule as reels-analyzer.
The skill respects "контент ≠ продукт" architecture. See
`references/prompts.md` verdict heuristics.

---

## Failure modes & graceful handling

- **YouTube bot-wall** (`Sign in to confirm you're not a bot`, or a garbled
  `BadStatusLine` / `Connection aborted`) -- happens on data-center / server IPs.
  As of 2026-06 **cookies alone are NOT enough** (YouTube now wants a home IP);
  even listing can fail. **Working fix = a residential proxy via `--proxy`.**
  NOTE: AdsPower / many residential proxies are **SOCKS5, not HTTP** — if
  `http://user:pass@host:port` returns a binary `BadStatusLine`, retry with
  `socks5://user:pass@host:port`. With a residential proxy cookies are usually
  not even needed. The proxy is masked in logs. See `references/pipeline.md`.
- **`yt-dlp not at ~/.local/bin/yt-dlp`** -- script aborts with
  clear path. Install: `pipx install yt-dlp` or `pip install --user yt-dlp`.
- **Channel has no `/videos` tab** -- script auto-falls back to `/shorts`.
- **Channel has both `/videos` and `/shorts`** -- script merges by id.
- **Groq key missing AND a video has no captions** -- record
  `transcript_error`, continue. Final report flags caption-only or
  description-only analysis for that row.
- **Channel is age-gated / private** -- yt-dlp errors out cleanly; script
  reports and stops.
- **Channel has < N videos** -- pipeline returns whatever exists; flag the
  small sample to operator.
- **VTT parsing edge cases** (overlapping cues, empty cues) -- handled by
  `vtt_to_text()` helper which dedupes consecutive identical lines.

---

## Example invocations

```
"проанализируй YouTube-канал @your_account, топ-5"
"что у конкурента на ютубе https://www.youtube.com/@your_channel, разбор"
"вытащи хуки с YouTube у этого блогера: youtube.com/@neuroreels"
"deep dive YT Shorts канал @creator_x с фокусом на тайтлы"
"research AI Shorts channel @ai_research, top-10"
```

Examples that should trigger but use *different* skills:

- "транскрибируй это видео https://youtube.com/watch?v=..." -> `youtube-transcript`
- "перепиши скрипт этого ролика на ютубе" -> `reel-reskinner` (or extend)
- "напиши 10 идей для YT Shorts" -> NOT this skill (creation, not analysis)
- "залей это видео на ютуб" -> NOT this skill (read-only)

---

## Phase 3: client-facing report (when forwarding to a client/work chat)

When the operator wants a **forward-ready professional report** (not the internal
verdict notes), render `references/client_report_template.md` from `report.json`:
professional but human language, виральность as ×median, action-oriented
recommendations, no agency-internal data. Deliver as ONE self-contained message.
Keep the 4-scale verdicts (`report_final.md`) as the internal version.

## References

- `references/client_report_template.md` -- forward-ready professional report (client chat)
- `references/prompts.md` -- LLM analysis prompt template (YouTube-adapted)
- `references/pipeline.md` -- detailed flow with yt-dlp commands + VTT parsing
- `evals/evals.json` -- 3 functional tests
- `evals/trigger_eval.json` -- 20 trigger queries (10 should + 10 should-not)
