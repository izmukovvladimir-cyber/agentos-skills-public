#!/usr/bin/env python3
"""Build a 9:16 HyperFrames project from a vertical clip + word-level transcript.

Produces `index.html` + `hyperframes.json` + `assets/source.mp4` in an output
directory, ready for `hf check` / `hf snapshot` / `hf render`.

Layout: full-bleed video, an optional hook card in the upper safe zone, and a
karaoke subtitle band in the lower third. The active word is highlighted by a
colour tween on the single paused timeline HyperFrames requires.

Two things here are load-bearing and were found by the engine's own gate, not by
reading:

* A line holds until the NEXT line starts. Whisper word spans overlap, so
  "last word end + padding" put two bands on screen at once and the text stacked
  into mush (`content_overlap`).
* Every timed element carries an id. Without one the composition renders fine but
  cannot be edited in Studio (`studio_missing_editable_id`).
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import shutil
import subprocess
import sys

HYPERFRAMES_JSON = {
    "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    "paths": {
        "blocks": "compositions",
        "components": "compositions/components",
        "assets": "assets",
    },
    "media": {"autoProxy": True},
}


def place_source(src: pathlib.Path, dst: pathlib.Path) -> str:
    """Put the clip at assets/source.mp4, remuxing when the container is not mp4.

    Phones hand us .MOV. Copying those bytes under an .mp4 name is a lie the
    browser preview believes and then fails on; remux first (`-c copy`, no
    re-encode), and only fall back to a real encode when the codecs cannot live
    in an mp4 container. Returns what was done, for the run log.
    """
    if src.suffix.lower() == ".mp4":
        shutil.copy2(src, dst)
        if not dst.is_file() or dst.stat().st_size == 0:
            raise RuntimeError(f"исходник {src} пуст")
        return "скопирован как есть"
    remux = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy",
         "-movflags", "+faststart", str(dst)],
        capture_output=True, text=True,
    )
    if remux.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
        return f"переупакован из {src.suffix} без перекодирования"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac",
         "-movflags", "+faststart", str(dst)],
        check=True,
    )
    # a zero exit is not a file: ffmpeg can return 0 having written nothing, and an
    # empty source.mp4 renders a black composition that looks like a styling bug
    if not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg отчитался успехом, но {dst} пуст")
    return f"перекодирован из {src.suffix}"


def probe_duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def group_lines(words: list[dict], max_words: int, max_chars: int) -> list[list[dict]]:
    """Chunk words into short subtitle lines that fit the band."""
    lines: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        cand = cur + [w]
        too_long = len(cand) > max_words or sum(len(x["word"]) + 1 for x in cand) > max_chars
        if cur and too_long:
            lines.append(cur)
            cur = [w]
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def timed_lines(lines: list[list[dict]], duration: float) -> list[tuple[int, float, float, list[dict]]]:
    """Clamp each line's end to the next line's start, so only one band shows."""
    out: list[tuple[int, float, float, list[dict]]] = []
    for i, ln in enumerate(lines):
        start = float(ln[0]["start"])
        nxt = float(lines[i + 1][0]["start"]) if i + 1 < len(lines) else duration
        end = min(float(ln[-1]["end"]) + 0.12, nxt, duration)
        if start >= duration or end <= start:
            continue
        out.append((i, start, end, ln))
    return out


def render_html(
    words: list[dict],
    duration: float,
    hook: str,
    hook_until: float,
    accent: str,
    width: int,
    height: int,
    max_words: int,
    max_chars: int,
    band_top: int,
) -> str:
    rows = timed_lines(group_lines(words, max_words, max_chars), duration)

    line_html: list[str] = []
    tweens: list[str] = []
    for li, start, end, ln in rows:
        spans = []
        for wi, w in enumerate(ln):
            wid = f"w{li}-{wi}"
            spans.append(f'<span id="{wid}">{html.escape(str(w["word"]))}</span>')
            if float(w["start"]) < duration:
                tweens.append(
                    f'tl.to("#{wid}", {{ color: "{accent}", duration: 0.08 }}, {float(w["start"]):.2f});'
                )
        line_html.append(
            f'      <div id="sub-{li}" class="clip subs" data-start="{start:.2f}" '
            f'data-duration="{end - start:.2f}" data-track-index="{3 + (li % 2)}">'
            f'<div class="band">{" ".join(spans)}</div></div>'
        )

    hook_block = ""
    hook_tween = ""
    if hook:
        hook_block = (
            f'      <div id="hook" class="clip hook" data-start="0.20" '
            f'data-duration="{max(hook_until - 0.2, 0.5):.2f}" data-track-index="2">'
            f'<div class="card" id="hook-card">{html.escape(hook)}</div></div>'
        )
        hook_tween = (
            'tl.fromTo("#hook-card", { y: -40, opacity: 0 }, '
            '{ y: 0, opacity: 1, duration: 0.45, ease: "power3.out" }, 0.2);'
        )

    nl = "\n"
    body_lines = nl.join([b for b in [hook_block, *line_html] if b])
    script_lines = nl.join("      " + t for t in [hook_tween, *tweens] if t).strip()

    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <title>reel</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; overflow: hidden; background: #000; }}
      body {{ font-family: "DejaVu Sans", Inter, system-ui, sans-serif; }}
      #root {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; }}
      #bg {{ position: absolute; inset: 0; background: #000; }}
      #a-roll {{ position: absolute; inset: 0; width: {width}px; height: {height}px; object-fit: cover; }}
      .hook {{ position: absolute; left: 56px; right: 56px; top: 150px; display: flex; justify-content: center; }}
      .hook .card {{
        background: rgba(10, 12, 16, 0.86); border: 4px solid {accent}; border-radius: 28px;
        padding: 28px 36px; color: #fff; font-size: 66px; font-weight: 800; line-height: 1.12;
        text-align: center; letter-spacing: -0.5px;
      }}
      .subs {{ position: absolute; left: 0; right: 0; top: {band_top}px; display: flex; justify-content: center; }}
      .band {{
        max-width: {width - 140}px; background: rgba(8, 10, 14, 0.92); border-radius: 24px;
        padding: 22px 34px; color: #fff; font-size: 62px; font-weight: 800; line-height: 1.18;
        text-align: center; text-transform: uppercase;
      }}
      .band span {{ color: #fff; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0"
         data-width="{width}" data-height="{height}" data-duration="{duration:.2f}">
      <div id="bg"></div>
      <video id="a-roll" class="clip" src="assets/source.mp4"
             data-start="0" data-duration="{duration:.2f}" data-track-index="0" muted playsinline></video>
      <audio id="a-roll-audio" src="assets/source.mp4"
             data-start="0" data-duration="{duration:.2f}" data-track-index="10" data-volume="1"></audio>
{body_lines}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {script_lines}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clip", type=pathlib.Path, required=True, help="vertical source video")
    ap.add_argument("--words", type=pathlib.Path, required=True, help="JSON from transcribe_words.py")
    ap.add_argument("--out", type=pathlib.Path, required=True, help="project directory to create")
    ap.add_argument("--hook", default="", help="text of the opening card (empty = no card)")
    ap.add_argument("--hook-until", type=float, default=4.5, help="seconds the hook card stays")
    ap.add_argument("--accent", default="#c8ff2e")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--duration", type=float, default=0.0, help="0 = full clip length")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=30)
    ap.add_argument("--band-top", type=int, default=1360)
    args = ap.parse_args()

    if not args.clip.is_file():
        print(f"ERR: нет клипа {args.clip}", file=sys.stderr)
        return 2
    if not args.words.is_file():
        print(f"ERR: нет транскрипта {args.words}", file=sys.stderr)
        return 2

    payload = json.loads(args.words.read_text(encoding="utf-8"))
    words = payload.get("words") if isinstance(payload, dict) else payload
    if not words:
        print("ERR: в транскрипте нет пословных отметок", file=sys.stderr)
        return 5

    duration = args.duration or probe_duration(args.clip)

    (args.out / "assets").mkdir(parents=True, exist_ok=True)
    try:
        placed = place_source(args.clip, args.out / "assets" / "source.mp4")
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"ERR: не удалось привести {args.clip.suffix} к mp4: {exc}", file=sys.stderr)
        return 3
    (args.out / "hyperframes.json").write_text(
        json.dumps(HYPERFRAMES_JSON, indent=2) + "\n", encoding="utf-8"
    )
    doc = render_html(
        words, duration, args.hook, args.hook_until, args.accent,
        args.width, args.height, args.max_words, args.max_chars, args.band_top,
    )
    (args.out / "index.html").write_text(doc, encoding="utf-8")

    n_lines = len(timed_lines(group_lines(words, args.max_words, args.max_chars), duration))
    print(f"проект: {args.out}, {duration:.1f} с, строк субтитров: {n_lines}, слов: {len(words)}")
    print(f"исходник: {placed}")
    print(f"дальше: cd {args.out} && ~opt/reels-studio/bin/hf check && hf render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
