"""Render the poster image shown before each 3D demo is launched, from the pinned build in demos/.

    py tools/demo_posters.py

Each demo is opened through a local server that serves demos/ the way the site does,
set up for a good first frame (the pergola with the outdoor kitchen at sunset, the
apartment's dollhouse view), and its canvas is captured. The capture is saved as WebP
at 1200 and 640 pixels wide into assets/work/. The posters record which demo commit
they show in tools/data/posters.json.
"""

from __future__ import annotations

import http.server
import io
import json
import sys
import threading
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_demos import VercelLike  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "work"
RECORD = ROOT / "tools" / "data" / "posters.json"
WIDTHS = (1200, 640)
RATIO = 16 / 9
GPU = ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"]


def frames(page, n: int) -> None:
    page.evaluate(f"() => new Promise(r => {{ let i = 0; const t = () => (++i < {n} ? requestAnimationFrame(t) : r()); "
                  "requestAnimationFrame(t); })")


def quote_engine(page, base: str) -> bytes:
    el = "custom-quote-builder"
    page.goto(f"{base}/demos/quote-engine")
    page.wait_for_function(f"() => document.querySelector('{el}')?.shadowRoot?.querySelector('[data-output=range]')"
                           "?.textContent.includes('$')", timeout=60_000)
    page.locator(f'{el} input[data-addon="outdoorKitchen"]').check()
    page.locator(f'{el} [data-lighting="sunset"]').click()
    frames(page, 90)
    return page.locator(f"{el} canvas").first.screenshot()


def lakeview(page, base: str) -> bytes:
    el = "apartment-walkthrough-studio"
    page.goto(f"{base}/demos/lakeview?quality=high")
    page.wait_for_function(f"() => document.querySelector('{el}')?.hasAttribute('data-ready')", timeout=300_000)
    frames(page, 120)
    return page.locator(f"{el} canvas").first.screenshot()


def save(png: bytes, name: str) -> list[dict]:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    crop_h = min(h, round(w / RATIO))
    crop_w = round(crop_h * RATIO)
    left, top = (w - crop_w) // 2, (h - crop_h) // 2
    img = img.crop((left, top, left + crop_w, top + crop_h))
    written = []
    for width in WIDTHS:
        path = OUT / f"{name}-poster-{width}.webp"
        img.resize((width, round(width / RATIO)), Image.LANCZOS).save(path, "WEBP", quality=78, method=6)
        written.append({"file": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size})
    return written


def main() -> int:
    from playwright.sync_api import sync_playwright
    pins = json.loads((ROOT / "tools" / "data" / "demos.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: VercelLike(*a, directory=str(ROOT), **k))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    record = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=GPU)
            for key, shoot in (("quote-engine", quote_engine), ("lakeview", lakeview)):
                page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
                record[key] = {"demo_commit": pins[key]["commit"], "files": save(shoot(page, base), key)}
                page.close()
                print(f"{key}: " + ", ".join(f"{f['file']} {f['bytes'] // 1024} KB" for f in record[key]["files"]))
            browser.close()
    finally:
        server.shutdown()
    RECORD.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
