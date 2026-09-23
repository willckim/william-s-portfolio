"""Command palette: opens, filters, navigates, traps focus, closes, and covers the site.

    py tests/check_palette.py
"""

from __future__ import annotations

import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve, site_pages

JS = (ROOT / "assets" / "palette.js").read_text(encoding="utf-8")
INDEX = re.findall(r'\["([^"]+)", "([^"]+)", "([^"]+)", "[^"]*"\]', JS)


def is_open(page) -> bool:
    return page.evaluate("!!document.querySelector('dialog.palette[open]')")


def focused(page) -> str:
    return page.evaluate("document.activeElement.id || document.activeElement.tagName")


def main() -> int:
    rep = Report("Command palette")
    base, server = serve()
    try:
        # Coverage: every deployed page is in the index, and every entry resolves.
        urls = {u for _, _, u in INDEX}
        missing = [p for p in site_pages() if p not in urls and not p.startswith("/copilot-")]
        rep.check("every deployed page is in the index", not missing, f"missing {missing}")
        rep.check("the résumé is in the index", "/resume.pdf" in urls)
        bad = []
        for _, _, u in INDEX:
            path, _, frag = u.partition("#")
            try:
                with urllib.request.urlopen(base + path) as r:
                    body = r.read().decode("utf-8", "ignore") if r.status == 200 else ""
                    if r.status != 200 or (frag and f'id="{frag}"' not in body):
                        bad.append(u)
            except Exception:  # noqa: BLE001 - reported as a bad entry
                bad.append(u)
        rep.check(f"all {len(INDEX)} entries resolve, anchors included", not bad, f"{bad}")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/work/concur")
            page.wait_for_load_state("networkidle")
            rep.check("closed until asked for, and not loaded", not page.evaluate("!!window.Palette"))

            page.keyboard.press("Control+k")
            page.wait_for_selector("dialog.palette[open]")
            rep.check("Ctrl+K opens it with the search field focused", is_open(page) and focused(page) == "pal-q")
            total = page.locator("#pal-list [role=option]").count()
            rep.check("empty query lists the whole index", total == len(INDEX), f"{total} of {len(INDEX)}")

            page.keyboard.type("mosca")
            titles = page.locator("#pal-list .pal-title").all_text_contents()
            rep.check("typing filters the list", titles and titles[0] == "Mosca's inequality calculator"
                      and len(titles) < total, f"{titles}")
            active = page.get_attribute("#pal-q", "aria-activedescendant")
            sel = page.locator("#pal-list [aria-selected=true] .pal-title").all_text_contents()
            rep.check("the first result is the active descendant", bool(active) and sel == [titles[0]])

            for _ in range(3):
                page.keyboard.press("Tab")
            page.keyboard.press("Shift+Tab")
            rep.check("Tab and Shift+Tab stay on the search field", focused(page) == "pal-q", focused(page))

            page.keyboard.press("Escape")
            rep.check("Escape closes it", not is_open(page))

            page.click("[data-palette-open]")
            page.wait_for_selector("dialog.palette[open]")
            rep.check("the header Search button opens it", is_open(page))
            page.keyboard.press("Escape")
            rep.check("closing returns focus to the Search button",
                      page.evaluate("document.activeElement.matches('[data-palette-open]')"))

            page.keyboard.press("Control+k")
            page.keyboard.type("zzqq")
            rep.check("no match says so", page.is_visible(".pal-empty"))
            page.fill("#pal-q", "time tracker")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowUp")
            with page.expect_navigation():
                page.keyboard.press("Enter")
            rep.check("arrows and Enter navigate to the chosen result",
                      page.url.endswith("/work/time-tracker"), page.url)

            page.keyboard.press("Meta+k")
            page.wait_for_selector("dialog.palette[open]")
            rep.check("Cmd+K opens it too", is_open(page))
            page.keyboard.type("grover")
            with page.expect_navigation():
                page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")
            rep.check("a Lab tool result lands on its panel", page.url.endswith("/lab#grover")
                      and page.evaluate("document.getElementById('grover').getBoundingClientRect().top < innerHeight"),
                      page.url)
            # A jump within the page it was opened on must stay at its target: closing
            # the dialog used to hand focus back to the opener and scroll up to it.
            page.goto(base + "/lab")
            page.wait_for_load_state("networkidle")
            page.focus("#m-x")
            page.keyboard.press("Control+k")
            page.wait_for_selector("dialog.palette[open]")
            page.keyboard.type("grover")
            page.keyboard.press("Enter")
            # Sampled until the scroll settles, not once: smooth scrolling takes a moment.
            top, last = None, -1.0
            for _ in range(30):
                page.wait_for_timeout(150)
                top = page.evaluate("document.getElementById('grover').getBoundingClientRect().top")
                if top == last:
                    break
                last = top
            rep.check("a same-page result stays scrolled to its panel", page.url.endswith("/lab#grover")
                      and 0 <= top < 200, f"grover top {top:.0f}px")
            rep.check("no page errors", not errors, "; ".join(errors[:3]))
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
