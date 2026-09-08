#!/usr/bin/env python3
"""Guard: a page that is no longer published must not survive in site/.

deploy.sh mirrors site/ to the client's live domain with `rsync -a --delete`, so anything
sitting in site/ is published whether or not the index links to it. Until 31.07.2026 build.py
only ADDED guide directories: a guide rejected by the client, switched back to draft, or dropped
from registry.json kept serving on the domain, and a post-deploy check of the front page showed
nothing wrong (found live: two rejected guides stayed reachable for two days after rejection).

Run: python3 test_draft_orphan.py   (builds throwaway copies under a temp dir, touches nothing else)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TPL = Path(__file__).resolve().parent
# Scripts under test come from the directory this test sits in — that is the point, each client
# base carries its own copy and they drift. The FIXTURE (registry + content) always comes from the
# template: a client registry references that client's own media and themes, so building it inside
# a temp dir fails for reasons that have nothing to do with what we are checking.
FIX = Path.home() / ".claude/skills/client-knowledge-base-site/template"
if not (FIX / "registry.json").exists() or not (FIX / "content").is_dir():
    FIX = TPL
PASS = FAIL = 0


def check(cond: bool, label: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def instance(tmp: Path, name: str) -> Path:
    """A throwaway base: the fixture registry + content, and the two scripts under test.

    The copy keeps the <workspace>/assets/<base>/ layout, because newer build.py copies read the
    brand palette from <workspace>/design.md by an explicit path and refuse to run without it.
    """
    inst = tmp / name / "assets" / TPL.name
    inst.mkdir(parents=True)
    ws = TPL.parent.parent
    if (ws / "design.md").exists():
        shutil.copy2(ws / "design.md", tmp / name / "design.md")
    if (ws / "skills").is_dir():
        # the palette reader imports carousel_lib from <workspace>/skills by an explicit path;
        # link rather than copy, the tree is large and the test only reads from it
        (tmp / name / "skills").symlink_to(ws / "skills")
    for f in ("build.py", "selfcheck.py"):
        shutil.copy2(TPL / f, inst / f)
    # newer copies moved the palette out of the registry into design.md and REFUSE a registry that
    # still carries site.colors; older ones simply ignore its absence. Dropping it is the only
    # shape both accept, and this test says nothing about colours either way.
    fix = json.loads((FIX / "registry.json").read_text(encoding="utf-8"))
    fix.get("site", {}).pop("colors", None)
    (inst / "registry.json").write_text(json.dumps(fix, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copytree(FIX / "content", inst / "content")
    return inst


def registry(inst: Path, mutate) -> None:
    reg = json.loads((inst / "registry.json").read_text(encoding="utf-8"))
    mutate(reg)
    (inst / "registry.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def run(inst: Path, script: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(inst / script)], cwd=inst,
                          capture_output=True, text=True)


def errors(r: subprocess.CompletedProcess) -> int:
    """Число жалоб самопроверки. Строку `FAIL: N error(s)` печатает её report()."""
    m = re.search(r"FAIL: (\d+) error", r.stdout + r.stderr)
    return int(m.group(1)) if m else 0


def publish_all(reg: dict) -> None:
    for g in reg["guides"]:
        g["status"] = "published"


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. published guide is built
        inst = instance(tmp, "a")
        registry(inst, publish_all)
        r = run(inst, "build.py")
        check(r.returncode == 0, f"сборка published упала: {r.stderr[-300:]}")
        page = inst / "site" / "guide-primer" / "index.html"
        check(page.exists(), "published-гайд не собран")

        # 2. published -> draft: the directory must go, not just the index entry
        registry(inst, lambda reg: [g.update(status="draft") for g in reg["guides"]])
        r = run(inst, "build.py")
        check(r.returncode == 0, f"пересборка после снятия упала: {r.stderr[-300:]}")
        check(not page.parent.exists(), "снятый с публикации гайд остался в site/ (уедет на домен)")
        idx = (inst / "site" / "index.html").read_text(encoding="utf-8")
        check("guide-primer" not in idx, "снятый гайд остался в индексе")

        # 3. dropped from registry entirely: nothing in the config points at it any more, so a fix
        #    that walks registry entries (the obvious one) cannot see it. The page still serves.
        inst = instance(tmp, "b")
        registry(inst, publish_all)
        run(inst, "build.py")
        check((inst / "site" / "guide-primer").is_dir(), "подготовка: гайд не собран")
        registry(inst, lambda reg: reg.__setitem__("guides", []))
        r = run(inst, "build.py")
        check(r.returncode == 0, f"сборка с пустым реестром упала: {r.stderr[-300:]}")
        check(not (inst / "site" / "guide-primer").exists(),
              "гайд, удалённый из registry.json, остался в site/")

        # 4. selfcheck is the second layer: it must refuse to ship a stale page even if build.py
        #    never ran (hand-edited site/, older build.py in a client copy, interrupted deploy)
        #    Судим по ПРИРОСТУ жалоб, а не по коду возврата: шаблон намеренно нафарширован
        #    заглушками ('ЗАПОЛНИ'), поэтому на нём самопроверка красная и без нашей правки.
        inst = instance(tmp, "c")
        registry(inst, publish_all)
        run(inst, "build.py")
        before = run(inst, "selfcheck.py")
        check("not a published guide" not in (before.stdout + before.stderr),
              "самопроверка жалуется на лишнюю страницу на чистой сборке")
        stale = inst / "site" / "guide-otozvan-klientom"
        stale.mkdir()
        (stale / "index.html").write_text("<html>отозванный материал</html>", encoding="utf-8")
        after = run(inst, "selfcheck.py")
        check(after.returncode != 0, "самопроверка пропустила чужую страницу в site/")
        check("guide-otozvan-klientom" in (after.stdout + after.stderr),
              "самопроверка не назвала лишнюю страницу поимённо")
        #    Код возврата на шаблоне красный и без нас, поэтому судим ещё и по ПРИРОСТУ числа
        #    ошибок: ровно одна новая, иначе гейт либо молчит, либо шумит на здоровых страницах
        check(errors(after) == errors(before) + 1,
              f"ошибок было {errors(before)}, стало {errors(after)}, ожидал ровно на одну больше")

        # 5. the prune must stay inside guide-*: the built-in pages are not guides and have their
        #    own lifecycle (policy/ is dropped by its own rule when analytics goes off)
        inst = instance(tmp, "d")
        registry(inst, publish_all)
        run(inst, "build.py")
        extra = inst / "site" / "assets"
        extra.mkdir()
        (extra / "cover.png").write_text("x", encoding="utf-8")
        run(inst, "build.py")
        check((inst / "site" / "about" / "index.html").exists(), "prune снёс about/")
        check((extra / "cover.png").exists(), "prune снёс постороннюю папку site/assets")

        # 5b. a directory under guide-* that is NOT our output (a human put files there) must
        #     survive the prune: silent deletion of a client's files is worse than the leak we are
        #     closing. selfcheck below is what makes it visible instead.
        handmade = inst / "site" / "guide-materialy-kursa"
        handmade.mkdir()
        (handmade / "index.html").write_text("<html>руками</html>", encoding="utf-8")
        (handmade / "kniga.pdf").write_text("PDF", encoding="utf-8")
        run(inst, "build.py")
        check((handmade / "kniga.pdf").exists(), "prune уничтожил чужие файлы под guide-*")
        r = run(inst, "selfcheck.py")
        check("guide-materialy-kursa" in (r.stdout + r.stderr),
              "самопроверка промолчала о чужом каталоге, который prune не тронул")
        shutil.rmtree(handmade, ignore_errors=True)   # у мутанта его уже нет, уборка не должна ронять прогон

        # 5c. a slug that is not a single path segment builds the page where the prune cannot see
        #     it: the build must refuse before writing, not produce a page nobody can retract.
        #     Судим по СПИСКУ РАЗРЕШЁННОГО: перечень запрещённых символов всегда короче на один.
        for n, badslug in enumerate(("foo/bar", "foo\\bar", "foo?bar", "foo#bar", "foo bar",
                                     "foo%2Fbar", "..", ".", "")):
            bad = instance(tmp, f"e{n}")
            registry(bad, lambda reg, s=badslug: [g.update(status="published", slug=s) for g in reg["guides"]])
            r = run(bad, "build.py")
            check(r.returncode != 0, f"сборка приняла слаг {badslug!r}")
            check("slug must be" in (r.stdout + r.stderr), f"сборка не назвала причину отказа на {badslug!r}")
            #  и НИЧЕГО не записала: иначе на диске остаётся смесь старой и новой сборки
            check(not (bad / "site").exists(), f"сборка успела записать site/ до отказа на {badslug!r}")

        #     обычный слаг проходит: гейт не должен рубить живые базы (269 страниц на 8 базах)
        ok = instance(tmp, "e-ok")
        registry(ok, lambda reg: [g.update(status="published", slug="moy_gayd-2.0") for g in reg["guides"]])
        r = run(ok, "build.py")
        check(r.returncode == 0, f"гейт слага отверг нормальное имя: {r.stderr[-200:]}")

        # 6. a stray FILE named guide-* must not crash the build (only directories are pages)
        stray = inst / "site" / "guide-zametka.txt"
        stray.write_text("не страница", encoding="utf-8")
        r = run(inst, "build.py")
        check(r.returncode == 0, f"сборка упала на файле guide-*: {r.stderr[-300:]}")
        check(stray.exists(), "prune удалил файл, а не каталог страницы")

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
