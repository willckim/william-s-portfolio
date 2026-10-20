"""Rebuild the two 3D demos from their private source repos into demos/, pinned by commit.

    py tools/build_demos.py                 both demos
    py tools/build_demos.py quote-engine    one of them (quote-engine, lakeview)

Only built files reach this repo, never source. For each demo, in order, and
stopping at the first refusal:

    1. the source repo must have no uncommitted or untracked changes
    2. its unit tests and its browser checks must all pass (their counts are recorded)
    3. it is built into a temporary folder with its site base path
    4. the build is scanned: personal information (the local needles file of
       tools/scan_history.py), secrets, local file paths, webhook URLs, source
       maps and source files all refuse the copy
    5. for the apartment studio, the real download at each quality is measured
       in a browser
    6. demos/<name>/ is replaced, and tools/data/demos.json records the source
       commit, test counts, file count, size and a content hash

The source repos are found at QUOTE_ENGINE_DIR and LAKEVIEW_DIR, or beside this
repo in OneDrive. They must also be on the same commit and still clean after
the build, so the pin names exactly what was built.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_history  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools" / "data" / "demos.json"
NPX = "npx.cmd" if os.name == "nt" else "npx"
NPM = "npm.cmd" if os.name == "nt" else "npm"


@dataclass(frozen=True)
class Demo:
    key: str
    env: str
    folder: str
    base: str
    builds: tuple[tuple[str, ...], ...]     # vite builds, {out} and {base} filled in
    drop: tuple[str, ...] = ()              # host files meant for another platform


DEMOS = {
    "quote-engine": Demo(
        key="quote-engine", env="QUOTE_ENGINE_DIR", folder="3d-quote-engine", base="/demos/quote-engine/",
        builds=(("vite", "build", "--base", "{base}", "--outDir", "{out}", "--emptyOutDir"),
                ("vite", "build", "--config", "vite.embed.config.ts", "--outDir", "{out}")),
        drop=("_headers",)),
    "lakeview": Demo(
        key="lakeview", env="LAKEVIEW_DIR", folder="apartment-walkthrough-studio", base="/demos/lakeview/",
        builds=(("vite", "build", "--base", "{base}", "--outDir", "{out}", "--emptyOutDir"),)),
}

FORBIDDEN = {
    "a local file path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/Users/[A-Za-z]|/home/[a-z]|file:///", re.I),
    "a secret": re.compile(r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{30,}"
                           r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"),
    "a webhook URL": re.compile(r"hooks\.zapier\.com|hook\.[a-z0-9]+\.make\.com|hooks\.slack\.com"
                                r"|discord(?:app)?\.com/api/webhooks|webhook\.site"
                                r"|\"leadWebhookUrl\"\s*:\s*\"[^\"]+\"", re.I),
    "a source map reference": re.compile(r"sourceMappingURL=", re.I),
}
SOURCE_SUFFIXES = {".ts", ".tsx", ".map", ".py", ".mjs"}


class Refused(SystemExit):
    pass


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def source_dir(demo: Demo) -> Path:
    return Path(os.environ.get(demo.env) or Path.home() / "OneDrive" / demo.folder)


def clean_head(src: Path) -> tuple[str, str]:
    """(short commit, commit date) of a source repo with nothing uncommitted, or refuse."""
    status = run(["git", "status", "--porcelain"], src)
    if status.returncode != 0:
        raise Refused(f"{src.name}: not a git repo ({status.stderr.strip()})")
    if status.stdout.strip():
        raise Refused(f"{src.name}: uncommitted changes, commit them first:\n{status.stdout.rstrip()}")
    commit = run(["git", "log", "-1", "--format=%h %cs"], src).stdout.split()
    return commit[0], commit[1]


def unit_tests(src: Path, tmp: Path) -> int:
    report = tmp / "vitest.json"
    done = run([NPX, "vitest", "run", "--reporter=json", f"--outputFile={report}"], src)
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    if done.returncode != 0 or not data.get("success"):
        raise Refused(f"{src.name}: unit tests failed ({data.get('numFailedTests', '?')} failed)")
    return int(data["numPassedTests"])


def browser_checks(src: Path) -> int:
    if run([NPM, "run", "build"], src).returncode != 0:
        raise Refused(f"{src.name}: npm run build failed")
    done = run([sys.executable, "scripts/e2e_smoke.py"], src)
    found = re.findall(r"(\d+)/(\d+) checks passed", done.stdout)
    if done.returncode != 0 or not found or found[-1][0] != found[-1][1]:
        tail = "\n".join(done.stdout.strip().splitlines()[-5:])
        raise Refused(f"{src.name}: browser checks failed\n{tail}")
    return int(found[-1][0])


def build(demo: Demo, src: Path, out: Path) -> None:
    if run([NPX, "tsc", "--noEmit"], src).returncode != 0:
        raise Refused(f"{src.name}: type check failed")
    for args in demo.builds:
        cmd = [NPX, *(a.format(out=out, base=demo.base) for a in args)]
        done = run(cmd, src)
        if done.returncode != 0:
            raise Refused(f"{src.name}: {' '.join(args[:3])} failed\n{done.stderr.strip()[-800:]}")
    for name in demo.drop:
        (out / name).unlink(missing_ok=True)


def scan(out: Path) -> list[str]:
    """Every reason the built files must not be published. Empty means clean."""
    needles = scan_history.load_needles()
    if not needles:
        raise Refused(f"NOT RUN: no needles in {scan_history.NEEDLES_FILE}, so the personal-information scan cannot run")
    problems = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        rel = path.relative_to(out).as_posix()
        if path.suffix.lower() in SOURCE_SUFFIXES:
            problems.append(f"{rel}: a source or source-map file")
            continue
        try:
            forms = scan_history.views(path.read_bytes())
        except Exception as e:  # noqa: BLE001  a file that cannot be opened is not published
            problems.append(f"{rel}: unreadable ({type(e).__name__})")
            continue
        for n in needles:
            if scan_history.matches(n, forms):
                problems.append(f"{rel}: {n.label}")
        # Secret prefixes are case-sensitive (AKIA, AIza, BEGIN ... PRIVATE KEY), so the patterns
        # also run on the text as written, not only on the case-folded forms the needles use.
        as_written = "\n".join(form.decode("utf-8", "replace") for _, form in forms)
        folded = "\n".join(t for _, form in forms for t in scan_history.texts(form))
        problems += [f"{rel}: {what}" for what, rx in FORBIDDEN.items()
                     if rx.search(as_written) or rx.search(folded)]
    return problems


class VercelLike(http.server.SimpleHTTPRequestHandler):
    """Serves a folder the way the site's host does: a trailing slash is redirected away and a
    folder answers with its index.html, so a build that resolves URLs against the folder breaks
    here, at build time, instead of in production."""

    def log_message(self, *args):
        pass

    def send_head(self):
        path = self.path.split("?", 1)[0]
        if path != "/" and path.endswith("/"):
            self.send_response(308)
            self.send_header("Location", path.rstrip("/") + self.path[len(path):])
            self.end_headers()
            return None
        disk = Path(self.translate_path(path))
        if disk.is_dir() and (disk / "index.html").exists():
            self.path = path + "/index.html" + self.path[len(path):]
        return super().send_head()


def wait_ready(page, missing: list[str], quality: str, seconds: int = 300) -> None:
    """Until the studio reports ready. A failed request refuses at once rather than at the timeout."""
    ready = "() => !!document.querySelector('apartment-walkthrough-studio')?.hasAttribute('data-ready')"
    for _ in range(seconds * 2):
        if missing:
            raise Refused(f"lakeview at {quality} quality: a request failed where the site serves it: {missing[:3]}")
        if page.evaluate(ready):
            return
        page.wait_for_timeout(500)
    raise Refused(f"lakeview at {quality} quality: not ready after {seconds} s")


def download_bytes(demo: Demo, out: Path, tmp: Path) -> dict[str, int]:
    """Bytes the apartment studio really downloads at each quality, measured in Chromium."""
    from playwright.sync_api import sync_playwright
    root = tmp / "served"
    shutil.copytree(out, root / demo.base.strip("/"))
    handler = lambda *a, **k: VercelLike(*a, directory=str(root), **k)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    sizes = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            for quality in ("high", "low"):
                ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                page, responses, missing = ctx.new_page(), [], []
                page.on("requestfinished", lambda r: responses.append(r))
                page.on("response", lambda r: missing.append(f"{r.status} {r.url}") if r.status >= 400 else None)
                page.goto(f"{base}{demo.base.rstrip('/')}?quality={quality}")   # as a visitor gets it
                wait_ready(page, missing, quality)
                page.wait_for_load_state("networkidle")
                sizes[quality] = sum(r.sizes()["responseBodySize"] for r in responses
                                     if r.url.startswith(base + demo.base))
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    return sizes


def content_hash(out: Path) -> tuple[int, int, str]:
    files = sorted(p for p in out.rglob("*") if p.is_file())
    digest = hashlib.sha256()
    for p in files:
        digest.update(p.relative_to(out).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return len(files), sum(p.stat().st_size for p in files), digest.hexdigest()[:16]


def publish(demo: Demo) -> dict:
    src = source_dir(demo)
    commit, date = clean_head(src)
    print(f"{demo.key}: {src.name} at {commit}, clean")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        unit = unit_tests(src, tmp)
        browser = browser_checks(src)
        print(f"{demo.key}: {unit} unit tests and {browser} browser checks passed")
        out = tmp / "out"
        build(demo, src, out)
        if clean_head(src) != (commit, date):
            raise Refused(f"{src.name}: the build or tests changed the repo, refusing to pin it")
        problems = scan(out)
        if problems:
            raise Refused(f"{demo.key}: the build is not safe to publish:\n  " + "\n  ".join(problems))
        print(f"{demo.key}: scan clean")
        entry = {"source": demo.folder, "commit": commit, "commit_date": date, "base": demo.base,
                 "tests": {"unit": unit, "browser": browser}}
        if demo.key == "lakeview":
            entry["download_bytes"] = download_bytes(demo, out, tmp)
        files, size, digest = content_hash(out)
        entry.update({"files": files, "bytes": size, "sha256_16": digest})
        dest = ROOT / demo.base.strip("/")
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(out, dest)
    entry["built_at"] = datetime.now().isoformat(timespec="seconds")
    return entry


def main(argv: list[str]) -> int:
    keys = argv or list(DEMOS)
    unknown = [k for k in keys if k not in DEMOS]
    if unknown:
        print(f"unknown demo {unknown}, choose from {list(DEMOS)}")
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    for key in keys:
        try:
            manifest = {**manifest, key: publish(DEMOS[key])}
        except Refused as e:
            print(f"REFUSED {e}")
            return 1
        # Written after each demo, so demos/ and the pin never disagree if a later demo is refused.
        MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"pinned {key} at {manifest[key]['commit']} in {MANIFEST.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
