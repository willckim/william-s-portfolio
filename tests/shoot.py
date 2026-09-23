"""Screenshots for a human look: py tests/shoot.py /work/concur [/lab ...] [--dark] [--mobile]

Writes PNGs to tests/shots/ (git-ignored). Prints console errors it saw.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from sitekit import serve

OUT = Path(__file__).resolve().parent / "shots"


def main() -> int:
    paths = [a for a in sys.argv[1:] if a.startswith("/")] or ["/"]
    dark = "--dark" in sys.argv
    mobile = "--mobile" in sys.argv
    full = "--viewport" not in sys.argv
    OUT.mkdir(exist_ok=True)
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            size = {"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900}
            ctx = browser.new_context(viewport=size, color_scheme="dark" if dark else "light",
                                      device_scale_factor=1)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            for path in paths:
                page.goto(base + path, wait_until="networkidle")
                page.wait_for_timeout(600)
                name = (path.strip("/").replace("/", "_") or "home") + ("_dark" if dark else "") \
                    + ("_m" if mobile else "") + ".png"
                page.screenshot(path=str(OUT / name), full_page=full)
                print("shot", OUT / name)
            browser.close()
            for e in errors:
                print("console error:", e)
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
