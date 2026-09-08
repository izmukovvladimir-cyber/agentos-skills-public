#!/usr/bin/env python3
"""Unbind live IG funnels from specific posts (all-posts sweep, 2026-07-20).

Why: mediaIds binding is incompatible with combined comment+DM triggers,
so the comment trigger never fires. Rule from the account owner: codewords must
work under any post.

Safety: dry-run by default. Only touches automations that HAVE medias set.
Retired/paused twins holding the same keyword are renamed to a dead keyword
first, because the API refuses the update while any automation reserves the word.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

BUILDER = str(Path("~/bin/cp_funnel_builder.py").expanduser())
IG_BOT = "<ig_bot_id>"  # uuid Instagram-бота кабинета, bots_list покажет

TRIGGER_NAME_TO_LABEL = {
    "Comment contains": "commentContains",
    "Comment equals": "commentEquals",
    "Message contains": "messageContains",
    "Message equals": "messageEquals",
}


def load_client():
    spec = importlib.util.spec_from_file_location("cpb", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cpb"] = mod
    spec.loader.exec_module(mod)
    return mod.CpClient()


def keywords(entry) -> list[str]:
    out = []
    for m in entry.get("startMessages") or []:
        out.append(m.get("name") or m.get("value") if isinstance(m, dict) else m)
    return [k for k in out if k]


def trigger_labels(entry) -> list[str]:
    out = []
    for t in entry.get("triggerTypes") or []:
        label = TRIGGER_NAME_TO_LABEL.get(t.get("name"))
        if label:
            out.append(label)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    args = ap.parse_args()

    cp = load_client()
    items = cp.call("automations_list", {"botId": IG_BOT})
    if isinstance(items, dict):
        items = items.get("data") or []

    bound = [a for a in items if a.get("medias")]
    others = [a for a in items if not a.get("medias")]
    print(f"automations: {len(items)}, bound to posts: {len(bound)}")

    # map keyword -> automations that reserve it (blockers are the ones we do not fix)
    reserved: dict[str, list[dict]] = {}
    for a in items:
        for k in keywords(a):
            reserved.setdefault(k.lower(), []).append(a)

    fixed, freed, failed = [], [], []
    for a in bound:
        kws = keywords(a)
        tt = trigger_labels(a)
        name = a.get("name", "")[:55]
        if not kws or not tt:
            failed.append((name, "no keywords or trigger types in list payload"))
            continue

        # free the word from retired twins first
        for k in kws:
            for twin in reserved.get(k.lower(), []):
                if twin["id"] == a["id"] or twin.get("statusName") == "Active":
                    continue
                dead = f"retired-{str(twin['id'])[:8]}-do-not-use"
                if keywords(twin) == [dead]:
                    continue
                print(f"  free keyword '{k}' from retired «{twin.get('name','')[:45]}»")
                if args.apply:
                    cp.call("automations_triggers_set", {
                        "automationId": twin["id"],
                        "triggerTypes": ["messageContains"],
                        "startMessages": [dead],
                    })
                    twin["startMessages"] = [dead]
                freed.append(twin.get("name", ""))

        payload = {
            "automationId": a["id"],
            "triggerTypes": tt,
            "startMessages": kws,
            "mediaIds": [],
            "startFrequency": 0,
        }
        print(f"UNBIND {name} | {tt} | {len(kws)} kw")
        if args.apply:
            try:
                cp.call("automations_triggers_set", payload)
                fixed.append(name)
            except Exception as exc:  # noqa: BLE001 - report and continue the sweep
                failed.append((name, str(exc)[:160]))
                print(f"   FAILED: {exc}")
        else:
            fixed.append(name)

    print("\n=== SUMMARY ===")
    print(f"{'unbound' if args.apply else 'would unbind'}: {len(fixed)}")
    print(f"retired twins freed: {len(freed)}")
    if failed:
        print(f"FAILED: {len(failed)}")
        for n, e in failed:
            print(f"  {n}: {e}")
    if not args.apply:
        print("\n(dry-run, re-run with --apply)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
