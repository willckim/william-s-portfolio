"""The Demos tab and page, and the Work page's Products tab, are easy to find and work everywhere.

    py tests/check_demos_page.py

/demos: six cards, each with a static image, what it is, what to try, and a link
that resolves (a page that answers 200, or a Lab section that exists). The page
loads nothing from demos/, no three.js, no jsPDF, no frame and no module script,
and its images are local files.

Menu: every page with the site header lists Demos between Work and Lab, marked as
the current page on /demos only, on desktop and inside the phone menu.

Work: the Products tab lists both 3D products, shows without JavaScript, and opens
straight to Products at /work#products and on a same-page link to it.

Paths: /demos is the page, while /demos/quote-engine and /demos/lakeview still
serve the raw demos, and /demos/ folds to /demos as every other path does.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve, site_pages

CARDS = ["3D Quote Engine", "Apartment Walkthrough Studio", "Construction Forecast", "Tour Engine",
         "Post-Quantum Readiness calculator", "Grover visualizer"]
DEMO_CODE = re.compile(r"/demos/|three|jspdf|quote-builder|\.glb|\.hdr", re.I)
PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}


def status(url: str) -> tuple[int, str]:
    class Keep(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        with urllib.request.build_opener(Keep).open(url) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "")


def check_cards(rep: Report, browser, base: str) -> None:
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors, urls = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: urls.append(r.url.replace(base, "")))
    page.goto(f"{base}/demos", wait_until="networkidle")
    page.mouse.wheel(0, 4000)                       # bring the lazy images in too
    page.wait_for_load_state("networkidle")
    rep.check("/demos: titled Try it yourself", page.locator("h1").inner_text() == "Try it yourself")
    cards = page.eval_on_selector_all(".demo-card", """cs => cs.map(c => ({
        name: c.querySelector('h2')?.textContent.trim(), img: c.querySelector('img')?.getAttribute('src'),
        alt: c.querySelector('img')?.getAttribute('alt'), what: c.querySelector('.what')?.textContent.trim(),
        tryline: c.querySelector('.try')?.textContent.trim(), href: c.querySelector('a.btn')?.getAttribute('href') }))""")
    rep.check("/demos: one card per live demo, in order", [c["name"] for c in cards] == CARDS, str([c["name"] for c in cards]))
    lab = None
    for c in cards:
        rep.check(f"/demos card {c['name']}: a local still image with alt text, what it is, what to try",
                  bool(c["img"]) and c["img"].startswith("/assets/") and c["img"].endswith(".webp") and bool(c["alt"])
                  and bool(c["what"]) and (c["tryline"] or "").startswith("Try:"), str(c))
        path, _, anchor = (c["href"] or "").partition("#")
        code, body = status(base + path)
        ok = code == 200
        if ok and anchor:
            lab = lab if lab is not None else body
            ok = f'id="{anchor}"' in lab
        rep.check(f"/demos card {c['name']}: its link answers 200 at {c['href']}", ok, f"{code}")
    images = [u for u in urls if u.endswith(".webp")]
    rep.check("/demos: every card image is loaded from this site", len(images) == len(CARDS) and
              all(u.startswith("/assets/") for u in images), str(images))
    code = [u for u in urls if DEMO_CODE.search(u)]
    rep.check("/demos: no demo code, model or frame loads on the page", code == [], str(code[:3]))
    rep.check("/demos: no iframe and no module script", page.evaluate(
        "() => !document.querySelector('iframe, script[type=module]')"))
    rep.check("/demos: no console errors", not errors, str(errors[:3]))
    page.close()


def check_menu(rep: Report, browser, base: str) -> None:
    pages = [u for u in site_pages() if u not in ("/quick", "/copilot", "/copilot-guardrail-card")]
    wrong = []
    for url in pages:
        code, html = status(base + url)
        nav = re.search(r'<ul class="tabs" id="nav">(.*?)</ul>', html, re.S)
        hrefs = re.findall(r'<a href="([^"]+)"', nav.group(1)) if nav else []
        current = re.findall(r'<a href="([^"]+)"[^>]*aria-current="page"', nav.group(1)) if nav else []
        if hrefs[1:4] != ["/work", "/demos", "/lab"] or ("/demos" in current) != (url == "/demos"):
            wrong.append(f"{url}: {hrefs} current {current}")
    rep.check(f"menu: Demos between Work and Lab on all {len(pages)} pages, current only on /demos", not wrong, str(wrong[:3]))
    for label, ctx in (("desktop", {"viewport": {"width": 1280, "height": 800}}), ("phone", PHONE)):
        page = browser.new_page(**ctx)
        page.goto(f"{base}/demos", wait_until="domcontentloaded")
        if label == "phone":
            page.click(".menu-btn")
        link = page.locator('#nav a[href="/demos"]')
        rep.check(f"menu, {label}: Demos is visible and marked current on /demos",
                  link.is_visible() and link.get_attribute("aria-current") == "page")
        page.goto(f"{base}/work", wait_until="domcontentloaded")
        if label == "phone":
            page.click(".menu-btn")
        link = page.locator('#nav a[href="/demos"]')
        rep.check(f"menu, {label}: Demos is visible and not current on /work",
                  link.is_visible() and link.get_attribute("aria-current") is None)
        page.close()


def settled(page, condition: str, seconds: int = 15) -> bool:
    """True once the condition holds. A timeout is a failed check, never a crash that hides the rest."""
    try:
        page.wait_for_function(condition, timeout=seconds * 1000)
        return True
    except Exception:  # noqa: BLE001
        return False


def check_work(rep: Report, browser, base: str) -> None:
    _, html = status(base + "/work")
    panel = re.search(r'<section class="panel" id="products".*?</section>', html, re.S)
    links = re.findall(r'href="(/work/(?:quote-engine|apartment-studio))"', panel.group(0)) if panel else []
    rep.check("Work, Products tab: rows link to both 3D products", sorted(links) == ["/work/apartment-studio", "/work/quote-engine"], str(links))
    page = browser.new_page(java_script_enabled=False)
    page.goto(f"{base}/work")
    rows = page.locator('#products a[href="/work/quote-engine"], #products a[href="/work/apartment-studio"]')
    rep.check("Work without JavaScript: the Products rows are visible", rows.count() == 2 and all(
        rows.nth(i).is_visible() for i in range(rows.count())))
    rep.check("Work without JavaScript: the tab buttons, which cannot work, are hidden", not page.locator(".subtabs").is_visible())
    page.close()
    page = browser.new_page()
    page.goto(f"{base}/work#products", wait_until="domcontentloaded")
    rep.check("/work#products opens straight to Products",
              settled(page, "() => document.getElementById('tab-products').getAttribute('aria-selected') === 'true'")
              and page.locator("#products").is_visible() and not page.locator("#ortho").is_visible())
    page.goto(f"{base}/work", wait_until="domcontentloaded")
    settled(page, "() => document.getElementById('tab-ortho').getAttribute('aria-selected') === 'true'")
    page.evaluate("() => { location.hash = 'products'; }")
    rep.check("Work: a same-page link to #products switches the tab",
              settled(page, "() => !document.getElementById('products').hidden", 5) and page.locator("#products").is_visible())
    page.close()


def check_paths(rep: Report, base: str) -> None:
    code, html = status(base + "/demos")
    rep.check("/demos is the Try it yourself page", code == 200 and "<h1>Try it yourself</h1>" in html, str(code))
    code, where = status(base + "/demos/")
    rep.check("/demos/ folds to /demos like every path", code == 308 and where == "/demos", f"{code} {where}")
    code, html = status(base + "/demos/quote-engine")
    rep.check("/demos/quote-engine still serves the raw demo", code == 200 and "custom-quote-builder" in html, str(code))
    code, html = status(base + "/demos/lakeview")
    rep.check("/demos/lakeview still serves the raw demo", code == 200 and "apartment-walkthrough-studio" in html, str(code))


def main() -> int:
    rep = Report("Demos tab, /demos page and the Products tab")
    base, server = serve()
    try:
        check_paths(rep, base)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            check_cards(rep, browser, base)
            check_menu(rep, browser, base)
            check_work(rep, browser, base)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
