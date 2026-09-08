#!/usr/bin/env python3
"""Vertical NEON stories/highlights renderer (1080x1920), headless Chrome, clean Cyrillic.

Neon style: near-black bg + blue/magenta glows, Onest Black headlines with neon accent,
glass cards for case numbers, neon ДО→ПОСЛЕ arrow. Text rendered by Chrome (no gpt-image
Cyrillic mangling). Optional photo cover (gpt-image neon portrait bg + neon text overlay).

Spec slide types:
  {"type":"cover","kicker":"...","title":"...","accent":"слово","subtitle":"..."}
  {"type":"cover_photo","bg":"hero.png","kicker":"...","title":"...","accent":"...","subtitle":"..."}
  {"type":"story","step":"01","heading":"...","accent":"слово","body":"..."}
  {"type":"case","niche":"🥊 Бокс","name":"Андрей Иванов","before":"8 322","after":"24 100","note":"×3","quote":"..."}
  {"type":"cta","title":"...","accent":"...","text":"...","button":"..."}
Usage: stories_neon_render.py spec.json out_dir/ [--scale 2]
"""
from __future__ import annotations
import argparse, base64, html, json, subprocess, sys
from pathlib import Path

W, H = 1080, 1920
ONEST = Path("~/.fonts/Onest.ttf")
ONEST_BLACK = Path("~/.fonts/Onest-Black.ttf")
# neon palette
BG = "#07070E"
BLUE = "#4D7CFF"
PINK = "#E64DFF"
CYAN = "#38E1FF"
WHITE = "#F5F6FF"
MUTED = "#A7AEDA"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def esc(s: str) -> str:
    return html.escape(str(s), quote=False).replace("\n", "<br>")


def fonts_css() -> str:
    out = []
    if ONEST.exists():
        out.append("@font-face{font-family:'Onest';font-weight:100 900;font-style:normal;"
                   f"src:url(data:font/ttf;base64,{b64(ONEST)}) format('truetype');}}")
    if ONEST_BLACK.exists():
        out.append("@font-face{font-family:'Onest Black';font-weight:900;font-style:normal;"
                   f"src:url(data:font/ttf;base64,{b64(ONEST_BLACK)}) format('truetype');}}")
    return "\n".join(out)


def _bg_css() -> str:
    return (f"radial-gradient(70% 50% at 18% 8%,rgba(77,124,255,.30) 0%,rgba(77,124,255,0) 60%),"
            f"radial-gradient(75% 55% at 88% 94%,rgba(230,77,255,.26) 0%,rgba(230,77,255,0) 60%),"
            f"radial-gradient(60% 40% at 90% 14%,rgba(56,225,255,.14) 0%,rgba(56,225,255,0) 55%),{BG}")


def _accentize(text: str, accent: str | None) -> str:
    if accent and accent in text:
        return esc(text).replace(esc(accent), f'<span class="acc">{esc(accent)}</span>')
    return esc(text)


def _head() -> str:
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
{FONTS}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px}}
body{{font-family:'Onest',sans-serif;color:{WHITE};overflow:hidden;background:{_bg_css()}}}
.acc{{color:{CYAN};text-shadow:0 0 22px rgba(56,225,255,.65),0 0 44px rgba(56,225,255,.35)}}
.page{{width:{W}px;height:{H}px;padding:150px 96px 130px;display:flex;flex-direction:column}}
.handle{{position:absolute;left:96px;bottom:72px;color:{MUTED};font-weight:700;font-size:32px;letter-spacing:.02em}}
.brandbar{{position:absolute;left:0;right:0;bottom:0;height:10px;
  background:linear-gradient(90deg,{BLUE},{PINK},{CYAN})}}
#fit{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0;font-size:30px}}
</style></head><body>"""


def cover_html(s: dict, handle: str) -> str:
    kicker = f'<div class="kicker">{esc(s["kicker"])}</div>' if s.get("kicker") else ""
    title = _accentize(s.get("title", ""), s.get("accent"))
    sub = f'<div class="sub">{esc(s["subtitle"])}</div>' if s.get("subtitle") else ""
    return _head() + f"""<style>
.kicker{{font-weight:800;letter-spacing:.24em;font-size:34px;text-transform:uppercase;color:{CYAN};margin-bottom:40px}}
.title{{font-family:'Onest Black','Onest';font-weight:900;font-size:118px;line-height:1.02;letter-spacing:-.02em;
  text-shadow:0 0 40px rgba(77,124,255,.35)}}
.sub{{font-size:46px;font-weight:500;color:{MUTED};margin-top:48px;line-height:1.3}}
</style>
<div class="page"><div id="fit"><div>{kicker}<div class="title">{title}</div>{sub}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def cover_photo_html(s: dict, base: Path, handle: str) -> str:
    bg = base64.b64encode((base / s["bg"]).read_bytes()).decode()
    kicker = f'<div class="kicker">{esc(s["kicker"])}</div>' if s.get("kicker") else ""
    title = _accentize(s.get("title", ""), s.get("accent"))
    sub = f'<div class="sub">{esc(s["subtitle"])}</div>' if s.get("subtitle") else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
{FONTS}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px}}
body{{font-family:'Onest',sans-serif;overflow:hidden}}
.wrap{{width:{W}px;height:{H}px;position:relative;background:url(data:image/png;base64,{bg}) center/cover no-repeat}}
.scrim{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,7,14,.15) 0%,rgba(7,7,14,.35) 40%,rgba(7,7,14,.92) 100%)}}
.glow{{position:absolute;inset:0;background:radial-gradient(60% 40% at 15% 90%,rgba(77,124,255,.28),rgba(77,124,255,0) 60%),radial-gradient(60% 40% at 90% 95%,rgba(230,77,255,.24),rgba(230,77,255,0) 60%)}}
.txt{{position:absolute;left:96px;right:96px;bottom:150px;color:{WHITE}}}
.kicker{{font-weight:800;letter-spacing:.24em;font-size:32px;text-transform:uppercase;color:{CYAN};margin-bottom:30px;text-shadow:0 0 20px rgba(56,225,255,.6)}}
.title{{font-family:'Onest Black','Onest';font-weight:900;font-size:108px;line-height:1.02;letter-spacing:-.02em;text-shadow:0 6px 40px rgba(0,0,0,.6)}}
.acc{{color:{CYAN};text-shadow:0 0 24px rgba(56,225,255,.7)}}
.sub{{font-size:42px;font-weight:500;color:#D7DBF5;margin-top:34px;line-height:1.3}}
.handle{{position:absolute;left:96px;bottom:72px;color:#C7CBEC;font-weight:700;font-size:32px}}
.brandbar{{position:absolute;left:0;right:0;bottom:0;height:10px;background:linear-gradient(90deg,{BLUE},{PINK},{CYAN})}}
</style></head><body><div class="wrap"><div class="scrim"></div><div class="glow"></div>
<div class="txt">{kicker}<div class="title">{title}</div>{sub}</div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div></body></html>"""


def story_html(s: dict, handle: str) -> str:
    step = f'<div class="step">{esc(s["step"])}</div>' if s.get("step") else ""
    heading = _accentize(s.get("heading", ""), s.get("accent"))
    body = f'<div class="body">{esc(s["body"])}</div>' if s.get("body") else ""
    return _head() + f"""<style>
.step{{font-family:'Onest Black','Onest';font-weight:900;font-size:160px;line-height:.9;color:transparent;
  -webkit-text-stroke:3px {BLUE};opacity:.55;margin-bottom:18px;text-shadow:0 0 40px rgba(77,124,255,.25)}}
.heading{{font-family:'Onest Black','Onest';font-weight:900;font-size:86px;line-height:1.05;letter-spacing:-.01em}}
.body{{font-size:48px;font-weight:500;color:{MUTED};margin-top:40px;line-height:1.34}}
</style>
<div class="page"><div id="fit"><div>{step}<div class="heading">{heading}</div>{body}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def case_html(s: dict, handle: str) -> str:
    niche = f'<div class="niche">{esc(s["niche"])}</div>' if s.get("niche") else ""
    name = f'<div class="name">{esc(s["name"])}</div>' if s.get("name") else ""
    note = f'<span class="note">{esc(s["note"])}</span>' if s.get("note") else ""
    quote = f'<div class="quote">«{esc(s["quote"])}»</div>' if s.get("quote") else ""
    return _head() + f"""<style>
.niche{{display:inline-block;align-self:flex-start;font-weight:800;font-size:34px;color:{CYAN};
  border:2px solid rgba(56,225,255,.45);border-radius:999px;padding:14px 30px;margin-bottom:40px;
  box-shadow:0 0 26px rgba(56,225,255,.25)}}
.name{{font-family:'Onest Black','Onest';font-weight:900;font-size:74px;line-height:1.04;margin-bottom:54px}}
.card{{background:rgba(255,255,255,.05);border:1px solid rgba(120,150,255,.28);border-radius:34px;
  padding:54px 44px;display:flex;align-items:center;justify-content:space-between;
  box-shadow:0 0 60px rgba(77,124,255,.18) inset}}
.col{{display:flex;flex-direction:column;gap:12px;text-align:center;flex:1}}
.lbl{{font-weight:800;font-size:32px;letter-spacing:.12em;color:{MUTED};text-transform:uppercase}}
.num{{font-family:'Onest Black','Onest';font-weight:900;font-size:96px;line-height:1;color:{WHITE}}}
.col.after .num{{color:{CYAN};text-shadow:0 0 30px rgba(56,225,255,.7),0 0 60px rgba(56,225,255,.35)}}
.arrow{{font-family:'Onest Black','Onest';font-weight:900;font-size:90px;color:{PINK};padding:0 18px;
  text-shadow:0 0 28px rgba(230,77,255,.7)}}
.note{{display:inline-block;margin-top:30px;align-self:flex-start;font-weight:800;font-size:40px;color:{PINK};
  text-shadow:0 0 22px rgba(230,77,255,.5)}}
.quote{{font-size:42px;font-style:italic;font-weight:500;color:#CFD4F4;margin-top:42px;line-height:1.34}}
</style>
<div class="page"><div id="fit"><div>{niche}{name}
<div class="card"><div class="col before"><div class="lbl">было</div><div class="num">{esc(s.get("before",""))}</div></div>
<div class="arrow">→</div><div class="col after"><div class="lbl">стало</div><div class="num">{esc(s.get("after",""))}</div></div></div>
{note}{quote}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def review_html(s: dict, handle: str) -> str:
    name = esc(s.get("name", ""))
    role = f'<div class="role">{esc(s["role"])}</div>' if s.get("role") else ""
    result = f'<div class="res">{esc(s["result"])}</div>' if s.get("result") else ""
    return _head() + f"""<style>
.quote{{font-family:'Onest','sans-serif';font-weight:600;font-size:54px;line-height:1.34;color:{WHITE};font-style:italic}}
.qmark{{font-family:'Onest Black','Onest';font-weight:900;font-size:150px;line-height:.6;color:{CYAN};
  text-shadow:0 0 30px rgba(56,225,255,.6);margin-bottom:6px}}
.who{{margin-top:54px;display:flex;align-items:center;gap:22px}}
.av{{width:84px;height:84px;border-radius:50%;flex:none;
  background:linear-gradient(135deg,{BLUE},{PINK});box-shadow:0 0 34px rgba(230,77,255,.4)}}
.nm{{font-family:'Onest Black','Onest';font-weight:900;font-size:46px;line-height:1.05}}
.role{{font-size:34px;color:{MUTED};font-weight:600;margin-top:4px}}
.res{{display:inline-block;align-self:flex-start;margin-top:34px;font-weight:800;font-size:38px;color:{CYAN};
  border:2px solid rgba(56,225,255,.4);border-radius:999px;padding:14px 30px;box-shadow:0 0 24px rgba(56,225,255,.22)}}
</style>
<div class="page"><div id="fit"><div><div class="qmark">«</div>
<div class="quote">{esc(s.get("quote",""))}</div>{result}
<div class="who"><div class="av"></div><div><div class="nm">{name}</div>{role}</div></div></div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def review_shot_html(s: dict, base: Path, handle: str) -> str:
    shot = base64.b64encode((base / s["shot"]).read_bytes()).decode()
    name = esc(s.get("name", ""))
    role = f'<span class="role">{esc(s["role"])}</span>' if s.get("role") else ""
    result = f'<div class="res">{esc(s["result"])}</div>' if s.get("result") else ""
    quote = f'<div class="quote">«{esc(s["quote"])}»</div>' if s.get("quote") else ""
    return _head() + f"""<style>
.page{{padding:120px 80px 130px}}
#fit{{justify-content:flex-start;gap:34px}}
.quote{{font-family:'Onest','sans-serif';font-weight:600;font-size:42px;line-height:1.3;color:{WHITE};font-style:italic}}
.frame{{align-self:center;border-radius:38px;padding:14px;background:rgba(255,255,255,.04);
  border:2px solid rgba(120,150,255,.35);box-shadow:0 0 70px rgba(77,124,255,.30)}}
.frame img{{display:block;max-height:1000px;max-width:620px;width:auto;border-radius:26px}}
.who{{display:flex;align-items:center;gap:18px;margin-top:6px}}
.av{{width:74px;height:74px;border-radius:50%;flex:none;background:linear-gradient(135deg,{BLUE},{PINK});box-shadow:0 0 30px rgba(230,77,255,.4)}}
.nm{{font-family:'Onest Black','Onest';font-weight:900;font-size:42px;line-height:1.05}}
.role{{font-size:30px;color:{MUTED};font-weight:600}}
.res{{display:inline-block;font-weight:800;font-size:34px;color:{CYAN};border:2px solid rgba(56,225,255,.4);
  border-radius:999px;padding:10px 26px;box-shadow:0 0 22px rgba(56,225,255,.22)}}
</style>
<div class="page"><div id="fit">{quote}
<div class="frame"><img src="data:image/jpeg;base64,{shot}"></div>
{result}<div class="who"><div class="av"></div><div><div class="nm">{name}</div>{role}</div></div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def review_chatcard_html(s: dict, base: Path, handle: str) -> str:
    name = esc(s.get("name", ""))
    role = f'<span class="role"> · {esc(s["role"])}</span>' if s.get("role") else ""
    time = esc(s.get("time", ""))
    initial = esc((s.get("name", "?") or "?").strip()[:1].upper())
    shot_html = ""
    if s.get("shot"):
        shot = base64.b64encode((base / s["shot"]).read_bytes()).decode()
        shot_html = f'<div class="frame"><img src="data:image/jpeg;base64,{shot}"></div>'
    result = f'<div class="res">{esc(s["result"])}</div>' if s.get("result") else ""
    return _head() + f"""<style>
.page{{padding:120px 76px 130px}}
#fit{{justify-content:center;gap:30px}}
.bubble{{background:#16182A;border:1px solid rgba(120,150,255,.28);border-radius:30px;border-top-left-radius:8px;
  padding:34px 38px;box-shadow:0 0 50px rgba(77,124,255,.20)}}
.bhead{{display:flex;align-items:center;gap:18px;margin-bottom:20px}}
.av{{width:72px;height:72px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
  font-family:'Onest Black','Onest';font-weight:900;font-size:36px;color:#fff;
  background:linear-gradient(135deg,{BLUE},{PINK});box-shadow:0 0 26px rgba(230,77,255,.4)}}
.nm{{font-family:'Onest Black','Onest';font-weight:900;font-size:40px;color:{CYAN}}}
.role{{font-size:30px;color:{MUTED};font-weight:600}}
.msg{{font-size:42px;line-height:1.36;color:{WHITE};font-weight:500}}
.time{{text-align:right;font-size:26px;color:{MUTED};margin-top:18px}}
.frame{{align-self:center;border-radius:34px;padding:12px;background:rgba(255,255,255,.04);
  border:2px solid rgba(120,150,255,.30);box-shadow:0 0 60px rgba(77,124,255,.26)}}
.frame img{{display:block;max-height:760px;max-width:560px;width:auto;border-radius:22px}}
.res{{align-self:center;font-weight:800;font-size:38px;color:{CYAN};border:2px solid rgba(56,225,255,.4);
  border-radius:999px;padding:12px 30px;box-shadow:0 0 24px rgba(56,225,255,.22)}}
</style>
<div class="page"><div id="fit"><div class="bubble"><div class="bhead"><div class="av">{initial}</div>
<div><span class="nm">{name}</span>{role}</div></div>
<div class="msg">{esc(s.get("text",""))}</div><div class="time">{time}</div></div>
{shot_html}{result}</div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def cover_round_html(s: dict, handle: str) -> str:
    # Big centered neon emblem optimized for IG circular highlight-cover crop (center zone).
    emblem = esc(s.get("emblem", "★"))
    label = f'<div class="lbl">{esc(s["label"])}</div>' if s.get("label") else ""
    c1 = s.get("c1", BLUE); c2 = s.get("c2", PINK)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
{FONTS}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px}}
body{{font-family:'Onest','Apple Color Emoji','Segoe UI Emoji',sans-serif;overflow:hidden;
  background:radial-gradient(60% 40% at 50% 50%,rgba(77,124,255,.30),rgba(7,7,14,0) 70%),{BG};
  display:flex;align-items:center;justify-content:center}}
.disc{{width:560px;height:560px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:radial-gradient(circle at 50% 38%,rgba(77,124,255,.30),rgba(230,77,255,.16) 60%,rgba(7,7,14,.2) 100%);
  border:6px solid rgba(56,225,255,.55);
  box-shadow:0 0 90px rgba(56,225,255,.45),0 0 160px rgba(230,77,255,.30),inset 0 0 80px rgba(77,124,255,.25)}}
.em{{font-size:300px;line-height:1;color:{CYAN};
  text-shadow:0 0 40px rgba(56,225,255,.8),0 0 90px rgba(230,77,255,.5)}}
.lbl{{position:absolute;bottom:120px;left:0;right:0;text-align:center;
  font-family:'Onest Black','Onest';font-weight:900;font-size:60px;color:{WHITE};letter-spacing:.04em;
  text-shadow:0 0 30px rgba(77,124,255,.5)}}
</style></head><body>
<div class="disc"><div class="em">{emblem}</div></div>{label}</body></html>"""


def cover_icon_html(s: dict, handle: str) -> str:
    emblem = esc(s.get("emblem", "★★★★★"))
    word = esc(s.get("word", ""))
    sub = f'<div class="csub">{esc(s["sub"])}</div>' if s.get("sub") else ""
    return _head() + f"""<style>
.page{{justify-content:center;align-items:center;text-align:center}}
#fit{{align-items:center;text-align:center}}
.ring{{width:430px;height:430px;border-radius:50%;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:18px;margin:0 auto 30px;
  border:4px solid rgba(56,225,255,.5);
  background:radial-gradient(circle at 50% 38%,rgba(77,124,255,.30),rgba(7,7,14,0) 70%);
  box-shadow:0 0 70px rgba(56,225,255,.35),inset 0 0 60px rgba(230,77,255,.20)}}
.emblem{{font-size:64px;color:{CYAN};letter-spacing:.08em;text-shadow:0 0 26px rgba(56,225,255,.7)}}
.word{{font-family:'Onest Black','Onest';font-weight:900;font-size:96px;line-height:1;
  color:{WHITE};text-shadow:0 0 40px rgba(77,124,255,.5)}}
.csub{{font-size:40px;color:{MUTED};font-weight:500;margin-top:30px;max-width:760px}}
</style>
<div class="page"><div id="fit"><div><div class="ring"><div class="emblem">{emblem}</div><div class="word">{word}</div></div>{sub}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def cta_html(s: dict, handle: str) -> str:
    title = _accentize(s.get("title", ""), s.get("accent"))
    text = f'<div class="text">{esc(s["text"])}</div>' if s.get("text") else ""
    btn = f'<div class="btn">{esc(s["button"])}</div>' if s.get("button") else ""
    return _head() + f"""<style>
.title{{font-family:'Onest Black','Onest';font-weight:900;font-size:92px;line-height:1.04;letter-spacing:-.01em}}
.text{{font-size:48px;font-weight:500;color:{MUTED};margin-top:40px;line-height:1.34}}
.btn{{align-self:flex-start;margin-top:64px;background:linear-gradient(90deg,{BLUE},{PINK});color:#fff;
  font-weight:800;font-size:46px;padding:34px 58px;border-radius:22px;box-shadow:0 0 50px rgba(230,77,255,.45)}}
</style>
<div class="page"><div id="fit"><div><div class="title">{title}</div>{text}{btn}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


def list_html(s: dict, handle: str) -> str:
    kicker = f'<div class="kicker">{esc(s["kicker"])}</div>' if s.get("kicker") else ""
    heading = _accentize(s.get("heading", ""), s.get("accent"))
    lead = f'<div class="lead">{esc(s["lead"])}</div>' if s.get("lead") else ""
    kind = s.get("kind", "dot")
    rows = []
    for i, it in enumerate(s.get("items", []), 1):
        if kind == "num":
            mk = f'<div class="mk num">{i}</div>'
        elif kind == "cross":
            mk = '<div class="mk cross">&#215;</div>'
        else:
            mk = '<div class="mk dot"></div>'
        rows.append(f'<div class="item">{mk}<div class="itext">{esc(it)}</div></div>')
    items = "".join(rows)
    return _head() + f"""<style>
.kicker{{font-weight:800;letter-spacing:.22em;font-size:30px;text-transform:uppercase;color:{CYAN};margin-bottom:26px}}
.heading{{font-family:'Onest Black','Onest';font-weight:900;font-size:78px;line-height:1.05;letter-spacing:-.01em}}
.lead{{font-size:42px;font-weight:500;color:#CFD4F4;margin-top:30px;line-height:1.3}}
.item{{display:flex;gap:28px;align-items:flex-start;margin-top:34px}}
.mk{{flex:none}}
.mk.num{{width:66px;height:66px;border-radius:18px;border:2px solid rgba(56,225,255,.55);
  display:flex;align-items:center;justify-content:center;font-family:'Onest Black','Onest';font-weight:900;
  font-size:38px;color:{CYAN};box-shadow:0 0 22px rgba(56,225,255,.30)}}
.mk.cross{{width:60px;height:60px;border-radius:16px;background:rgba(230,77,120,.18);
  border:2px solid rgba(255,90,120,.6);display:flex;align-items:center;justify-content:center;
  font-family:'Onest Black','Onest';font-weight:900;font-size:42px;color:#FF6A86;line-height:1}}
.mk.dot{{width:24px;height:24px;border-radius:50%;margin-top:18px;
  background:linear-gradient(135deg,{BLUE},{PINK});box-shadow:0 0 18px rgba(230,77,255,.55)}}
.itext{{font-size:44px;font-weight:500;color:{WHITE};line-height:1.32}}
</style>
<div class="page"><div id="fit"><div>{kicker}<div class="heading">{heading}</div>{lead}{items}</div></div>
<div class="handle">{esc(handle)}</div><div class="brandbar"></div></div>{FIT_JS}</body></html>"""


FIT_JS = """<script>(function(){
  var fit=document.getElementById('fit'); if(!fit)return;
  var avail=fit.clientHeight, availW=fit.clientWidth;
  function over(px){ fit.style.fontSize=px+'px'; return fit.scrollHeight>avail+1||fit.scrollWidth>availW+1; }
  var lo=12, hi=34;
  if(over(hi)){ for(var i=0;i<26;i++){ var mid=(lo+hi)/2; if(over(mid)) hi=mid; else lo=mid; } fit.style.fontSize=lo+'px'; }
  else { fit.style.fontSize=hi+'px'; }
  document.documentElement.setAttribute('data-fit','done');
})();</script>"""

FONTS = ""


def render(spec: dict, out_dir: Path, base: Path, scale: int) -> list[Path]:
    global FONTS
    FONTS = fonts_css()
    chrome = next((b for b in ("google-chrome-stable", "google-chrome", "chromium")
                   if subprocess.run(["bash", "-lc", f"command -v {b}"], capture_output=True).returncode == 0), None)
    if not chrome:
        sys.exit("ERROR: no chrome found")
    out_dir = out_dir.resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    handle = spec.get("handle", "@your_account"); outs = []
    for i, s in enumerate(spec.get("slides", []), 1):
        t = s.get("type")
        h = s.get("handle", handle)
        if t == "cover":
            doc = cover_html(s, h)
        elif t == "cover_photo":
            doc = cover_photo_html(s, base, h)
        elif t == "story":
            doc = story_html(s, h)
        elif t == "case":
            doc = case_html(s, h)
        elif t == "review":
            doc = review_html(s, h)
        elif t == "review_shot":
            doc = review_shot_html(s, base, h)
        elif t == "review_chatcard":
            doc = review_chatcard_html(s, base, h)
        elif t == "cover_icon":
            doc = cover_icon_html(s, h)
        elif t == "cover_round":
            doc = cover_round_html(s, h)
        elif t == "list":
            doc = list_html(s, h)
        elif t == "cta":
            doc = cta_html(s, h)
        else:
            sys.exit(f"unknown slide type: {t}")
        htmlf = (out_dir / f"_s{i:02d}.html"); htmlf.write_text(doc, encoding="utf-8")
        png = out_dir / f"slide_{i:02d}.png"
        cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
               f"--force-device-scale-factor={scale}", f"--screenshot={png}",
               f"--window-size={W},{H}", f"file://{htmlf}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if not png.exists():
            sys.exit(f"render failed slide {i}: {r.stderr[:400]}")
        htmlf.unlink(missing_ok=True); print(f"slide {i} ({t}) ok", flush=True); outs.append(png)
    return outs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out_dir")
    ap.add_argument("--scale", type=int, default=1, choices=(1, 2, 3))
    a = ap.parse_args()
    specp = Path(a.spec); spec = json.loads(specp.read_text(encoding="utf-8"))
    outs = render(spec, Path(a.out_dir), specp.parent, a.scale)
    print(f"done: {len(outs)} slides")


if __name__ == "__main__":
    main()
