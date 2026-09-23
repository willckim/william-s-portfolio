"""Copy rules for every deployed page: no em dashes, no semicolons, no stale CPA date.

Reads the visible text of each page (script and style contents excluded, entities
decoded), plus the text a visitor or a screen reader is given in title, alt,
aria-label and meta description attributes.

Run: py tests/check_copy.py
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser

from sitekit import ROOT, Report, site_pages

VISIBLE_ATTRS = {"title", "alt", "aria-label", "placeholder"}


class TextOf(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        a = dict(attrs)
        for k in VISIBLE_ATTRS:
            if a.get(k):
                self.parts.append(a[k])
        if tag == "meta" and a.get("name") == "description" and a.get("content"):
            self.parts.append(a["content"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def page_file(url: str):
    if url == "/":
        return ROOT / "index.html"
    p = ROOT / (url.lstrip("/") + ".html")
    return p if p.exists() else ROOT / url.lstrip("/") / "index.html"


RULES = [
    ("no em dash", re.compile("—")),
    ("no semicolon", re.compile(";")),
    ("no October 2026 CPA date", re.compile(r"October\s+2026", re.I)),
    # Figures corrected on 2026-09-23: the toolkit's latest scenario is 2040, the
    # mutation figure is the engine's own suites only, and there are three systems.
    ("no retired 2041 scenario", re.compile(r"\b2041\b")),
    ("no retired mutation figures", re.compile(r"145 of 145|\b251\b")),
    ("no retired system count", re.compile(r"four production systems|\b4\b Production systems", re.I)),
]


def main() -> int:
    rep = Report("Copy rules")
    pages = site_pages()
    if not pages:
        rep.not_run("pages found", "no deployed HTML pages were found")
        return rep.finish()
    # Copy that lives in scripts: the tour's cards.
    tour = (ROOT / "assets" / "tour" / "tour-host.js").read_text(encoding="utf-8")
    strings = " ".join(re.findall(r'(?:title|body|targetName|instruction): "([^"]*)"', tour))
    for name, rx in RULES:
        hits = [strings[max(0, m.start() - 40): m.end() + 20] for m in rx.finditer(strings)]
        rep.check(f"tour cards: {name}", bool(strings) and not hits, "; ".join(repr(h) for h in hits[:3]))
    for url in pages:
        parser = TextOf()
        parser.feed(page_file(url).read_text(encoding="utf-8"))
        text = re.sub(r"\s+", " ", " ".join(parser.parts))
        for name, rx in RULES:
            hits = [text[max(0, m.start() - 40): m.end() + 20] for m in rx.finditer(text)]
            rep.check(f"{url}: {name}", not hits, "; ".join(repr(h) for h in hits[:3]))
    rendered(rep)
    return rep.finish()


def rendered(rep: Report) -> None:
    """The same rules on what a browser shows: text drawn by scripts (the Mosca table
    and its notes from the toolkit's config, Grover's status, the palette) never
    appears in the HTML files the static pass reads."""
    from playwright.sync_api import sync_playwright

    from sitekit import serve

    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            for url in site_pages():
                page.goto(base + url, wait_until="networkidle")
                texts = [page.inner_text("body")]
                if url == "/lab":
                    for t in page.eval_on_selector_all("#m-type option", "os => os.map(o => o.value)"):
                        page.select_option("#m-type", t)             # each record type's basis note
                        texts.append(page.inner_text("#m-x-note"))
                    page.click("[data-g=oracle]")
                    texts.append(page.inner_text("#grover"))
                    page.keyboard.press("Control+k")
                    page.wait_for_selector("dialog.palette[open]")
                    texts.append(page.inner_text("dialog.palette"))
                text = re.sub(r"\s+", " ", " ".join(texts))
                for name, rx in RULES:
                    hits = [text[max(0, m.start() - 40): m.end() + 20] for m in rx.finditer(text)]
                    rep.check(f"rendered {url}: {name}", bool(text.strip()) and not hits,
                              "; ".join(repr(h) for h in hits[:3]))
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
