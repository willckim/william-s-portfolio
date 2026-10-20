"""Render the static preview images for the Lab cards on /demos.

    py tools/demo_cards.py

The /demos page shows a still image per demo and loads no demo code. The two 3D
products reuse their posters (tools/demo_posters.py). The four Lab tools are
captured here from the Lab itself, served the way the site serves it, cropped to
16:9 and saved as WebP at 640 pixels wide into assets/cards/.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from sitekit import serve  # noqa: E402   the site's clean URLs, as the checks serve it

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "cards"
WIDTH, RATIO = 640, 16 / 9
# card key -> the element on /lab that the card previews
SHOTS = {"construction": "#construction", "tour": "#tour", "pqc": "#mosca", "grover": "#grover"}


def save(png: bytes, name: str) -> Path:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    crop_h = min(h, round(w / RATIO))
    img = img.crop((0, 0, round(crop_h * RATIO), crop_h))
    path = OUT / f"{name}.webp"
    img.resize((WIDTH, round(WIDTH / RATIO)), Image.LANCZOS).save(path, "WEBP", quality=80, method=6)
    return path


def main() -> int:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900}, reduced_motion="reduce",
                                    color_scheme="light")
            page.goto(f"{base}/lab", wait_until="networkidle")
            page.add_style_tag(content=".site-header { visibility: hidden !important; }")   # sticky, it would cover a card
            page.click("[data-g=step]")                  # Grover after one iteration, the marked bar already taller
            for name, selector in SHOTS.items():
                el = page.locator(selector).first
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                path = save(el.screenshot(), name)
                print(f"{name}: {path.relative_to(ROOT).as_posix()} {path.stat().st_size // 1024} KB")
            browser.close()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
