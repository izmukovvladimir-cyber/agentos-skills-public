#!/usr/bin/env python3
"""Self-check for the knowledge base. Run after build.py. Exit 0 = clean, exit 1 = problems.

Validates: config filled in with no template leftovers, cover images actually on disk,
registry well-formed, every published guide has a content file and a built page, no long
dashes anywhere in user-facing text, no broken internal links, every prompt has non-empty
text, no leftover placeholder/TODO.

Never publish on a FAIL: this runs inside deploy.sh precisely so a broken base cannot reach
a client's domain.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CONTENT = ROOT / "content"
DASH_RE = re.compile(r"[—–]")

errors: list[str] = []
warns: list[str] = []


def err(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warns.append(m)


def main() -> int:
    reg_path = ROOT / "registry.json"
    if not reg_path.exists():
        err("registry.json missing")
        return report()
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    site = reg.get("site", {})
    check_site(site)

    slugs = set()
    published = set()
    codewords = set()
    for g in reg.get("guides", []):
        slug = g.get("slug", "")
        if not slug:
            err(f"guide with empty slug: {g}")
            continue
        if slug in slugs:
            err(f"duplicate slug: {slug}")
        slugs.add(slug)
        cw = g.get("codeword", "").upper()
        if not cw:
            err(f"{slug}: empty codeword")
        if cw in codewords:
            err(f"duplicate codeword: {cw}")
        codewords.add(cw)
        for f in ("title", "category", "summary"):
            v = g.get(f, "")
            if not v:
                err(f"{slug}: empty {f}")
            elif DASH_RE.search(v):
                err(f"{slug}: long dash in {f}: {v!r}")

        cfile = CONTENT / g.get("content", "")
        if g.get("status") == "published":
            published.add(slug)
            if not g.get("content") or not cfile.exists():
                err(f"{slug}: published but content file missing ({g.get('content')})")
            else:
                check_content(slug, cfile)
            page = SITE / f"guide-{slug}" / "index.html"
            if not page.exists():
                err(f"{slug}: published but built page missing (run build.py)")
            else:
                check_page(slug, page)

    # deploy mirrors site/ to the live domain with `rsync --delete`, so anything sitting in site/
    # is published whether or not the index links to it. A directory left over from a guide that
    # was rejected or unpublished keeps serving on the client's domain, and checking the front page
    # never reveals it. build.py prunes these; this refuses to ship if one is still here.
    if SITE.exists():
        for d in sorted(SITE.glob("guide-*")):
            if d.is_dir() and d.name[len("guide-"):] not in published:
                err(f"{d.name}: page in site/ is not a published guide (stale build, would go live)")

    for label, page in (("site/index.html", SITE / "index.html"),
                        ("site/about/index.html", SITE / "about" / "index.html")):
        if not page.exists():
            err(f"{label} missing (run build.py)")
        else:
            check_page(label, page)
    return report()


PLACEHOLDERS = ("ИМЯ КЛИЕНТА", "example.com", "TODO", "TBD", "ЗАПОЛНИ", "client-domain")


def check_site(site: dict) -> None:
    """The config is the whole client-specific surface, so a base that shipped with template
    leftovers in it (someone forgot to replace a placeholder) must fail here, not in front of
    the client."""
    for field in ("author", "domain"):
        if not site.get(field):
            err(f"site.{field} empty")
    hero = site.get("hero") or {}
    for field in ("eyebrow", "title", "desc"):
        if not hero.get(field):
            err(f"site.hero.{field} empty")
    about = site.get("about") or {}
    if not about.get("title") or not about.get("blocks"):
        err("site.about: needs a title and at least one block")

    # upsell is optional (a base can sell nothing yet), but a half-filled one is a bug
    if site.get("upsell_url"):
        if site["upsell_url"].strip().rstrip("/") in ("#", ""):
            err("site.upsell_url is a placeholder #")
        for field in ("upsell_label_top", "upsell_title", "upsell_text", "upsell_button"):
            if not site.get(field):
                err(f"site.{field} empty (upsell_url is set, so the block renders)")
    else:
        warn("site.upsell_url not set — the «next step» block is off everywhere")

    for text in _walk_strings(site):
        for bad in PLACEHOLDERS:
            if bad.lower() in text.lower():
                err(f"site: leftover template placeholder {bad!r} in {text[:60]!r}")

    # cover images are optional, but a config pointing at a file that is not there means a
    # silently empty hero in production
    for label, path in (("site.hero_image", site.get("hero_image")),
                        ("site.about.image", about.get("image"))):
        if path and not (SITE / path.lstrip("/")).exists():
            err(f"{label}: file missing at site{path}")


def _walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_strings(v)


def check_content(slug: str, cfile: Path) -> None:
    data = json.loads(cfile.read_text(encoding="utf-8"))
    if not data.get("prompts") and not data.get("sections"):
        err(f"{slug}: content has neither prompts nor sections")
    for f in ("lead", "meta", "how"):
        v = data.get(f, "")
        if v and DASH_RE.search(v):
            err(f"{slug}.{f}: long dash")
    for p in data.get("prompts", []):
        ptext = p.get("prompt", "").strip()
        if not ptext:
            err(f"{slug}.prompt#{p.get('n')}: empty prompt text")
        for fld in ("prompt", "title", "example", "when"):
            v = p.get(fld, "")
            if v and DASH_RE.search(v):
                err(f"{slug}.prompt#{p.get('n')}.{fld}: long dash")
        for bad in ("TODO", "TBD", "XXX", "lorem"):
            if bad.lower() in (p.get("prompt", "") + p.get("title", "")).lower():
                err(f"{slug}.prompt#{p.get('n')}: leftover placeholder {bad}")
        # senior-level heuristic (CONTENT_STANDARD.md): a real working prompt has
        # substitutions [...] and enough body. Soft signal "maybe shallow", review by hand.
        if ptext and "[" not in ptext:
            warn(f"{slug}.prompt#{p.get('n')}: no [substitutions] — shallow? (CONTENT_STANDARD)")
        if ptext and len(ptext) < 90:
            warn(f"{slug}.prompt#{p.get('n')}: very short ({len(ptext)} chars) — shallow? (CONTENT_STANDARD)")
    # any long dash anywhere in section content
    for s in _walk_strings(data.get("sections", [])):
        if DASH_RE.search(s):
            err(f"{slug}: long dash in section text: {s[:50]!r}")


def check_page(slug: str, page: Path) -> None:
    h = page.read_text(encoding="utf-8")
    # internal links must resolve to a built file (ignore #anchor fragments)
    for m in re.finditer(r'href="(/[^"]*)"', h):
        href = m.group(1).split("#")[0]
        if href in ("", "/"):
            target = SITE / "index.html"
        elif href.endswith("/"):
            target = SITE / href.strip("/") / "index.html"
        else:
            target = SITE / href.lstrip("/")
        if not target.exists():
            err(f"{slug}: broken internal link {m.group(1)}")
    if DASH_RE.search(re.sub(r"<[^>]+>", "", h)):
        # strip tags, check visible text only
        err(f"{slug}: long dash in rendered page text")


def report() -> int:
    for w in warns:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"\nFAIL: {len(errors)} error(s)")
        return 1
    print("OK: knowledge-base self-check passed (no errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
