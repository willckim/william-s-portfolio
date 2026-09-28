"""No fixed or sticky layer covers page content once a visitor has scrolled to the end.

Every page, both themes, at phone and desktop width, with motion allowed: scroll to
the bottom, then hit-test a grid of points across the viewport. A point fails when
the topmost thing painted there belongs to a fixed or sticky element other than the
page's own header, and a piece of content (text, a link, a control, an image) lies
underneath it. Hit testing follows real paint order, so a layer behind the content
(the Home stage behind the story) passes, and one on top of it does not.

Pointer events are forced on for the probe only: an overlay with pointer-events: none
still covers what is under it, and would otherwise be invisible to the hit test.

Controls, so a pass means the probe could see: an injected fixed band over the
content must be caught, and so must the Home stage with the rule that let it
outlive the story (margin-bottom: -100vh on a sticky element) put back. That one is
desktop only: on a phone the old stage had scrolled away by the bottom of the page.

    py tests/check_layers.py
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from sitekit import Report, serve, site_pages

SIZES = {"phone": {"width": 390, "height": 844}, "desktop": {"width": 1336, "height": 768}}
STEP = 16   # px between probe points

PROBE = """(step) => {
  const desc = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') +
    (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/).join('.') : '');
  const pos = e => getComputedStyle(e).position;
  const isHeader = e => e.tagName === 'HEADER' && !e.parentElement.closest('main, article, section, aside');
  const layerOf = e => {
    for (let n = e; n && n !== document.body; n = n.parentElement)
      if (/^(fixed|sticky)$/.test(pos(n))) return isHeader(n) ? null : n;
    return null;
  };
  const opaque = (e, stop) => {
    for (let n = e; n; n = n.parentElement) {
      if (parseFloat(getComputedStyle(n).opacity) === 0) return false;
      if (n === stop) break;
    }
    return true;
  };
  const CONTENT = 'a, button, input, select, textarea, img, svg, canvas, video, h1, h2, h3, h4, h5, h6, ' +
                  'p, li, dt, dd, td, th, label, figcaption, blockquote, pre';
  const force = document.createElement('style');
  force.textContent = '*, *::before, *::after { pointer-events: auto !important; }';
  document.head.appendChild(force);
  const hits = {}, seen = new Set();
  let points = 0, onContent = 0;
  try {
    for (let y = step / 2; y < innerHeight; y += step) {
      for (let x = step / 2; x < innerWidth; x += step) {
        const stack = document.elementsFromPoint(x, y);
        if (!stack.length) continue;
        points++;
        const top = stack[0], layer = layerOf(top);
        if (stack.some(e => e.matches(CONTENT) && !layerOf(e))) onContent++;
        if (!layer || !opaque(top, layer)) continue;
        const under = stack.find(e => !layer.contains(e) && !e.contains(layer) && e.matches(CONTENT));
        if (!under) continue;
        const key = desc(layer);
        hits[key] = hits[key] || { points: 0, covers: [] };
        hits[key].points++;
        const c = desc(under);
        if (!seen.has(key + c) && hits[key].covers.length < 4) { seen.add(key + c); hits[key].covers.push(c); }
      }
    }
  } finally {
    force.remove();
  }
  return { points, onContent, hits };
}"""

BAND = """() => {
  const b = document.createElement('div');
  b.id = 'probe-band';
  b.style.cssText = 'position:fixed;left:0;right:0;top:0;height:45vh;z-index:10;pointer-events:none;' +
                    'background:linear-gradient(90deg,#1b4d3a,#1a2640)';
  document.body.appendChild(b);
}"""

# The rule that caused the bug: a sticky stage with a negative bottom margin, which
# lets it stay stuck up to a screen past the end of the story.
OLD_STAGE = """() => {
  const s = document.createElement('style');
  s.textContent = '.cine { display: block !important; } ' +
    '.cine-stage { grid-area: auto !important; align-self: auto !important; margin-bottom: -100vh !important; }';
  document.head.appendChild(s);
}"""


def to_bottom(page) -> tuple[int, int]:
    """Scroll to the end and wait until it stays there (Lenis and late layout settle)."""
    last = -1
    for _ in range(30):
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(250)
        y = page.evaluate("Math.round(scrollY)")
        if y == last:
            break
        last = y
    page.wait_for_timeout(400)
    return page.evaluate("[Math.round(scrollY), document.documentElement.scrollHeight - innerHeight]")


def settle(page, url: str) -> None:
    page.wait_for_function("!document.documentElement.classList.contains('intro-on')", timeout=8000)
    if url == "/":
        page.wait_for_function("document.getElementById('stage').matches('.ready, .static')", timeout=10000)


def grade(rep: Report, name: str, page, expect_clear: bool, want: str = "") -> None:
    y, end = to_bottom(page)
    if y < end - 1:
        rep.check(f"{name}: reached the bottom", False, f"scrollY {y} of {end}")
        return
    r = page.evaluate(PROBE, STEP)
    if not r["onContent"]:
        rep.not_run(name, f"no content under any of {r['points']} probe points")
        return
    detail = "; ".join(f"{k} covers {', '.join(v['covers'])} at {v['points']} points" for k, v in r["hits"].items())
    if expect_clear:
        rep.check(name, not r["hits"], detail or f"{r['onContent']} of {r['points']} points on content, none covered")
    else:
        rep.check(name, any(want in k for k in r["hits"]), detail or "nothing caught")


def main() -> int:
    rep = Report("Layers at the bottom of every page")
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for size, vp in SIZES.items():
                for scheme in ("light", "dark"):
                    ctx = browser.new_context(viewport=vp, color_scheme=scheme, reduced_motion="no-preference",
                                              is_mobile=size == "phone", has_touch=size == "phone")
                    for url in site_pages():
                        page = ctx.new_page()
                        page.goto(base + url, wait_until="load")
                        settle(page, url)
                        # /quick, /copilot and the card theme by media query alone, with no attribute.
                        resolved = page.evaluate("document.documentElement.getAttribute('data-theme-resolved')")
                        if resolved not in (None, scheme):
                            rep.check(f"{size} {scheme} {url}: theme applied", False, f"resolved {resolved}")
                        else:
                            grade(rep, f"{size} {scheme} {url}: only the header overlaps content", page, True)
                        page.close()
                    ctx.close()

            # Controls: the probe must catch a layer over the content, pointer-events or not.
            for size, vp in SIZES.items():
                ctx = browser.new_context(viewport=vp, color_scheme="dark", reduced_motion="no-preference",
                                          is_mobile=size == "phone", has_touch=size == "phone")
                page = ctx.new_page()
                page.goto(base + "/about", wait_until="load")
                settle(page, "/about")
                page.evaluate(BAND)
                grade(rep, f"control, {size} /about: an injected fixed band (pointer-events: none) is caught",
                      page, False, "div#probe-band")
                # On a phone the content after the story is taller than a screen, so the old
                # stage had already scrolled away by the bottom: it is a desktop-only control.
                if size == "desktop":
                    page.goto(base + "/", wait_until="load")
                    settle(page, "/")
                    page.evaluate(OLD_STAGE)
                    grade(rep, f"control, {size} /: the old sticky stage (margin-bottom: -100vh) is caught",
                          page, False, "div.cine-stage")
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
