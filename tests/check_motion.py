"""The cinematic layer, and the promises that keep it safe for a recruiter.

1. /quick: no script in the file, and it reads in full with JavaScript switched off.
2. Every page with the site header links to /quick.
3. Reduced motion: no Lenis and no motion layer. With motion allowed, both are on
   (the control, so the reduced-motion case cannot pass by the layer never loading).
4. The CDN down: every page still renders its content with no page errors.

Every guard is run on a case where it must pass as well as where it must fail.

    py tests/check_motion.py
"""

from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve, site_pages

HEADERLESS = {"/quick", "/copilot-guardrail-card"}   # /quick has its own; the card is a printable sheet


def page_file(url: str):
    if url == "/":
        return ROOT / "index.html"
    p = ROOT / (url.lstrip("/") + ".html")
    return p if p.exists() else ROOT / url.lstrip("/") / "index.html"


def quick(rep: Report, browser, base: str) -> None:
    html = page_file("/quick").read_text(encoding="utf-8")
    rep.check("/quick: no <script> anywhere in the file", "<script" not in html.lower())
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 800})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(base + "/quick", wait_until="load")
    heads = page.eval_on_selector_all("main h2", "e => e.map(x => x.textContent.trim())")
    rep.check("/quick, JavaScript off: summary, Ortho, projects, credentials, contact",
              heads == ["At Ortho", "Projects", "Credentials", "Contact"], f"{heads}")
    cases = page.eval_on_selector_all("main .items h3 a", "e => e.map(x => x.getAttribute('href'))")
    rep.check("/quick, JavaScript off: all five Ortho items link their case studies",
              sorted(cases) == sorted({"/work/concur", "/work/royalty", "/work/fast-close",
                                            "/work/time-tracker", "/work/consolidation"}), f"{cases}")
    rep.check("/quick, JavaScript off: the résumé link is there", page.locator("a[href='/resume.pdf']").count() > 0)
    nums = page.eval_on_selector_all(".proof .num", "e => e.map(x => x.textContent)")
    rep.check("/quick: the proof strip's four numbers, as on Home", nums == ["36h → 10m", "95–97%", "~40 hrs", "3"],
              f"{nums}")
    rep.check("/quick: no console errors", not errors, "; ".join(errors[:3]))
    ctx.close()


def without_quick(pages: dict[str, str]) -> list[str]:
    """Pages whose header has no link to /quick."""
    out = []
    for url, html in pages.items():
        head = re.search(r"<header\b.*?</header>", html, re.S)
        if not head or 'href="/quick"' not in head.group(0):
            out.append(url)
    return out


def header_links(rep: Report) -> None:
    pages = {u: page_file(u).read_text(encoding="utf-8") for u in site_pages() if u not in HEADERLESS}
    missing = without_quick(pages)
    rep.check(f"all {len(pages)} pages with the site header link to Quick view", len(pages) >= 11 and not missing,
              f"missing on {missing}")
    # Control: the same scan, on a copy of Home with the link removed, must report it.
    stripped = pages["/"].replace('href="/quick"', 'href="/"')
    rep.check("control: the scan reports a header without the link", without_quick({"/": stripped}) == ["/"])


def reduced(rep: Report, browser, base: str) -> None:
    for motion in ("no-preference", "reduce"):
        ctx = browser.new_context(reduced_motion=motion, viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(base + "/about", wait_until="networkidle")
        state = page.evaluate("""() => ({ lenis: document.documentElement.classList.contains('lenis'),
            motion: !!(window.__motion && window.__motion.on), gsap: !!window.gsap })""")
        if motion == "reduce":
            rep.check("reduced motion: Lenis and the motion layer are off",
                      state["gsap"] and not state["lenis"] and not state["motion"], f"{state}")
        else:
            rep.check("control, motion allowed: Lenis and the motion layer are on",
                      state["lenis"] and state["motion"], f"{state}")
        ctx.close()


def cdn_down(rep: Report, browser, base: str) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.route(re.compile(r"https://cdn\.jsdelivr\.net/.*"), lambda r: r.abort())
    for url in ("/", "/work", "/work/concur", "/lab", "/about"):
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + url, wait_until="load")
        page.wait_for_timeout(2600)
        visible = page.evaluate("""() => { const h = document.querySelector('main h1');
            const s = h && getComputedStyle(h); return !!h && s.visibility === 'visible' && +s.opacity === 1
            && h.getBoundingClientRect().height > 0; }""")
        rep.check(f"CDN down, {url}: the headline shows and no page errors", visible and not errors,
                  "; ".join(errors[:2]))
        page.close()
    ctx.close()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rep = Report("Motion layer")
    header_links(rep)
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            quick(rep, browser, base)
            reduced(rep, browser, base)
            cdn_down(rep, browser, base)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
