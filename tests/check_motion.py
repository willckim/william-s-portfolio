"""The cinematic layer, and the promises that keep it safe for a recruiter.

1. /quick: no script in the file, and it reads in full with JavaScript switched off.
2. Every page with the site header links to /quick.
3. Reduced motion: no Lenis and no motion layer. With motion allowed, both are on
   (the control, so the reduced-motion case cannot pass by the layer never loading).
4. The CDN down: every page still renders its content with no page errors.
5. The intro: once per session, 1.5 s cap under a stalled CDN, Skip, the headline as LCP.
6. The story: the particle numbers are the proof strip's values and form their shapes
   (graded against text drawn independently, with a mismatched pairing as the mutant),
   scroll scrubs each chapter, rendering pauses off screen, and reduced motion shows
   all five chapters' captions as a plain list.
7. Work: hover and keyboard previews on desktop, drawn thumbnails on touch, none under
   reduced motion. Case studies: diagrams draw in with every label readable throughout,
   and leave no inline style behind. Titles reveal with their text intact.
8. Keyboard: every story link reachable in order, focus rings everywhere, the cursor
   hidden while tabbing (with a control that it shows for the mouse).
9. Polish: the view transition runs (none under reduced motion), the fallback overlay
   wipes and never leaves a page covered, magnetic buttons, About and Lab reveals.
10. Teardown: reduced motion switched on mid-session reverts everything cleanly, and a
   touch on a hybrid laptop hides the custom cursor.

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

    # Skip, then straight to the keyboard: the first stop in the hero must be fully shown,
    # not focused while its reveal is still at opacity 0.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(base + "/", wait_until="commit")
    page.wait_for_selector("#intro-skip", state="visible", timeout=3000)
    page.wait_for_function("window.gsap && window.__motion && window.__motion.on", timeout=10000)
    page.focus("#intro-skip")
    page.keyboard.press("Enter")
    for _ in range(25):
        page.keyboard.press("Tab")
        if page.evaluate("!!document.activeElement.closest('.hero .btn-row')"):
            break
    shown = page.evaluate("""() => { let o = 1; for (let n = document.activeElement; n && n.nodeType === 1; n = n.parentElement)
        o *= +getComputedStyle(n).opacity; return [document.activeElement.textContent.trim(),
        !!document.activeElement.closest('.hero .btn-row'), o]; }""")
    rep.check("Skip then Tab: the first hero button to take focus is fully shown at once",
              shown[1] and shown[2] == 1, f"{shown}")
    ctx.close()

    # Reduced motion: never.
    ctx = browser.new_context(reduced_motion="reduce", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(base + "/", wait_until="commit")
    page.wait_for_timeout(250)
    s = page.evaluate(INTRO_STATE)
    rep.check("reduced motion: no intro", not s["on"] and not s["shown"], f"{s}")
    ctx.close()


# Draws `text` in the proof strip's own face, independently of the hero's sampler, and
# grades the hero's points against it: the share of points that land on ink, and the
# share of ink that has a point near it. Both are measured in the text's ink box.
SHAPE = """async ({ text, points }) => {
  await document.fonts.load('500 100px "IBM Plex Mono"', text);
  const px = 160, c = document.createElement('canvas'), g = c.getContext('2d');
  g.font = `500 ${px}px "IBM Plex Mono", monospace`;
  const w = Math.ceil(g.measureText(text).width) + 40, h = Math.ceil(px * 1.6);
  c.width = w; c.height = h;
  g.font = `500 ${px}px "IBM Plex Mono", monospace`; g.textBaseline = 'middle'; g.fillText(text, 20, h / 2);
  const d = g.getImageData(0, 0, w, h).data, ink = (x, y) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 100;
  let x0 = w, y0 = h, x1 = 0, y1 = 0;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (ink(x, y)) {
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  const near = (x, y, r) => { for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) if (ink(x + dx, y + dy)) return true; return false; };
  const cell = new Set(); let on = 0; const n = points.length / 2;
  for (let i = 0; i < n; i++) {
    const x = Math.round(x0 + points[2 * i] * (x1 - x0)), y = Math.round(y0 + points[2 * i + 1] * (y1 - y0));
    if (near(x, y, 2)) on++;
    cell.add((x >> 2) + ',' + (y >> 2));
  }
  let total = 0, covered = 0;
  for (let y = y0; y <= y1; y += 3) for (let x = x0; x <= x1; x += 3) if (ink(x, y)) {
    total++;
    let hit = false;
    for (let dy = -1; dy <= 1 && !hit; dy++) for (let dx = -1; dx <= 1 && !hit; dx++)
      if (cell.has(((x >> 2) + dx) + ',' + ((y >> 2) + dy))) hit = true;
    if (hit) covered++;
  }
  return { onInk: on / n, coverage: covered / total, n };
}"""


def story(rep: Report, browser, base: str) -> None:
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(base + "/", wait_until="networkidle")
    page.wait_for_function("window.__hero && window.__hero.fontsReady() && window.__hero.glyphs().length === 3",
                           timeout=20000)
    proof = page.eval_on_selector_all(".proof > a", """e => e.map(a => ({ href: a.getAttribute('href'),
        num: a.querySelector('.num').textContent }))""")
    values = {p["num"]: p["href"] for p in proof}
    glyphs = page.evaluate("window.__hero.glyphs()")
    chapters = page.eval_on_selector_all("[data-glyph]", """e => e.map(h => ({ text: h.textContent.trim(),
        href: h.closest('.ch-card').querySelector('.ch-go').getAttribute('href') }))""")
    texts = [g["text"] for g in glyphs]
    rep.check("the particles draw 36h → 10m, then 95–97%, then 3",
              texts == ["36h → 10m", "95–97%", "3"], f"{texts}")
    rep.check("each particle number is exactly a proof strip value",
              bool(texts) and all(t in values for t in texts), f"proof strip {list(values)}")
    rep.check("each number's chapter links where the proof strip does",
              all(values.get(c["text"]) == c["href"] for c in chapters), f"{chapters}")
    for g in glyphs:
        want = g["text"] if g["text"] in values else None
        if want is None:
            rep.check(f"particle shape of {g['text']!r}", False, "not a proof strip value")
            continue
        m = page.evaluate(SHAPE, {"text": want, "points": g["points"]})
        rep.check(f"particles form {want!r}: points on its ink, ink covered by points",
                  m["onInk"] >= 0.95 and m["coverage"] >= 0.8,
                  f"on ink {m['onInk']:.3f}, coverage {m['coverage']:.3f}, {m['n']} points")
    # Mutant: the same grading, on shapes paired with the wrong text, must fail.
    if len(glyphs) == 3:
        wrong = [page.evaluate(SHAPE, {"text": glyphs[(i + 1) % 3]["text"], "points": g["points"]})
                 for i, g in enumerate(glyphs)]
        rep.check("mutant: every shape graded against another number fails the gate",
                  all(not (m["onInk"] >= 0.95 and m["coverage"] >= 0.8) for m in wrong),
                  "; ".join(f"on {m['onInk']:.2f} cov {m['coverage']:.2f}" for m in wrong))

    # Scrubbing: at each chapter's centre the scroll asks for that chapter's shape, and
    # the particles settle on it. The caption has revealed.
    rep.check("motion on: the stage is sticky, nothing is pinned",
              page.evaluate("getComputedStyle(document.querySelector('.cine-stage')).position") == "sticky"
              and page.evaluate("ScrollTrigger.getAll().every(t => !t.pin)"))
    secs = page.eval_on_selector_all("#story .chapter", """e => e.map(c => [c.getBoundingClientRect().top + scrollY,
        c.offsetHeight, c.dataset.stage])""")
    for i, (top, hh, st) in enumerate(secs):
        want = st.split()
        for k, v in enumerate(want):
            frac = 0.5 if len(want) == 1 else (k + 0.5) / len(want)
            page.evaluate("y => window.scrollTo({ top: y, behavior: 'instant' })", top + hh * frac - 450)
            page.wait_for_timeout(1400)
            got = page.evaluate("[window.__story.stage, window.__hero.shown()]")
            ok = abs(got[0] - float(v)) < 0.01 and abs(got[1] - float(v)) < 0.06
            rep.check(f"chapter {i + 1}, stage {v}: scroll scrubs to it and the particles settle", ok,
                      f"scroll {got[0]:.3f}, drawn {got[1]:.3f}")
        vis = page.evaluate(f"""() => {{ const c = document.querySelectorAll('#story .ch-card')[{i}], s = getComputedStyle(c);
            return s.visibility === 'visible' && +s.opacity === 1; }}""")
        rep.check(f"chapter {i + 1}: its caption has revealed", vis)
    page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: \'instant\' })")
    page.wait_for_timeout(600)
    rep.check("scrolling carries on past the story to the proof strip",
              page.evaluate("document.getElementById('facts').getBoundingClientRect().bottom < innerHeight"))
    ctx.close()

    # Paused off screen, running on screen (phone, where the stage leaves the viewport).
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(base + "/", wait_until="networkidle")
    page.mouse.wheel(0, 10)   # a first sign of a person starts the scene on a phone
    page.wait_for_function("window.__hero && window.__hero.running()", timeout=15000)
    page.wait_for_timeout(900)  # let Lenis finish easing that wheel before jumping
    rep.check("control: on screen, the scene renders", page.evaluate("window.__hero.running()"))
    page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: \'instant\' })")
    page.wait_for_timeout(700)
    rep.check("off screen, the scene stops rendering", not page.evaluate("window.__hero.running()"))
    page.evaluate("window.scrollTo({ top: 0, behavior: \'instant\' })")
    page.wait_for_timeout(700)
    rep.check("back on screen, it renders again", page.evaluate("window.__hero.running()"))
    ctx.close()

    # Reduced motion: no scrub, no Lenis, all five chapters' captions as normal content.
    CAPTIONS = """() => [...document.querySelectorAll('#story .ch-card')].map(c => { const s = getComputedStyle(c);
        return s.visibility === 'visible' && +s.opacity === 1 && c.getBoundingClientRect().height > 0; })"""
    for motion in ("no-preference", "reduce"):
        ctx = browser.new_context(reduced_motion=motion, viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
        page = ctx.new_page()
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(400)
        shown = page.evaluate(CAPTIONS)
        if motion == "reduce":
            state = page.evaluate("""() => ({ story: 'stage' in (window.__story || {}),
                triggers: window.ScrollTrigger ? ScrollTrigger.getAll().length : 0,
                lenis: document.documentElement.classList.contains('lenis'),
                sticky: getComputedStyle(document.querySelector('.cine-stage')).position === 'sticky',
                tall: [...document.querySelectorAll('#story .chapter')].some(c => c.offsetHeight > innerHeight * 0.6) })""")
            rep.check("reduced motion: no scroll scrub, no Lenis, no sticky stage, no screen-tall chapters",
                      not any(state.values()), f"{state}")
            nums = page.eval_on_selector_all("[data-glyph]", """e => e.map(h => { const s = getComputedStyle(h);
                return s.position !== 'absolute' && +s.opacity === 1; })""")
            rep.check(f"reduced motion: all {len(shown)} chapter captions show as normal content, numbers included",
                      len(shown) == 7 and all(shown) and len(nums) == 3 and all(nums), f"{shown} {nums}")
        else:
            rep.check("control, motion on: captions further down wait for their chapter",
                      len(shown) == 7 and not all(shown), f"{shown}")
        ctx.close()


INKED = """sel => { const c = document.querySelector(sel); if (!c || !c.width) return 0;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n / (d.length / 4); }"""


def work(rep: Report, browser, base: str) -> None:
    slugs = ["concur", "royalty", "fast-close", "time-tracker", "consolidation"]
    for motion in ("no-preference", "reduce"):
        ctx = browser.new_context(reduced_motion=motion, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/work", wait_until="networkidle")
        if motion == "no-preference":
            rows = page.eval_on_selector_all(".ix-row", """e => e.map(r => [r.dataset.preview,
                r.querySelector('.ix-link').getAttribute('href')])""")
            rep.check("/work: five Ortho names, each linking its case study, each with a preview",
                      rows == [[s, f"/work/{s}"] for s in slugs]
                      and page.evaluate("window.__previews.names").__len__() == 5, f"{rows}")
            for s in slugs:
                name = page.locator(f'.ix-row[data-preview="{s}"] .ix-name')
                name.scroll_into_view_if_needed()
                b = name.bounding_box()
                page.mouse.move(b["x"] + 40, b["y"] + b["height"] / 2)
                page.mouse.move(b["x"] + 90, b["y"] + b["height"] / 2)
                page.wait_for_timeout(500)
                on = page.evaluate("document.querySelector('.ix-preview.on') !== null")
                ink = page.evaluate(INKED, ".ix-preview canvas")
                rep.check(f"desktop hover on {s}: its live preview shows and draws", on and ink > 0.005
                          and page.evaluate("window.__previews.active()") == s, f"ink {ink:.3f}")
            page.mouse.move(5, 5)
            page.wait_for_timeout(400)
            rep.check("moving off the names hides the preview",
                      page.evaluate("document.querySelector('.ix-preview.on') === null"))
            page.focus('.ix-row[data-preview="royalty"] .ix-link')
            page.keyboard.press("Shift+Tab")
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)
            rep.check("keyboard focus on a name shows its preview too",
                      page.evaluate("window.__previews.active()") == "royalty")
            rep.check("desktop: the inline thumbnails stay hidden",
                      page.evaluate("[...document.querySelectorAll('.ix-thumb')].every(c => !c.offsetParent)"))
        else:
            name = page.locator('.ix-row[data-preview="concur"] .ix-name')
            b = name.bounding_box()
            page.mouse.move(b["x"] + 40, b["y"] + 20)
            page.mouse.move(b["x"] + 90, b["y"] + 20)
            page.wait_for_timeout(400)
            rep.check("reduced motion: no preview follows the cursor",
                      page.evaluate("document.querySelector('.ix-preview.on') === null"))
        rep.check(f"/work ({motion}): no page errors", not errors, "; ".join(errors[:2]))
        ctx.close()

    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(base + "/work", wait_until="networkidle")
    thumbs = []
    for s in slugs:
        page.locator(f'.ix-row[data-preview="{s}"] .ix-thumb').scroll_into_view_if_needed()
        page.wait_for_timeout(350)
        thumbs.append(page.evaluate(INKED, f'.ix-row[data-preview="{s}"] .ix-thumb'))
    rep.check("touch: every row shows its preview inline as a drawn thumbnail",
              all(t > 0.005 for t in thumbs), " ".join(f"{t:.3f}" for t in thumbs))
    ctx.close()


def case_studies(rep: Report, browser, base: str) -> None:
    TEXT = """() => [...document.querySelectorAll('svg.diagram text')].every(t => +getComputedStyle(t).opacity === 1)"""
    STYLED = """() => [...document.querySelectorAll('svg.diagram *')].filter(e => e.getAttribute('style')).length"""
    for motion in ("no-preference", "reduce"):
        ctx = browser.new_context(reduced_motion=motion, viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(base + "/work/concur", wait_until="networkidle")
        heads = page.eval_on_selector_all(".ledger > aside h2", "e => e.map(h => h.textContent)")
        if motion == "reduce":
            rep.check("reduced motion: the diagram is fully drawn from the start, nothing styled over it",
                      page.evaluate(STYLED) == 0 and page.evaluate(TEXT))
            ctx.close()
            continue
        before = page.evaluate("""() => { const b = document.querySelector('svg.diagram .dg-box');
            return getComputedStyle(b).strokeDashoffset; }""")
        page.evaluate("document.querySelector('svg.diagram').scrollIntoView({ block: 'center', behavior: 'instant' })")
        page.wait_for_timeout(350)
        mid_text = page.evaluate(TEXT)
        mid = page.evaluate("""() => [...document.querySelectorAll('svg.diagram .dg-box, svg.diagram .dg-arrow')]
            .some(e => parseFloat(getComputedStyle(e).strokeDashoffset) > 0)""")
        rep.check("the diagram draws itself in as it arrives (strokes mid-trace)", mid and before != "0px",
                  f"offset before arriving {before}")
        rep.check("mid-draw, every label in the diagram is fully readable", mid_text)
        page.wait_for_timeout(2500)
        rep.check("once drawn, the diagram is back to its stylesheet: no leftover inline styles",
                  page.evaluate(STYLED) == 0)
        page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })")
        page.wait_for_timeout(1500)
        after = page.eval_on_selector_all(".ledger > aside h2", """e => e.map(h => [h.textContent,
            getComputedStyle(h).visibility === 'visible', h.querySelectorAll('.t-line').length])""")
        rep.check("section titles revealed, with their text intact and the split undone",
                  [a[0] for a in after] == heads and all(a[1] and a[2] == 0 for a in after), f"{after}")
        ctx.close()


FOCUS = """() => { const e = document.activeElement, s = getComputedStyle(e);
    let o = 1; for (let n = e; n && n.nodeType === 1; n = n.parentElement) o *= +getComputedStyle(n).opacity;
    return { href: e.getAttribute('href'), text: (e.textContent || '').trim().slice(0, 40), opacity: o,
             inStory: !!e.closest('#story'), inProof: !!e.closest('.proof'),
             ring: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2 }; }"""
CURSOR = """() => { const c = document.querySelector('.cursor'); return c ? +getComputedStyle(c).opacity : null; }"""


def keyboard(rep: Report, browser, base: str) -> None:
    """Tab through Home from the top: every link in the story is reachable, in order,
    each stop shows a focus ring, and the custom cursor gets out of the way."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(base + "/", wait_until="networkidle")
    page.mouse.move(700, 450)          # a mouse user, who then reaches for the keyboard
    page.mouse.move(720, 460)
    page.wait_for_timeout(400)
    before = page.evaluate(CURSOR)
    seen, cursor = [], []
    for _ in range(40):
        page.keyboard.press("Tab")
        page.wait_for_timeout(120)
        f = page.evaluate(FOCUS)
        seen.append(f)
        cursor.append(page.evaluate(CURSOR))
        if f["inProof"]:
            break
    story = [f["href"] for f in seen if f["inStory"]]
    want = ["/work/concur", "/work/concur#results-h", "/work#ortho", "/lab", "/work", "/resume.pdf", "/contact"]
    rep.check("keyboard: Tab reaches every story link, in order, before the proof strip",
              story == want and seen[-1]["inProof"], f"{story}")
    faint = [f["text"] or f["href"] for f in seen if f["opacity"] < 1]
    rep.check("keyboard: whatever takes focus is fully shown, not left mid-reveal", bool(seen) and not faint,
              f"faint: {faint[:4]}")
    # Focus that lands before its card has scrolled into view (no scroll at all): the
    # card must still finish revealing, not freeze at the opacity it started from.
    page.goto(base + "/", wait_until="networkidle")          # fresh: no card revealed yet
    fresh = page.evaluate("+getComputedStyle(document.querySelector('.ch-end .ch-card')).opacity")
    page.evaluate("document.querySelector('.ch-end .btn').focus({ preventScroll: true })")
    page.wait_for_timeout(300)
    card = page.evaluate("+getComputedStyle(document.querySelector('.ch-end .ch-card')).opacity")
    rep.check("focus reaching a card before its reveal finishes the reveal", fresh < 1 and card == 1,
              f"opacity {fresh} before focus, {card} after")
    no_ring = [f["text"] or f["href"] for f in seen if not f["ring"]]
    rep.check(f"keyboard: all {len(seen)} stops show a 2px focus ring", bool(seen) and not no_ring,
              f"without: {no_ring[:4]}")
    rep.check("control: the custom cursor shows for the mouse", before is not None and before > 0,
              f"opacity {before}")
    rep.check("keyboard: the custom cursor hides while tabbing, so it never covers focus",
              before is not None and all(c == 0 for c in cursor), f"opacities {sorted(set(map(str, cursor)))}")
    ctx.close()


INLINE = """() => [...document.querySelectorAll('.hero .copy, .hero .copy *, #story, #story *')]
    .map((e, i) => [i, e.getAttribute('style') || '']).filter(r => /opacity|transform|visibility/.test(r[1]))"""


def teardown(rep: Report, browser, base: str) -> None:
    """Reduced motion switched on mid-session tears the motion layer down completely:
    focus arriving afterwards must not replay a reveal the switch has already undone.
    And a touch on a hybrid laptop (fine pointer present) hides the custom cursor.

    Seen failing against the code before its fix (2026-09-27): the story's scrub tween
    threw mid-revert, which aborted the teardown and left Lenis, the cursor and the
    hero copy at opacity 0. The focus listeners that outlived the teardown showed no
    visible effect on their own, so this grades the revert, not the listener cleanup."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/", wait_until="networkidle")
    page.mouse.move(700, 450)
    page.mouse.move(720, 460)
    page.wait_for_timeout(300)
    shown = page.evaluate(CURSOR)
    page.evaluate("""window.dispatchEvent(new PointerEvent('pointerdown',
        { pointerType: 'touch', clientX: 300, clientY: 300, bubbles: true }))""")
    page.wait_for_timeout(100)
    touched = page.evaluate(CURSOR)
    rep.check("hybrid laptop: a touch hides the custom cursor (shown for the mouse first)",
              shown is not None and shown > 0 and touched == 0, f"opacity {shown} then {touched}")

    page.goto(base + "/", wait_until="networkidle")          # fresh: cards still waiting to reveal
    page.emulate_media(reduced_motion="reduce")
    page.wait_for_timeout(400)
    off = page.evaluate("!window.__motion.on && !document.querySelector('.cursor')")
    before = page.evaluate(INLINE)
    for sel in (".hero .btn-row .btn", ".ch-end .btn"):
        page.evaluate(f"document.querySelector('{sel}').focus({{ preventScroll: true }})")
        page.wait_for_timeout(250)
    after = page.evaluate(INLINE)
    rep.check("reduced motion switched on mid-session: the motion layer and cursor are gone", off)
    rep.check("after that switch, focus replays no reveal (no inline motion styles come back)",
              off and after == before and not errors, f"{len(before)} styled before focus, {len(after)} after, errors {errors[:2]}")
    ctx.close()


def polish(rep: Report, browser, base: str) -> None:
    # Page transitions: a native view transition where supported, none under reduced motion.
    for motion in ("no-preference", "reduce"):
        ctx = browser.new_context(reduced_motion=motion, viewport={"width": 1280, "height": 800})
        ctx.add_init_script("""addEventListener('pagereveal', e => { window.__vt = !!e.viewTransition; });
            try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}""")
        page = ctx.new_page()
        page.goto(base + "/about", wait_until="networkidle")
        with page.expect_navigation():
            page.click('#nav a[href="/work"]')
        page.wait_for_load_state("networkidle")
        vt = page.evaluate("window.__vt")
        if motion == "reduce":
            rep.check("reduced motion: pages change with no transition", vt is False and page.url.endswith("/work"))
        else:
            rep.check("page change runs the ledger-line view transition", vt is True and page.url.endswith("/work"),
                      f"viewTransition {vt}")
        ctx.close()

    # The fallback overlay, for browsers without cross-document view transitions.
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.add_init_script("window.__noViewTransitions = true; try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(base + "/about", wait_until="networkidle")
    # Every clip the overlay passes through is kept in session storage, which outlives the page.
    page.evaluate("""() => { const w = document.querySelector('.page-wipe');
        new MutationObserver(() => { const k = JSON.parse(sessionStorage.getItem('wipe') || '[]');
            k.push(w.style.clipPath); sessionStorage.setItem('wipe', JSON.stringify(k)); }).observe(w, { attributes: true }); }""")
    with page.expect_navigation():
        page.click('#nav a[href="/lab"]')
    page.wait_for_load_state("load")
    clips = page.evaluate("JSON.parse(sessionStorage.getItem('wipe') || '[]')")
    covered = [float(c.split()[1].rstrip("%")) for c in clips if c.startswith("inset(")]
    rep.check("fallback: the overlay wipes across, left to right, before the next page loads",
              page.url.endswith("/lab") and len(covered) > 3 and covered == sorted(covered, reverse=True)
              and covered[-1] < 1, f"{len(covered)} frames, right inset {covered[:1]} to {covered[-1:]}")
    page.go_back()
    page.wait_for_load_state("load")
    left = page.evaluate("(() => { const w = document.querySelector('.page-wipe'); return w ? getComputedStyle(w).visibility : 'none'; })()")
    rep.check("fallback: back to a page, it is not left covered", left in ("hidden", "none"), left)
    ctx.close()

    # In-page links glide there and take keyboard focus with them, as a native jump would.
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(base + "/lab", wait_until="networkidle")
    page.focus('.jump a[href="#pqc"]')
    page.keyboard.press("Enter")
    page.wait_for_timeout(1800)
    state = page.evaluate("""() => ({ top: Math.round(document.getElementById('pqc').getBoundingClientRect().top),
        hash: location.hash, inside: document.getElementById('pqc').contains(document.activeElement),
        shown: +getComputedStyle(document.getElementById('pqc')).opacity })""")
    page.keyboard.press("Tab")
    next_in = page.evaluate("document.getElementById('pqc').contains(document.activeElement)")
    rep.check("an in-page link scrolls to its target and the next Tab continues from there",
              0 <= state["top"] <= 100 and state["hash"] == "#pqc" and state["shown"] == 1 and next_in,
              f"{state}, next Tab inside {next_in}")
    ctx.close()

    # Magnetic primary buttons, and the reveals on About and Lab.
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.add_init_script("try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(base + "/", wait_until="networkidle")
    b = page.locator(".hero .btn.primary").bounding_box()
    page.mouse.move(b["x"] + b["width"] - 4, b["y"] + b["height"] - 4)
    page.mouse.move(b["x"] + b["width"] - 2, b["y"] + b["height"] - 2)
    page.wait_for_timeout(500)
    pulled = page.evaluate("gsap.getProperty(document.querySelector('.hero .btn.primary'), 'x')")
    page.mouse.move(5, 5)
    page.wait_for_timeout(1200)
    back = page.evaluate("gsap.getProperty(document.querySelector('.hero .btn.primary'), 'x')")
    rep.check("the primary button leans toward the pointer and springs back", pulled > 3 and abs(back) < 0.5,
              f"x {pulled:.1f} then {back:.1f}")
    for path, sel in (("/about", "main .ledger"), ("/lab", "main .lab-panel")):
        page.goto(base + path, wait_until="networkidle")
        waiting = page.evaluate(f"[...document.querySelectorAll('{sel}')].filter(s => +getComputedStyle(s).opacity < 1).length")
        focusable = page.evaluate(f"""[...document.querySelectorAll('{sel}')].every(s => getComputedStyle(s).visibility === 'visible')""")
        page.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })")
        page.wait_for_timeout(1400)
        page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
        page.wait_for_timeout(300)
        settled = page.evaluate(f"""[...document.querySelectorAll('{sel}')].every(s => +getComputedStyle(s).opacity === 1
            && !s.style.transform && !s.style.filter)""")
        rep.check(f"{path}: sections fade in as they arrive, stay focusable meanwhile, and settle clean",
                  waiting > 0 and focusable and settled, f"{waiting} waiting at load")
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
            story(rep, browser, base)
            work(rep, browser, base)
            case_studies(rep, browser, base)
            keyboard(rep, browser, base)
            polish(rep, browser, base)
            teardown(rep, browser, base)
            reduced(rep, browser, base)
            cdn_down(rep, browser, base)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
