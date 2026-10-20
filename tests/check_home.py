"""Home's Try it yourself section and Now block, and the One Website Project wording site-wide.

    py tests/check_home.py

Try it yourself: right below the proof strip, three cards in the brief's order, each
with a local still image, what it is, what to try, and a link that answers 200, then a
See all demos link to /demos. Home loads no demo code for it: nothing from demos/, no
3D model or environment file, no jsPDF, no frame. The hero's own three.js is not demo
code and is not judged here.

Now: exactly the three lines of the brief. One Website Project: every place it is
described says it is in progress, with ongoing improvements through 2027 (the old
launch date is a copy rule in check_copy). About says the VP of Accounting selected
William to lead the team's automation work.

Every expected value here is copied from the brief of 2026-10-20, not read off the pages.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from sitekit import Report, serve

CARDS = [("Construction Forecast", "/lab#construction"), ("3D Quote Engine", "/work/quote-engine"),
         ("Apartment Walkthrough Studio", "/work/apartment-studio")]
NOW = [("CPA exams", "January 2027"),
       ("One Website Project", "In progress, with ongoing improvements through 2027"),
       ("Recently shipped", "3D Quote Engine and Apartment Walkthrough Studio, both live on this site.")]
ONGOING = "in progress, with ongoing improvements through 2027"
# Where the One Website Project is described, and the element that describes it there.
ONE_WEBSITE = {"/": ".now", "/about": "main", "/work": '.ix-row[data-preview="consolidation"]',
               "/work/consolidation": "main", "/quick": 'li:has(a[href="/work/consolidation"])'}
SELECTED = "the VP of Accounting selected me to lead the team's automation work"
DEMO_CODE = re.compile(r"/demos/|\.(?:glb|gltf|hdr|ktx2|exr)(?:\?|$)|jspdf|quote-builder", re.I)
PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}


def status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def link_ok(base: str, href: str) -> tuple[bool, str]:
    path, _, anchor = (href or "").partition("#")
    code, body = status(base + path)
    return code == 200 and (not anchor or f'id="{anchor}"' in body), str(code)


def open_home(browser, ctx_args: dict):
    ctx = browser.new_context(**ctx_args)
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    errors, urls = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: urls.append(r.url))
    return ctx, page, errors, urls


def check_try(rep: Report, browser, base: str, label: str, ctx_args: dict) -> None:
    ctx, page, errors, urls = open_home(browser, ctx_args)
    page.goto(base + "/", wait_until="networkidle")
    section = page.locator("#try")
    if section.count() != 1:
        rep.check(f"Home, {label}: a Try it yourself section", False, "no #try on Home")
        ctx.close()
        return
    rep.check(f"Home, {label}: the section sits right below the proof strip", page.evaluate(
        "() => document.getElementById('facts').nextElementSibling === document.getElementById('try')"))
    rep.check(f"Home, {label}: titled Try it yourself", section.locator("h2").first.inner_text().strip() == "Try it yourself")
    section.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    page.wait_for_load_state("networkidle")
    cards = page.eval_on_selector_all("#try .demo-card", """cs => cs.map(c => ({
        name: c.querySelector('h3')?.textContent.trim(), img: c.querySelector('img')?.getAttribute('src'),
        alt: c.querySelector('img')?.getAttribute('alt'), what: c.querySelector('.what')?.textContent.trim(),
        tryline: c.querySelector('.try')?.textContent.trim(), href: c.querySelector('a.btn')?.getAttribute('href'),
        shown: c.getBoundingClientRect().height > 0 }))""")
    rep.check(f"Home, {label}: three cards in order", [(c["name"], c["href"]) for c in cards] == CARDS, str(cards))
    for c in cards:
        rep.check(f"Home, {label}, card {c['name']}: a local still image with alt text, what it is, what to try",
                  (c["img"] or "").startswith("/assets/") and c["img"].endswith(".webp") and bool(c["alt"])
                  and bool(c["what"]) and (c["tryline"] or "").startswith("Try:") and c["shown"], str(c))
    images = sorted(u.replace(base, "") for u in urls if u.endswith(".webp"))
    rep.check(f"Home, {label}: the three card images load from this site",
              images == sorted(c["img"] for c in cards), str(images))
    more = page.locator('#try a[href="/demos"]')
    rep.check(f"Home, {label}: ends with a See all demos link to /demos",
              more.count() == 1 and more.inner_text().strip() == "See all demos" and more.is_visible()
              and page.evaluate("() => { const a = document.querySelector('#try a[href=\"/demos\"]'); "
                                "return [...document.querySelectorAll('#try a')].pop() === a; }"))
    code = [u for u in urls if DEMO_CODE.search(u)]
    rep.check(f"Home, {label}: no demo code, model or frame loads", code == [] and page.evaluate(
        "() => !document.querySelector('iframe')"), str(code[:3]))
    rep.check(f"Home, {label}: no console errors", not errors, str(errors[:3]))
    ctx.close()


def check_links(rep: Report, base: str) -> None:
    for name, href in CARDS + [("See all demos", "/demos")]:
        ok, code = link_ok(base, href)
        rep.check(f"Home link {name}: answers 200 at {href}", ok, code)


def check_now(rep: Report, browser, base: str) -> None:
    page = browser.new_page()
    page.goto(base + "/", wait_until="domcontentloaded")
    items = page.eval_on_selector_all(".now li", """ls => ls.map(l => [l.querySelector('strong').textContent.trim(),
        l.querySelector('span:last-child').textContent.trim()])""")
    rep.check("Home, Now: CPA exams, the One Website Project and what shipped, nothing else",
              [tuple(i) for i in items] == NOW, str(items))
    for url, where in ONE_WEBSITE.items():
        page.goto(base + url, wait_until="domcontentloaded")
        el = page.locator(where).first
        text = re.sub(r"\s+", " ", el.text_content() if el.count() else "")
        rep.check(f"{url}: the One Website Project is in progress, with ongoing improvements through 2027",
                  ONGOING in text.lower() and "One Website Project" in text, text[:120])
    page.goto(base + "/about", wait_until="domcontentloaded")
    rep.check("/about: the VP of Accounting selected William to lead the team's automation work",
              SELECTED in re.sub(r"\s+", " ", page.locator("main").text_content()))
    page.close()


def main() -> int:
    rep = Report("Home: Try it yourself, Now, and the One Website Project")
    base, server = serve()
    try:
        check_links(rep, base)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            check_try(rep, browser, base, "desktop", {"viewport": {"width": 1280, "height": 900}})
            check_try(rep, browser, base, "phone", PHONE)
            check_now(rep, browser, base)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
