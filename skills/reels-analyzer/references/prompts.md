# LLM analysis prompts -- reels-analyzer

These are prompt scaffolds the calling agent uses on each reel after
`analyze.py` produces `report.json`. The agent has caption + transcript +
metrics for each reel; the agent itself is the LLM, no separate model call
needed unless analysis is delegated to a subagent.

---

## Per-reel analysis prompt (use as internal scaffold)

For each reel object in `report.json["reels"]`, reason through:

```
INPUT:
  caption: <r.caption>
  transcript: <r.transcript>  (or [NO TRANSCRIPT] if missing)
  metrics: views=<r.play_count>, likes=<r.like_count>, comments=<r.comment_count>,
           reshares=<r.reshare_count>, ER=<r.er_pct>%, duration=<r.video_duration_s>s
  permalink: <r.permalink>

PRODUCE (markdown, exactly this structure):
  ### #<rank> · <play_count formatted> views · <duration>s · <date>
  [permalink](permalink)

  metrics line: ❤️ likes · 💬 comments · 🔁 reshares · ER X.XX%

  - **хук (0-3s):** "<exact first 1-2 sentences from transcript>"
    Why it hooks: <1 line>. Tactic: <curiosity-gap | shock | loop | pattern-interrupt | specific-number | authority | contrarian | sensory>.

  - **структура:** intro (0-Xs) <what happens> → body (X-Ys) <what happens> → close (Y-end) <CTA / loop / cliffhanger>.

  - **тема / архетип:** <news-jacking | satisfying-process | hot-take | how-to | story | listicle | contrarian | demo | BTS | AI-generated>. Topic: <one-liner>.

  - **почему залетает:** <2-3 bullet mechanics>. Be specific:
      - <hook + audio combo / visual contrast / dopamine loop>
      - <audience trigger: outrage / aspiration / curiosity / nostalgia>
      - <Instagram algorithm signal: high reshares = boost, comment density, watchtime via duration>

  - **вердикт:** **КОПИРОВАТЬ** | **АДАПТИРОВАТЬ** | **ПРОПУСТИТЬ** -- <1 line why>.
```

---

## Executive summary prompt (top of report_final.md)

After all per-reel analyses are written, prepend a 2-paragraph exec summary:

```
PARAGRAPH 1 -- Pattern across the top:
  - What's the dominant theme mix? (e.g. "4 of 5 are political news-jacking")
  - What's the dominant hook style? (e.g. "all open with a name + shock claim")
  - What's the duration distribution? (short <30s viral vs long 90+s deep)
  - What's the CTA hit-rate? (how many of N have a call-to-action?)

PARAGRAPH 2 -- Strategic gap (THE money paragraph):
  Identify 2-3 leverage points. Examples to look for:
    - viral reels without CTA = lost funnel ("X views × 0.5% CTR = N missed leads")
    - audience-product mismatch (theme attracts wrong demo for the offer)
    - ethical/platform risk (AI-fake news on a verified account)
    - over-dependence on news cycle (not durable, no evergreen content)
    - high-ER format underused (one reel hit 5%+ ER, why isn't this scaled?)

  End with one concrete next-action ("the obvious 80/20 move is X").
```

---

## Verdict heuristics

To pick КОПИРОВАТЬ vs АДАПТИРОВАТЬ vs ПРОПУСТИТЬ consistently:

**Operator strategy context (critical):** the owner runs a 2-layer funnel --
front-end is *cold-viral* (intentionally broad topics: news, politics,
relationships, esoterica, life-hacks) for maximum reach; back-end is
*warm-expert* (Telegram bot + tripwire + flagship). **Don't flag a viral
front-end reel as ПРОПУСТИТЬ just because the topic isn't aligned with the
product.** Niche-product mismatch on front-end is a feature, not a bug --
that's exactly how he hit 39M views on the previous account.

**КОПИРОВАТЬ** when:
- Format and topic are both transferable as-is to operator's account
- Universal viral format (satisfying-process, demo, how-to) AND no
  celebrity / news / platform-risk dependency
- Strong CTA mechanic already present and on-brand

**АДАПТИРОВАТЬ** when:
- Format transfers (hook style, pacing, CTA shape) regardless of whether
  topic does or not
- For the owner specifically: any cold-viral format with a clean topic
  (no platform-risk) is АДАПТИРОВАТЬ -- topic doesn't need to match product
- Most viral formats fall here

**ПРОПУСТИТЬ** when (only legitimate reasons -- do NOT use "off-niche"):
- AI-deepfake of a recognizable public figure (Mizulina, Zelensky, Solovyov,
  etc.) -- platform-risk for verified accounts, prior bans seen
- Depends on irreplaceable factor: live celebrity access, real breaking
  news with <24h relevance window, paid collab requiring disclosure
- Format requires real footage operator cannot capture (e.g., war zone)
- Ethical/legal risk specific to operator's verified-account status

When in doubt -- АДАПТИРОВАТЬ is the default. ПРОПУСТИТЬ requires a *real
reason* (platform-risk, irreplaceability, legal/ethical), not vibes and
not "wrong niche".

---

## Tone

- Russian for operator-facing report content (the owner's preference).
- Direct, no hedging. "Это слабый хук" not "Возможно, хук можно улучшить".
- Specific numbers when available ("2.75M views × 0.5% conversion = 14K leads
  on the table") not abstract claims.
- Don't soften the strategic gap paragraph. Operator wants the leverage point,
  not flattery.
