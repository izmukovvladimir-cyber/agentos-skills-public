#!/usr/bin/env python3
"""Knowledge-base builder: renders a static expert knowledge base from registry.json + content/*.json.

Nothing here is client-specific. Everything the site says about its owner (name, logo,
palette, cover images, headline, about page, next-step CTA) lives in the `site` block of
registry.json, so the same engine builds any client's base. Fill the config, drop the
material into content/, run this file.

Single source of truth = registry.json. Each published guide becomes /guide-<slug>/index.html
on one shared template, grouped by category, with a top nav and an /about/ page.
URLs are contract: /guide-<slug>/, /about/, / — once bot funnels point at a page, its slug
must never change, or every live funnel breaks silently.

Visual system (approved reference base): dark ink hero card with a cover
image, category tabs on an even auto-fit grid, cards, sticky side menu on long reads.
Light and dark themes are both first-class: the theme resolves on :root via data-theme
(prefers-color-scheme by default, localStorage once the reader picks).

Guides with TOC_MIN_SECTIONS+ sections get the sticky «На странице» menu on the right
(scroll-spy via IntersectionObserver, hidden under 1100px). Shorter guides keep the bare
reading column at the same measure.

Palette: `site.theme` picks a preset, `site.colors` overrides any token (client brand
colors go here). CLI override: `python3 build.py <theme>`.
Run selfcheck.py after building; build.py refuses to emit on a long dash (hard rule).
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
# what a guide slug may contain: it is a directory name and a URL segment at the same time.
# '.' and '..' are excluded separately below, they match the character set but are not names.
SLUG_RE = re.compile(r"[a-zA-Z0-9._-]+")
CONTENT = ROOT / "content"
DASH_RE = re.compile(r"[—–]")
TOC_MIN_SECTIONS = 4  # guides with fewer sections render as a bare reading column

FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&family=Inter+Tight:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500;600;700"
    "&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&display=swap"
)

# ---- themes: only the brand accent/ink/bg tokens change, layout is shared ----
# Presets to start from. A client with its own brand colors does not need a new preset here:
# put the hex values in registry.json → site.colors, they override the preset token by token.
#   accent      = brand color (buttons, marks, accents)
#   accent_ink  = text ON the accent, must stay readable (dark text on a light accent)
#   ink         = the dark card color (hero, footer), also the outline color
#   bg_light    = page background in the light theme
#   bg_dark     = page background in the dark theme
THEMES = {
    "lime": {"accent": "#bff03a", "ink": "#16180f", "bg_light": "#f6f4ec", "bg_dark": "#14150f",
             "accent_ink": "#16180f"},
    "sand": {"accent": "#d59468", "ink": "#2b261f", "bg_light": "#f1ece1", "bg_dark": "#1c1813",
             "accent_ink": "#2b261f"},
    "midnight": {"accent": "#63e0a6", "ink": "#0f1115", "bg_light": "#eef1f4", "bg_dark": "#0f1115",
                 "accent_ink": "#0c0e12"},
    "royal": {"accent": "#7d93ff", "ink": "#16203a", "bg_light": "#f4f1e9", "bg_dark": "#111829",
              "accent_ink": "#16203a"},
}
THEME_TOKENS = ("accent", "accent_ink", "ink", "bg_light", "bg_dark")

THEME = "lime"  # set by main()
COLORS: dict[str, str] = {}  # resolved palette, set by main()
SITE_CFG: dict = {}  # the registry `site` block, set by main() (CSS needs the cover images)


def resolve_colors(theme: str, overrides: dict | None) -> dict[str, str]:
    """Preset first, client brand colors on top. Unknown keys are a typo, not a feature."""
    palette = dict(THEMES[theme])
    for key, value in (overrides or {}).items():
        if key not in THEME_TOKENS:
            raise SystemExit(f"site.colors: unknown token {key!r}, allowed: {list(THEME_TOKENS)}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(value)):
            raise SystemExit(f"site.colors.{key}: expected a #rrggbb hex, got {value!r}")
        palette[key] = value
    return palette


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def cover_css(site: dict) -> str:
    """Cover images are optional, so they live outside BASE_CSS.

    site.hero_image  — wide cover for the index hero (dark art, the headline sits on its left).
    site.about.image — portrait for /about/. It takes the right half of the card, the copy the
    left, and a fade stitches them: the copy must never land on the face. Under 760px they stack.
    Without an image the hero keeps the dot-grid + accent bloom from BASE_CSS, which is a valid
    look on day one, so a base can ship before the photos exist.
    """
    css = []
    hero_img = site.get("hero_image")
    if hero_img:
        # scoped to the index hero: /about/ decides on its own, it may still be running the
        # textured fallback while the index already has a cover
        css.append(
            f".hero:not(.about-hero) .art{{background:var(--ink) url('{hero_img}') center right/cover no-repeat}}"
            ".hero:not(.about-hero) .grid{display:none}.hero:not(.about-hero) .glow{display:none}"
            "@media(max-width:900px){.hero:not(.about-hero) .art{background-position:72% center}}"
        )
    about_img = (site.get("about") or {}).get("image")
    if about_img:
        css.append(
            ".hero.about-hero{min-height:420px}"
            f".hero.about-hero .art{{left:auto;right:0;width:50%;background:url('{about_img}') right center/cover no-repeat;"
            "-webkit-mask-image:linear-gradient(90deg,transparent 0%,#000 44%);"
            "mask-image:linear-gradient(90deg,transparent 0%,#000 44%)}"
            ".hero.about-hero .txt{max-width:50%;background:none}"
            ".hero.about-hero h1{font-size:32px;max-width:12ch}"
            ".hero.about-hero .desc{font-size:15px;max-width:30ch}"
            "@media(max-width:760px){"
            ".hero.about-hero{display:block;padding-top:210px}"
            ".hero.about-hero .art{left:0;right:0;width:100%;height:230px;background-position:center 22%;"
            "-webkit-mask-image:linear-gradient(180deg,#000 62%,transparent 100%);"
            "mask-image:linear-gradient(180deg,#000 62%,transparent 100%)}"
            ".hero.about-hero .txt{max-width:100%;padding-top:6px}"
            ".hero.about-hero h1{font-size:27px;max-width:none}"
            ".hero.about-hero .desc{max-width:none}"
            "}"
        )
    return "".join(css)


def no_dash(label: str, text: str) -> None:
    if DASH_RE.search(text):
        raise SystemExit(f"DASH ERROR in {label}: {text!r}")


_TR = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "abvgdeejzijklmnoprstufhccss y eua")


def cat_id(category: str) -> str:
    return "cat-" + re.sub(r"[^a-z0-9]+", "-", category.lower().translate(_TR)).strip("-")


def root_css(theme: str) -> str:
    """Brand tokens + theme resolution. Light is the default, dark overrides on :root[data-theme=dark];
    prefers-color-scheme covers the no-JS first paint."""
    t = COLORS or THEMES[theme]
    return f"""
:root{{
--accent:{t['accent']};--accent-ink:{t['accent_ink']};--ink:{t['ink']};--offwhite:#ffffff;
--bg-light:{t['bg_light']};--bg-dark:{t['bg_dark']};
--bg:var(--bg-light);--text:#1c1c1f;--muted:#6b7280;--surface:#ffffff;
--card-bg:rgba(0,0,0,.035);--card-border:rgba(0,0,0,.10);--hair:rgba(0,0,0,.08);
--dot:rgba(0,0,0,.05);--shadow:0 10px 30px rgba(0,0,0,.10);
--font-display:'Inter Tight',system-ui,sans-serif;
--font-body:'Inter',system-ui,-apple-system,sans-serif;
--font-mono:'JetBrains Mono',ui-monospace,monospace;
--font-serif:'PT Serif',Georgia,serif;
}}
:root[data-theme=dark]{{
--bg:var(--bg-dark);--text:#f4f4f5;--muted:#9ca3af;--surface:#1a1a1c;
--card-bg:rgba(255,255,255,.05);--card-border:rgba(255,255,255,.12);--hair:rgba(255,255,255,.10);
--dot:rgba(255,255,255,.05);--shadow:0 10px 30px rgba(0,0,0,.45);
}}
@media(prefers-color-scheme:dark){{
:root:not([data-theme=light]){{
--bg:var(--bg-dark);--text:#f4f4f5;--muted:#9ca3af;--surface:#1a1a1c;
--card-bg:rgba(255,255,255,.05);--card-border:rgba(255,255,255,.12);--hair:rgba(255,255,255,.10);
--dot:rgba(255,255,255,.05);--shadow:0 10px 30px rgba(0,0,0,.45);
}}
}}
"""


BASE_CSS = """
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg)}
body{color:var(--text);font-family:var(--font-body);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--font-mono)}
/* ============ header ============ */
.hd{position:sticky;top:0;z-index:50;background:var(--bg);border-bottom:1px solid var(--hair)}
.hd-in{height:66px;max-width:1340px;margin:0 auto;padding:0 44px;display:flex;align-items:center;gap:24px}
.logo{font-family:var(--font-display);font-weight:700;font-size:19px;letter-spacing:-.04em;text-transform:uppercase;color:var(--text);display:inline-flex;align-items:center;flex:none;white-space:nowrap}
.logo .sq{width:8px;height:8px;background:var(--accent);border:1.5px solid var(--ink);display:inline-block;margin:0 5px 0 3px}
:root[data-theme=dark] .logo .sq{border-color:rgba(255,255,255,.7)}
.hd-nav{display:flex;align-items:center;gap:22px;font-size:14px;flex:none}
.hd-nav a{color:var(--muted);position:relative;padding:4px 1px;transition:color .15s;white-space:nowrap}
.hd-nav a:hover{color:var(--text)}
.hd-nav a.cur{color:var(--text);font-weight:600}
.hd-nav a.cur::after{content:'';position:absolute;left:0;right:0;bottom:-3px;height:1.5px;background:var(--text);opacity:.8}
.sp{flex:1}
.tools{display:flex;align-items:center;gap:10px;flex:none}
.tgl{width:34px;height:34px;border:1px solid var(--hair);border-radius:9px;display:grid;place-items:center;color:var(--text);background:none;cursor:pointer;padding:0;transition:border-color .15s}
.tgl:hover{border-color:var(--muted)}
.tgl svg{display:block;width:15px;height:15px}
.tgl .ic-sun{display:none}
:root[data-theme=dark] .tgl .ic-sun{display:block}
:root[data-theme=dark] .tgl .ic-moon{display:none}
.hd-btn{font-family:var(--font-display);font-size:14px;font-weight:600;padding:10px 17px;border-radius:999px;display:inline-flex;align-items:center;gap:8px;white-space:nowrap;background:var(--accent);color:var(--accent-ink);border:1.5px solid var(--ink);transition:transform .12s;flex:none}
.hd-btn:hover{transform:translateY(-1px)}
.hd-btn .ar{transition:transform .15s}
.hd-btn:hover .ar{transform:translateX(3px)}
:root[data-theme=dark] .hd-btn{border-color:var(--accent)}
/* ============ shell ============ */
.wrap{max-width:1340px;margin:0 auto;padding:0 44px 60px}
.eyebrow{font-family:var(--font-mono);font-size:10.5px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;display:inline-flex;align-items:center;gap:8px;color:var(--muted)}
.eyebrow .dot{width:7px;height:7px;background:var(--accent);outline:1px solid var(--ink);display:inline-block;flex:none}
:root[data-theme=dark] .eyebrow .dot{outline-color:rgba(255,255,255,.35)}
/* ============ hero ============ */
.hero{margin:26px 0 6px;border-radius:18px;overflow:hidden;background:var(--ink);color:#f5f5f0;position:relative;min-height:340px;display:flex}
.hero .art{position:absolute;inset:0;background:var(--ink)}
/* the dot-grid and the accent bloom are the fallback look while there is no cover image yet;
   cover_css() turns them off as soon as site.hero_image is set (two of each only muddies it) */
.hero .grid{position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.09) 1px,transparent 1px);background-size:11px 11px}
.hero .glow{position:absolute;right:-90px;top:-90px;width:420px;height:420px;border-radius:50%;background:var(--accent);filter:blur(120px);opacity:.28}
/* scrim keeps the copy on dark whatever the glow does behind it (on narrow screens the
   glow otherwise floods the whole card and the title lands on bright lime) */
.hero .txt{position:relative;z-index:2;padding:44px 44px 38px;display:flex;flex-direction:column;max-width:760px;
background:linear-gradient(100deg,color-mix(in srgb,var(--ink) 88%,transparent) 0%,color-mix(in srgb,var(--ink) 55%,transparent) 62%,transparent 100%)}
.hero .eyebrow{color:var(--accent)}
/* hero is always the dark ink card, so its title must not follow --text (black on black in light theme) */
.hero h1{font-family:var(--font-display);font-size:42px;font-weight:700;letter-spacing:-.025em;line-height:1.08;margin:18px 0 14px;max-width:17ch;color:#f5f5f0}
.hero .desc{font-size:16px;line-height:1.55;color:rgba(245,245,240,.72);max-width:52ch;margin:0}
.hero .read{margin-top:auto;padding-top:30px;display:inline-flex;align-items:center;gap:14px;color:#fbfbf8;cursor:pointer;align-self:flex-start}
.hero .read .circ{width:46px;height:46px;border-radius:50%;background:var(--accent);display:grid;place-items:center;color:var(--accent-ink);flex:none;transition:transform .15s}
.hero .read:hover .circ{transform:translateX(3px)}
.hero .read .lbl{font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase}
/* ============ tabs ============ */
/* grid, not flex-wrap: inline chips left a ragged right edge and one orphan on the
   second row. auto-fit + minmax(240px) resolves to exactly 5 columns on a 1440 shell
   (avail 1352px: 6 cols would need 240*6+8*5=1480), so 10 chips read as a deliberate
   5+5 block. Narrow screens re-solve to 4/3/2 columns via the overrides below. */
.tabs{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:34px 0 0;padding-top:24px;border-top:1px solid var(--hair)}
.tab{font-size:13px;font-weight:500;padding:9px 14px;border-radius:999px;border:1px solid var(--card-border);color:var(--muted);background:none;cursor:pointer;font-family:inherit;white-space:nowrap;transition:border-color .15s,color .15s;display:flex;align-items:center;justify-content:center;text-align:center;width:100%;min-width:0}
.tab:hover{color:var(--text);border-color:var(--muted)}
.tab.on{background:var(--accent);color:var(--accent-ink);border-color:var(--ink);font-weight:600}
:root[data-theme=dark] .tab.on{border-color:var(--accent)}
.count{font-family:var(--font-mono);font-size:12px;color:var(--muted);margin:18px 0 14px}
/* ============ cards ============ */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:16px}
.card{border:1px solid var(--card-border);border-radius:14px;padding:18px;background:var(--card-bg);display:flex;flex-direction:column;gap:9px;min-height:158px;transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--ink);transform:translateY(-2px)}
:root[data-theme=dark] .card:hover{border-color:var(--accent)}
.card .tag{font-family:var(--font-mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px}
.card .tag .d{width:7px;height:7px;background:var(--accent);outline:1px solid var(--ink);display:inline-block;flex:none}
:root[data-theme=dark] .card .tag .d{outline-color:rgba(255,255,255,.35)}
.card .ct{font-family:var(--font-display);font-size:17px;font-weight:600;letter-spacing:-.01em;line-height:1.25;color:var(--text)}
.card .cd{font-size:13.5px;color:var(--muted);line-height:1.5;flex:1;margin:0}
.card .cm{font-family:var(--font-mono);font-size:10.5px;color:var(--muted)}
.empty{font-family:var(--font-display);font-size:17px;font-weight:600;color:var(--muted);padding:30px 0}
/* ============ article ============ */
.page{max-width:760px;margin:0 auto;padding:34px 44px 60px}
.pcol{min-width:0}
/* ============ toc: long guides only (4+ sections), shell adds .has-toc ============ */
/* the reading column keeps the exact measure of a short guide (672px = 760 minus the
   44px gutters), the menu hangs to its right and the pair is centered together, so a
   long guide reads at the same width as a short one. */
.page.has-toc{max-width:1180px;display:grid;grid-template-columns:minmax(0,672px) 200px;gap:44px;justify-content:center;align-items:start}
/* padding-top 0 so «На странице» sits on the breadcrumb line of the article column */
.toc{position:sticky;top:66px;align-self:start;max-height:calc(100vh - 96px);overflow-y:auto;font-size:12.5px;padding:0 0 24px}
.toc .h{font-family:var(--font-mono);font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:12px;padding-left:13px}
/* the marker gutter is always reserved (transparent border), so switching sections
   recolors in place instead of nudging the text. NB: .toc scrolls on the y axis, which
   makes the x axis a scroll box too, so a negative margin here would be clipped away. */
.toc a{display:block;color:var(--muted);padding:5px 0 5px 11px;line-height:1.4;border-left:2px solid transparent;transition:color .15s,border-color .15s}
.toc a:hover{color:var(--text)}
.toc a.on{color:var(--text);font-weight:600;border-left-color:var(--accent)}
.toc{scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.18) transparent}
.toc::-webkit-scrollbar{width:5px}
.toc::-webkit-scrollbar-track{background:transparent}
.toc::-webkit-scrollbar-thumb{background:rgba(0,0,0,.18);border-radius:10px}
:root[data-theme=dark] .toc{scrollbar-color:rgba(255,255,255,.2) transparent}
:root[data-theme=dark] .toc::-webkit-scrollbar-thumb{background:rgba(255,255,255,.18)}
/* anchor lands below the sticky header, not under it */
.sec h2[id]{scroll-margin-top:86px}
/* no room for a side column: fall back to the plain reading page */
@media(max-width:1100px){
.page.has-toc{display:block;max-width:760px}
.toc{display:none}
}
.bc{font-family:var(--font-mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}
.bc a:hover{color:var(--text)}
h1{font-family:var(--font-display);font-size:36px;font-weight:700;letter-spacing:-.02em;line-height:1.12;margin:0 0 6px;color:var(--text)}
.lead{font-family:var(--font-serif);font-size:20px;line-height:1.5;font-weight:700;color:var(--text);border-left:3px solid var(--accent);padding-left:18px;margin:20px 0 22px}
.meta{font-family:var(--font-mono);font-size:11px;color:var(--muted);padding-bottom:20px;border-bottom:1px solid var(--hair);margin-bottom:26px}
.how{border:1px solid var(--card-border);border-radius:12px;background:var(--surface);padding:16px 18px;margin:22px 0;font-size:14.5px;line-height:1.56;color:var(--text)}
.p,.sec{border:1px solid var(--card-border);border-radius:14px;background:var(--card-bg);padding:20px;margin:18px 0}
.p .num{display:inline-block;font-family:var(--font-mono);font-size:11px;font-weight:700;color:var(--accent-ink);background:var(--accent);border:1px solid var(--ink);padding:3px 10px;margin-bottom:10px}
:root[data-theme=dark] .p .num{border-color:var(--accent)}
.p h2{font-family:var(--font-display);font-size:20px;margin:0 0 6px;font-weight:700;letter-spacing:-.01em}
.p .when{font-size:13.5px;color:var(--muted);margin:0 0 10px}
.sec h2{font-family:var(--font-display);font-size:22px;margin:0 0 10px;font-weight:700;letter-spacing:-.015em}
.sec h3{font-family:var(--font-display);font-size:17px;margin:18px 0 6px;font-weight:700}
.sec p,.p p{font-size:15.5px;line-height:1.66;margin:10px 0}
.sec ol,.sec ul{margin:8px 0;padding-left:22px;font-size:15.5px;line-height:1.66}
.sec li{margin:0 0 7px}
.sec li::marker{color:var(--muted)}
.lblrow{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:14px 0 6px}
.lbl{font-family:var(--font-mono);font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}
.box{font-family:var(--font-mono);font-size:12.5px;background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:14px 16px;white-space:pre-wrap;line-height:1.6;color:var(--text);overflow-x:auto}
.copy{font-family:var(--font-mono);font-size:11px;color:var(--muted);background:none;border:1px solid var(--card-border);border-radius:8px;padding:6px 11px;cursor:pointer;white-space:nowrap;transition:color .15s,border-color .15s,background .15s}
.copy:hover{color:var(--text);border-color:var(--muted)}
.copy.done{background:var(--accent);color:var(--accent-ink);border-color:var(--ink);font-weight:600}
.ex{font-size:14px;color:var(--muted);margin-top:12px}
.ex b{color:var(--text)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px}
.cardb{background:var(--surface);border:1px solid var(--card-border);border-radius:12px;padding:14px 16px}
.cardb h3{font-family:var(--font-display);margin:0 0 6px;font-size:16px}
.cardb ul,.cardb ol{padding-left:18px;margin:6px 0;font-size:14.5px}
.cardb p{font-size:14.5px;margin:6px 0}
.quote{font-family:var(--font-serif);font-style:italic;color:var(--text);opacity:.85;border-left:3px solid var(--accent);padding-left:14px;margin:14px 0;font-size:15.5px}
.note{font-size:14.5px;line-height:1.56;color:var(--text);background:var(--surface);border:1px solid var(--card-border);border-left:3px solid var(--accent);border-radius:10px;padding:12px 16px;margin:14px 0}
.linkbtn{display:inline-block;margin:12px 0 4px;font-weight:600;font-size:15px;color:var(--text);word-break:break-word;border-bottom:2px solid var(--accent)}
.linkbtn:hover{opacity:.75}
.mid{margin:26px 0;text-align:center}
.mid a{display:inline-flex;align-items:center;gap:9px;font-family:var(--font-display);font-size:14.5px;font-weight:600;padding:12px 22px;border-radius:999px;background:var(--ink);color:var(--offwhite);border:1px solid var(--ink)}
:root[data-theme=dark] .mid a{background:var(--surface);border-color:var(--accent);color:var(--text)}
/* ============ CTA ============ */
.cta{margin:40px 0 6px;padding:30px 32px;border-radius:18px;background:var(--ink);color:#f5f5f0;background-image:radial-gradient(rgba(255,255,255,.08) 1px,transparent 1px);background-size:10px 10px}
.cta .ttl{font-family:var(--font-display);font-size:25px;font-weight:700;letter-spacing:-.02em;margin:10px 0 6px}
.cta .sub{font-size:14.5px;line-height:1.55;color:rgba(245,245,240,.68);margin:0 0 20px;max-width:60ch}
.cta .eyebrow{color:var(--accent)}
.cta-btn{font-family:var(--font-display);font-size:15px;font-weight:600;padding:13px 22px;border-radius:999px;background:var(--accent);color:var(--accent-ink);border:1px solid var(--accent);display:inline-flex;align-items:center;gap:9px}
.cta-btn:hover{transform:translateY(-1px)}
/* ============ footer ============ */
.ft{border-top:1px solid var(--hair);background-image:radial-gradient(var(--dot) 1px,transparent 1px);background-size:9px 9px;padding:36px 0 26px}
.ft-in{max-width:1340px;margin:0 auto;padding:0 44px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.ft-in .logo{font-size:17px}
.ft-links{display:flex;gap:20px;font-size:13.5px;color:var(--text);opacity:.82}
.ft-links a:hover{opacity:1}
.ft-bot{max-width:1340px;margin:20px auto 0;padding:16px 44px 0;border-top:1px solid var(--hair);font-family:var(--font-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
/* ============ responsive ============ */
@media(max-width:900px){
.hd-in,.wrap,.ft-in,.ft-bot{padding-left:20px;padding-right:20px}
.page{padding:26px 20px 50px}
/* narrow: the copy sits ON the artwork (no room to dodge it), so the scrim goes near-opaque
   under the text and only clears near the bottom edge, where the art can breathe */
.hero .txt{padding:30px 24px 26px;background:linear-gradient(180deg,color-mix(in srgb,var(--ink) 94%,transparent) 0%,color-mix(in srgb,var(--ink) 88%,transparent) 68%,color-mix(in srgb,var(--ink) 60%,transparent) 100%)}
.hero .glow{width:240px;height:240px;right:-80px;top:-80px;opacity:.2}
.hero h1{font-size:29px}
.hero{min-height:0}
h1{font-size:28px}
.grid2{grid-template-columns:1fr}
.tabs{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
}
@media(max-width:700px){
.hd-in{height:60px;gap:12px}
.hd-nav{display:none}
.logo{font-size:16px}
.hd-btn{font-size:12.5px;padding:9px 13px}
.cards{grid-template-columns:1fr}
.cta{padding:24px 20px}
.cta .ttl{font-size:21px}
.lead{font-size:18px}
.ft-in{gap:14px}
}
/* phone: logo + toggle + CTA must all survive on a 390px bar, so tighten the type
   and let the CTA label clamp instead of pushing the button off the screen */
@media(max-width:460px){
.hd-in{gap:8px;padding:0 14px}
.logo{font-size:12.5px}
.hd-btn{font-size:11px;padding:8px 10px;gap:5px;min-width:0}
.hd-btn .lb{display:block;max-width:36vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tgl{width:32px;height:32px}
.wrap,.ft-in,.ft-bot{padding-left:14px;padding-right:14px}
.page{padding:22px 14px 44px}
/* phone: 2 even columns. 3 would starve the longest label ("Образ и внешность")
   and force a mid-word wrap inside the pill. */
.tabs{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px}
.tab{font-size:12.5px;padding:9px 8px}
}
"""


THEME_JS = """
<script>
(function(){
  var d=document.documentElement;
  function set(t){d.setAttribute('data-theme',t);}
  var q=(location.search.match(/[?&]theme=(dark|light)/)||[])[1];
  var s=null;try{s=localStorage.getItem('vi-theme');}catch(e){}
  set(q||s||(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
  document.addEventListener('click',function(e){
    var b=e.target.closest('.tgl');if(!b)return;
    var n=d.getAttribute('data-theme')==='dark'?'light':'dark';
    set(n);try{localStorage.setItem('vi-theme',n);}catch(err){}
  });
})();
</script>
"""

COPY_JS = """
<script>
document.querySelectorAll('.copy').forEach(function(b){
  b.addEventListener('click',function(){
    navigator.clipboard.writeText(b.getAttribute('data-text')).then(function(){
      var o=b.textContent;b.textContent='Скопировано';b.classList.add('done');
      setTimeout(function(){b.textContent=o;b.classList.remove('done');},1600);
    });
  });
});
</script>
"""

TOC_JS = """
<script>
(function(){
  var links=document.querySelectorAll('.toc a');
  var heads=Array.prototype.slice.call(document.querySelectorAll('.sec h2[id]'));
  if(!links.length||!heads.length)return;
  function mark(){
    var cur=0;
    for(var i=0;i<heads.length;i++){
      if(heads[i].getBoundingClientRect().top<=90)cur=i;else break;
    }
    links.forEach(function(a,i){a.classList.toggle('on',i===cur);});
  }
  // The observer fires exactly when a heading crosses the band under the header, which
  // is exactly when the active section can change. The class is then set from geometry
  // so a section taller than the band (most of them) never leaves the menu blank.
  if(window.IntersectionObserver){
    var io=new IntersectionObserver(mark,{rootMargin:'-86px 0px -70% 0px',threshold:0});
    heads.forEach(function(h){io.observe(h);});
  }else{
    window.addEventListener('scroll',mark,{passive:true});
  }
  mark();
  links.forEach(function(a){a.addEventListener('click',function(e){
    var h=a.getAttribute('href'),el=document.getElementById(h.slice(1));
    if(!el)return;
    e.preventDefault();
    el.scrollIntoView({behavior:'smooth',block:'start'});
    history.replaceState(null,'',h);
  });});
})();
</script>
"""

FILTER_JS = """
<script>
(function(){
  var tabs=document.querySelectorAll('.tab'),cards=document.querySelectorAll('.card'),cnt=document.getElementById('count');
  function apply(id){
    var n=0;
    cards.forEach(function(c){
      var on=(id==='all'||c.getAttribute('data-cat')===id);
      c.style.display=on?'':'none';if(on)n++;
    });
    tabs.forEach(function(t){t.classList.toggle('on',t.getAttribute('data-cat')===id);});
    if(cnt)cnt.textContent=n+' '+(n%10===1&&n%100!==11?'материал':(n%10>=2&&n%10<=4&&(n%100<10||n%100>=20)?'материала':'материалов'));
    var e=document.getElementById('empty');if(e)e.style.display=n?'none':'';
  }
  tabs.forEach(function(t){t.addEventListener('click',function(){
    var id=t.getAttribute('data-cat');
    history.replaceState(null,'',id==='all'?location.pathname:'#'+id);
    apply(id);
  });});
  var h=(location.hash||'').replace('#','');
  apply(h&&document.querySelector('.tab[data-cat="'+h+'"]')?h:'all');
  var r=document.querySelector('.hero .read');
  if(r)r.addEventListener('click',function(){
    var t=document.getElementById('list');if(t)t.scrollIntoView({behavior:'smooth',block:'start'});
  });
})();
</script>
"""

ICON_MOON = ('<svg class="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>')
ICON_SUN = ('<svg class="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/>'
            '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/></svg>')


def categories(guides):
    seen, out = set(), []
    for g in guides:
        if g.get("status") == "published" and g["category"] not in seen:
            seen.add(g["category"])
            out.append(g["category"])
    return out


def logo(site):
    """The accent square sits between the two halves of the name. site.logo overrides the split
    for a brand that is not «Имя Фамилия» (e.g. ["Живое","Дерево"] or a single word)."""
    parts = site.get("logo") or site["author"].split(" ", 1)
    if len(parts) == 1:
        return f'<a class="logo" href="/"><i class="sq"></i>{esc(parts[0])}</a>'
    return f'<a class="logo" href="/">{esc(parts[0])}<i class="sq"></i>{esc(parts[1])}</a>'


def header(site, active=None):
    # active: "home" | "about" | None (guide pages keep the nav quiet, breadcrumb carries context)
    def cls(key):
        return ' class="cur"' if active == key else ""
    btn = ""
    if site.get("upsell_url"):
        btn = (
            f'<a class="hd-btn" href="{esc(site["upsell_url"])}">'
            f'<span class="lb">{esc(site["upsell_label_top"])}</span>'
            '<span class="ar">&#8594;</span></a>'
        )
    return (
        '<header class="hd"><div class="hd-in">'
        f"{logo(site)}"
        f'<nav class="hd-nav"><a{cls("home")} href="/">Все материалы</a>'
        f'<a{cls("about")} href="/about/">{esc(site.get("about_nav", "Обо мне"))}</a></nav>'
        '<span class="sp"></span>'
        '<div class="tools">'
        f'<button class="tgl" type="button" aria-label="Сменить тему">{ICON_MOON}{ICON_SUN}</button>'
        f"{btn}"
        "</div></div></header>"
    )


def footer(site):
    # the bottom line is «кто · где его найти»: handle and channel are optional, a client
    # without them gets just the name instead of stray separators
    tail = [site["author"]]
    for key in ("handle", "channel"):
        if site.get(key):
            tail.append(site[key])
    link = ""
    if site.get("upsell_url"):
        link = f'<a href="{esc(site["upsell_url"])}">{esc(site["upsell_label_top"])}</a>'
    # a base with an analytics counter (or a form) carries a privacy policy; the footer is
    # where it lives, same as every other legal link on the web
    policy_link = '<a href="/policy/">Политика конфиденциальности</a>' if policy_required(site) else ""
    return (
        '<footer class="ft"><div class="ft-in">'
        f"{logo(site)}"
        '<span class="sp"></span>'
        '<nav class="ft-links"><a href="/">Все материалы</a>'
        f'<a href="/about/">{esc(site.get("about_nav", "Обо мне"))}</a>'
        f"{link}{policy_link}</nav>"
        "</div>"
        f'<div class="ft-bot">{esc(" · ".join(tail))}</div></footer>'
    )


def upsell(site):
    """The «next step» block. A base that sells nothing yet simply omits site.upsell_url and
    the block disappears everywhere at once."""
    if not site.get("upsell_url"):
        return ""
    return (
        '<div class="cta">'
        f'<span class="eyebrow"><i class="dot"></i>{esc(site.get("upsell_eyebrow", "Следующий шаг"))}</span>'
        f'<div class="ttl">{esc(site["upsell_title"])}</div>'
        f'<p class="sub">{esc(site["upsell_text"])}</p>'
        f'<a class="cta-btn" href="{esc(site["upsell_url"])}">{esc(site["upsell_button"])}'
        '<span class="ar">&#8594;</span></a></div>'
    )


# ---- analytics + privacy policy (both off by default) ----
# A base ships with neither. The moment site.analytics.yandex_metrika is set, the counter is
# injected into every page AND a /policy/ page becomes mandatory: Yandex Metrika writes IP and
# cookies, which Roskomnadzor treats as personal data, so a counter without a published policy
# is the exact 152-FZ gap we are closing. build_all() refuses to emit the counter without a
# valid legal block, so the two can never drift apart.
#
# Second path to the same page: site.contacts_collection. The engine still ships no forms, but a
# bot funnel that asks a person for a phone number collects personal data off-site and needs a
# published policy to link to from the consent line above that button. The page is one document
# either way: whichever paths are on describe themselves, and a path that is off says nothing.
LEGAL_REQUIRED = ("operator", "inn", "email")  # minimum for a contactable, identified operator
CONTACTS_REQUIRED = ("where", "data", "purpose")


def metrika_id(site: dict) -> str | None:
    """The Yandex Metrika counter id, or None. A non-digit value is a config typo, not a feature."""
    an = site.get("analytics")
    if an is None:
        an = {}
    if not isinstance(an, dict):
        # a present-but-malformed value ([], "", 0) is a config error, not "analytics off"
        raise SystemExit('site.analytics: expected an object, e.g. {"yandex_metrika": "12345678"}')
    # This engine injects exactly one counter and the policy page says so in plain words ("no
    # web analytics counters on the site"). A second counter set under a key we ignore would make
    # that sentence a lie while the build reports success, so an unknown key is an error here.
    unknown = sorted(set(an) - {"yandex_metrika"})
    if unknown:
        raise SystemExit(
            f"site.analytics: unknown keys {unknown}. This engine supports yandex_metrika only; "
            "another counter needs its own paragraph in the privacy policy before it can ship."
        )
    cid = str(an.get("yandex_metrika") or "").strip()
    if not cid:
        return None
    if not cid.isdigit():
        raise SystemExit(f"site.analytics.yandex_metrika: expected a numeric counter id, got {cid!r}")
    return cid


def contacts_cfg(site: dict) -> dict | None:
    """site.contacts_collection describes personal data the owner collects OUTSIDE this site (a
    bot funnel asking for a phone number). Returns the normalized block, or None when nothing is
    collected. Every field is copy that lands verbatim on the published page, so it is validated
    and dash-checked here, not at render time."""
    cc = site.get("contacts_collection")
    if cc is None:
        return None
    if not isinstance(cc, dict):
        raise SystemExit(
            "site.contacts_collection: expected an object with "
            f"{list(CONTACTS_REQUIRED)} (optional: processors, retention)"
        )
    # An unknown key is a typo, and a typo here is silent: `processor` instead of `processors`
    # would drop the list of services from a legal document while the build reports success.
    known = set(CONTACTS_REQUIRED) | {"processors", "retention"}
    unknown = sorted(set(cc) - known)
    if unknown:
        raise SystemExit(
            f"site.contacts_collection: unknown keys {unknown}. "
            f"Allowed: {sorted(known)}"
        )
    norm: dict[str, object] = {}
    for k, v in cc.items():
        if k == "processors":
            if not isinstance(v, list):
                raise SystemExit("site.contacts_collection.processors: expected a list of names")
            for x in v:
                # a dict or a number here would reach the page as its Python repr
                if not isinstance(x, str) or isinstance(x, bool):
                    raise SystemExit(
                        "site.contacts_collection.processors: expected names as strings, "
                        f"got {type(x).__name__}"
                    )
                # a blank entry would silently shrink the list, and an empty list changes the
                # legal text exactly like a missing field: the attempt to name a processor
                # would be lost without a word
                if not x.strip():
                    raise SystemExit(
                        "site.contacts_collection.processors: an empty name. Remove the entry "
                        "or name the service."
                    )
            norm[k] = [x.strip() for x in v]
            continue
        # every other field is copy for a legal page: only a real string counts. A number or a
        # boolean would render as "123" or "False" and still pass a truthiness check.
        if v is None:
            norm[k] = ""
            continue
        if not isinstance(v, str) or isinstance(v, bool):
            raise SystemExit(
                f"site.contacts_collection.{k}: expected a string, got {type(v).__name__}"
            )
        norm[k] = v.strip()
    missing = [k for k in CONTACTS_REQUIRED if not norm.get(k)]
    if missing:
        raise SystemExit(
            f"site.contacts_collection is incomplete. Missing: {missing}. "
            f"Required keys: {list(CONTACTS_REQUIRED)}; optional: processors, retention."
        )
    for k, val in norm.items():
        text = " ".join(val) if isinstance(val, list) else str(val)
        no_dash(f"contacts_collection.{k}", text)
    return norm


def policy_required(site: dict) -> bool:
    """A privacy policy is needed once the site runs analytics (a Yandex Metrika counter writes
    cookies + IP, which are personal data) or once the owner collects contact details through a
    funnel declared in site.contacts_collection. A pure static base with neither needs no policy."""
    return bool(metrika_id(site)) or contacts_cfg(site) is not None


def metrika_snippet(site: dict) -> str:
    cid = metrika_id(site)
    if not cid:
        return ""
    # standard Yandex Metrika async tag; no em/en dashes so the no-dash rule holds
    return (
        '<script type="text/javascript">'
        "(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};"
        "m[i].l=1*new Date();"
        "for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}"
        "k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,"
        "a.parentNode.insertBefore(k,a)})"
        '(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");'
        f'ym({cid},"init",{{clickmap:true,trackLinks:true,accurateTrackBounce:true}});'
        "</script>"
        f'<noscript><div><img src="https://mc.yandex.ru/watch/{cid}" '
        'style="position:absolute;left:-9999px;" alt="" /></div></noscript>'
    )


def _validate_legal(site: dict) -> dict:
    legal = site.get("legal")
    if legal is None:
        legal = {}
    if not isinstance(legal, dict):
        raise SystemExit("site.legal: expected an object with operator/inn/email")
    # Normalize every value to a trimmed string first, so validation, the no-dash rule and the
    # rendering below all operate on the same concrete text. A list or object in a legal field
    # is a config error (it would slip past a truthiness check and reach esc() as a non-string).
    norm: dict[str, str] = {}
    for k, v in legal.items():
        if isinstance(v, (dict, list)):
            raise SystemExit(f"site.legal.{k}: expected a string, got {type(v).__name__}")
        norm[k] = "" if v is None else str(v).strip()
    missing = [k for k in LEGAL_REQUIRED if not norm.get(k)]
    if missing:
        raise SystemExit(
            "site.legal is incomplete but a privacy policy is required "
            "(analytics counter and/or site.contacts_collection present). "
            f"Missing: {missing}. "
            f"Required keys: {list(LEGAL_REQUIRED)}; optional: ogrnip, address, policy_date."
        )
    # the no-dash rule covers the whole emitted page, so operator-supplied legal text must clear
    # it too, not only the static copy
    for k, val in norm.items():
        no_dash(f"legal.{k}", val)
    return norm


def render_policy(site: dict) -> str:
    """152-FZ privacy policy. Operator identity comes from site.legal; the sections describe only
    the paths that are actually on (analytics counter, contact collection through a funnel), so
    the page never claims a practice the owner does not run. The copy is deliberately dash-free
    so the no-dash rule holds on emit."""
    legal = _validate_legal(site)
    cc = contacts_cfg(site)
    has_metrika = bool(metrika_id(site))
    domain = site.get("domain", "")
    rows = [("Наименование", legal["operator"]), ("ИНН", legal["inn"])]
    if legal.get("ogrnip"):
        rows.append(("ОГРНИП", legal["ogrnip"]))
    if legal.get("address"):
        rows.append(("Адрес", legal["address"]))
    rows.append(("Электронная почта", legal["email"]))
    req = "".join(f"<li><b>{esc(k)}:</b> {esc(str(v))}</li>" for k, v in rows)
    email = esc(legal["email"])
    op = esc(legal["operator"])
    dom = esc(domain)
    edition = ""
    if legal.get("policy_date"):
        edition = f'<p class="meta">Редакция от {esc(str(legal["policy_date"]))}</p>'

    def sec(title: str, paras: list[str]) -> str:
        # a heading with nothing under it would read as a promise the page does not keep
        if not paras:
            return ""
        return f"<h2>{title}</h2>" + "".join(f"<p>{t}</p>" for t in paras)

    # Nothing below may guess HOW the owner collects contacts. site.contacts_collection.where is
    # free text: it can name a messenger, a phone call, a paper form or a CRM widget. Copy that
    # assumes a messenger reads as a practice the owner does not run, and stays silent about the
    # real one, which is the same defect as a missing page (Codex, 01.08.2026).
    # render_policy is only reached when at least one path is on, so neither list is ever empty.
    whom = []
    consent = []
    if has_metrika:
        whom.append("посетителей сайта " + dom)
        consent.append("Используя сайт")
    if cc:
        whom.append("людей, которые обращаются к Оператору")
        consent.append("обращаясь к Оператору")
    who = " и ".join(whom)
    # The clause opens a sentence, and on the contacts-only path it starts with a gerund
    # ("обращаясь"), so without this the page reads "...к Оператору. обращаясь к Оператору".
    # Two of the three live combinations start with "Используя" and hid it.
    lead_consent = " или ".join(consent)
    lead_consent = lead_consent[:1].upper() + lead_consent[1:]

    collected = []
    if cc:
        collected.append(
            f"{esc(str(cc['where']))}. Состав данных: {esc(str(cc['data']))}. "
            "Вы передаёте эти сведения добровольно и вправе их не передавать."
        )
    if has_metrika:
        collected.append(
            "Сайт представляет собой базу знаний и не содержит форм регистрации или сбора "
            "контактных данных. При посещении сайта система веб-аналитики Яндекс.Метрика "
            "собирает данные: файлы cookie, IP адрес, сведения о переходах и "
            "просмотренных страницах, о браузере и устройстве, а также о действиях на "
            "страницах. Эти данные используются в статистической форме, для сбора статистики "
            "посещаемости сайта."
        )
    else:
        collected.append(
            "Сам сайт представляет собой базу знаний. Форм регистрации, сбора контактных "
            "данных и счётчиков веб-аналитики на нём нет."
        )

    purposes = []
    if cc:
        purposes.append(esc(str(cc["purpose"])))
    if has_metrika:
        purposes.append(
            "Данные веб-аналитики обрабатываются для сбора статистики посещаемости, анализа "
            "поведения посетителей и улучшения содержания сайта."
        )

    basis = [
        "Обработка ведётся на основании Федерального закона от 27.07.2006 № 152-ФЗ "
        "О персональных данных."
    ]
    if cc:
        basis.append(
            "Основанием служит ваше согласие. Вы даёте его, когда сами передаёте Оператору "
            "свои данные. Согласие можно отозвать в любой момент."
        )
    if has_metrika:
        basis.append(
            "Для веб-аналитики основанием служит ваше согласие, которое выражается "
            "использованием сайта, а также настройки вашего браузера в отношении файлов cookie."
        )

    cookies = []
    if has_metrika:
        cookies.append(
            "Для веб-аналитики применяется сервис Яндекс.Метрика, предоставляемый ООО Яндекс. "
            "Данные, собранные Метрикой, обрабатываются на условиях, опубликованных на сайте "
            "Яндекса. Вы можете отключить файлы cookie в настройках браузера или "
            "воспользоваться инструментами отказа от веб-аналитики."
        )

    transfer = []
    processors = cc.get("processors") if cc else None
    if processors:
        names = ", ".join(esc(str(x)) for x in processors)
        transfer.append(
            f"Контактные данные проходят через сервисы: {names}."
        )
    if has_metrika:
        transfer.append(
            "Данные веб-аналитики обрабатываются с использованием сервиса Яндекс.Метрика "
            "(ООО Яндекс)."
        )
    if cc and not processors:
        # The owner collects contacts somewhere off-site and named no processors, so we do not
        # know whether a service is involved. An absolute "we share with nobody" here would be a
        # claim the config does not support: collecting in a messenger already means a processor.
        transfer.append(
            "Данные могут быть предоставлены государственным органам в случаях, "
            "предусмотренных законом."
        )
    else:
        transfer.append(
            "Иным третьим лицам, кроме названных выше, Оператор данные не передаёт. Данные могут "
            "быть предоставлены государственным органам в случаях, предусмотренных законом."
        )

    retention = []
    if cc:
        retention.append(
            esc(str(cc.get("retention")))
            if cc.get("retention")
            # Without site.contacts_collection.retention the config says nothing about a term, so
            # the page states the statutory floor (152-FZ art. 5 p. 7: no longer than the purpose
            # requires) instead of inventing a practice the owner never described.
            else "Контактные данные хранятся до достижения цели обработки "
                 "или до отзыва вашего согласия."
        )
    if has_metrika:
        retention.append(
            "Данные веб-аналитики хранятся в течение срока, установленного "
            "сервисом Яндекс.Метрика."
        )

    rights = [
        "Вы вправе запросить сведения об обработке ваших данных, потребовать их уточнения, "
        "блокирования или удаления, а также отозвать согласие. Для этого направьте обращение "
        f"на электронную почту {email}."
    ]

    optout = []
    if cc:
        optout.append(
            "Чтобы отозвать согласие и удалить переданные вами данные, напишите об этом "
            f"Оператору на почту {email}. Оператор прекращает обработку и уничтожает данные "
            "в сроки, предусмотренные законодательством Российской Федерации."
        )
    if has_metrika:
        optout.append(
            "Чтобы прекратить сбор данных веб-аналитики, отключите файлы cookie в настройках "
            "браузера или используйте расширения, блокирующие веб-аналитику."
        )

    body = (
        f'<p class="lead">Настоящая Политика описывает, как {op} (далее Оператор) '
        f"обрабатывает данные {who}. {lead_consent}, вы соглашаетесь "
        "с условиями Политики.</p>"
        f"{edition}"
        '<div class="sec">'
        "<h2>Оператор и реквизиты</h2>"
        f"<ul>{req}</ul>"
        + sec("Какие данные обрабатываются", collected)
        + sec("Цели обработки", purposes)
        + sec("Правовое основание", basis)
        + sec("Файлы cookie и Яндекс.Метрика", cookies)
        + sec("Передача данных", transfer)
        + sec("Сроки обработки", retention)
        + sec("Права субъекта данных", rights)
        + sec("Как отказаться от обработки", optout)
        + sec(
            "Изменения политики",
            [
                "Оператор вправе изменять настоящую Политику. Актуальная редакция всегда "
                "доступна на этой странице."
            ],
        )
        + sec("Контакты", [f"По вопросам обработки персональных данных пишите на {email}."])
        + "</div>"
    )
    parts = [
        header(site), '<main class="page">',
        '<div class="bc">Политика конфиденциальности</div>',
        "<h1>Политика конфиденциальности</h1>",
        body,
        "</main>",
        footer(site),
    ]
    return shell("Политика конфиденциальности", "\n".join(parts))


def render_block(slug, b):
    t = b.get("type")
    if t == "text":
        no_dash(f"{slug}.text", b["text"])
        return f"<p>{esc(b['text'])}</p>"
    if t == "subhead":
        return f"<h3>{esc(b['text'])}</h3>"
    if t == "list":
        no_dash(f"{slug}.list", " ".join(b["items"]))
        tag = "ol" if b.get("ordered") else "ul"
        return f"<{tag}>" + "".join(f"<li>{esc(i)}</li>" for i in b["items"]) + f"</{tag}>"
    if t == "quote":
        no_dash(f"{slug}.quote", b["text"])
        return f'<div class="quote">{esc(b["text"])}{" " + esc(b["by"]) if b.get("by") else ""}</div>'
    if t == "note":
        no_dash(f"{slug}.note", b["text"])
        return f'<div class="note">{esc(b["text"])}</div>'
    if t == "copy":
        no_dash(f"{slug}.copy", b["text"])
        return (
            '<div class="lblrow"><span class="lbl">Промпт</span>'
            f'<button class="copy" data-text="{esc(b["text"])}">Скопировать</button></div>'
            f'<div class="box">{esc(b["text"])}</div>'
        )
    if t == "link":
        label = b.get("label") or b["url"]
        no_dash(f"{slug}.link", label)
        if b.get("download"):
            dl = f' download="{esc(b["download"])}"' if isinstance(b["download"], str) else " download"
            return f'<a class="linkbtn" href="{esc(b["url"])}"{dl} rel="noopener">{esc(label)}</a>'
        return f'<a class="linkbtn" href="{esc(b["url"])}" target="_blank" rel="noopener">{esc(label)}</a>'
    if t == "cards":
        cells = []
        for c in b["items"]:
            inner = f"<h3>{esc(c['h'])}</h3>"
            if c.get("body"):
                no_dash(f"{slug}.card", c["body"])
                inner += f"<p>{esc(c['body'])}</p>"
            if c.get("list"):
                no_dash(f"{slug}.cardlist", " ".join(c["list"]))
                tag = "ol" if c.get("ordered") else "ul"
                inner += f"<{tag}>" + "".join(f"<li>{esc(i)}</li>" for i in c["list"]) + f"</{tag}>"
            if c.get("quote"):
                no_dash(f"{slug}.cardquote", c["quote"])
                inner += f'<div class="quote">{esc(c["quote"])}</div>'
            cells.append(f'<div class="cardb">{inner}</div>')
        return f'<div class="grid2">{"".join(cells)}</div>'
    if t == "image":
        cap = b.get("caption", "")
        alt = b.get("alt") or cap
        if cap:
            no_dash(f"{slug}.imgcap", cap)
        fig = (
            '<figure style="margin:1.6rem auto;text-align:center;max-width:420px">'
            f'<img src="{esc(b["src"])}" alt="{esc(alt)}" loading="lazy" '
            'style="display:block;width:100%;height:auto;border-radius:14px;'
            'box-shadow:0 2px 20px rgba(0,0,0,.16)">'
        )
        if cap:
            fig += (
                '<figcaption style="margin-top:.6rem;font-size:.86em;'
                f'line-height:1.45;opacity:.72">{esc(cap)}</figcaption>'
            )
        return fig + "</figure>"
    raise SystemExit(f"{slug}: unknown block type {t!r}")


def render_guide(site, guides, g):
    data = json.loads((CONTENT / g["content"]).read_text(encoding="utf-8"))
    for f in ("lead", "meta", "how"):
        if data.get(f):
            no_dash(f"{g['slug']}.{f}", data[f])
    sections = data.get("sections") or []
    # side menu only pays for itself on a long read; short guides keep the bare column
    has_toc = len(sections) >= TOC_MIN_SECTIONS
    parts = [header(site), f'<main class="page{" has-toc" if has_toc else ""}">',
             '<article class="pcol">',
             f'<div class="bc"><a href="/#{cat_id(g["category"])}">{esc(g["category"])}</a></div>',
             f"<h1>{esc(g['title'])}</h1>"]
    if data.get("lead"):
        parts.append(f'<p class="lead">{esc(data["lead"])}</p>')
    if data.get("meta"):
        parts.append(f'<p class="meta">{esc(data["meta"])}</p>')
    if data.get("how"):
        parts.append(f'<div class="how">{esc(data["how"])}</div>')
    prompts = data.get("prompts") or []
    mid = len(prompts) // 2 if len(prompts) >= 6 else None
    for i, p in enumerate(prompts):
        no_dash(f"{g['slug']}.prompt{p['n']}", p["prompt"])
        no_dash(f"{g['slug']}.title{p['n']}", p["title"])
        blk = ['<div class="p">', f'<span class="num">{p["n"]} из {len(prompts)}</span>', f'<h2>{esc(p["title"])}</h2>']
        if p.get("when"):
            blk.append(f'<p class="when">{esc(p["when"])}</p>')
        blk.append('<div class="lblrow"><span class="lbl">Промпт</span>'
                   f'<button class="copy" data-text="{esc(p["prompt"])}">Скопировать</button></div>')
        blk.append(f'<div class="box">{esc(p["prompt"])}</div>')
        if p.get("example"):
            blk.append(f'<p class="ex"><b>Пример:</b> {esc(p["example"])}</p>')
        blk.append("</div>")
        parts.append("".join(blk))
        if mid is not None and i == mid and site.get("upsell_url"):
            parts.append(f'<div class="mid"><a href="{esc(site["upsell_url"])}">{esc(site["upsell_label_top"])}</a></div>')
    half = len(sections) // 2 if len(sections) >= 4 else None
    for i, s in enumerate(sections):
        chunk = ['<div class="sec">', f'<h2 id="sec-{i}">{esc(s["title"])}</h2>']
        if s.get("intro"):
            no_dash(f"{g['slug']}.intro", s["intro"])
            chunk.append(f'<p>{esc(s["intro"])}</p>')
        for b in s.get("blocks", []):
            chunk.append(render_block(g["slug"], b))
        chunk.append("</div>")
        parts.append("".join(chunk))
        if half is not None and i == half and site.get("upsell_url"):
            parts.append(f'<div class="mid"><a href="{esc(site["upsell_url"])}">{esc(site["upsell_label_top"])}</a></div>')
    parts.append(upsell(site))
    parts.append("</article>")
    if has_toc:
        links = "".join(f'<a href="#sec-{i}">{esc(s["title"])}</a>' for i, s in enumerate(sections))
        parts.append(f'<aside class="toc"><div class="h">На странице</div>{links}</aside>')
    parts.append("</main>")
    parts.append(footer(site))
    return shell(g["title"], "\n".join(parts) + COPY_JS + (TOC_JS if has_toc else ""))


def plural(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "материал"
    if 2 <= n % 10 <= 4 and not 10 <= n % 100 < 20:
        return "материала"
    return "материалов"


def render_index(site, guides):
    pub = [g for g in guides if g.get("status") == "published"]
    cats = categories(guides)
    hero = site["hero"]
    for field in ("eyebrow", "title", "desc"):
        no_dash(f"hero.{field}", hero[field])
    parts = [header(site, active="home"), '<main class="wrap">',
             '<section class="hero"><div class="art"></div><div class="grid"></div><div class="glow"></div>'
             '<div class="txt">'
             f'<span class="eyebrow"><i class="dot"></i>{esc(hero["eyebrow"])}</span>'
             f'<h1>{esc(hero["title"])}</h1>'
             f'<p class="desc">{esc(hero["desc"])}</p>'
             '<div class="read"><span class="circ">&#8594;</span>'
             f'<span class="lbl">{esc(hero.get("cta", "Смотреть материалы"))}</span></div>'
             "</div></section>",
             '<div class="tabs" id="list">',
             '<button class="tab on" type="button" data-cat="all">Все материалы</button>']
    for c in cats:
        parts.append(f'<button class="tab" type="button" data-cat="{cat_id(c)}">{esc(c)}</button>')
    parts.append("</div>")
    parts.append(f'<div class="count" id="count">{len(pub)} {plural(len(pub))}</div>')
    parts.append('<div class="cards">')
    for g in pub:
        parts.append(
            f'<a class="card" data-cat="{cat_id(g["category"])}" href="/guide-{esc(g["slug"])}/">'
            f'<div class="tag"><i class="d"></i>{esc(g["category"])}</div>'
            f'<div class="ct">{esc(g["title"])}</div>'
            f'<p class="cd">{esc(g["summary"])}</p>'
            f'<div class="cm">Кодовое слово: {esc(g["codeword"])}</div></a>'
        )
    parts.append("</div>")
    parts.append('<div class="empty" id="empty" style="display:none">В этом разделе пока пусто</div>')
    parts.append(upsell(site))
    parts.append("</main>")
    parts.append(footer(site))
    return shell("Полезные материалы", "\n".join(parts) + FILTER_JS)


def render_about(site, guides):
    a = site["about"]
    blocks = list(a["blocks"])
    # the lead-in paragraph (the one before any heading) rides in the portrait hero, the rest
    # stays in the reading column — same shape as the index, so /about/ doesn't read as a
    # different site
    lead = ""
    if blocks and not blocks[0].get("h") and blocks[0].get("p"):
        lead = blocks.pop(0)["p"]
        no_dash("about.p", lead)
    # with a portrait the art layer is the photo; without one, the same dot-grid and bloom as
    # the index keeps the card from reading as an empty black box
    art = '<div class="art"></div>'
    if not a.get("image"):
        art += '<div class="grid"></div><div class="glow"></div>'
    parts = [header(site, active="about"), '<main class="page">',
             f'<div class="bc">{esc(site.get("about_nav", "Обо мне"))}</div>',
             f'<section class="hero about-hero">{art}',
             '<div class="txt"><div class="eyebrow mono">ОБО МНЕ</div>',
             f'<h1>{esc(a["title"])}</h1>']
    if lead:
        parts.append(f'<p class="desc">{esc(lead)}</p>')
    parts.append('</div></section>')
    parts.append('<div class="sec">')
    for blk in blocks:
        if blk.get("h"):
            parts.append(f'<h3>{esc(blk["h"])}</h3>')
        if blk.get("p"):
            no_dash("about.p", blk["p"])
            parts.append(f'<p>{esc(blk["p"])}</p>')
    parts.append("</div>")
    parts.append(upsell(site))
    parts.append("</main>")
    parts.append(footer(site))
    return shell(a["title"], "\n".join(parts))


def shell(title, body):
    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        f"<title>{esc(title)}</title>"
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{FONTS_HREF}">'
        f"<style>{root_css(THEME)}{BASE_CSS}{cover_css(SITE_CFG)}</style>"
        f"{THEME_JS}"
        f"{metrika_snippet(SITE_CFG)}"
        f"</head><body>{body}</body></html>"
    )


def build_all(site, guides, out=SITE):
    # shell() reads the counter from the SITE_CFG global; bind it to the site we are building so
    # the injected Metrika tag and the /policy/ page (built from `site`) can never diverge
    global SITE_CFG
    SITE_CFG = site
    # a present site.legal must be an object even before a policy is built, so a malformed value
    # (a list, a string, a number) fails now instead of sitting in the config until analytics is
    # switched on; this does not require the fields, only the right shape
    legal_cfg = site.get("legal")
    if legal_cfg is not None and not isinstance(legal_cfg, dict):
        raise SystemExit("site.legal: expected an object with operator/inn/email")
    # fail before writing anything if a counter is set without a valid legal block, so the
    # analytics tag and its policy can never ship apart
    if policy_required(site):
        _validate_legal(site)
    # a slug becomes both a directory name and a URL segment. Judge it by what is ALLOWED, not by
    # a list of characters to forbid: that list is always short by one. A slug outside the set
    # either lands somewhere the prune below cannot recognise as ours, or builds a page the URL
    # never reaches. Checked here, before the first file is written, so a bad slug in the tenth
    # guide cannot leave site/ half-rebuilt.
    for g in guides:
        if g.get("status") != "published":
            continue
        slug = str(g.get("slug", ""))
        if not SLUG_RE.fullmatch(slug) or slug in (".", ".."):
            raise SystemExit(f"guide slug must be a single path segment of [a-zA-Z0-9._-]: {slug!r}")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(render_index(site, guides), encoding="utf-8")
    (out / "about").mkdir(exist_ok=True)
    (out / "about" / "index.html").write_text(render_about(site, guides), encoding="utf-8")
    n = 2
    policy_dir = out / "policy"
    if policy_required(site):
        policy_dir.mkdir(exist_ok=True)
        (policy_dir / "index.html").write_text(render_policy(site), encoding="utf-8")
        n += 1
    elif policy_dir.exists():
        # analytics was turned off since a prior build: drop the orphan page so the old URL stops serving
        shutil.rmtree(policy_dir)
    kept = set()
    for g in guides:
        if g.get("status") != "published":
            continue
        d = out / f"guide-{g['slug']}"
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(render_guide(site, guides, g), encoding="utf-8")
        kept.add(d.name)
        n += 1
    # a guide can leave the published set at any time: rejected by the client, switched back to
    # draft, or dropped from registry.json outright. Its directory would survive every later build,
    # and deploy mirrors site/ with `rsync --delete`, so the page keeps serving on the client's
    # domain while the index and the menu show nothing. Checking the front page after a deploy
    # therefore proves nothing about it. Same orphan rule as /policy/ above, applied to guides.
    # Deleting is restricted to what this generator itself produces: a directory holding exactly
    # one index.html and nothing else (true of all 269 pages across the live bases on 31.07.2026).
    # Anything richer under guide-* was put there by a human, and silently destroying a client's
    # files is worse than the leak we are closing: it stays, and selfcheck.py names it so someone
    # decides. A refusal that names the thing beats a deletion nobody sees.
    for stale in out.glob("guide-*"):
        if stale.is_dir() and stale.name not in kept:
            if [p.name for p in stale.iterdir()] == ["index.html"]:
                shutil.rmtree(stale)
    return n


def main():
    global THEME, COLORS, SITE_CFG
    reg = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
    site = reg["site"]
    THEME = sys.argv[1] if len(sys.argv) > 1 else site.get("theme", "lime")
    if THEME not in THEMES:
        raise SystemExit(f"unknown theme {THEME!r}, options: {list(THEMES)}")
    COLORS = resolve_colors(THEME, site.get("colors"))
    SITE_CFG = site
    n = build_all(site, reg["guides"])
    custom = f", colors={sorted(site['colors'])}" if site.get("colors") else ""
    print(f"built {n} pages into {SITE} (theme={THEME}{custom})")


if __name__ == "__main__":
    main()
