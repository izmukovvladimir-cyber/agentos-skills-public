#!/usr/bin/env python3
"""Handwritten "blue pen on cream paper" carousel renderer (Chrome headless, no PIL).

Mirrors the donor_ten / donor_seven viral notebook format but PRETTIER and
READABLE per the operator 2026-07-04: same handwritten vibe (Caveat, deep-blue ink, warm
cream paper, faint ruled lines) rendered LARGE and clean so nothing is cramped or thin.

Same spec schema as ~/bin/carousel_render.py:
  slide types: cover | prompts | note | cta
Usage: notebook_render.py spec.json out_dir/ [--scale 2]
"""
from __future__ import annotations
import argparse, base64, html, json, shutil, subprocess, sys, tempfile
from pathlib import Path

W, H = 1080, 1350
CAVEAT = Path("~/.fonts/Caveat")

INK = "#213A7C"        # deep pen blue
INK_SOFT = "#3350A0"   # heading / accent blue
PAPER1 = "#F5EEDD"     # warm cream
PAPER2 = "#EFE6D1"
RULE = "rgba(33,58,124,.07)"
HANDLE = "rgba(33,58,124,.42)"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def esc(s: str) -> str:
    return html.escape(str(s), quote=False).replace("\n", "<br>")


def fonts_css() -> str:
    if not CAVEAT.exists():
        print("WARNING: Caveat not found", file=sys.stderr)
        return ""
    return ("@font-face{font-family:'Caveat';font-weight:400 700;font-style:normal;"
            f"src:url(data:font/ttf;base64,{b64(CAVEAT)}) format('truetype');}}")


DOODLES = {
    # small blue line-doodles for the cover (echo original), stroke=currentColor
    "chat": '<svg viewBox="0 0 64 64" class="doodle"><path d="M12 14h40a6 6 0 0 1 6 6v18a6 6 0 0 1-6 6H30l-12 9v-9h-6a6 6 0 0 1-6-6V20a6 6 0 0 1 6-6z" fill="none" stroke="currentColor" stroke-width="3"/><path d="M24 29c0-4 4-7 8-7s8 3 8 7-4 6-8 6" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="42" r="1.8" fill="currentColor"/></svg>',
    "cake": '<svg viewBox="0 0 64 64" class="doodle"><path d="M10 40c0-6 5-10 12-10h20c7 0 12 4 12 10v12H10V40z" fill="none" stroke="currentColor" stroke-width="3"/><path d="M10 44h44" stroke="currentColor" stroke-width="3"/><path d="M24 30V18M32 30V16M40 30V18" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M24 14c0 3-4 3-4 0 0-2 2-4 2-4s2 2 2 4zM32 12c0 3-4 3-4 0 0-2 2-4 2-4s2 2 2 4zM40 14c0 3-4 3-4 0 0-2 2-4 2-4s2 2 2 4z" fill="none" stroke="currentColor" stroke-width="2.4"/></svg>',
    "spark": '<svg viewBox="0 0 64 64" class="doodle"><path d="M32 8v20M32 36v20M8 32h20M36 32h20M16 16l12 12M36 36l12 12M48 16L36 28M28 36L16 48" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>',
    "briefcase": '<svg viewBox="0 0 64 64" class="doodle"><rect x="10" y="22" width="44" height="30" rx="5" fill="none" stroke="currentColor" stroke-width="3"/><path d="M24 22v-5a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v5" fill="none" stroke="currentColor" stroke-width="3"/><path d="M10 34h44" stroke="currentColor" stroke-width="3"/></svg>',
}


def _cover(s: dict) -> str:
    doods = "".join(DOODLES.get(d, "") for d in s.get("doodles", []))
    doodle_row = f'<div class="doodles">{doods}</div>' if doods else ""
    kicker = f'<div class="kicker">{esc(s["kicker"])}</div>' if s.get("kicker") else ""
    sub = f'<div class="cover-sub">{esc(s["subtitle"])}</div>' if s.get("subtitle") else ""
    return (f'<div class="cover">{doodle_row}{kicker}'
            f'<div class="cover-title">{esc(s.get("title",""))}</div>'
            f'<div class="uline"></div>{sub}</div>')


def _prompts(s: dict) -> str:
    head = f'<div class="sec-heading">{esc(s["heading"])}</div>' if s.get("heading") else ""
    rows = []
    items = s.get("items", [])
    for idx, it in enumerate(items):
        num = esc(it.get("n", ""))
        label = esc(it.get("label", ""))
        head_line = f'<span class="p-num">{num}.</span> <span class="p-label">{label}</span>'
        rows.append(
            f'<div class="prompt"><div class="p-head">{head_line}<span class="p-uline"></span></div>'
            f'<div class="p-text">{esc(it.get("text",""))}</div></div>')
        if idx != len(items) - 1:
            rows.append('<div class="dash">· · · · ·</div>')
    return f'<div class="prompts">{head}{"".join(rows)}</div>'


def _note(s: dict) -> str:
    title = f'<div class="note-title">{esc(s["title"])}</div>' if s.get("title") else ""
    return f'<div class="note">{title}<div class="note-text">{esc(s.get("text",""))}</div></div>'


def _cta(s: dict) -> str:
    title = f'<div class="cta-title">{esc(s["title"])}</div>' if s.get("title") else ""
    text = f'<div class="cta-text">{esc(s["text"])}</div>' if s.get("text") else ""
    btn = f'<div class="cta-btn">{esc(s["button"])}</div>' if s.get("button") else ""
    return f'<div class="cta">{title}<div class="uline"></div>{text}{btn}</div>'


BUILDERS = {"cover": _cover, "prompts": _prompts, "note": _note, "cta": _cta}


def slide_html(slide: dict, handle: str, fonts: str) -> str:
    body = BUILDERS.get(slide.get("type", "note"), _note)(slide)
    foot = esc(slide.get("handle", handle))
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
{fonts}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px}}
body{{font-family:'Caveat',cursive;color:{INK};-webkit-font-smoothing:antialiased;overflow:hidden;
 background:
  radial-gradient(120% 90% at 15% 8%, rgba(255,255,255,.55), rgba(255,255,255,0) 55%),
  radial-gradient(120% 120% at 85% 95%, rgba(150,120,70,.10), rgba(150,120,70,0) 60%),
  repeating-linear-gradient(0deg,{RULE} 0 1px,transparent 1px 64px),
  linear-gradient(160deg,{PAPER1} 0%,{PAPER2} 100%);}}
.page{{width:{W}px;height:{H}px;padding:104px 96px 84px;display:flex;flex-direction:column;position:relative}}
#fit{{flex:1;display:flex;flex-direction:column;justify-content:center;font-size:44px;
 line-height:1.28;min-height:0;overflow-wrap:anywhere;word-break:break-word;font-weight:600}}
.doodles{{display:flex;gap:26px;color:{INK};margin-bottom:22px}}
.doodle{{width:74px;height:74px}}
.kicker{{font-size:.68em;font-weight:700;color:{INK_SOFT};margin-bottom:6px}}
.cover{{display:flex;flex-direction:column;gap:16px}}
.cover-title{{font-size:1.62em;font-weight:700;line-height:1.06;letter-spacing:.005em}}
.cover-sub{{font-size:.86em;font-weight:600;color:{INK};opacity:.92;max-width:96%}}
.uline{{width:200px;height:7px;border-radius:6px;background:{INK_SOFT};opacity:.85;margin:10px 0 6px}}
.sec-heading{{font-size:1.05em;font-weight:700;margin-bottom:.5em;color:{INK_SOFT}}}
.prompts{{display:flex;flex-direction:column;gap:.42em}}
.prompt{{display:flex;flex-direction:column;gap:.12em}}
.p-head{{position:relative;display:inline-block}}
.p-num{{font-weight:700;color:{INK_SOFT};font-size:1.08em}}
.p-label{{font-weight:700;font-size:1.06em;color:{INK}}}
.p-uline{{display:block;height:5px;border-radius:4px;background:{INK_SOFT};opacity:.45;margin-top:2px;width:100%}}
.p-text{{font-weight:600;font-size:.95em;line-height:1.26;color:{INK}}}
.dash{{color:{INK};opacity:.5;font-size:.85em;letter-spacing:.08em;text-align:center;margin:.12em 0}}
.note{{display:flex;flex-direction:column;gap:.4em}}
.note-title{{font-size:1.35em;font-weight:700;color:{INK_SOFT}}}
.note-text{{font-size:1.0em;font-weight:600;line-height:1.3}}
.cta{{display:flex;flex-direction:column;gap:20px;justify-content:center;height:100%}}
.cta-title{{font-size:1.5em;font-weight:700;line-height:1.08}}
.cta-text{{font-size:1.0em;font-weight:600;line-height:1.32}}
.cta-btn{{align-self:flex-start;border:4px solid {INK_SOFT};color:{INK_SOFT};font-weight:700;
 font-size:1.15em;padding:12px 40px;border-radius:44px}}
.footer{{display:flex;align-items:center;justify-content:flex-end;padding-top:20px;margin-top:22px;
 border-top:2px dashed {RULE}}}
.handle{{font-weight:700;font-size:32px;color:{HANDLE}}}
</style></head><body><div class="page">
<div id="fit">{body}</div>
<div class="footer"><span class="handle">{foot}</span></div></div>
<script>
(function(){{var fit=document.getElementById('fit');
var avail=fit.clientHeight,availW=fit.clientWidth;
function over(px){{fit.style.fontSize=px+'px';return fit.scrollHeight>avail+1||fit.scrollWidth>availW+1;}}
var lo=30,hi=48;  // readable floor (правило: рукопись не мельче ~30px, иначе NB_OVERFLOW → слайд переспличивать, не ужимать в мелочь)
if(over(hi)){{for(var i=0;i<26;i++){{var mid=(lo+hi)/2;if(over(mid))hi=mid;else lo=mid;}}fit.style.fontSize=lo+'px';}}
else{{fit.style.fontSize=hi+'px';}}
if(over(parseFloat(fit.style.fontSize))){{console.error('NB_OVERFLOW');document.documentElement.setAttribute('data-overflow','1');}}
document.documentElement.setAttribute('data-fit','done');}})();
</script></body></html>"""


def render(spec: dict, out_dir: Path, scale: int) -> None:
    chrome = next((b for b in ("google-chrome-stable", "google-chrome", "chromium",
                               "chromium-browser") if shutil.which(b)), None)
    if not chrome:
        sys.exit("no chrome found")
    handle = spec.get("handle", "@your_account")
    fonts = fonts_css()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for i, slide in enumerate(spec.get("slides", []), 1):
            hp = tdp / f"s{i}.html"
            hp.write_text(slide_html(slide, handle, fonts), encoding="utf-8")
            png = out_dir / f"slide_{i:02d}.png"
            if png.exists():
                png.unlink()
            cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                   "--disable-dev-shm-usage", "--enable-logging=stderr", "--v=0",
                   f"--force-device-scale-factor={scale}", f"--screenshot={png}",
                   f"--window-size={W},{H}", "--no-first-run", "--no-default-browser-check",
                   "--virtual-time-budget=5000", f"file://{hp}"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not png.exists() or png.stat().st_size == 0:
                sys.exit(f"render fail slide {i}: {r.stderr[-300:]}")
            warn = " !!OVERFLOW" if "NB_OVERFLOW" in r.stderr else ""
            print(f"  slide {i:02d} [{slide.get('type')}] {png.stat().st_size//1024}KB{warn}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out_dir")
    ap.add_argument("--scale", type=int, default=2, choices=(1, 2, 3))
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    print(f"notebook render {len(spec.get('slides',[]))} slides scale={a.scale}")
    render(spec, Path(a.out_dir), a.scale)
    print("DONE")


if __name__ == "__main__":
    main()
