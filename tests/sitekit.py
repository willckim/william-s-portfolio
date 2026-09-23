"""Shared helpers for the site checks: a local server that behaves like vercel.json.

vercel.json sets cleanUrls: true and trailingSlash: false, so /work serves work.html,
/work/concur serves work/concur.html, and /work.html redirects to /work. The server
here does the same, so a check that passes locally is testing the URLs that deploy.

Every check prints PASS, FAIL or NOT RUN per line and exits non-zero on any FAIL.
A check that cannot see its subject reports NOT RUN, never PASS.
"""

from __future__ import annotations

import functools
import os
import http.server
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("SITE_ROOT") or Path(__file__).resolve().parent.parent).resolve()
EXCLUDED_DIRS = {"_archive", "tests", "tools", ".git", ".claude", "node_modules"}


def site_pages() -> list[str]:
    """Every deployed HTML page, as the clean URL a visitor would type."""
    urls = []
    for path in sorted(ROOT.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in EXCLUDED_DIRS:
            continue
        stem = rel.with_suffix("").as_posix()
        if stem == "index":
            urls.append("/")
        elif stem.endswith("/index"):
            urls.append("/" + stem[: -len("/index")])
        else:
            urls.append("/" + stem)
    return urls


class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        path = urlsplit(self.path).path
        if path.endswith(".html"):
            target = path[: -len(".html")]
            if target.endswith("/index"):
                target = target[: -len("index")]
            self.send_response(308)
            self.send_header("Location", target or "/")
            self.end_headers()
            return None
        if path != "/" and path.endswith("/"):
            self.send_response(308)
            self.send_header("Location", path.rstrip("/"))
            self.end_headers()
            return None
        disk = ROOT / path.lstrip("/")
        if path != "/" and not disk.exists():
            html = disk.with_suffix(".html")
            if html.exists():
                query = urlsplit(self.path).query
                self.path = path + ".html" + ("?" + query if query else "")
            elif (disk / "index.html").exists():
                self.path = path + "/index.html"
        return super().send_head()


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve() -> tuple[str, _Server]:
    handler = functools.partial(CleanUrlHandler, directory=str(ROOT))
    server = _Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server


class Report:
    def __init__(self, title: str):
        self.title = title
        self.rows: list[tuple[str, str, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append(("PASS" if ok else "FAIL", name, detail))
        return ok

    def not_run(self, name: str, reason: str) -> None:
        self.rows.append(("NOT RUN", name, reason))

    def finish(self) -> int:
        print(f"\n== {self.title} ==")
        for label, name, detail in self.rows:
            print(f"  [{label}] {name}" + (f"  ({detail})" if detail else ""))
        ran = [r for r in self.rows if r[0] != "NOT RUN"]
        passed = sum(r[0] == "PASS" for r in ran)
        skipped = len(self.rows) - len(ran)
        print(f"  {passed}/{len(ran)} passed" + (f", {skipped} NOT RUN" if skipped else ""))
        failed = passed != len(ran) or not ran
        return 1 if failed else 0


if __name__ == "__main__":
    base, _ = serve()
    print(base, *site_pages(), sep="\n")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        sys.exit(0)
