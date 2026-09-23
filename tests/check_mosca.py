"""Mosca calculator: every preset reproduces the toolkit's published results exactly.

Expected values come from the toolkit's REPORT (pqc_readiness_report.md, Finding 1),
which its Python engine wrote. The page computes from the toolkit's CONFIG inputs in
JavaScript. So the two sides share inputs but not arithmetic: a wrong comparison,
a wrong subtraction or a stale data file on the site each shows up as a mismatch.

Then the mutation runs: the same comparison against a copy of mosca.js with one
comparison flipped. Each mutant must FAIL the preset check, or the check is not
able to see the thing it claims to grade.

    py tests/check_mosca.py            PQC_DIR overrides the toolkit folder

If the toolkit folder is not on this machine, the report checks are NOT RUN.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

PQC_DIR = Path(os.environ.get("PQC_DIR") or
               Path.home() / "OneDrive" / "quantum" / "04_security" / "pqc_readiness")
MOSCA_JS = (ROOT / "assets" / "lab" / "mosca.js").read_text(encoding="utf-8")

MUTANTS = {
    "x + y > z flipped to <": ("if (x + y > z)", "if (x + y < z)"),
    "x + y > z loosened to >=": ("if (x + y > z)", "if (x + y >= z)"),
    "x > z flipped to <": ("if (x > z)", "if (x < z)"),
}


def published() -> tuple[dict, dict]:
    """Finding 1's table: {scenario: {record type: (status, years over or None)}} and
    the planning year each column was calculated at."""
    text = (PQC_DIR / "pqc_readiness_report.md").read_text(encoding="utf-8")
    head = re.search(r"^\| Data type \| Shelf life.*$", text, re.M)
    if not head:
        raise ValueError("Finding 1 table not found in the report")
    cols = [c.strip() for c in head.group(0).strip("|").split("|")][3:]
    names, years = [], {}
    for c in cols:
        m = re.match(r"(\w+) \(\d{4}-\d{4}\), at (\d{4})", c)
        names.append(m.group(1))
        years[m.group(1)] = int(m.group(2))
    table = {n: {} for n in names}
    body = text[head.end():].split("\n\n", 1)[0].strip().splitlines()[1:]
    for line in body:
        cells = [c.strip() for c in line.strip("|").split("|")]
        name = re.sub(r"\s*\(ASSUMPTION\)$", "", cells[0])
        for n, cell in zip(names, cells[3:]):
            m = re.search(r"(Exposed now|Exposed|safe)\**(?: \(\+(\d+)\))?", cell)
            status = {"Exposed now": "now", "Exposed": "exposed", "safe": "safe"}[m.group(1)]
            table[n][name] = (status, int(m.group(2)) if m.group(2) else None)
    return table, years


def page_table(page) -> dict:
    return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#m-table tbody tr')]
        .map(tr => [tr.dataset.type, [tr.querySelector('.status').dataset.status,
                                      +tr.querySelector('.margin').dataset.over]]))""")


def compare(page, table: dict) -> list[str]:
    """Click each preset; return every difference from the published table."""
    diffs = []
    for scenario, rows in table.items():
        page.click(f'button[data-preset="{scenario}"]')
        got = page_table(page)
        if set(got) != set(rows):
            diffs.append(f"{scenario}: record types differ {sorted(set(got) ^ set(rows))}")
            continue
        for name, (status, over) in rows.items():
            g_status, g_over = got[name]
            ok = g_status == status and (g_over == over if over is not None else g_over <= 0)
            if not ok:
                diffs.append(f"{scenario} / {name}: page {g_status} {g_over:+d}, "
                             f"report {status} {'+' + str(over) if over else ''}")
    return diffs


def main() -> int:
    rep = Report("Mosca calculator")
    if not (PQC_DIR / "pqc_readiness_report.md").exists():
        rep.not_run("presets match the toolkit's report", f"toolkit not found at {PQC_DIR}")
        return rep.finish()
    table, years = published()
    cfg = yaml.safe_load((PQC_DIR / "pqc_config.yaml").read_text(encoding="utf-8"))

    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(base + "/lab", wait_until="networkidle")

            data = page.evaluate("window.PQC_DATA")
            rep.check("site inputs match the toolkit's current pqc_config.yaml",
                      [(d["name"], d["shelf_life"]) for d in data["data_types"]]
                      == [(d["name"], d["shelf_life_years"]) for d in cfg["data_types"]]
                      and data["migration_years"] == cfg["migration"]["years"]
                      and [s["planning_year"] for s in data["scenarios"]]
                      == [s["planning_year"] for s in cfg["scenarios"]],
                      "re-run tools/extract_pqc.py and tools/sitegen.py if this fails")
            rep.check("report columns were calculated at the config's planning years",
                      years == {s["name"]: s["planning_year"] for s in cfg["scenarios"]}, f"{years}")

            requests: list[str] = []
            page.on("request", lambda r: requests.append(r.url))
            diffs = compare(page, table)
            n = sum(len(r) for r in table.values())
            rep.check(f"every preset matches the published report ({len(table)} scenarios, {n} cells)",
                      not diffs, "; ".join(diffs[:4]))
            for s in table:
                page.click(f'button[data-preset="{s}"]')
                pressed = page.eval_on_selector_all(
                    '.preset[aria-pressed="true"]', "els => els.map(e => e.dataset.preset)")
                rep.check(f"{s}: only its own preset shows as pressed", pressed == [s], f"{pressed}")

            # Sliders are live and local: moving z changes the summary, and nothing is fetched.
            before = page.text_content("#m-summary")
            page.fill("#m-z", "25")
            page.dispatch_event("#m-z", "input")
            after = page.text_content("#m-summary")
            rep.check("moving z recomputes the table", before != after and "2051" in after, after)
            rep.check("no network requests while using the calculator", not requests, f"{requests}")

            b = page.evaluate("""() => [Mosca.assess(5, 4, 9), Mosca.assess(6, 4, 9),
                                         Mosca.assess(10, 0, 9)]""")
            rep.check("boundary: x + y = z is safe", b[0]["status"] == "safe", f"{b[0]}")
            rep.check("boundary: x + y = z + 1 is exposed by 1 year",
                      b[1]["status"] == "exposed" and b[1]["over"] == 1, f"{b[1]}")
            rep.check("x > z is exposed now, even with no migration time", b[2]["status"] == "now", f"{b[2]}")
            rep.check("no console errors on /lab", not errors, "; ".join(errors[:3]))

            # ---- mutation runs ------------------------------------------------------
            for label, (old, new) in MUTANTS.items():
                if MOSCA_JS.count(old) != 1:
                    rep.check(f"mutant '{label}' applies to mosca.js", False,
                              f"'{old}' found {MOSCA_JS.count(old)} times")
                    continue
                mutated = MOSCA_JS.replace(old, new)
                mpage = browser.new_page()
                mpage.route("**/assets/lab/mosca.js",
                            lambda route, _req, body=mutated: route.fulfill(
                                status=200, content_type="text/javascript", body=body))
                mpage.goto(base + "/lab", wait_until="networkidle")
                mdiffs = compare(mpage, table)
                rep.check(f"mutant '{label}' is caught by the preset check", bool(mdiffs),
                          f"{len(mdiffs)} mismatches, first: {mdiffs[0] if mdiffs else 'none'}")
                mpage.close()
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
