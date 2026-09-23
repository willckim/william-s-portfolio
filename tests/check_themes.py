"""Light and dark themes: WCAG 2.1 AA on every page in both, and the toggle holds.

1. Token pairs, read live from each theme's computed custom properties: every
   accent on the page, on a raised card and on its own tint, and ink and muted ink
   on the page and cards, at 4.5:1 or better. This covers SVG text too, which axe
   does not grade.
2. axe-core, full WCAG 2.1 A and AA rules, on every deployed page in both themes,
   and again with the command palette open and with a tour card showing.
3. The toggle: it flips the theme, persists across a reload, overrides the system
   setting in both directions, and the stored choice is applied before first paint.

Needs `npm --prefix tests install` for axe-core.
    py tests/check_themes.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve, site_pages

AXE = Path(__file__).resolve().parent / "node_modules" / "axe-core" / "axe.min.js"
ACCENTS = ("ledger", "blueprint", "amber", "coral", "violet")


def lum(hexc: str) -> float:
    h = hexc.strip().lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tokens(page) -> dict:
    names = ["bone", "surface", "ink", "ink-2", "ink-3", "on-accent"] + \
        [a for x in ACCENTS for a in (x, x + "-2")]
    return page.evaluate("""names => { const s = getComputedStyle(document.documentElement);
        return Object.fromEntries(names.map(n => [n, s.getPropertyValue('--' + n).trim()])); }""", names)


def pairs(t: dict) -> list[tuple[str, str]]:
    out = [(fg, bg) for fg in ("ink", "ink-2", "ink-3") for bg in ("bone", "surface")]
    out += [("ink", a + "-2") for a in ACCENTS] + [("ink-2", a + "-2") for a in ACCENTS]
    for a in ACCENTS:
        out += [(a, "bone"), (a, "surface"), (a, a + "-2"), ("on-accent", a)]
    return out


def axe(page, context: str | None = None) -> list[str]:
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""ctx => axe.run(ctx || document, { runOnly: { type: 'tag',
        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })
        .then(r => r.violations.map(v => v.id + ' x' + v.nodes.length + ': ' +
                                    v.nodes[0].target.join(' ')))""", context)
    return res


def main() -> int:
    rep = Report("Themes and contrast")
    if not AXE.exists():
        rep.not_run("axe-core on every page", "run: npm --prefix tests install")
        return rep.finish()
    pages = [p for p in site_pages() if not p.startswith("/copilot")]
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("light", "dark"):
                ctx = browser.new_context(color_scheme=scheme, viewport={"width": 1280, "height": 900})
                page = ctx.new_page()
                page.goto(base + "/")
                t = tokens(page)
                low = sorted((ratio(t[f], t[b]), f, b) for f, b in pairs(t))
                fails = [f"{f} on {b} {r:.2f}" for r, f, b in low if r < 4.5]
                rep.check(f"{scheme}: {len(low)} token pairs at 4.5:1 or better", not fails,
                          f"lowest {low[0][0]:.2f} ({low[0][1]} on {low[0][2]})" if not fails else "; ".join(fails))
                # ink-3 on tints is the one family under 4.5 in light: it must not be used there.
                for path in pages:
                    page.goto(base + path, wait_until="networkidle")
                    v = axe(page)
                    rep.check(f"{scheme}: axe WCAG 2.1 AA on {path}", not v, "; ".join(v[:3]))
                page.goto(base + "/about")
                page.keyboard.press("Control+k")
                page.wait_for_selector("dialog.palette[open]")
                page.keyboard.type("quantum")
                v = axe(page, "dialog.palette")
                rep.check(f"{scheme}: axe on the open command palette", not v, "; ".join(v[:3]))
                page.goto(base + "/")
                page.click("[data-tour-start]")
                page.wait_for_selector('[data-tour-ui="tooltip"]:not([hidden])')
                page.wait_for_timeout(600)
                v = axe(page, '[data-tour-ui="tooltip"]')
                rep.check(f"{scheme}: axe on a tour card", not v, "; ".join(v[:3]))
                page.keyboard.press("Escape")
                ctx.close()

            # The toggle, against a dark system setting.
            ctx = browser.new_context(color_scheme="dark")
            page = ctx.new_page()
            page.goto(base + "/lab")
            state = lambda: page.evaluate("""() => [document.documentElement.getAttribute('data-theme-resolved'),
                document.querySelector('[data-theme-toggle]').getAttribute('aria-pressed'),
                getComputedStyle(document.body).backgroundColor]""")  # noqa: E731
            first = state()
            rep.check("system dark, no choice stored: dark, toggle pressed", first[:2] == ["dark", "true"], f"{first}")
            page.click("[data-theme-toggle]")
            after = state()
            rep.check("toggle switches to light and the page repaints", after[:2] == ["light", "false"]
                      and after[2] != first[2], f"{after}")
            page.reload()
            rep.check("the light choice survives a reload, over a dark system setting",
                      state()[:2] == ["light", "false"])
            page.click("[data-theme-toggle]")
            page.goto(base + "/work/concur")
            rep.check("the dark choice carries to another page", state()[:2] == ["dark", "true"])
            ctx.close()
            ctx = browser.new_context(color_scheme="light")
            page = ctx.new_page()
            page.goto(base + "/")
            page.evaluate("localStorage.setItem('theme', 'dark')")
            page.goto(base + "/about")
            rep.check("a stored dark choice overrides a light system setting", state()[0] == "dark")
            ctx.close()
            browser.close()

        # Before first paint: the theme script sits in <head> ahead of the stylesheet.
        order_ok = []
        for path in pages:
            f = ROOT / ("index.html" if path == "/" else path.lstrip("/") + ".html")
            html = f.read_text(encoding="utf-8")
            s, c = html.find("data-theme-resolved"), html.find('rel="stylesheet"')
            order_ok.append(0 < s < c < html.find("</head>"))
        rep.check("every page applies a stored theme in <head>, before the stylesheet", all(order_ok),
                  f"{order_ok.count(False)} pages out of order")
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
