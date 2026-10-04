"""Construction Forecast: the browser reproduces the engine's Python results.

Expected values come from the forecasting engine's Python (scenario.py), stored by
tools/extract_construction.py as `reference` in tools/data/construction.json and
never shipped to the page. The page computes every preset itself in JavaScript
from the model inputs. The two share inputs but not arithmetic, so a wrong
formula, a random draw out of order, or a stale data file each shows up as a
mismatch. Custom slider mixes are checked against the engine's Python directly
when the engine is on this machine (FORECAST_DIR), and reported NOT RUN when not.

Then the mutation runs: the same comparison against copies of construction.js
with one thing broken. Each mutant must FAIL, or the check cannot see what it
claims to grade.

Also checked: keyboard sliders, text alternatives on every chart, reduced
motion, no network requests while using the panel, the Excel download, the
"fictional" label, and that the extractor refuses a dirty engine checkout.

    py tests/check_construction.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

DATA = json.loads((ROOT / "tools" / "data" / "construction.json").read_text(encoding="utf-8"))
MODEL = DATA["contractor"]["model"]
REFERENCE = DATA["contractor"]["reference"]
ENGINE = Path(os.environ.get("FORECAST_DIR") or Path.home() / "OneDrive" / "forecasting-engine")
JS = (ROOT / "assets" / "lab" / "construction.js").read_text(encoding="utf-8")
REL = 1e-9

MUTANTS = {
    "escalation passes through on fixed-price work": ("* (1.0 - fixedShare) *", "* fixedShare *"),
    "rate lag ignored": ("var lagged = m - r.lag_months;", "var lagged = m;"),
    "random draws out of order": ("var zPpi = rng.normal(), zRate = rng.normal()",
                                  "var zRate = rng.normal(), zPpi = rng.normal()"),
    "weather destroys work instead of shifting it": ("carry = available - done;", "carry = 0;"),
    "percentile interpolates the wrong way": ("* (position - low);", "* (high - position);"),
    "the 24-month view is dropped": ("return main === n ? [main] : [main, n];", "return [main];"),
    "the tariff episode choice is ignored": ("model.materials.episodes[settings.tariff_episode | 0]",
                                             "model.materials.episodes[0]"),
    "diesel ramps over 24 months instead of 12": ("Math.min(1.0, (m + 1) / main)", "Math.min(1.0, (m + 1) / n)"),
    "spread sorted as text": ("var sorted = values.slice().sort(function (a, b) { return a - b; })",
                              "var sorted = values.slice().sort()"),
}
CUSTOM_MIXES = [
    {"weather": -0.75, "tariff": -0.5, "rate_bp": -50, "funding_delay": 0, "diesel": -1, "tariff_episode": 1},
    {"weather": 0.5, "tariff": 1.5, "rate_bp": 50, "funding_delay": 1, "diesel": 0.5, "tariff_episode": 0},
]


def close(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= REL * max(1.0, abs(a), abs(b))
    return a == b


def first_difference(a, b, path="") -> str:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in b:
            if k not in a:
                return f"{path}.{k} missing on the page"
        for k in a:
            if k not in b:
                return f"{path}.{k} on the page but not in Python"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return ""
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return "" if len(a) == len(b) else f"{path} length {len(a)} vs {len(b)}"
    return "" if close(a, b) else f"{path}: page {a} python {b}"


def settings_of(preset: dict) -> dict:
    return {k: preset[k] for k in ("weather", "tariff", "rate_bp", "funding_delay", "diesel", "tariff_episode")}


def page_run(page, settings: dict) -> dict:
    return page.evaluate("s => Construction.runSettings(Construction.model, s)", settings)


def compare_mixes(page, expected: list[tuple[dict, dict]]) -> list[str]:
    """Custom slider mixes against the engine's Python results computed for them."""
    diffs = []
    for mix, want in expected:
        got = page_run(page, mix)
        for part in ("views", "bridge", "monte_carlo"):
            d = first_difference(got[part], want[part], f"mix {mix}.{part}")
            if d:
                diffs.append(d)
    return diffs


# Values whose text order differs from their numeric order, with numpy's answers.
QUANTILE_CASE = ([100.0, 9.0, 10.0, 2500.0, -3.0], {"p10": -3 + 0.4 * 12, "p50": 10.0, "p90": 100 + 0.6 * 2400})


def compare_quantiles(page) -> list[str]:
    values, want = QUANTILE_CASE
    got = page.evaluate("v => Construction.quantiles(v, [10, 50, 90])", values)
    d = first_difference(got, want, "quantiles")
    return [d] if d else []


def compare_presets(page) -> list[str]:
    """Click each preset, then compare the page's full results with Python's."""
    diffs = []
    for preset in MODEL["presets"]:
        page.click(f'button[data-preset="{preset["key"]}"]')
        got = page_run(page, settings_of(preset))
        ref = REFERENCE[preset["key"]]
        for part in ("views", "change_from_base", "bridge", "monte_carlo"):
            d = first_difference(got[part], ref[part], f"{preset['key']}.{part}")
            if d:
                diffs.append(d)
    return diffs


def money(k: float) -> str:
    v = k / 1000
    return ("−" if v < 0 else "") + f"${abs(v):,.1f}M"


def engine_scenario():
    """The engine's own Python, imported from FORECAST_DIR, or None if it is not here."""
    if not (ENGINE / "construction" / "scenario.py").exists():
        return None
    sys.path.insert(0, str(ENGINE))
    from construction import scenario  # noqa: E402
    return scenario


def dirty_refusal(rep: Report) -> None:
    """The extractor must refuse a working tree with uncommitted changes."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)  # noqa: E731
        run("init", "-q")
        run("config", "user.email", "check@localhost")
        run("config", "user.name", "check")
        (repo / "readme.txt").write_text("clean\n", encoding="utf-8")
        run("add", ".")
        run("commit", "-q", "-m", "init")
        extractor = [sys.executable, str(ROOT / "tools" / "extract_construction.py"), str(repo)]
        clean = subprocess.run(extractor, capture_output=True, text=True)
        rep.check("extractor accepts a clean checkout (then stops on the missing results)",
                  clean.returncode != 0 and "not found" in clean.stderr + clean.stdout, (clean.stderr + clean.stdout)[-200:])
        (repo / "edited.txt").write_text("dirty\n", encoding="utf-8")
        dirty = subprocess.run(extractor, capture_output=True, text=True)
        rep.check("extractor refuses a checkout with uncommitted changes",
                  dirty.returncode != 0 and "uncommitted changes" in dirty.stderr + dirty.stdout,
                  (dirty.stderr + dirty.stdout)[-200:])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # details carry minus signs
    rep = Report("Construction Forecast")
    dirty_refusal(rep)
    workbook = ROOT / "assets" / "lab" / "prairie-ridge-model.xlsx"
    rep.check("the Excel model on the site is the one the engine produced",
              workbook.exists() and hashlib.sha256(workbook.read_bytes()).hexdigest()[:16]
              == DATA["workbook"]["sha256_16"] == DATA["provenance"]["files"]["prairie_ridge_model.xlsx"],
              "re-run tools/extract_construction.py")
    if (ENGINE / ".git").exists():
        head = subprocess.run(["git", "-C", str(ENGINE), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
        rep.check("site data is pinned to the engine's current commit", head == DATA["provenance"]["commit"],
                  f"engine HEAD {head}, site {DATA['provenance']['commit']}")
    else:
        rep.not_run("site data is pinned to the engine's current commit", f"engine not found at {ENGINE}")

    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(base + "/lab", wait_until="networkidle")

            shipped = page.evaluate("window.CONSTRUCTION_DATA")
            rep.check("the page computes from the extracted model", close(shipped["model"], MODEL))
            rep.check("the page does not ship the Python reference results", "reference" not in json.dumps(shipped))
            rep.check("the provenance line shows the engine commit and the private-source note",
                      DATA["provenance"]["commit"] in page.inner_text("#construction")
                      and "Source is private for now. Happy to walk through it in a call." in page.inner_text("#construction"))

            requests: list[str] = []
            page.on("request", lambda r: requests.append(r.url))
            quantile_diffs = compare_quantiles(page)
            rep.check("quantiles sort numerically, not as text", not quantile_diffs, "; ".join(quantile_diffs))
            diffs = compare_presets(page)
            rep.check(f"every preset matches the engine's Python ({len(MODEL['presets'])} presets, totals, bridge and "
                      "Monte Carlo, both views)", not diffs, "; ".join(diffs[:3]))

            # What a visitor reads is the same number, formatted.
            for preset in MODEL["presets"]:
                page.click(f'button[data-preset="{preset["key"]}"]')
                ref = REFERENCE[preset["key"]]["views"]["12"]
                shown = [page.text_content("#cf-rev"), page.text_content("#cf-gp")]
                rep.check(f"{preset['label']}: the summary shows revenue and gross profit from Python",
                          shown == [money(ref["revenue"]), money(ref["gross_profit"])], f"{shown}")
                pressed = page.eval_on_selector_all('#cf-presets [aria-pressed="true"]', "els => els.map(e => e.dataset.preset)")
                rep.check(f"{preset['label']}: only its own preset shows as pressed", pressed == [preset["key"]], f"{pressed}")

            scenario = engine_scenario()
            expected_mixes: list[tuple[dict, dict]] = []
            if scenario is None:
                rep.not_run("custom slider mixes match the engine's Python", f"engine not found at {ENGINE}")
            else:
                expected_mixes = [(mix, json.loads(json.dumps(scenario.run_settings(MODEL, dict(mix)))))
                                  for mix in CUSTOM_MIXES]
                for mix, want in expected_mixes:
                    d = compare_mixes(page, [(mix, want)])
                    rep.check(f"custom mix {mix} matches the engine's Python", not d, "; ".join(d[:2]))

            # Keyboard: sliders move with arrow keys and the result follows.
            page.click('button[data-preset="base"]')
            before = page.text_content("#cf-summary")
            page.focus("#cf-weather")
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(100)
            after = page.text_content("#cf-summary")
            value = page.eval_on_selector("#cf-weather", "e => +e.value")
            rep.check("the weather slider moves by keyboard and the result updates",
                      value == MODEL["sliders"]["weather"]["step"] and before != after, f"value {value}")
            page.keyboard.press("End")
            page.wait_for_timeout(100)
            rep.check("End jumps to the harshest weather, matching the Harsh winter preset",
                      page.get_attribute('button[data-preset="harsh_winter"]', "aria-pressed") == "true")
            valuetext = page.get_attribute("#cf-weather", "aria-valuetext")
            rep.check("sliders announce their meaning, not just a number", bool(valuetext) and "P90" in valuetext, valuetext)
            page.focus('button[data-preset="funding_delayed"]')
            page.keyboard.press("Enter")
            rep.check("presets work from the keyboard",
                      page.get_attribute('button[data-preset="funding_delayed"]', "aria-pressed") == "true")

            # 24-month view.
            page.check('input[name="cf-view"][value="24"]')
            rows = page.eval_on_selector_all("#cf-month-table tbody tr", "rs => rs.map(r => r.cells[0].textContent)")
            rep.check("the 24-month view lists 24 months, months 13 to 24 marked as extension",
                      len(rows) == 24 and all("(extension)" in r for r in rows[12:]) and
                      not any("(extension)" in r for r in rows[:12]), f"{len(rows)} rows")
            rep.check("the 24-month view labels the extension on the chart",
                      "extension" in (page.text_content("#cf-rev-chart") or "").lower())
            page.check('input[name="cf-view"][value="12"]')

            # Text alternatives on every chart in the panel.
            charts = page.eval_on_selector_all("#construction svg.chart", """els => els.map(s => {
                const ids = (s.getAttribute('aria-labelledby') || '').split(' ');
                return { role: s.getAttribute('role'), texts: ids.map(i => (document.getElementById(i) || {}).textContent || '') };
            })""")
            rep.check(f"every chart has role img, a title and a description ({len(charts)} charts)",
                      len(charts) == 3 and all(c["role"] == "img" and len(c["texts"]) == 2 and all(len(t) > 20 for t in c["texts"])
                                               for c in charts), f"{charts}")
            d1 = page.text_content("#cf-bridge-d")
            page.click('button[data-preset="tariffs_raised"]')
            d2 = page.text_content("#cf-bridge-d")
            rep.check("the bridge description follows the scenario", d1 != d2 and "materials and tariffs" in d2, d2[:120])

            # Fictional label.
            # textContent, not innerText: closed details, chart descriptions and
            # the no-script table count too.
            text = re.sub(r"\s+", " ", page.text_content("#construction"))
            names = [m.end() for m in re.finditer("Prairie Ridge Builders", text)]
            rep.check(f"every mention of the company is labeled fictional ({len(names)} mentions)",
                      bool(names) and all(text[i:i + 12] == " (fictional)" for i in names))

            rep.check("no network requests while using the panel", not requests, f"{requests[:3]}")

            # The download link serves the file.
            href = page.get_attribute('#cf a[download]', "href")
            response = page.request.get(base + href)
            rep.check("the Excel download link serves the workbook",
                      response.status == 200 and hashlib.sha256(response.body()).hexdigest()[:16] == DATA["workbook"]["sha256_16"],
                      f"{href} {response.status}")
            rep.check("no console errors on /lab", not errors, "; ".join(errors[:3]))

            # Reduced motion: nothing in the panel animates.
            rm = browser.new_page(reduced_motion="reduce")
            rm.goto(base + "/lab", wait_until="networkidle")
            rm.click('button[data-preset="harsh_winter"]')
            animations = rm.evaluate("""() => document.getAnimations().filter(a => {
                const t = a.effect && a.effect.target; return t && t.closest && t.closest('#construction');
            }).length""")
            transitions = rm.eval_on_selector_all("#construction .chart *, #construction .preset", """els =>
                els.filter(e => parseFloat(getComputedStyle(e).transitionDuration) > 0).length""")
            rep.check("reduced motion: no animations or transitions in the panel", animations == 0 and transitions == 0,
                      f"{animations} animations, {transitions} transitions")
            rm.close()

            # ---- mutation runs ------------------------------------------------------
            for label, (old, new) in MUTANTS.items():
                if JS.count(old) != 1:
                    rep.check(f"mutant '{label}' applies to construction.js", False, f"'{old}' found {JS.count(old)} times")
                    continue
                mutated = JS.replace(old, new)
                mpage = browser.new_page()
                mpage.route("**/assets/lab/construction.js", lambda route, _req, body=mutated: route.fulfill(
                    status=200, content_type="text/javascript", body=body))
                mpage.goto(base + "/lab", wait_until="networkidle")
                mdiffs = compare_quantiles(mpage) + compare_presets(mpage) + compare_mixes(mpage, expected_mixes)
                rep.check(f"mutant '{label}' is caught by the preset and custom-mix checks", bool(mdiffs),
                          f"{len(mdiffs)} mismatches, first: {mdiffs[0] if mdiffs else 'none'}")
                mpage.close()
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
