"""The cinematic layer, and the promises that keep it safe for a recruiter.

1. /quick: no script in the file, and it reads in full with JavaScript switched off.
2. Every page with the site header links to /quick.
3. Reduced motion: no Lenis and no motion layer. With motion allowed, both are on
   (the control, so the reduced-motion case cannot pass by the layer never loading).
4. The CDN down: every page still renders its content with no page errors.
5. The intro: once per session, 1.5 s cap under a stalled CDN, Skip, the headline as LCP.

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


INTRO_STATE = """() => ({ on: document.documentElement.classList.contains('intro-on'),
    shown: (() => { const e = document.getElementById('intro'); return !!e && !e.hidden && getComputedStyle(e).display !== 'none'; })(),
    done: !!window.__introDone, t: window.__intro || null })"""


def intro(rep: Report, browser, base: str) -> None:
    """Once per session, capped at 1.5 s even when loading stalls, Skip ends it, and the
    headline underneath is the page's largest paint."""
    # A slow CDN: every jsDelivr response held 3 s. The intro must still end by its cap.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.route(re.compile(r"https://cdn\.jsdelivr\.net/.*"),
              lambda r: (__import__("time").sleep(3), r.continue_()))
    page = ctx.new_page()
    page.add_init_script("""window.__counts = []; new MutationObserver(() => {
        const n = document.getElementById('intro-n'); if (n) window.__counts.push(+n.textContent); })
        .observe(document, { subtree: true, childList: true, characterData: true });
        (function first() { const e = document.getElementById('intro');   // the state it first paints with
          if (!e) return requestAnimationFrame(first);
          requestAnimationFrame(() => { window.__introFirst = { on: document.documentElement.classList.contains('intro-on'),
            shown: !e.hidden && getComputedStyle(e).display !== 'none' }; }); })();
        window.__lcp = []; new PerformanceObserver(l => l.getEntries().forEach(e =>
        window.__lcp.push(e.element ? e.element.tagName : '?'))).observe({ type: 'largest-contentful-paint', buffered: true });""")
    page.goto(base + "/", wait_until="commit")
    page.wait_for_function("window.__introDone === true", timeout=30000)
    first = page.evaluate("window.__introFirst")
    rep.check("first visit: the intro shows", bool(first) and first["on"] and first["shown"], f"{first}")
    s = page.evaluate(INTRO_STATE)
    took = s["t"]["t1"] - s["t"]["t0"]
    rep.check("slow CDN: the intro still ends within 1.5 s (never waits on a stalled load)",
              took <= 1500 and not s["shown"], f"{took:.0f} ms")
    counts = [c for c in page.evaluate("window.__counts") if c == c]
    rep.check("the counter climbs from 0 to 100 without going back",
              bool(counts) and counts[-1] == 100 and counts == sorted(counts) and len(set(counts)) > 5,
              f"{len(counts)} values, last {counts[-1] if counts else None}")
    lcp = page.evaluate("window.__lcp")
    rep.check("the largest paint is the headline, real HTML text under the intro",
              bool(lcp) and lcp[-1] == "H1", f"{lcp}")

    # Same session (same tab): Home again, after another page. No intro.
    page.goto(base + "/about")
    page.goto(base + "/", wait_until="commit")
    page.wait_for_timeout(250)
    again = page.evaluate(INTRO_STATE)
    rep.check("second visit in the session: no intro", not again["on"] and not again["shown"], f"{again}")
    ctx.close()

    # Control: a fresh session shows it again, so "no intro" above is not a broken intro.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(base + "/", wait_until="commit")
    page.wait_for_selector("#intro-skip", state="visible", timeout=3000)
    rep.check("control: a new session shows the intro again", page.evaluate(INTRO_STATE)["shown"])
    page.click("#intro-skip")
    page.wait_for_timeout(60)
    s = page.evaluate(INTRO_STATE)
    rep.check("Skip ends it at once", s["done"] and not s["shown"] and s["t"]["skipped"], f"{s}")
    visible = page.evaluate("getComputedStyle(document.querySelector('.hero h1')).visibility === 'visible'")
    rep.check("after Skip the headline is there", visible)
    ctx.close()

    # Reduced motion: never.
    ctx = browser.new_context(reduced_motion="reduce", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(base + "/", wait_until="commit")
    page.wait_for_timeout(250)
    s = page.evaluate(INTRO_STATE)
    rep.check("reduced motion: no intro", not s["on"] and not s["shown"], f"{s}")
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
            intro(rep, browser, base)
            reduced(rep, browser, base)
            cdn_down(rep, browser, base)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
