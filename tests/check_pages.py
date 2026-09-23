"""Every deployed page: zero console errors, no failed requests, every external link 200.

Pages are visited in both themes at desktop and phone width, and held long enough
for the hero to start (it waits up to 2.5 s after load). External links are
collected from the HTML and fetched with a browser user agent, following redirects.
A link that returns 200 only after a redirect is reported with where it landed.

    py tests/check_pages.py            --no-links skips the external fetches
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve, site_pages

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")


def page_file(url: str):
    if url == "/":
        return ROOT / "index.html"
    p = ROOT / (url.lstrip("/") + ".html")
    return p if p.exists() else ROOT / url.lstrip("/") / "index.html"


def external_links() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for url in site_pages():
        html = page_file(url).read_text(encoding="utf-8")
        # Anchors and scripts: what a visitor follows or the page loads. <link> tags
        # (canonical, preconnect) name origins and future URLs, not links.
        for href in re.findall(r'<(?:a|script)\b[^>]*?(?:href|src)="(https?://[^"]+)"', html):
            found.setdefault(href.replace("&amp;", "&"), []).append(url)
    for js in ("assets/hero3d.js",):           # a script-loaded URL is a link too
        for href in re.findall(r'"(https://[^"]+\.js)"', (ROOT / js).read_text(encoding="utf-8")):
            found.setdefault(href, []).append(js)
    return found


def fetch(url: str) -> tuple[int | str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
    except Exception as e:  # noqa: BLE001 - reported
        return type(e).__name__, url


def main() -> int:
    rep = Report("Pages and links")
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme, width in (("light", 1280), ("dark", 390)):
                ctx = browser.new_context(color_scheme=scheme, viewport={"width": width, "height": 900})
                for url in site_pages():
                    page = ctx.new_page()
                    errors: list[str] = []
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on("response", lambda r: errors.append(f"{r.status} {r.url}")
                            if r.status >= 400 else None)
                    page.goto(base + url, wait_until="networkidle")
                    if url == "/":
                        # The hero starts on interaction or 2.5 s after load. Assert it did.
                        page.wait_for_function("document.getElementById('stage').matches('.ready, .static')",
                                               timeout=10000)
                        rep.check(f"{scheme} {width}px /: the hero started (not the static fallback)",
                                  page.evaluate("document.getElementById('stage').classList.contains('ready')"))
                    page.wait_for_timeout(500)
                    rep.check(f"{scheme} {width}px {url}: zero console errors, no failed requests",
                              not errors, "; ".join(errors[:3]))
                    page.close()
                ctx.close()
            browser.close()
    finally:
        server.shutdown()

    if "--no-links" in sys.argv:
        rep.not_run("external links", "skipped with --no-links")
        return rep.finish()
    links = external_links()
    # A pattern that matches nothing would pass every link it never saw: it happened once.
    rep.check("the link scan found the site's external links", len(links) >= 20, f"{len(links)} found")
    for url, where in sorted(links.items()):
        status, final = fetch(url)
        moved = f" -> {final}" if final.rstrip("/") != url.rstrip("/") else ""
        rep.check(f"link {url}", status == 200, f"{status}{moved} (on {', '.join(sorted(set(where)))})")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
