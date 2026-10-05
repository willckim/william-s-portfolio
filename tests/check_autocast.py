"""Forecast your own data: the browser matches the engine's Python, parses real-world
CSVs, explains every bad file, and never sends anything anywhere.

Expected values:
  - the three samples: the forecasting engine's Python results (src/autoforecast.py),
    stored by tools/extract_construction.py and never shipped to the page
  - the parser: values written by hand in this file for each CSV variant
  - the error messages: one bad file per message, each built by hand here

Mutation runs: copies of autocast.js with one rule broken must fail the sample check.

    py tests/check_autocast.py
"""

from __future__ import annotations

import csv
import io
import json
import sys

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

DATA = json.loads((ROOT / "tools" / "data" / "construction.json").read_text(encoding="utf-8"))
SAMPLES = DATA["samples"]["samples"]
FIXTURES = DATA["samples"]["test_fixtures"]["cases"]          # synthetic, never shipped to the page
JS = (ROOT / "assets" / "lab" / "autocast.js").read_text(encoding="utf-8")
REL = 1e-9
KEYS = ("frequency", "season", "horizon", "points_used", "points_dropped", "seasonal_strength", "origins",
        "first_origin", "publication_lag",
        "metric", "band_scale", "winner", "table", "forecast")

MUTANTS = {
    "seasonal update in the classic form": ("gamma * (y[t] - level - damped)", "gamma * (y[t] - newLevel)"),
    "log scale never used": ("var useLog = allPositive(train);", "var useLog = false;"),
    "near-ties go to the more complex model": ("return r[metric] <= best * (1 + TIE); })[0].key",
                                               "return r[metric] <= best * (1 + TIE); }).pop().key"),
    "backtest uses one origin fewer": ("for (var o = firstOrigin; o < n - 1; o++)", "for (var o = firstOrigin + 1; o < n - 1; o++)"),
    "band read off the wrong percentile": ("percentile(errs, q)", "percentile(errs, 100 - q)"),
    "the testable minimum is dropped": ("if (n < testable) {", "if (false) {"),
    "a sample's settings are ignored": ("run(parsed.periods, parsed.values, settings)", "run(parsed.periods, parsed.values)"),
}
ALL_MUTANTS = {
    "the race guard is removed": ("if (mine !== latest) return;", ""),
}


# Finished means the result line for that name is up, not just the "Read ..." line.
DONE = """k => { const t = document.getElementById('ac-status').textContent || '';
                 return t.includes(k) && t.includes('Winner by backtest'); }"""

# Every model forecasts a constant series exactly, so all three tie. The documented
# rule (near-ties go to the simpler model) must pick seasonal naive.
TIE_CASE = {"dates": [f"{2015 + i // 12}-{i % 12 + 1:02d}" for i in range(60)], "values": [250.0] * 60}


def tie_check(page) -> list[str]:
    got = page.evaluate("""s => { const p = s.dates.map(d => [+d.slice(0, 4), +d.slice(5, 7)]);
                                  return Autocast.run(p, s.values).winner; }""", TIE_CASE)
    return [] if got == "seasonal_naive" else [f"tie went to {got}"]


def close(a, b) -> str:
    """'' when equal to rounding, else the first difference."""
    if isinstance(b, dict):
        for k in b:
            if not isinstance(a, dict) or k not in a:
                return f".{k} missing"
            d = close(a[k], b[k])
            if d:
                return f".{k}{d}"
        return ""
    if isinstance(b, list):
        if not isinstance(a, list) or len(a) != len(b):
            return f" length {len(a) if isinstance(a, list) else a} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = close(x, y)
            if d:
                return f"[{i}]{d}"
        return ""
    if isinstance(b, (int, float)) and not isinstance(b, bool) and isinstance(a, (int, float)):
        return "" if abs(a - b) <= REL * max(1.0, abs(a), abs(b)) else f": page {a} python {b}"
    return "" if a == b else f": page {a!r} python {b!r}"


JS_NAMES = {"seasonal_naive": "Seasonal naive", "linear_trend": "Linear trend + seasonality",
            "holt_winters_damped": "Holt-Winters (ETS), damped"}


def tabs_agree(page) -> list[str]:
    """Both Lab tabs on the construction series, as a visitor reads them.

    Tab two: the construction sample's table and winner. Tab one: the "How it works"
    backtest table, in the column for the published publication lag. Same models must
    show the same average MAPE to the printed digit, and the same winner.
    """
    macro = DATA["macro"]
    lag = macro["published"]["publication_lag_months"]
    main_names = {r["key"]: r["name"] for r in macro["variants"][0]["table"]}
    sample = next(x for x in SAMPLES if x.get("settings"))
    page.click("#cf-tab-own")
    page.click(f'button[data-sample="{sample["key"]}"]')
    page.wait_for_function(DONE, arg=sample["series_id"], timeout=20000)
    tab2 = {r[0].replace(" (winner)", ""): r[1] for r in page.eval_on_selector_all(
        "#ac-table tbody tr", "rs => rs.map(r => [r.cells[0].textContent, r.cells[1].textContent])")}
    winner2 = page.text_content("#ac-winner")
    main_table = page.eval_on_selector_all(
        "#construction .cf-how table.cf-table", """ts => { const t = ts.find(x => (x.caption || {}).textContent === 'Backtest error by model');
            return [...t.tBodies[0].rows].map(r => [r.cells[0].textContent, ...[...r.cells].slice(1).map(c => c.textContent)]); }""")
    variants = [v["publication_lag_months"] for v in macro["variants"]]
    column = 2 * variants.index(lag)                          # each lag has an average then a 12-month column
    tab1 = {row[0]: row[1 + column] for row in main_table}
    diffs = []
    for key, name in JS_NAMES.items():
        if tab2.get(name) != tab1.get(main_names[key]):
            diffs.append(f"{key}: own-data tab {tab2.get(name)}, main tab {tab1.get(main_names[key])}")
    main_winner = next(v["winner"] for v in macro["variants"] if v["publication_lag_months"] == lag)
    if winner2 != JS_NAMES.get(main_winner):
        diffs.append(f"winner: own-data tab {winner2}, main tab {main_names[main_winner]}")
    return diffs


def compare_fixtures(page) -> list[str]:
    """The synthetic fixtures: results where Python had results, the same refusal where it refused."""
    diffs = []
    for f in FIXTURES:
        got = page.evaluate("""s => { const p = s.dates.map(d => [+d.slice(0, 4), +d.slice(5, 7)]);
                                      try { return { result: Autocast.run(p, s.values) }; }
                                      catch (e) { return { error: e.message }; } }""", f)
        if "error" in f:
            if got.get("error") != f["error"]:
                diffs.append(f"{f['key']}: page {got.get('error') or 'gave a result'!r}, python {f['error']!r}")
            continue
        if "result" not in got:
            diffs.append(f"{f['key']}: page refused with {got['error']!r}")
            continue
        d = close({k: got["result"].get(k) for k in KEYS}, {k: f["result"][k] for k in KEYS})
        if d:
            diffs.append(f"{f['key']}{d}")
    return diffs


def compare_samples(page) -> list[str]:
    diffs = []
    for s in SAMPLES:
        got = page.evaluate("""s => { const p = s.dates.map(d => [+d.slice(0, 4), +d.slice(5, 7)]);
                                      return Autocast.run(p, s.values, s.settings || undefined); }""", s)
        d = close({k: got.get(k) for k in KEYS}, {k: s["result"][k] for k in KEYS})
        if d:
            diffs.append(f"{s['key']}{d}")
    return diffs


def race_check(page) -> list[str]:
    """Deterministic: in one task, start a sample's analysis, then a newer bad one. The
    sample's deferred work must find itself stale and leave the newer error alone."""
    page.evaluate("""() => { document.querySelector('button[data-sample="construction"]').click();
                             Autocast.analyse('late.csv', 'date,value\\n'); }""")
    page.wait_for_timeout(800)
    shown = page.text_content("#ac-error") or ""
    ok = not page.eval_on_selector("#ac-error", "e => e.hidden") and "needs two columns" in shown
    hidden = page.eval_on_selector("#ac-results", "e => e.hidden")
    return [] if ok and hidden else [f"after the race: error shown {not page.eval_on_selector('#ac-error', 'e => e.hidden')}, "
                                     f"results hidden {hidden}, status {page.text_content('#ac-status')[:80]!r}"]


def months(n: int, start=(2018, 1)) -> list[str]:
    out, y, m = [], *start
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def body(dates, values, header="date,value") -> str:
    return "\n".join(([header] if header else []) + [f"{d},{v}" for d, v in zip(dates, values)])


# ---- formats the parser must read: (label, csv text, expected first 3 values, expected count, frequency)
D24 = months(24)
FORMATS = [
    ("plain ISO months", body(D24, range(100, 124)), [100, 101, 102], 24, "monthly"),
    ("full ISO dates and no header", body([d + "-01" for d in D24], range(100, 124), header=None), [100, 101, 102], 24, "monthly"),
    ("quoted values with dollar signs and thousands separators",
     "Month,\"Sales ($)\"\n" + "\n".join(f"{d},\"${1000 + 1000 * i:,}.50\"" for i, d in enumerate(D24)),
     [1000.5, 2000.5, 3000.5], 24, "monthly"),
    ("US dates M/D/YYYY with CRLF line endings",
     "date,value\r\n" + "\r\n".join(f"{int(d[5:])}/15/{d[:4]},{v}" for d, v in zip(D24, range(50, 74))),
     [50, 51, 52], 24, "monthly"),
    ("month names and a byte order mark",
     "﻿period,amount\n" + "\n".join(f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(d[5:]) - 1]} {d[:4]},{v}"
                                       for d, v in zip(D24, range(10, 34))),
     [10, 11, 12], 24, "monthly"),
    ("tab-separated, newest first, negatives in parentheses",
     "date\tvalue\n" + "\n".join(f"{d}\t({v})" for d, v in reversed(list(zip(D24, range(1, 25))))),
     [-1, -2, -3], 24, "monthly"),
    ("quarters written 2019Q1", body([f"{2019 + i // 4}Q{i % 4 + 1}" for i in range(8)], range(200, 208)),
     [200, 201, 202], 8, "quarterly"),
    ("two-digit years pivot at 30, as Excel does",
     body([f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i % 12]}-{(99 + i // 12) % 100:02d}"
           for i in range(24)], range(24)), [0, 1, 2], 24, "monthly"),
    ("semicolon-separated", "date;value\n" + "\n".join(f"{d};{v}" for d, v in zip(D24, range(7, 31))), [7, 8, 9], 24, "monthly"),
    ("MM/YYYY with a minus sign and decimals",
     body([f"{d[5:]}/{d[:4]}" for d in D24], [f"−{i}.25" for i in range(24)]), [-0.25, -1.25, -2.25], 24, "monthly"),
]

# ---- one bad file per message: (label, csv text, a phrase the message must contain)
GOOD = list(zip(D24, range(100, 124)))
BAD = [
    ("empty file", "", "The file is empty."),
    ("a single column", "date\n" + "\n".join(D24), "needs two columns"),
    ("three columns", "date,a,b\n" + "\n".join(f"{d},{v},{v}" for d, v in GOOD), "3 columns with data"),
    ("a missing date", body([""] + D24[1:], range(100, 124)), "Row 2 has no date."),
    ("an unreadable date", body(["someday"] + D24[1:], range(100, 124)), "Row 2 has a date that could not be read"),
    ("a missing value", body(D24, ["", *range(101, 124)]), "has no value"),
    ("a non-numeric value", body(D24, ["n/a", *range(101, 124)]), "is not a number"),
    ("a duplicated month", body(D24[:12] + [D24[11]] + D24[12:], range(100, 125)), "appears twice"),
    ("a gap", body(D24[:5] + D24[7:], range(100, 122)), "The series has gaps: Jun 2018, Jul 2018 missing."),
    ("uneven quarterly spacing",
     body(["2019-01", "2019-04", "2019-08", "2019-11", "2020-02", "2020-05", "2020-08", "2020-11", "2021-02"], range(9)),
     "not evenly spaced"),
    ("every other month", body([f"{2018 + i // 6}-{(i % 6) * 2 + 1:02d}" for i in range(30)], range(30)),
     "not monthly or quarterly"),
    ("too few monthly points", body(months(20), range(20)), "Only 20 monthly points. At least 24"),
    ("too few quarterly points", body([f"{2019 + i // 4}Q{i % 4 + 1}" for i in range(6)], range(6)), "Only 6 quarterly points. At least 8"),
    ("too short to test every horizon", body(months(41), [100 + i for i in range(41)]), "needs at least 42"),
    ("day-first dates", body([f"{13 + i % 12}/{i % 12 + 1}/2020" for i in range(24)], range(24)), "reads as day first"),
    ("dotted dates", body([f"01.{i % 12 + 1:02d}.{2018 + i // 12}" for i in range(24)], range(24)), "reads as day first"),
    ("a value with two signs", body(D24, ["(-5)", *range(101, 124)]), "is not a number"),
    ("more than twenty columns", "a" + ",a" * 25 + "\n" + "\n".join(f"{d}," + ",".join(["1"] * 25) for d in D24), "more than 20 columns"),
    ("more than ten thousand rows", body(months(10050, (1200, 1)), [1] * 10050), "more than 10,000 rows"),
    ("a typo in the first row's date, with no header", body(["2O18-01"] + D24[1:], range(100, 124), header=None),
     "Row 1 has a date that could not be read"),
    ("a blank line before the bad row", "date,value\n\n" + "\n".join(f"{d},{v}" for d, v in GOOD[:3]) + "\n2018-04,x\n"
     + "\n".join(f"{d},{v}" for d, v in GOOD[4:]), "Row 6 has a value that is not a number"),
    ("daily data", "date,value\n" + "\n".join(f"2018-01-{d:02d},{d}" for d in range(1, 29)), "If this is daily or weekly data"),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rep = Report("Forecast your own data")
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(base + "/lab", wait_until="networkidle")
            requests: list[str] = []
            page.on("request", lambda r: requests.append(r.url))

            # Samples: the engine call itself, then through the page's own buttons.
            diffs = compare_samples(page)
            rep.check(f"all three samples match the engine's Python ({len(SAMPLES)} samples, every model, horizon and band)",
                      not diffs, "; ".join(diffs[:3]))
            tie = tie_check(page)
            rep.check("near-ties go to the simpler model (a constant series, every model exact)", not tie, "; ".join(tie))
            fdiffs = compare_fixtures(page)
            rep.check(f"synthetic fixtures match the engine's Python, refusals word for word ({len(FIXTURES)} cases: zeros, "
                      "negatives, quarterly, the exact minimum, one point short)", not fdiffs, "; ".join(fdiffs[:3]))
            first = page.evaluate("""() => { const d = []; const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                for (let i = 0; i < 24; i++) d.push(names[i % 12] + '-' + String((99 + Math.floor(i / 12)) % 100).padStart(2, '0') + ',' + i);
                const r = Autocast.parse('date,value\\n' + d.join('\\n')); return [r.periods[0], r.periods[23]]; }""")
            rep.check("Jan-99 reads as 1999 and Dec-00 as 2000", first == [[1999, 1], [2000, 12]], f"{first}")
            agree = tabs_agree(page)
            rep.check("both tabs show the same winner and average errors for the construction series", not agree,
                      "; ".join(agree))
            rep.check("the page does not ship the Python results",
                      all("result" not in s for s in page.evaluate("window.CONSTRUCTION_DATA.samples")))
            page.click("#cf-tab-own")
            for s in SAMPLES:
                page.click(f'button[data-sample="{s["key"]}"]')
                page.wait_for_function(DONE, arg=s["series_id"], timeout=20000)
                winner = next(t["name"] for t in s["result"]["table"] if t["key"] == s["result"]["winner"])
                rep.check(f"{s['label']}: the page names Python's winner", page.text_content("#ac-winner") == winner,
                          page.text_content("#ac-winner"))

            # Download: the CSV holds the forecast just shown.
            with page.expect_download() as info:
                page.click("#ac-download")
            text = info.value.path().read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(text)))
            want = SAMPLES[-1]["result"]["forecast"]
            ok = len(rows) == len(want) and all(
                r["date"] == f"{f['year']}-{f['month']:02d}" and abs(float(r["forecast"]) - f["point"]) <= 1e-9 * abs(f["point"])
                and abs(float(r["p90"]) - f["p90"]) <= 1e-9 * abs(f["p90"]) for r, f in zip(rows, want))
            rep.check("the downloaded CSV holds the forecast on the page", ok, text[:120])

            # Formats.
            for label, text, first3, count, freq in FORMATS:
                got = page.evaluate("t => { try { const r = Autocast.parse(t); return [r.frequency, r.values.length, r.values.slice(0, 3)]; }"
                                    " catch (e) { return ['error', e.message]; } }", text)
                rep.check(f"parses {label}", got == [freq, count, first3], f"{got}")

            # Every error message, through the real file input so the page shows it.
            for label, text, phrase in BAD:
                page.set_input_files("#ac-file", files=[{"name": "bad.csv", "mimeType": "text/csv", "buffer": text.encode("utf-8")}])
                page.wait_for_function("() => !document.getElementById('ac-error').hidden", timeout=10000)
                shown = page.text_content("#ac-error")
                rep.check(f"a file with {label} gets a clear message", phrase in shown and
                          page.get_attribute("#ac-error", "role") == "alert" and
                          page.eval_on_selector("#ac-results", "e => e.hidden"), shown)
                page.click('button[data-sample="retail"]')                   # reset to a good state, fully finished
                page.wait_for_function(DONE, arg="RSAFSNA", timeout=20000)
            big = b"date,value\n" + b"2020-01,1\n" * 600000
            page.set_input_files("#ac-file", files=[{"name": "big.csv", "mimeType": "text/csv", "buffer": big}])
            page.wait_for_function("() => !document.getElementById('ac-error').hidden", timeout=5000)
            rep.check("a file over 5 MB is refused before it is read", "larger than 5 MB" in page.text_content("#ac-error"))

            race = race_check(page)
            rep.check("an older analysis never overwrites a newer error", not race, "; ".join(race))
            rep.check("the file picker is cleared after each choice, so the same file can be chosen again",
                      page.eval_on_selector("#ac-file", "e => e.value") == "")

            # A good file through the input, and the same file dropped on the zone. A visitor's
            # file gets the general defaults, so the expected result is a default-settings sample's.
            plain = next(x for x in SAMPLES if not x.get("settings"))
            good = body(plain["dates"], plain["values"]).encode("utf-8")
            page.set_input_files("#ac-file", files=[{"name": "mine.csv", "mimeType": "text/csv", "buffer": good}])
            page.wait_for_function(DONE, arg="mine.csv", timeout=20000)
            rep.check("a chosen file is forecast with the general defaults", page.text_content("#ac-winner") ==
                      next(t["name"] for t in plain["result"]["table"] if t["key"] == plain["result"]["winner"]))
            page.evaluate("""text => { const dt = new DataTransfer();
                dt.items.add(new File([text], 'dropped.csv', { type: 'text/csv' }));
                const zone = document.getElementById('ac-drop');
                zone.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
                zone.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""",
                          good.decode("utf-8"))
            page.wait_for_function(DONE, arg="dropped.csv", timeout=20000)
            rep.check("a dropped file is forecast", "dropped.csv" in page.text_content("#ac-status"))
            rep.check("no network request while choosing, dropping, forecasting or downloading", not requests,
                      f"{requests[:3]}")

            # Keyboard and screen readers.
            page.focus("#cf-tab-own")
            page.keyboard.press("ArrowLeft")
            rep.check("arrow keys move between the tabs", page.get_attribute("#cf-tab-scen", "aria-selected") == "true"
                      and page.evaluate("document.activeElement.id") == "cf-tab-scen"
                      and page.eval_on_selector("#ac", "e => e.hidden") and not page.eval_on_selector("#cf", "e => e.hidden"))
            page.keyboard.press("End")
            rep.check("End selects the last tab", page.get_attribute("#cf-tab-own", "aria-selected") == "true")
            tabs = page.eval_on_selector_all("#cf-tabs [role=tab]", "ts => ts.map(t => [t.getAttribute('aria-controls'), t.tabIndex])")
            rep.check("tabs are wired to their panels, one in the tab order", tabs == [["cf", -1], ["ac", 0]], f"{tabs}")
            page.focus("#cf-tab-own")
            page.keyboard.press("Tab")
            rep.check("the file picker is the next stop after the tabs", page.evaluate("document.activeElement.id") == "ac-file",
                      page.evaluate("document.activeElement.id"))
            page.focus('button[data-sample="construction"]')
            page.keyboard.press("Enter")
            page.wait_for_function(DONE, arg="PNRESCON", timeout=20000)
            rep.check("samples run from the keyboard", page.text_content("#ac-winner") ==
                      next(t["name"] for t in SAMPLES[0]["result"]["table"] if t["key"] == SAMPLES[0]["result"]["winner"]))
            rep.check("results are announced politely in one region, errors as alerts in another",
                      page.get_attribute("#ac-status", "role") == "status" and page.get_attribute("#ac-status", "aria-live") == "polite"
                      and page.get_attribute("#ac-error", "role") == "alert")
            desc = page.text_content("#ac-chart-d")
            rep.check("the forecast chart has a text alternative that states the numbers",
                      page.get_attribute("#ac-chart", "role") == "img" and len(desc) > 60 and "range of past misses" in desc, desc[:100])
            rep.check("no console errors", not errors, "; ".join(errors[:3]))

            # ---- mutation runs -------------------------------------------------------
            for label, (old, new) in {**MUTANTS, **ALL_MUTANTS}.items():
                count = JS.count(old)
                if count == 0 or (label in MUTANTS and count != 1):
                    rep.check(f"mutant '{label}' applies to autocast.js", False, f"'{old}' found {count} times")
                    continue
                mutated = JS.replace(old, new)
                mpage = browser.new_page()
                mpage.route("**/assets/lab/autocast.js", lambda route, _req, b=mutated: route.fulfill(
                    status=200, content_type="text/javascript", body=b))
                mpage.goto(base + "/lab", wait_until="networkidle")
                mpage.click("#cf-tab-own")
                mdiffs = (compare_samples(mpage) + tie_check(mpage) + compare_fixtures(mpage) + race_check(mpage)
                          + tabs_agree(mpage))
                rep.check(f"mutant '{label}' is caught by the sample, tie, fixture, race and agreement checks", bool(mdiffs),
                          f"{len(mdiffs)} samples differ, first: {mdiffs[0][:120] if mdiffs else 'none'}")
                mpage.close()
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
