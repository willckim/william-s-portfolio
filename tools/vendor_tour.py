"""Vendor the Tour Engine into assets/tour/tour.js, with the recorder disabled.

    py tools/vendor_tour.py <path to a tour-engine checkout>

The engine is copied as committed, then four patches take record mode out of the
deployed build. Each patch must match EXACTLY ONCE in the source, or the script
stops: an engine update that moves one of them must be looked at, not guessed at.

    1. ?tour=record no longer starts anything
    2. recStart() returns at once              (the only way to begin a recording)
    3. recArrive() returns at once             (the only way to take one up after a load)
    4. Tour.record() is a no-op

recOpen() is the one place `recording` becomes true, and 2 and 3 are its only
callers, so with them closed the recorder cannot run and never writes its
sessionStorage key. tests/check_tour.py proves that in a browser.

Writes TOUR_ENGINE.md with the commit, date, blob id and hashes, as the engine's
README asks of every consumer.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "tour" / "tour.js"
RECORD = ROOT / "TOUR_ENGINE.md"
MARK = "RECORDER DISABLED in this build (tools/vendor_tour.py)"

PATCHES = (
    ("const wantsRecord = /(^|[?&])tour=record(&|$)/.test(location.search);",
     f"const wantsRecord = false;   // {MARK}"),
    ("    function recStart() {\n        if (recording) return;",
     f"    function recStart() {{\n        return;   // {MARK}\n        if (recording) return;"),
    ("    function recArrive(how) {\n        const saved = recSaved();",
     f"    function recArrive(how) {{\n        return;   // {MARK}\n        const saved = recSaved();"),
    ("        record: recStart,",
     f"        record: function () {{ return null; }},   // {MARK}"),
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    repo = Path(sys.argv[1]).resolve()
    if git(repo, "status", "--porcelain", "tour.js"):
        raise SystemExit("tour.js has uncommitted changes in the checkout: vendor a commit")
    src = (repo / "tour.js").read_text(encoding="utf-8")
    out = src
    for old, new in PATCHES:
        n = out.count(old)
        if n != 1:
            raise SystemExit(f"patch target found {n} times, expected 1:\n{old}")
        out = out.replace(old, new)
    commit = git(repo, "rev-parse", "HEAD")
    header = (f"/* Tour Engine, vendored from the private tour-engine repo at {commit[:7]}.\n"
              f" * Recorder disabled: see tools/vendor_tour.py and TOUR_ENGINE.md. */\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + out, encoding="utf-8", newline="\n")
    RECORD.write_text(f"""# Tour Engine: vendored copy

| | |
|---|---|
| Source | github.com/willckim/tour-engine (private repo) |
| Commit | `{commit}` |
| Commit date | {git(repo, "log", "-1", "--format=%ci")} |
| Vendored | {date.today().isoformat()} |
| `tour.js` blob | `{git(repo, "rev-parse", "HEAD:tour.js")}` |
| Source sha256 | `{hashlib.sha256(src.encode("utf-8")).hexdigest()}` |
| Deployed sha256 | `{hashlib.sha256(OUT.read_bytes()).hexdigest()}` |

The deployed `assets/tour/tour.js` is the source plus four patches that disable
record mode (listed in `tools/vendor_tour.py`), and a two-line header. The styles
travel inside `tour.js`, so `tour.css` is not copied. The site's host adapter is
`assets/tour/tour-host.js`.

Update: `py tools/vendor_tour.py <tour-engine checkout>`, then `py tests/check_tour.py`.
""", encoding="utf-8", newline="\n")
    print(f"vendored {commit[:7]} with {len(PATCHES)} patches -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
