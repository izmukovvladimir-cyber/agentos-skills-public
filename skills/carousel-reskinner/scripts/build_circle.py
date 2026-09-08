#!/usr/bin/env python3
"""Build a transparent IG-analytics ring cutout from a raw screenshot.

Input: raw screenshot path (jpg/png) — should be a tight crop around the ring.
Output: PNG with white background made transparent. Optional dark→light inversion
for the inner number text so it reads on a dark backdrop.

CLI:
    build_circle.py <src> <dst> [--invert-dark]
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image
import logging

log = logging.getLogger(__name__)


def build(src: Path, dst: Path, invert_dark: bool = False, white_thresh: int = 235,
          dark_thresh: int = 90) -> None:
    im = Image.open(src).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if r > white_thresh and g > white_thresh and b > white_thresh:
                px[x, y] = (0, 0, 0, 0)
            elif invert_dark and r < dark_thresh and g < dark_thresh and b < dark_thresh:
                px[x, y] = (255, 255, 255, 255)
    im.save(dst, "PNG")
    log.info("saved %s", dst)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    invert = "--invert-dark" in args
    args = [a for a in args if not a.startswith("--")]
    build(Path(args[0]), Path(args[1]), invert_dark=invert)


if __name__ == "__main__":
    main()
