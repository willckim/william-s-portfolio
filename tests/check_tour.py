"""Tour Engine on this site: the tour completes end to end, fits the motion layer,
and the recorder is off.

The tour is driven the way a person would: Next on a card, or a click on the thing
the card points at (a nav link, a project name, the Menu button on a phone). It
crosses real page loads, so each run also proves resume works through the host
adapter's page-as-tab mapping. Runs: desktop Chrome, desktop Firefox, a phone,
reduced motion, dark mode, and one started from the Lab.

Against the motion layer (assets/tour/tour-host.js):
  - the tour waits for the preloader, finished or skipped
  - a step scrolls with Lenis, which pauses wheel scrolling until it lands
  - the numbers step lands on its chapter's anchor, where 36h -> 10m is formed
  - the spotlight stays on its target while the page scrolls under it
  - the first card on a new page waits for the ledger-line wipe to finish, and the
    page that is leaving draws no card during its wipe
  - the custom cursor dot hides while a tour runs and comes back after
  - Skip, at every step, leaves no tour, no lock, no hidden cursor, no saved place

The recorder check is graded twice: against the deployed engine (must NOT record)
and against the unpatched engine from a tour-engine checkout (MUST record), so a
check that could not see the recorder at all would fail the second half.

    py tests/check_tour.py            TOUR_ENGINE_SRC=<checkout> for the second half
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

EXPECTED = [  # (page, card title) for the seven authored steps, in order
    ("home", "Who I am, in one line"),
    ("home", "36h → 10m"),
    ("home", "Quick view"),
    ("home", "See the work"),
    ("work", "Start with Concur"),
    ("case-concur", "The guardrails"),
    ("lab", "The Mosca calculator"),
]
PAGE_OF = {"home": "/", "work": "/work", "case-concur": "/work/concur", "lab": "/lab"}
SRC = os.environ.get("TOUR_ENGINE_SRC")
NO_INTRO = "try { sessionStorage.setItem('wk.intro', '1') } catch (e) {}"
ALIGN_PX = 1.5   # spotlight edge to target edge, net of the engine's 6px padding

# Recorded on every page: whether it arrived with a view transition and when that
# finished, when the first tour card appeared and whether a wipe was running then,
# and, on a page leaving through the fallback overlay, whether any tour card was
# visible at each frame of the wipe (kept in sessionStorage, which outlives the page).
WATCH = """(() => {
  const wipingNow = () => (document.getAnimations ? document.getAnimations() : []).some(a =>
      a.effect && a.effect.pseudoElement && a.effect.pseudoElement.startsWith('::view-transition')
      && a.playState === 'running');
  window.__wipingNow = wipingNow;
  addEventListener('pagereveal', e => {
    window.__vt = !!e.viewTransition;
    if (e.viewTransition) e.viewTransition.finished.finally(() => { window.__vtDone = performance.now(); });
  });
  (function card() {
    const t = document.querySelector('[data-tour-ui="tooltip"]');
    if (t && !t.hidden && t.getBoundingClientRect().height > 0) {
      window.__cardAt = performance.now(); window.__cardDuringWipe = wipingNow(); return;
    }
    requestAnimationFrame(card);
  })();
  document.addEventListener('DOMContentLoaded', () => {
    const w = document.querySelector('.page-wipe');
    if (!w) return;
    new MutationObserver(() => {
      if (getComputedStyle(w).visibility !== 'visible') return;
      const t = document.querySelector('[data-tour-ui="tooltip"]');
      const seen = t && !t.hidden && getComputedStyle(t).visibility === 'visible' ? 'visible' : 'hidden';
      const k = JSON.parse(sessionStorage.getItem('wipe.cards') || '[]');
      k.push(seen); sessionStorage.setItem('wipe.cards', JSON.stringify(k));
    }).observe(w, { attributes: true });
  });
})();"""

STATE = """() => {
  if (!window.Tour) return null;
  const s = Tour.state();
  const tip = document.querySelector('[data-tour-ui="tooltip"]');
  s.shown = !!tip && !tip.hidden && tip.getBoundingClientRect().height > 0;
  s.title = tip ? (tip.querySelector('.tour-tip__title') || {}).textContent : null;
  s.page = document.body.dataset.page;
  s.next = !!(tip && tip.querySelector('.tour-btn-next'));
  s.align = null;
  const sp = document.querySelector('[data-tour-ui="spotlight"]');
  let t = null;
  try { t = s.sel ? document.querySelector(s.sel) : null; } catch (e) { t = null; }
  if (sp && !sp.hidden && t) {
    const a = sp.getBoundingClientRect(), b = t.getBoundingClientRect();
    s.align = Math.max(Math.abs(a.left + 6 - b.left), Math.abs(a.top + 6 - b.top),
                       Math.abs(a.width - 12 - b.width), Math.abs(a.height - 12 - b.height));
  }
  const dot = document.querySelector('.cursor');
  s.dot = dot ? getComputedStyle(dot).display : null;
  s.running = document.documentElement.classList.contains('tour-running');
  if (s.shown && window.__cardAt === undefined) {   // seen here before the frame watcher ran
    window.__cardAt = performance.now(); window.__cardDuringWipe = window.__wipingNow(); }
  s.vt = window.__vt === true; s.vtDone = window.__vtDone; s.cardAt = window.__cardAt;
  s.cardDuringWipe = window.__cardDuringWipe;
  const M = window.__motion || {};
  s.lenis = !!M.lenis; s.locked = !!(M.lenis && M.lenis.isLocked);
  s.stage = window.__story ? window.__story.stage : null;
  s.y = window.scrollY;
  return s; }"""


def state(page) -> dict | None:
    try:
        return page.evaluate(STATE)
    except Exception:  # noqa: BLE001 - mid-navigation, the context is gone; ask again
        return None


def settled(page) -> dict | None:
    """State once the spotlight has stopped gliding: the engine animates it from one
    target to the next, and Lenis eases a scroll out for a while after the wheel."""
    prev = state(page)
    for _ in range(25):
        page.wait_for_timeout(100)
        s = state(page)
        if s and prev and s["align"] is not None and prev["align"] is not None \
                and abs(s["align"] - prev["align"]) < 0.1 and abs(s["y"] - prev["y"]) < 0.5:
            return s
        prev = s
    return prev


def wait_card(page, last: tuple | None, ms: int = 15000) -> dict | None:
    """The next card that is on screen and different from the last one handled."""
    for _ in range(ms // 100):
        s = state(page)
        if s and s["active"] and s["shown"] and (s["page"], s["index"], s["title"]) != last:
            first = {k: s[k] for k in ("vt", "vtDone", "cardAt", "cardDuringWipe")}
            return {**(settled(page) or s), **first}     # arrival timing as first seen
        if s and not s["active"] and last and last[2] == EXPECTED[-1][1]:
            return s
        page.wait_for_timeout(100)
    return None


def context(browser, width=1280, height=900, reduced=False, dark=False, phone=False, intro=False):
    opts = {"viewport": {"width": width, "height": height},
            "reduced_motion": "reduce" if reduced else "no-preference",
            "color_scheme": "dark" if dark else "light"}
    if phone and browser.browser_type.name == "chromium":
        opts.update(is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx = browser.new_context(**opts)
    ctx.add_init_script(WATCH)
    if not intro:
        ctx.add_init_script(NO_INTRO)
    return ctx


def drive(rep: Report, browser, base: str, label: str, start: str = "/", **kw) -> None:
    ctx = context(browser, **kw)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(base + start, wait_until="networkidle")
    mouse = not kw.get("phone") and not kw.get("reduced")
    if mouse:                                        # a mouse user: the dot is showing
        page.mouse.move(640, 300)
        page.mouse.move(660, 320)
        page.wait_for_timeout(200)
    with_motion = not kw.get("reduced")
    page.click("[data-tour-start]")
    authored, cards, timeouts, last, aligns, dots, arrivals = [], 0, 0, None, [], [], []
    numbers, scrolled, locked_mid, seen_pages = None, None, None, []
    for _ in range(40):
        s = wait_card(page, last)
        if s is None:
            rep.check(f"{label}: tour reached the end", False, f"stuck after {authored[-1] if authored else 'start'}")
            break
        if not s["active"]:
            break
        cards += 1
        timeouts += bool(s["timedOut"])
        last = (s["page"], s["index"], s["title"])
        if s["page"] not in seen_pages:              # the first card on a newly loaded page
            seen_pages.append(s["page"])
            arrivals.append(s)
        if s["align"] is not None:
            aligns.append((s["title"], round(s["align"], 2)))
        dots.append(s["dot"])
        if (s["page"], s["title"]) in EXPECTED:
            authored.append((s["page"], s["title"]))
        if s["title"] == EXPECTED[1][1]:             # the numbers chapter
            story = page.evaluate("""() => { const ch = document.querySelector('#story .chapter[data-stage="2"]');
                const c = ch.querySelector('.ch-card'); return { anchor: window.__story && window.__story.anchorOf
                ? Math.round(window.__story.anchorOf(ch)) : null, shown: +getComputedStyle(c).opacity }; }""")
            numbers = {**story, "stage": s["stage"], "y": round(s["y"])}
            page.mouse.move(640, 450)
            page.mouse.wheel(0, 260)                 # the page moves under the spotlight
            page.wait_for_timeout(300)
            after = settled(page)
            scrolled = {"moved": round(after["y"] - s["y"]), "align": after["align"]}
        if s["next"]:
            page.click('[data-tour-ui="tooltip"] .tour-btn-next')
        else:
            page.click(s["sel"])                     # a nav link, a project name, Menu
        if s["title"] == EXPECTED[0][1] and with_motion:
            page.wait_for_timeout(120)               # the numbers step is scrolling now
            locked_mid = page.evaluate("!!(window.__motion.lenis && window.__motion.lenis.isLocked)")
    final = state(page)
    rep.check(f"{label}: all seven authored steps shown in order", authored == EXPECTED,
              f"{len(authored)} of 7 via {cards} cards")
    rep.check(f"{label}: Done ends the tour on the Lab, no step left",
              bool(final) and not final["active"] and final["page"] == "lab")
    rep.check(f"{label}: no step fell back to 'could not find'", timeouts == 0, f"{timeouts}")
    bad = [a for a in aligns if a[1] > ALIGN_PX]
    rep.check(f"{label}: the spotlight sits on its target on every card", len(aligns) >= 7 and not bad,
              f"{len(aligns)} cards, worst {max((a[1] for a in aligns), default=None)}px {bad[:2]}")
    if numbers is None:
        rep.check(f"{label}: the numbers step was reached", False)
    elif with_motion:
        rep.check(f"{label}: the numbers step lands on its chapter anchor, 36h → 10m formed",
                  numbers["anchor"] is not None and abs(numbers["y"] - numbers["anchor"]) <= 2
                  and abs(numbers["stage"] - 2) < 0.01 and numbers["shown"] == 1, f"{numbers}")
        rep.check(f"{label}: Lenis holds the wheel while a step scrolls", locked_mid is True, f"{locked_mid}")
    else:
        rep.check(f"{label}: the numbers step shows its caption as plain content, no Lenis",
                  numbers["shown"] == 1 and not (final or {}).get("lenis"), f"{numbers}")
    if scrolled is not None:
        rep.check(f"{label}: scrolling under the numbers step, the spotlight stays on the card",
                  abs(scrolled["moved"]) > 50 and scrolled["align"] is not None and scrolled["align"] <= ALIGN_PX,
                  f"{scrolled}")
    changes = arrivals[1:]                           # every page after the first
    if browser.browser_type.name == "chromium" and with_motion:
        early = [a["page"] for a in changes if not a["vt"] or a["vtDone"] is None or a["cardAt"] < a["vtDone"]
                 or a["cardDuringWipe"]]
        rep.check(f"{label}: each new page's first card waits for the view transition to finish",
                  len(changes) >= 3 and not early, f"{len(changes)} page changes, early or unseen: {early}")
    elif with_motion:
        frames = page.evaluate("JSON.parse(sessionStorage.getItem('wipe.cards') || '[]')")
        rep.check(f"{label}: the fallback wipe runs on each page change and no card shows during it",
                  len(changes) >= 3 and len(frames) >= 3 * len(changes) and "visible" not in frames,
                  f"{len(frames)} wipe frames over {len(changes)} changes, visible {frames.count('visible')}")
    if mouse:
        rep.check(f"{label}: the cursor dot is hidden on every card", bool(dots) and set(dots) == {"none"},
                  f"{sorted(set(map(str, dots)))}")
        page.mouse.move(600, 300)
        page.mouse.move(620, 320)
        page.wait_for_timeout(300)
        back = page.evaluate("""() => { const c = document.querySelector('.cursor'); return c && [getComputedStyle(c).display,
            +getComputedStyle(c).opacity, document.documentElement.classList.contains('tour-running')]; }""")
        rep.check(f"{label}: after the tour the cursor dot comes back", bool(back) and back[0] != "none"
                  and back[1] > 0 and not back[2], f"{back}")
    rep.check(f"{label}: no saved place left behind",
              page.evaluate("sessionStorage.getItem('tour.resume')") is None)
    rep.check(f"{label}: zero console errors", not errors, "; ".join(errors[:3]))
    ctx.close()


def preloader(rep: Report, browser, base: str) -> None:
    """Take the tour pressed while the preloader is up: nothing starts under it, and
    the tour begins once it ends, on its own or by Skip.

    Pressed from the keyboard once the page's scripts have run: the intro covers the
    page, so a mouse cannot reach the button, and before DOMContentLoaded no button on
    the site does anything yet. A press made earlier graded nothing about the intro."""
    for how in ("finished", "skipped"):
        ctx = context(browser, intro=True)
        page = ctx.new_page()
        page.goto(base + "/", wait_until="domcontentloaded")
        page.focus(".hero [data-tour-start]")
        page.keyboard.press("Enter")
        if not page.evaluate("document.documentElement.classList.contains('intro-on')"):
            rep.not_run(f"preloader {how}: Take the tour waits for it", "the intro had ended before the press")
            ctx.close()
            continue
        early = []
        for _ in range(4):
            early.append(page.evaluate("""!document.documentElement.classList.contains('intro-on')
                || !!(window.Tour && Tour.state().active)"""))
            page.wait_for_timeout(60)
        if how == "skipped":
            page.click("#intro-skip")
        s = wait_card(page, None, 6000)
        timing = page.evaluate("[window.__intro && window.__intro.t1, window.__cardAt]")
        ok = s is not None and s["title"] == EXPECTED[0][1] and not any(early) and timing[0] and timing[1] >= timing[0]
        rep.check(f"preloader {how}: Take the tour waits for it, then starts at step 1", ok,
                  f"card {s and s['title']!r}, intro ended {timing[0]}, card at {timing[1]}, started under it {any(early)}")
        ctx.close()


def skips(rep: Report, browser, base: str) -> None:
    """Skip on every authored step: the tour, its lock and its cursor rule all go."""
    results = []
    for k, (tab, title) in enumerate(EXPECTED):
        ctx = context(browser)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + PAGE_OF[tab], wait_until="networkidle")
        page.evaluate(f"sessionStorage.setItem('tour.resume', JSON.stringify({{ id: 'default', index: {k} }}))")
        page.reload(wait_until="networkidle")
        s = wait_card(page, None)
        if not s or s["title"] != title:
            results.append((k, f"never reached, saw {s and s['title']!r}"))
            ctx.close()
            continue
        page.mouse.move(700, 500)
        page.click('[data-tour-ui="tooltip"] .tour-btn-skip')
        page.wait_for_timeout(250)
        y0 = page.evaluate("window.scrollY")
        page.mouse.move(640, 420)
        page.mouse.move(660, 440)
        page.mouse.wheel(0, 300 if y0 < 400 else -300)
        page.wait_for_timeout(900)
        after = page.evaluate("""(y0) => { const M = window.__motion || {}, c = document.querySelector('.cursor'),
            h = document.documentElement.classList;
            return { active: !!(window.Tour && Tour.state().active), ui: document.querySelectorAll('[data-tour-ui]').length,
              running: h.contains('tour-running'), leaving: h.contains('tour-leaving'),
              lenis: !!M.lenis, locked: !!(M.lenis && M.lenis.isLocked), stopped: !!(M.lenis && M.lenis.isStopped),
              scrolls: Math.abs(window.scrollY - y0) > 50, dot: c ? +getComputedStyle(c).opacity : null,
              saved: sessionStorage.getItem('tour.resume') }; }""", y0)
        ok = (not after["active"] and after["ui"] == 0 and not after["running"] and not after["leaving"]
              and after["lenis"] and not after["locked"] and not after["stopped"] and after["scrolls"]
              and after["dot"] and after["saved"] is None and not errors)
        if not ok:
            results.append((k, {**after, "errors": errors[:2]}))
        ctx.close()
    rep.check("Skip on each of the 7 steps: no tour, Lenis free, the page scrolls, the dot is back, no saved place",
              not results, f"{results[:2]}")


def palette(rep: Report, browser, base: str) -> None:
    """The command palette during a tour: its list scrolls natively, as it does without
    one. The tour's scrollIntoView goes to Lenis, and must not take the palette's too."""
    ctx = context(browser, height=620)
    page = ctx.new_page()
    page.goto(base + "/", wait_until="networkidle")
    page.click("[data-tour-start]")
    s = wait_card(page, None)
    if not s or s["title"] != EXPECTED[0][1]:
        rep.not_run("palette during a tour: its list scrolls, not the page", f"no first card, saw {s}")
        ctx.close()
        return
    y0 = page.evaluate("window.scrollY")
    page.keyboard.press("Control+k")
    page.wait_for_selector("dialog.palette[open]")
    for _ in range(14):
        page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    r = page.evaluate("""(y0) => { const l = document.querySelector('#pal-list'), a = l.querySelector('[aria-selected="true"]'),
        lr = l.getBoundingClientRect(), ar = a.getBoundingClientRect(), M = window.__motion || {};
        return { listTop: Math.round(l.scrollTop), inView: ar.top >= lr.top - 1 && ar.bottom <= lr.bottom + 1,
                 pageMoved: Math.round(window.scrollY - y0), locked: !!(M.lenis && M.lenis.isLocked),
                 lenis: !!M.lenis, tour: !!(window.Tour && Tour.state().active) }; }""", y0)
    rep.check("palette during a tour: its list scrolls to the chosen result, the page stays put, no lock",
              r["lenis"] and r["tour"] and r["listTop"] > 0 and r["inView"] and r["pageMoved"] == 0
              and not r["locked"], f"{r}")
    ctx.close()


def copy(rep: Report, browser, base: str) -> None:
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(base + "/")
    page.click("[data-tour-start]")
    page.wait_for_function("window.Tour !== undefined && window.TourHost !== undefined")
    steps = page.evaluate("TourHost.steps.map(s => [s.title, s.body, s.targetName, s.instruction])")
    ctx.close()
    words = " ".join(w for s in steps for w in s if w)
    rep.check("step text: no em dash and no semicolon", len(steps) == 7 and not re.search("[—;]", words),
              f"{len(steps)} steps")
    # Worded by the owner in the tour brief, not read off tour-host.js.
    briefed = {2: "Short on time? Here is the one-page version.",
               5: "The model never posts anything. Rules and a person check every result.",
               6: "Try the calculator yourself."}
    wrong = {k + 1: steps[k][1] for k, want in briefed.items() if len(steps) > k and steps[k][1] != want}
    rep.check("steps 3, 6 and 7 read exactly as briefed", len(steps) == 7 and not wrong, f"{wrong}")
    rep.check("step 2 quotes the proof strip exactly",
              steps[1][0] == "36h → 10m" and steps[1][1].rstrip(".") in
              (ROOT / "index.html").read_text(encoding="utf-8"), steps[1][1][:40])


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
    sys.stdout.reconfigure(encoding="utf-8")
    rep = Report("Tour Engine")
    deployed = (ROOT / "assets" / "tour" / "tour.js").read_text(encoding="utf-8")
    rep.check("vendored engine carries all four recorder patches",
              deployed.count("RECORDER DISABLED in this build") == 4)
    only = set(sys.argv[1:])
    base, server = serve()
    try:
        with sync_playwright() as p:
            chrome = p.chromium.launch(channel="chrome")
            run = lambda name: not only or name in only   # noqa: E731
            if run("copy"):
                copy(rep, chrome, base)
            if run("desktop"):
                drive(rep, chrome, base, "desktop Chrome")
            if run("firefox"):
                try:
                    firefox = p.firefox.launch()
                except Exception as e:  # noqa: BLE001
                    rep.not_run("desktop Firefox", f"no Playwright Firefox: {str(e)[:80]}")
                else:
                    drive(rep, firefox, base, "desktop Firefox")
                    firefox.close()
            if run("phone"):
                drive(rep, chrome, base, "phone", width=390, height=844, phone=True)
            if run("reduced"):
                drive(rep, chrome, base, "reduced motion", reduced=True)
            if run("dark"):
                drive(rep, chrome, base, "dark mode", dark=True)
            if run("lab"):
                drive(rep, chrome, base, "desktop, from the Lab's Try it", start="/lab")
            if run("preloader"):
                preloader(rep, chrome, base)
            if run("skip"):
                skips(rep, chrome, base)
            if run("palette"):
                palette(rep, chrome, base)
            if run("recorder"):
                r = recorder_runs(chrome, base, None)
                rep.check("deployed build: ?tour=record and Tour.record() record nothing",
                          not r["on"] and not r["bar"] and not r["saved"], f"{r}")
                src = Path(SRC) / "tour.js" if SRC else None
                if src and src.exists():
                    u = recorder_runs(chrome, base, src.read_text(encoding="utf-8"))
                    rep.check("control: the unpatched engine DOES record under the same check",
                              u["on"] and u["bar"], f"{u}")
                else:
                    rep.not_run("control: the unpatched engine records", "set TOUR_ENGINE_SRC to a checkout")
            chrome.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
