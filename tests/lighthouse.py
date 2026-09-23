"""Lighthouse, mobile preset, on the pages the brief gates: 95+ in all four categories.

    py tests/lighthouse.py [/path ...]      default: /, /work, /work/concur, /lab

Runs the Lighthouse CLI from tests/node_modules against the local clean-URL server
(gzip on, as Vercel serves), with the installed Chrome. Each page runs three times
and the median Performance run is reported, since one sample is not a settled
number. Reports are written to tests/shots/lh-*.json.

What the Performance score covers: the Home hero loads three.js on the first
interaction or 2.5 s after load. Lighthouse does not interact and stops measuring
shortly after load, so Home's score does not include the hero's WebGL cost. With
three.js forced in during the run, Home measured 89 to 92 on this machine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sitekit import Report, serve

HERE = Path(__file__).resolve().parent
LH = HERE / "node_modules" / "lighthouse" / "cli" / "index.js"
CHROME = os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CATS = ("performance", "accessibility", "best-practices", "seo")
RUNS = 3


def run(url: str, out: Path) -> dict:
    subprocess.run(["node", str(LH), url, "--quiet", "--output=json", f"--output-path={out}",
                    f"--only-categories={','.join(CATS)}", "--chrome-flags=--headless=new"],
                   check=True, env={**os.environ, "CHROME_PATH": CHROME})
    r = json.loads(out.read_text(encoding="utf-8"))
    scores = {c: round(r["categories"][c]["score"] * 100) for c in CATS}
    scores["_lcp"] = r["audits"]["largest-contentful-paint"]["displayValue"]
    scores["_tbt"] = r["audits"]["total-blocking-time"]["displayValue"]
    scores["_fails"] = [a for c in CATS[1:] for a in
                        (x["id"] for x in r["categories"][c]["auditRefs"])
                        if r["audits"][a]["score"] is not None and r["audits"][a]["score"] < 1
                        and r["audits"][a]["scoreDisplayMode"] == "binary"]
    return scores


def main() -> int:
    rep = Report("Lighthouse, mobile")
    if not LH.exists():
        rep.not_run("Lighthouse", "run: npm --prefix tests install")
        return rep.finish()
    paths = [a for a in sys.argv[1:] if a.startswith("/")] or ["/", "/work", "/work/concur", "/lab"]
    (HERE / "shots").mkdir(exist_ok=True)
    base, server = serve()
    try:
        for path in paths:
            name = path.strip("/").replace("/", "_") or "home"
            runs = [run(base + path, HERE / "shots" / f"lh-{name}-{i}.json") for i in range(RUNS)]
            runs.sort(key=lambda s: s["performance"])
            s = runs[RUNS // 2]
            detail = " ".join(f"{c[:4]} {s[c]}" for c in CATS) + \
                f" | LCP {s['_lcp']} TBT {s['_tbt']} | perf runs {[r['performance'] for r in runs]}"
            if s["_fails"]:
                detail += f" | failing: {s['_fails']}"
            rep.check(f"{path}: 95+ in all four", all(s[c] >= 95 for c in CATS), detail)
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
