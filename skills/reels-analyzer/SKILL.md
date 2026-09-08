---
name: reels-analyzer
description: Full Instagram Reels viral-analysis pipeline. Pulls a target account's top-N reels by views, downloads each video, extracts audio, transcribes via Groq Whisper, and produces a structured report with metrics + caption + transcript ready for LLM analysis of hook/structure/why-it-flew/copy-or-adapt verdict. Use this skill whenever the operator asks to "проанализировать reels", "разобрать почему залетает", "вытащить хуки", "скопировать формат у конкурента", "Reels Challenge research", or any phrasing involving deep dive into someone's Instagram reels (own or competitor) -- even if they don't say "analyzer". Skip when the task is a one-shot metric pull without transcripts (use `hikerapi` skill directly instead) or when they want to POST to Instagram.
---

# Reels Analyzer -- viral reels deep-dive

End-to-end pipeline that turns "@username" into a structured viral-analysis
report. Built on top of two existing skills (do not reinvent):

- **`hikerapi`** -- Instagram REST data layer (profile, medias, media info)
- **`groq-voice`** -- Whisper Large v3 Turbo transcription (key in
  `$GROQ_API_KEY`)

Plus `ffmpeg` for video→audio extraction.

---

## When to use

Trigger on any of these (Russian and English):

- "проанализируй reels у @...", "разбери почему залетает", "сделай разбор аккаунта"
- "вытащи хуки у конкурента", "скопировать формат", "почему у него такие просмотры"
- "Reels Challenge research", "найди что взлетает в нише X"
- explicit: "reels analyzer", "виральный разбор", "deep dive reels"
- bare instagram.com link + intent to *understand* (not just fetch metrics)

Skip when:

- Task is one-shot metric lookup ("сколько подписчиков у @user") -- use
  `hikerapi` directly, no transcription pipeline needed.
- Task is content *creation* (write captions, generate ideas) -- this skill
  is for *analysis* of existing reels.
- POST to Instagram or schedule content -- read-only, scrape only.

---

## Cost model (rough, per run)

The operator runs Claude on a flat subscription (Claude Code / Claude.ai),
NOT pay-as-you-go API. So LLM-analysis tokens are effectively $0 to the
operator -- only out-of-pocket cash costs are HikerAPI and Groq.

| Item | Per top-5 run |
|---|---|
| HikerAPI: 3 paging + 1 user-resolve + 5 enrich = **~9 calls** | ~$0.30-0.50 |
| Groq Whisper (5 reels × ~30s avg = ~150s) | ~$0.02 |
| LLM-analysis (this session, Opus on subscription) | **$0** |
| **Total cash** | **~$0.35-0.55** |

Optimization priority: **HikerAPI calls are the only real cost driver.**
Don't over-engineer LLM-input compactness for cost reasons (it's free) --
but keep compact markdown for readability/quality. Always run `hikerapi
balance` before a multi-account batch -- $2 starter balance covers
~30-40 single-account top-5 runs.

---

## Two-phase workflow

### Phase 1: data collection (deterministic, scripted)

Run the bundled orchestrator. It does: profile resolve → 30 medias paging →
filter reels → engagement-rank → top-N → enrich with real `play_count` →
download mp4 (480p+) → ffmpeg mono 16kHz 32kbps mp3 → Groq transcribe →
emit `report.json` + draft `report.md`.

```bash
python3 ~/.claude/skills/reels-analyzer/scripts/analyze.py \
    --user @your_account --top 5 --history 30 --verbose
# or by user_id (skips one resolve call):
python3 ~/.claude/skills/reels-analyzer/scripts/analyze.py \
    --user-id 17841400000000000 --top 5
# debug without Groq key:
python3 ... --skip-transcribe
```

Output goes to `/tmp/reels-analyzer/<username>/`:
```
report.json        -- full structured payload (read this)
report.md          -- draft report with LLM-analysis fields blank
videos/<code>.mp4  -- raw downloaded video (~1-15MB each)
audio/<code>.mp3   -- 32kbps mono (small)
transcripts/<code>.txt  -- Whisper output
```

### Phase 2: LLM analysis (you, the agent)

Read `report.json`, then for each reel produce 5 fields by reasoning over
caption + transcript + metrics. Write the full report back as
`<out>/report_final.md`.

**See `references/prompts.md` for the analysis prompt template.**

The 5 fields:

1. **хук (0-3s)** -- exact opening line from transcript, plus 1-line analysis
   of *why this hook hooks* (curiosity gap / shock / loop / pattern interrupt
   / specific number / authority / contrarian claim).
2. **структура** -- map the reel into beats: `intro (0-Xs) → body (X-Ys) → CTA
   or loop (Y-end)`. Identify the rhythm.
3. **тема / архетип** -- one of: news-jacking, satisfying-process, hot-take,
   how-to, story, listicle, contrarian, demo, behind-the-scenes, AI-generated.
   Plus 1-line topic ("AI tool for X", "geopolitics commentary", etc).
4. **почему залетает** -- top 2-3 mechanics combining hook + theme + audience
   trigger + visual contrast + audio. Be specific, not generic.
5. **вердикт** -- exactly one of:
   - **КОПИРОВАТЬ** -- format and topic both transferable as-is to operator's account.
   - **АДАПТИРОВАТЬ** -- format works, topic needs swap to operator's niche.
   - **ПРОПУСТИТЬ** -- format depends on factors operator can't replicate
     (celebrity access, breaking news, paid ads, ethical risk for verified account).

   Each verdict needs a 1-line *why*.

---

## Strategic layer (this is what 80% of users actually want)

After per-reel analysis, write a **2-paragraph executive summary** at the top
of `report_final.md` covering:

1. **Pattern across the top** -- what's common (theme mix, hook style, length).
2. **Strategic gap** -- where is the operator's content losing money? Common
   ones: viral reels with no CTA (lost lead funnel), niche mismatch (audience
   ≠ buyer), ethical risks for verified accounts, dependency on news cycles
   (not durable). Be direct, not diplomatic.

The operator hires this skill not for cute report rendering but to find
**leverage points** -- be the partner that names them.

---

## Failure modes & graceful handling

- **`Groq key missing`** -- script skips transcription, populates
  `transcript_error`. Tell operator how to fix (free key at console.groq.com),
  optionally proceed with caption-only analysis (lower quality, flag this).
- **`Cloudflare 1010`** -- HikerAPI default already routes to `api.instagrapi.com`
  to bypass. If still blocked, check `hikerapi` skill notes.
- **`download failed` (Instagram CDN expired)** -- IG video URLs expire in
  ~24h. Re-fetch the media via HikerAPI, the URL is regenerated.
- **`ffmpeg failed`** -- check `which ffmpeg`. Should be 6.1.1+. Ubuntu apt
  install ffmpeg if missing.
- **Account is private** -- `is_private: true` in profile -> can't fetch
  medias. Stop and report.
- **Account has < 5 reels** -- pipeline returns whatever exists; flag the
  small sample to operator.

---

## Example invocations

```
"проанализируй reels у @nasa, топ-5 за последние 30"
"разбери почему залетают рилсы у @your_account"
"сделай deep dive @username, я хочу понять что копировать"
"reels analyzer для @competitor с фокусом на хуки"
```

Examples that should trigger but use *different* skills:

- "сколько подписчиков у @user" -> `hikerapi` (no analysis needed)
- "напиши 20 идей для reels" -> NOT this skill (creation, not analysis)
- "опубликуй ролик в инсте" -> NOT this skill (read-only)

---

## References

- `references/prompts.md` -- LLM analysis prompt template
- `references/pipeline.md` -- detailed flow with timing
- `evals/evals.json` -- 3 functional tests
- `evals/trigger_eval.json` -- 20 trigger queries (10/10) for description tuning
