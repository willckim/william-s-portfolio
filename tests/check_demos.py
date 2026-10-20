"""The hosted 3D demos: pinned, safe to publish, and working where the site serves them.

    py tests/check_demos.py

Pin: tools/data/demos.json must describe demos/ exactly (file count, bytes and
a content hash), and each pinned commit must be the clean HEAD of its source
repo, so the site never serves a build of code that has since changed. With no
source repo on this machine that part reports NOT RUN.

Guards of tools/build_demos.py, each with a passing and a failing case: a dirty
source repo is refused and a clean one is not, and the publish scan refuses a
webhook URL, a local path, a secret, a source map and a planted identity inside
a gzip, while a clean build passes.

Launch: each case page loads nothing from demos/, no three.js and no jsPDF, until
"Launch the demo" is clicked, then loads the real embed snippet or the frame (at
the lighter quality on a phone). No page names a private repo or links GitHub.

Served: both demos load through the local server, which strips trailing slashes
and /index.html the way Vercel does (checked first, as the control), with no
failed request and no console error, on desktop and on a phone. The apartment
studio keeps its on-screen Credits and licenses panel.
"""

from __future__ import annotations

import gzip
import re
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from sitekit import ROOT, CleanUrlHandler, Report, serve

sys.path.insert(0, str(ROOT / "tools"))
import build_demos  # noqa: E402
import scan_history  # noqa: E402

MANIFEST = json.loads((ROOT / "tools" / "data" / "demos.json").read_text(encoding="utf-8"))
GL = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
QE, APT = "custom-quote-builder", "apartment-walkthrough-studio"
class ProductionHeaders(CleanUrlHandler):
    """The site's clean URLs with the cache header Vercel really sends. The page checks use
    no-store for freshness, and under no-store Chromium intermittently aborts a few of the
    apartment's large parallel downloads (net::ERR_ABORTED, seen in 1 of 2 runs, 0 of 2 without
    it), which is a condition visitors never meet."""

    def end_headers(self):
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        http.server.SimpleHTTPRequestHandler.end_headers(self)


PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}


def check_pin(rep: Report) -> None:
    for key, demo in build_demos.DEMOS.items():
        entry = MANIFEST.get(key)
        if not rep.check(f"{key}: pinned in tools/data/demos.json", entry is not None):
            continue
        files, size, digest = build_demos.content_hash(ROOT / demo.base.strip("/"))
        rep.check(f"{key}: demos/ is exactly the pinned build", (files, size, digest) ==
                  (entry["files"], entry["bytes"], entry["sha256_16"]), f"{files} files, {digest}")
        src = build_demos.source_dir(demo)
        if not (src / ".git").exists():
            rep.not_run(f"{key}: pin is the source repo's clean HEAD", f"no source repo at {demo.env}")
            continue
        try:
            head = build_demos.clean_head(src)[0]
            rep.check(f"{key}: pin is the source repo's clean HEAD (else run tools/build_demos.py)",
                      head == entry["commit"], f"pin {entry['commit']}, HEAD {head}")
        except build_demos.Refused as e:
            rep.check(f"{key}: pin is the source repo's clean HEAD", False, str(e).splitlines()[0])
    # The hash above reads the working copy. What deploys is what git holds, so nothing may be uncommitted.
    pending = subprocess.run(["git", "status", "--porcelain", "--", "demos", "tools/data/demos.json"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
    rep.check("demos/ and its pin are committed, so the deploy is the build the pin names", pending == "",
              pending.replace("\n", " | ")[:200])


def check_counts(rep: Report) -> None:
    """The build refuses a failing browser suite, and a suite that ran nothing."""
    rep.check("build script reads a passing browser suite's count", build_demos.passed_checks("x", 0, "34/34 checks passed") == 34)
    for out, code, why in (("33/34 checks passed", 1, "a failing suite"), ("0/0 checks passed", 0, "an empty suite"),
                           ("no summary line", 0, "a suite with no summary")):
        try:
            build_demos.passed_checks("x", code, out)
            rep.check(f"build script refuses {why}", False)
        except build_demos.Refused:
            rep.check(f"build script refuses {why}", True)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                   cwd=repo, check=True, capture_output=True)


def check_guards(rep: Report, tmp: Path) -> None:
    repo = tmp / "src"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a")
    rep.check("build script accepts a clean source repo", build_demos.clean_head(repo)[0] != "")
    (repo / "b.txt").write_text("untracked", encoding="utf-8")
    try:
        build_demos.clean_head(repo)
        rep.check("build script refuses a source repo with uncommitted changes", False)
    except build_demos.Refused:
        rep.check("build script refuses a source repo with uncommitted changes", True)

    planted = "jane.example@example.org"
    real = scan_history.load_needles
    scan_history.load_needles = lambda *a: []
    try:
        build_demos.scan(tmp)
        rep.check("publish scan refuses to run without the needles file (NOT RUN, never clean)", False)
    except build_demos.Refused as e:
        rep.check("publish scan refuses to run without the needles file (NOT RUN, never clean)", "NOT RUN" in str(e))
    scan_history.load_needles = lambda *a: [scan_history.needle("email", planted)]
    try:
        clean = tmp / "clean"
        clean.mkdir()
        (clean / "index.html").write_text("<p>Argon Outdoor Living, a fictional contractor</p>", encoding="utf-8")
        (clean / "pricing-config.json").write_text('{"leadWebhookUrl": ""}', encoding="utf-8")
        rep.check("publish scan passes a clean build", build_demos.scan(clean) == [], str(build_demos.scan(clean)))
        bad = {
            "a webhook URL": ("pricing-config.json", b'{"leadWebhookUrl": "https://hooks.zapier.com/hooks/catch/1/x"}'),
            "a local file path": ("app.js", b'const p = "C:\\\\Users\\\\jane\\\\project\\\\src";'),
            "a secret": ("app.js", b'const key = "sk-abcdefghijklmnopqrstuvwxyz012345";'),
            "an AWS access key": ("app.js", b'const id = "AKIA0000000000000000";'),
            "a Google API key": ("app.js", b'const k = "AIza' + b"0" * 35 + b'";'),
            "a private key": ("key.txt", b"-----BEGIN RSA PRIVATE KEY-----\nMIIB\n"),
            "a source map": ("app.js.map", b'{"version":3}'),
            "a source map reference": ("app.js", b"//# sourceMappingURL=app.js.map"),
            "an identity inside a gzip": ("data.json.gz", gzip.compress(planted.encode() + b" " * 200)),
        }
        for what, (name, data) in bad.items():
            case = tmp / f"bad-{len(name)}-{what.replace(' ', '-')}"
            shutil.copytree(clean, case)
            (case / name).write_bytes(data)
            rep.check(f"publish scan refuses {what}", any(name in p for p in build_demos.scan(case)))
    finally:
        scan_history.load_needles = real


def watch(page) -> tuple[list[str], list[str]]:
    errors, failed = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    page.on("requestfailed", lambda r: failed.append(f"failed {r.url}"))
    return errors, failed


def check_control(rep: Report, base: str) -> None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(f"{base}/demos/lakeview/")
        status, where = 200, ""
    except urllib.error.HTTPError as e:
        status, where = e.code, e.headers.get("Location", "")
    rep.check("control: the local server strips the trailing slash like Vercel", status == 308
              and where == "/demos/lakeview", f"{status} -> {where}")


def check_quote_engine(rep: Report, browser, base: str, label: str, **ctx_args) -> None:
    ctx = browser.new_context(**ctx_args)
    page = ctx.new_page()
    errors, failed = watch(page)
    page.goto(f"{base}/demos/quote-engine/")
    try:
        page.wait_for_function(f"() => document.querySelector('{QE}')?.shadowRoot?.querySelector('[data-output=range]')"
                               "?.textContent.includes('$')", timeout=60_000)
        price = page.locator(f'{QE} [data-output="range"]').inner_text()
    except Exception as e:  # noqa: BLE001  reported as a failure, never skipped
        price = f"not ready: {type(e).__name__}"
    rep.check(f"quote engine, {label}: loads and prices at /demos/quote-engine", "$" in price, price)
    rep.check(f"quote engine, {label}: no failed request", not failed, str(failed[:3]))
    rep.check(f"quote engine, {label}: no console errors", not errors, str(errors[:3]))
    ctx.close()


def check_demo_mode(rep: Report, browser, base: str) -> None:
    """The hosted quote engine is in demo mode: the form says so, the PDF downloads, and submit
    makes no network request. The source repo's suite has the control that sees a webhook POST."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=True)
    page = ctx.new_page()
    errors, _ = watch(page)
    page.goto(f"{base}/demos/quote-engine/")
    page.wait_for_function(f"() => document.querySelector('{QE}')?.shadowRoot?.querySelector('[data-output=range]')"
                           "?.textContent.includes('$')", timeout=60_000)
    page.locator(f'{QE} [data-action="quote"]').click()
    notice = page.locator(f"{QE} dialog[open]").inner_text()
    for field, value in (("name", "Jordan Rivera"), ("email", "jordan@example.com"),
                         ("phone", "(555) 201-3344"), ("zip", "60010")):
        page.locator(f"{QE} #qb-f-{field}").fill(value)
    requests: list[str] = []
    page.on("request", lambda r: requests.append(f"{r.method} {r.url}"))
    with page.expect_download() as dl:
        page.locator(f'{QE} form button[type="submit"]').click()
    page.locator(f"{QE} .qb-success").wait_for(state="visible")
    page.wait_for_timeout(1500)
    rep.check("quote engine: the hosted demo says nothing is sent", "Demo only, nothing you enter is sent anywhere" in notice)
    rep.check("quote engine: the hosted demo's PDF downloads", dl.value.suggested_filename.endswith(".pdf"),
              dl.value.suggested_filename)
    rep.check("quote engine: submit on the hosted demo makes no network request", requests == [], str(requests[:3]))
    rep.check("quote engine: no console errors through submit", not errors, str(errors[:3]))
    ctx.close()


def settled(page, condition: str, seconds: int) -> bool:
    """True once the condition holds. A timeout is a failed check, never a crash that hides the rest."""
    try:
        page.wait_for_function(condition, timeout=seconds * 1000)
        return True
    except Exception:  # noqa: BLE001
        return False


DEMO_FILES = re.compile(r"/demos/|three|jspdf", re.I)


def check_launch(rep: Report, browser, base: str, slug: str, label: str, **ctx_args) -> None:
    """The case page loads nothing of its demo until "Launch the demo" is clicked, then loads it."""
    ctx = browser.new_context(**ctx_args)
    page = ctx.new_page()
    errors, failed = watch(page)
    urls: list[str] = []
    page.on("request", lambda r: urls.append(r.url))
    page.goto(f"{base}/work/{slug}", wait_until="networkidle")
    early = [u for u in urls if DEMO_FILES.search(u.replace(base, ""))]
    rep.check(f"/work/{slug}, {label}: nothing from /demos, no three.js or jsPDF before launch", early == [], str(early[:3]))
    rep.check(f"/work/{slug}, {label}: the poster is shown before launch",
              any("/assets/work/" in u and u.endswith(".webp") for u in urls))
    def hosts() -> set[str]:   # network hosts only: about:blank, blob: and data: never leave the browser
        return {urlsplit(u).netloc for u in urls if urlsplit(u).scheme in ("http", "https")}
    hosts_before = hosts()
    page.click("[data-demo-launch]")
    if slug == "quote-engine":
        rep.check(f"/work/{slug}, {label}: the launched widget prices",
                  settled(page, f"() => document.querySelector('{QE}')?.shadowRoot?.querySelector('[data-output=range]')"
                                "?.textContent.includes('$')", 120))
        loaded = [u.replace(base, "") for u in urls if "/demos/quote-engine/" in u]
        rep.check(f"/work/{slug}, {label}: launch loads the embed and its config from /demos/quote-engine",
                  "/demos/quote-engine/quote-builder-embed.js" in loaded
                  and any(u.startswith("/demos/quote-engine/pricing-config.json") for u in loaded), str(loaded))
        rep.check(f"/work/{slug}, {label}: the launched widget is in demo mode",
                  page.evaluate(f"() => !!document.querySelector('{QE}[demo-mode]')"))
    else:
        src = page.evaluate("() => document.querySelector('.demo-frame iframe')?.getAttribute('src')")
        want = "/demos/lakeview?quality=low" if ctx_args.get("is_mobile") else "/demos/lakeview"
        rep.check(f"/work/{slug}, {label}: launch opens the studio in a frame at {want}", src == want, str(src))
        rep.check(f"/work/{slug}, {label}: the studio in the frame reports ready",
                  settled(page, f"() => document.querySelector('.demo-frame iframe')?.contentDocument"
                                f"?.querySelector('{APT}')?.hasAttribute('data-ready')", 300))
        bar = page.locator(".demo-bar").inner_text()
        rep.check(f"/work/{slug}, {label}: the studio runs in the page, with an own-tab link",
                  "Open in its own tab" in bar, bar.replace("\n", " | "))
        if not ctx_args.get("is_mobile"):
            rep.check(f"/work/{slug}, {label}: a full screen button where the browser supports it",
                      "Full screen" in bar or not page.evaluate("() => document.fullscreenEnabled"), bar)
    added = sorted(hosts() - hosts_before)
    rep.check(f"/work/{slug}, {label}: launch contacts no new host, only this site", added == [], str(added))
    rep.check(f"/work/{slug}, {label}: no failed request through launch", not failed, str(failed[:3]))
    rep.check(f"/work/{slug}, {label}: no console errors through launch", not errors, str(errors[:3]))
    ctx.close()


def check_no_source_links(rep: Report) -> None:
    """Both source repos stay private: no GitHub link or mention for the two products anywhere."""
    pages = {f"/work/{s}": (ROOT / "work" / f"{s}.html").read_text(encoding="utf-8")
             for s in ("quote-engine", "apartment-studio")}
    work = (ROOT / "work.html").read_text(encoding="utf-8")
    rows = re.findall(r"<tr>\s*<td class=\"name\">(?:3D Quote Engine|Apartment Walkthrough Studio).*?</tr>", work, re.S)
    rep.check("Products tab: both 3D products are listed", len(rows) == 2, f"{len(rows)} rows")
    for where, html in [*pages.items(), *((f"Products row {i + 1}", r) for i, r in enumerate(rows))]:
        rep.check(f"{where}: no GitHub link or mention", "github" not in html.lower())
    for name in ("3d-quote-engine", "apartment-walkthrough-studio", "3D-Quote-Engine"):
        hits = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.html")
                if "_archive" not in p.parts and "demos" not in p.parts and name in p.read_text(encoding="utf-8")]
        rep.check(f"no page names the private repo {name}", hits == [], str(hits[:3]))


def check_lakeview(rep: Report, browser, base: str, label: str, query: str, **ctx_args) -> None:
    ctx = browser.new_context(**ctx_args)
    page = ctx.new_page()
    errors, failed = watch(page)
    page.goto(f"{base}/demos/lakeview/{query}")
    try:
        page.wait_for_function(f"() => document.querySelector('{APT}')?.hasAttribute('data-ready')", timeout=300_000)
        ready = True
    except Exception:  # noqa: BLE001
        ready = False
    rep.check(f"apartment studio, {label}: loads at /demos/lakeview", ready)
    quality = page.evaluate(f"() => document.querySelector('{APT}')?.quality") if ready else None
    if query:
        rep.check(f"apartment studio, {label}: runs at {query[1:]}", quality == query.split("=")[1], str(quality))
    if ready and label == "desktop":
        page.evaluate(f"""() => document.querySelector('{APT}').shadowRoot.querySelector('[data-action="credits"]').click()""")
        panel = page.evaluate(f"""() => {{ const p = document.querySelector('{APT}').shadowRoot.querySelector('.credits-panel');
            return p && !p.hidden ? {{ text: p.textContent, links: p.querySelectorAll('a[href^="https://"]').length }} : null; }}""")
        rep.check("apartment studio: Credits and licenses opens a panel with license links",
                  bool(panel) and panel["links"] > 0 and "CC" in panel["text"], str(panel and panel["links"]))
    rep.check(f"apartment studio, {label}: no failed request", not failed, str(failed[:3]))
    rep.check(f"apartment studio, {label}: no console errors", not errors, str(errors[:3]))
    ctx.close()


def main() -> int:
    rep = Report("3D demos: pinned, safe to publish, working at /demos")
    check_pin(rep)
    check_no_source_links(rep)
    check_counts(rep)
    with tempfile.TemporaryDirectory() as t:
        check_guards(rep, Path(t))
    base, server = serve(ProductionHeaders)
    try:
        check_control(rep, base)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=GL)
            check_quote_engine(rep, browser, base, "desktop", viewport={"width": 1280, "height": 800})
            check_quote_engine(rep, browser, base, "phone", **PHONE)
            check_demo_mode(rep, browser, base)
            check_lakeview(rep, browser, base, "desktop", "", viewport={"width": 1280, "height": 800})
            check_lakeview(rep, browser, base, "phone", "?quality=low", **PHONE)
            for slug in ("quote-engine", "apartment-studio"):
                check_launch(rep, browser, base, slug, "desktop", viewport={"width": 1280, "height": 800})
                check_launch(rep, browser, base, slug, "phone", **PHONE)
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
