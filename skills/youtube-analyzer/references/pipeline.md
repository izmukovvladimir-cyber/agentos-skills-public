# YouTube analyzer -- detailed pipeline

End-to-end flow with `yt-dlp` commands, VTT parsing, and fallback chain.

```
┌─────────────────────────────────────────────────────────────────┐
│                     analyze.py orchestrator                     │
└─────────────────────────────────────────────────────────────────┘

1. NORMALIZE HANDLE                                              [~0s]
   Accept: bare handle, @handle, full URL (/@handle, /channel/UC...).
   Output: (handle, https://www.youtube.com/@handle | /channel/UC...).

2. RESOLVE CHANNEL LISTING                            [~2-5s, no API key]
   Try /videos tab first (long-form first):
     yt-dlp -J --flat-playlist "<root>/videos"
   If error contains "does not have a videos tab" -> fall back to /shorts.
   If channel has BOTH (a typical Shorts-heavy creator might post
   occasional longs), fetch both and merge entries by id. Tag each entry
   with its source tab for later format detection.
   --flat-playlist returns ALL videos with view_count in one call -- this
   is why YouTube analysis is cheaper than IG (no paging fees).

3. SORT + TOP-N                                                  [~0s]
   Sort entries by view_count desc, take top-N (default 5).

4. PER-VIDEO: full metadata                              [~1-3s each, no key]
   yt-dlp -j --skip-download "https://www.youtube.com/watch?v=<id>"
   Pulls: title, description, duration, view/like/comment_count, upload_date,
   thumbnails[], channel meta, available `subtitles` and `automatic_captions`.

5. PER-VIDEO: caption priority chain                     [~1-2s each, no key]
   Try in order, stop on first hit:
     a) manual subs in ru:  --write-sub --sub-lang ru
     b) manual subs in en:  --write-sub --sub-lang en  (flag transcript_language='en')
     c) auto-captions in ru: --write-auto-sub --sub-lang ru  (lower confidence)
     d) auto-captions in en: --write-auto-sub --sub-lang en  (lower confidence)
   Output is .vtt -> parse via vtt_to_text() (see below).

6. PER-VIDEO: Groq fallback (only if a-d all missed)      [~5-10s each]
   yt-dlp -x --audio-format mp3 ...   # extract audio
   bash transcribe.sh <mp3>           # Groq Whisper Large v3 Turbo
   Cost: ~$0.005 per fallback video. Fires only when channel publishes
   without captions (rare for established creators).

7. AGGREGATE STATS                                               [~0s]
   Over the FULL listing (not just top-N): views total/mean/median, format
   mix (Shorts vs Long count), mean duration. Top-N's "× медианы" is then
   measured against the channel's actual median, not a top-only median.

8. WRITE OUTPUTS                                                  [~0s]
   /tmp/youtube-analyzer/<handle>/
     report.json             - full structured data, ALL fields (read this)
     report.md               - draft markdown, LLM analysis fields blank
     transcripts/<id>.txt    - clean caption text (or Whisper output)
     audio/<id>.mp3          - only when Groq fallback was triggered

Total wall time for top-5 (with captions): ~15-30 seconds.
With Groq fallback on all 5: ~60-90 seconds.
```

## VTT parsing notes

YouTube auto-captions emit "rolling" cues -- each cue repeats the previous
line plus one new word, producing massive duplication if naively concatenated.

`vtt_to_text()` handles this:
- Strips WebVTT headers (`WEBVTT`, `Kind:`, `Language:`, `NOTE`).
- Strips timestamp lines (`00:00:01.000 --> 00:00:03.000`).
- Strips inline timing tags (`<00:00:01.000><c>foo</c>`).
- Dedupes consecutive identical cues.
- Handles "previous-is-prefix-of-current" by replacing the previous line with
  the longer current one (avoids losing the final continuation).
- Skips current cues that are prefixes of the previous one (already captured).

Net effect: 1000+ line VTT -> ~50-150 line clean transcript.

## YouTube bot-wall (data-center IPs)

YouTube increasingly challenges per-video `yt-dlp -j` calls and audio
downloads from data-center IPs with `Sign in to confirm you're not a bot`.
Channel listing (`-J --flat-playlist /videos|/shorts`) usually still works
because it hits a different endpoint. The script handles this:

- Per-video metadata failure -> `metadata_error` recorded, video stays in
  the report using flat-playlist fallback fields (id, title, view_count,
  thumbnail URL, tab-based format).
- Audio download for Groq fallback failure -> `transcript_error` recorded
  with the bot-wall message; report renders title + description + (any)
  transcript that did succeed.

**Workarounds when bot-walled:**

```bash
# Pass cookies from a logged-in browser:
yt-dlp --cookies-from-browser firefox -j ...
# Or export cookies.txt and pass:
yt-dlp --cookies /path/to/cookies.txt -j ...
```

For an `owner` server with no browser, the easiest path is to scp a
cookies.txt from a logged-in personal machine into
`$YOUTUBE_COOKIES` (mode 600). The script
does NOT auto-load cookies today -- if the bot-wall becomes a regular
blocker on the operator's stack, add `--cookies` flag wiring as a follow-up.

## Channel resolve edge cases

- **Handle with hyphens / dots / underscores:** `@my-handle.99_v2` is valid,
  the regex `[A-Za-z0-9._-]+` covers it.
- **Channel ID URL** (`/channel/UC...`): preserved as-is; bypasses handle
  redirect.
- **Auto-detected `_tab`:** entries from `/shorts` always Format='Short',
  entries from `/videos` use the duration<=60s rule (some channels post
  long-form Shorts mistakenly tagged on the /videos tab; the duration
  rule is the source of truth).

## What this script does NOT do

- Comments fetching (use yt-dlp's `--write-comments` if needed).
- Frame extraction / vision analysis (out of scope).
- Channel-level subscriber growth tracking (one-shot snapshot).
- Cross-channel batch (loop yourself).
- End-screen / cards / chapters extraction (yt-dlp doesn't expose these
  cleanly; would need YouTube Data API v3 with quota).

## When to extend this script (vs work around it)

Extend when:
- Multi-channel batch (loop over handles) becomes a regular workflow.
- Want to attach comment-sentiment to each video.
- Want frame thumbnails for visual analysis (B-roll cuts, on-screen text).

Work around (don't bloat the script) when:
- One-off custom analysis -> read report.json and process inline.
- Ad-hoc stats across N reports -> separate aggregator script.
- Need only metadata, not transcripts -> use `--no-transcribe`.
