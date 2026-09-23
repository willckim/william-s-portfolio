"""Tour Engine on this site: the tour completes end to end, and the recorder is off.

The tour is driven the way a person would: Next on a card, or a click on the thing
the card points at (a tab link, a preset button, the Menu button on a phone). It
crosses real page loads, so each run also proves resume works through the host
adapter's page-as-tab mapping. Run at desktop and phone widths.

The recorder check is graded twice: against the deployed engine (must NOT record)
and against the unpatched engine from a tour-engine checkout (MUST record), so a
check that could not see the recorder at all would fail the second half.

    py tests/check_tour.py            TOUR_ENGINE_SRC=<checkout> for the second half
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

EXPECTED = [  # (page, card title) for the seven authored steps, in order
    ("home", "Five tabs, the whole site"),
    ("home", "Every number has a source"),
    ("work", "Five projects, five case studies"),
    ("case-concur", "The model suggests, a person decides"),
    ("lab", "Try the calculator"),
    ("lab", "Which records are exposed"),
    ("contact", "That is the tour"),
]
SRC = os.environ.get("TOUR_ENGINE_SRC")


def state(page) -> dict | None:
    try:
        return page.evaluate("""() => {
            if (!window.Tour) return null;
            const s = Tour.state();
            const tip = document.querySelector('[data-tour-ui="tooltip"]');
            s.shown = !!tip && !tip.hidden && tip.getBoundingClientRect().height > 0;
            s.title = tip ? (tip.querySelector('.tour-tip__title') || {}).textContent : null;
            s.page = document.body.dataset.page;
            s.next = !!(tip && tip.querySelector('.tour-btn-next'));
            return s; }""")
    except Exception:  # noqa: BLE001 - mid-navigation, the context is gone; ask again
        return None


def wait_card(page, last: tuple | None, ms: int = 15000) -> dict | None:
    """The next card that is on screen and different from the last one handled."""
    for _ in range(ms // 100):
        s = state(page)
        if s and s["active"] and s["shown"] and (s["page"], s["index"], s["title"]) != last:
            page.wait_for_timeout(250)          # let the cursor land; a person would too
            return state(page)
        if s and not s["active"] and last and last[2] == EXPECTED[-1][1]:
            return s
        page.wait_for_timeout(100)
    return None


def drive(browser, base: str, width: int, start_path: str, rep: Report, label: str) -> None:
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(base + start_path)
    page.click("[data-tour-start]")
    authored, cards, timeouts, last = [], 0, 0, None
    for _ in range(40):
        s = wait_card(page, last)
        if s is None:
            rep.check(f"{label}: tour reached the end", False,
                      f"stuck after {authored[-1] if authored else 'start'}")
            break
        if not s["active"]:
            break
        cards += 1
        timeouts += bool(s["timedOut"])
        last = (s["page"], s["index"], s["title"])
        if (s["page"], s["title"]) in EXPECTED:
            authored.append((s["page"], s["title"]))
        if s["next"]:
            page.click('[data-tour-ui="tooltip"] .tour-btn-next')
        else:
            page.click(s["sel"])            # a tab guide, Menu, or the preset button
    final = state(page)
    rep.check(f"{label}: all seven authored steps shown in order", authored == EXPECTED,
              f"{len(authored)} of 7 via {cards} cards")
    rep.check(f"{label}: tour ended on Contact with no step left", bool(final) and not final["active"]
              and final["page"] == "contact")
    rep.check(f"{label}: no step fell back to 'could not find'", timeouts == 0, f"{timeouts}")
    rep.check(f"{label}: no saved place left behind",
              page.evaluate("sessionStorage.getItem('tour.resume')") is None)
    rep.check(f"{label}: zero console errors", not errors, "; ".join(errors[:3]))
    ctx.close()


def recorder_runs(browser, base: str, engine_body: str | None) -> dict:
    ctx = browser.new_context()
    page = ctx.new_page()
    if engine_body is not None:
        page.route("**/assets/tour/tour.js", lambda route, _req: route.fulfill(
            status=200, content_type="text/javascript", body=engine_body))
    page.goto(base + "/lab?tour=record")
    page.click("[data-tour-start]")                   # loads the engine on this page
    page.wait_for_function("window.Tour !== undefined")
    page.wait_for_timeout(1500)                       # the engine polls for record mode each second
    out = page.evaluate("""() => { const r = Tour.record(); return {
        on: Tour.recording().on,
        bar: !!document.querySelector('[data-tour-ui="recorder"]:not([hidden])'),
        saved: sessionStorage.getItem('tour.record') !== null }; }""")
    ctx.close()
    return out


def main() -> int:
    rep = Report("Tour Engine")
    deployed = (ROOT / "assets" / "tour" / "tour.js").read_text(encoding="utf-8")
    rep.check("vendored engine carries all four recorder patches",
              deployed.count("RECORDER DISABLED in this build") == 4)
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            drive(browser, base, 1280, "/", rep, "desktop, from Home")
            drive(browser, base, 390, "/", rep, "phone, from Home")
            drive(browser, base, 1280, "/lab", rep, "desktop, from the Lab's Try it")

            r = recorder_runs(browser, base, None)
            rep.check("deployed build: ?tour=record and Tour.record() record nothing",
                      not r["on"] and not r["bar"] and not r["saved"], f"{r}")
            src = Path(SRC) / "tour.js" if SRC else None
            if src and src.exists():
                u = recorder_runs(browser, base, src.read_text(encoding="utf-8"))
                rep.check("control: the unpatched engine DOES record under the same check",
                          u["on"] and u["bar"], f"{u}")
            else:
                rep.not_run("control: the unpatched engine records", "set TOUR_ENGINE_SRC to a checkout")
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
