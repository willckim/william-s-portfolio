"""Case studies: same template for all five, under 400 words, accessible diagrams.

Reads the pages through the local clean-URL server, so it grades the URLs that
deploy (/work/concur, not work/concur.html).

Run: py tests/check_case_studies.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser

from sitekit import ROOT, Report, serve

SLUGS = ("concur", "royalty", "fast-close", "time-tracker", "consolidation")
SECTIONS = ["Problem", "What I did", "How it works", "Results", "What I'd do next", "Stack"]
MAX_WORDS = 400
# The Concur diagram must show this order: model output, then rules, then a person, then posting.
CONCUR_ORDER = ["OpenAI API proposes", "Deterministic rules check", "accountant reviews", "person posts"]


class MainText(HTMLParser):
    """Visible words inside <main>, and the h2 headings in order. An SVG's title and
    desc are for assistive tech, not on screen, so they are not counted as words."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = 0
        self.hidden = 0
        self.in_h2 = False
        self.words: list[str] = []
        self.h2: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main += 1
        if tag in ("title", "desc", "script", "style"):
            self.hidden += 1
        if tag == "h2" and self.in_main:
            self.in_h2 = True
            self.h2.append("")

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main -= 1
        if tag in ("title", "desc", "script", "style"):
            self.hidden -= 1
        if tag == "h2":
            self.in_h2 = False

    def handle_data(self, data):
        if self.in_main and not self.hidden:
            self.words += re.findall(r"[\w'’./%~→–-]+", data)
            if self.in_h2:
                self.h2[-1] += data.strip()


def fetch(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url) as r:
        return r.status, r.read().decode("utf-8")


def main() -> int:
    rep = Report("Case studies")
    base, server = serve()
    try:
        for slug in SLUGS:
            url = f"{base}/work/{slug}"
            try:
                status, html = fetch(url)
            except Exception as e:  # noqa: BLE001 - reported, not swallowed
                rep.check(f"/work/{slug}: served at its clean URL", False, str(e))
                continue
            rep.check(f"/work/{slug}: served at its clean URL", status == 200, str(status))
            p = MainText()
            p.feed(html)
            rep.check(f"/work/{slug}: template sections in order", p.h2 == SECTIONS, f"{p.h2}")
            rep.check(f"/work/{slug}: under {MAX_WORDS} words", len(p.words) < MAX_WORDS,
                      f"{len(p.words)} words")
            svgs = re.findall(r"<svg\b[^>]*class=\"diagram\"[^>]*>.*?</svg>", html, re.S)
            rep.check(f"/work/{slug}: exactly one diagram", len(svgs) == 1, f"{len(svgs)}")
            if not svgs:
                continue
            svg = svgs[0]
            head = re.match(r"<svg\b[^>]*>", svg).group(0)
            ids = re.search(r'aria-labelledby="([^"]+)"', head)
            title = re.search(r'<title id="([^"]+)">([^<]+)</title>', svg)
            desc = re.search(r'<desc id="([^"]+)">([^<]+)</desc>', svg)
            rep.check(f"/work/{slug}: diagram has role=img, title and desc it is labelled by",
                      bool('role="img"' in head and ids and title and desc
                           and ids.group(1).split() == [title.group(1), desc.group(1)]))
            literal = re.findall(r'(?:fill|stroke)="(?!none)[^"]+"|style="', svg)
            rep.check(f"/work/{slug}: diagram colours come from the theme, not literals",
                      not literal, f"{literal[:3]}")
            if slug == "concur":
                text = " ".join(re.findall(r'<text class="dg-text"[^>]*>([^<]*)</text>', svg))
                at = [text.find(w) for w in CONCUR_ORDER]
                rep.check("/work/concur: model output, then rules, then human review, then posting",
                          -1 not in at and at == sorted(at), f"positions {at}")
                rep.check("/work/concur: the model and rules sit inside the guardrail boundary",
                          'class="dg-group"' in svg and "Deterministic rule guardrails" in svg)
        gen = subprocess.run([sys.executable, str(ROOT / "tools" / "sitegen.py"), "--check"],
                             capture_output=True, text=True)
        rep.check("generated pages match tools/sitegen.py", gen.returncode == 0, gen.stdout.strip())
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
