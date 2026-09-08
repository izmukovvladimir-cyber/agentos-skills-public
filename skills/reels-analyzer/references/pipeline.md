# Reels analyzer -- detailed pipeline

End-to-end flow with timing estimates and failure modes per stage.

```
┌─────────────────────────────────────────────────────────────────┐
│                     analyze.py orchestrator                     │
└─────────────────────────────────────────────────────────────────┘

1. RESOLVE USER                                          [~1s, 1 API call]
   ├─ --user X    -> /v2/user/by/username -> {pk, follower_count, ...}
   └─ --user-id N -> /v2/user/by/id

2. PAGE MEDIAS                                       [~3s, 2-3 API calls]
   /v2/user/medias (NOT /gql/user/medias -- gql is unstable, returns
   "Instagram GQL stream returned no usable data" intermittently)
   - 12 items per page, paginate via response.next_page_id
   - response wrapper: items live at `response.items` OR root `items`
     (varies between calls, handle both)
   - filter: media_type == 2 OR product_type == "clips"

3. RANK & ENRICH                                       [~3s, N API calls]
   /v2/user/medias has play_count = 0 (always). Rank by engagement proxy
   (likes + 2*comments) to pick top-(N*2) candidates, then enrich each
   via /v2/media/info/by/code which returns real play_count.
   Response shape: {"media_or_ad": {...}, "status": "ok"} -- unwrap.

4. SORT BY REAL play_count                                       [~0s]
   Final top-N from the enriched set.

5. PER-REEL: download mp4                                    [~2-15s each]
   video_versions[*] -- pick smallest >=480p (saves bandwidth, Whisper
   doesn't need 1080p). URL signed by IG CDN, expires in ~24h.
   User-Agent must be set (urllib default fails on IG CDN).

6. PER-REEL: extract audio                                   [~1-2s each]
   ffmpeg -y -loglevel error -i in.mp4 -vn -ac 1 -ar 16000 -b:a 32k out.mp3
   - mono (saves bytes)
   - 16kHz (Whisper input rate)
   - 32kbps (transparent for speech)
   Result ~100KB-2MB depending on duration.

7. PER-REEL: transcribe                                      [~2-5s each]
   bash transcribe.sh <mp3>
   - calls Groq Whisper Large v3 Turbo
   - response_format=text -> stdout
   - 25MB upload limit (we're well under)
   - free tier 14400 audio-seconds/day (plenty for testing)

8. WRITE OUTPUTS                                                  [~0s]
   /tmp/reels-analyzer/<username>/
     report.json   - full structured data, ALL fields (read this)
     report.md     - draft markdown, LLM analysis fields blank
     videos/
     audio/
     transcripts/

Total wall time for top-5: ~30-60 seconds.
```

## Failure handling

Each stage is independent in `process_media()`. A failure in download/audio/
transcribe is recorded in `transcript_error` field and the reel still appears
in `report.json` -- the agent decides whether to skip it in the final report
or proceed with caption-only analysis.

## What this script does NOT do

- Comments fetching (use `hikerapi raw /v2/media/comments id=<pk>`)
- Music/audio track lookup (use `/v2/track/by/canonical/id`)
- Frame extraction / vision analysis (out of scope; would need OpenAI Vision
  or Claude vision model)
- Scheduled monitoring (one-shot only; cron yourself if needed)

## When to extend this script (vs work around it)

Extend when:
- Multi-account batch (loop over usernames) becomes a regular workflow
- Want to attach comment-sentiment to each reel
- Want frame thumbnails for visual analysis

Work around (don't bloat the script) when:
- One-off custom analysis -> read report.json and process inline
- Ad-hoc stats across N reports -> separate aggregator script
