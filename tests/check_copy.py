"""Copy rules for every deployed page: no em dashes, no semicolons, and the résumé facts.

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
    # The contractor in the Construction Forecast is made up. Its name never
    # appears without the label right after it.
    ("contractor labeled fictional", re.compile(r"Prairie Ridge Builders(?! \(fictional\))")),
    # Résumé facts, swept on 2026-10-19. The Concur review was 12 hours, not 36. The ~40 hours a
    # month figure came from an old wrong number. The title and project names are fixed.
    ("no retired 36", re.compile(r"(?<![\w.,])36(?![\w]|[.,]\d)")),
    ("no retired 40 hours", re.compile(r"\b40\s*(?:hours|hrs|h)\b|~\s*40\b", re.I)),
    ("never Accounting's lead", re.compile(r"Accounting['’]s lead", re.I)),
    ("never Practitioner Website Consolidation", re.compile(r"Practitioner Website Consolidation", re.I)),
    ("no Clinical Care Path report", re.compile(r"Clinical Care Path", re.I)),
    ("no sales tax automation", re.compile(r"sales tax automation", re.I)),
    ("no workshop", re.compile(r"workshop", re.I)),
    ("no Automation Lead title", re.compile(r"Automation Lead", re.I)),
    # The One Website Project has no launch date any more (2026-10-20). It is in progress, with
    # ongoing improvements through 2027.
    ("no retired One Website launch date", re.compile(r"(?<!\w)Dec(?:ember)?\.?\s+31,?\s+2026(?!\d)", re.I)),
]

# Any month and year near the CPA exams must be January 2027, whichever side it sits on.
_DATE = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
         r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+20\d\d")
_CPA_DATES = re.compile(rf"CPA exams?\W{{0,3}}(?:in\s+)?({_DATE})|({_DATE})\W{{0,3}}CPA exams?|Sitting\s+({_DATE})", re.I)
_JANUARY_2027 = re.compile(r"Jan(?:uary)?\.?\s+2027", re.I)


def wrong_cpa_dates(text: str) -> list[str]:
    return [m.group(0) for m in _CPA_DATES.finditer(text)
            if not _JANUARY_2027.fullmatch(next(g for g in m.groups() if g))]


RULES.append(("CPA exams only in January 2027", wrong_cpa_dates))

# Phrases a rule must not judge, with the reason. Only removed from the page named.
EXEMPT = {
    # The Lab's forecasting tools, kept as is: the construction backtest window ("the last 36
    # months"), and the second tab's 36 backtest origins, fold counts ("36 to 25") and chart
    # caption ("the last 36 points of your data").
    ("/lab", "no retired 36"): [re.compile(r"the last 36 (?:months|points)|\b36 origins\b|\b36 to \d+\b", re.I)],
}

# Every rule above added on 2026-10-19 or later, with copy it must catch and copy it must pass.
SELF_TESTS = [
    ("no retired 36", "cut a 36-hour review", "cut a 12-hour review, 4.36 GB, 360 days, 1,936"),
    ("no retired 40 hours", "~40 hrs of close work", "40 percent, 1,940 transactions"),
    ("never Accounting's lead", "Accounting's lead on the project", "the bridge between Accounting, IT, and Marketing"),
    ("never Practitioner Website Consolidation", "Practitioner Website Consolidation", "One Website Project"),
    ("no Clinical Care Path report", "a Clinical Care Path rebate report", "a royalty report"),
    ("no sales tax automation", "a sales tax automation", "reviewing a sales tax reconciliation"),
    ("no workshop", "Workshop resource", "Guide"),
    ("no Automation Lead title", "Staff Accountant, Automation Lead", "Staff Accountant · Technical Solutions"),
    # Restored on 2026-10-20: the VP of Accounting's selection is a fact, and neither title rule
    # may fire on it.
    ("no Automation Lead title", "Automation Lead", "the VP of Accounting selected me to lead the team's automation work"),
    ("never Accounting's lead", "Accounting's lead", "the VP of Accounting selected me to lead the team's automation work"),
    ("no retired One Website launch date", "launching December 31, 2026",
     "in progress, with ongoing improvements through 2027. December 2026. Dec 30, 2026. 31 records in 2026"),
    ("no retired One Website launch date", "in progress, launch Dec 31, 2026", "Dec 31, 2027"),
    ("CPA exams only in January 2027", "CPA exams December 2026",
     "CPA exams January 2027. Jan 2027 CPA exams. Sitting January 2027. CPA candidate in Illinois. Mar 2026 Staff"),
]


def hits(rule, text: str) -> list[str]:
    if callable(rule):
        return rule(text)
    return [text[max(0, m.start() - 40): m.end() + 20] for m in rule.finditer(text)]


def judged(url: str, name: str, text: str) -> str:
    for rx in EXEMPT.get((url, name), []):
        text = rx.sub(" ", text)
    return text


def self_test(rep: Report) -> None:
    rules = dict(RULES)
    for name, bad, good in SELF_TESTS:
        rep.check(f"rule '{name}' catches {bad!r} and passes {good!r}",
                  bool(hits(rules[name], bad)) and not hits(rules[name], good))


def main() -> int:
    rep = Report("Copy rules")
    self_test(rep)
    pages = site_pages()
    if not pages:
        rep.not_run("pages found", "no deployed HTML pages were found")
        return rep.finish()
    # Copy that lives in scripts: the tour's cards.
    tour = (ROOT / "assets" / "tour" / "tour-host.js").read_text(encoding="utf-8")
    strings = " ".join(re.findall(r'(?:title|body|targetName|instruction): "([^"]*)"', tour))
    for name, rule in RULES:
        found = hits(rule, strings)
        rep.check(f"tour cards: {name}", bool(strings) and not found, "; ".join(repr(h) for h in found[:3]))
    for url in pages:
        parser = TextOf()
        parser.feed(page_file(url).read_text(encoding="utf-8"))
        text = re.sub(r"\s+", " ", " ".join(parser.parts))
        for name, rule in RULES:
            found = hits(rule, judged(url, name, text))
            rep.check(f"{url}: {name}", not found, "; ".join(repr(h) for h in found[:3]))
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
                    for key in page.eval_on_selector_all("#cf-presets .preset", "bs => bs.map(b => b.dataset.preset)"):
                        page.click(f'button[data-preset="{key}"]')     # each preset's summary and chart text
                        texts.append(page.inner_text("#construction"))
                        texts += page.eval_on_selector_all("#construction desc", "ds => ds.map(d => d.textContent)")
                    page.check('input[name="cf-view"][value="24"]')
                    page.check('input[name="cf-metric"][value="revenue"]')
                    texts.append(page.inner_text("#construction"))
                    texts += page.eval_on_selector_all("#construction desc", "ds => ds.map(d => d.textContent)")
                    page.click("#cf-tab-own")                            # the second tab: a result and an error
                    page.click('button[data-sample="retail"]')
                    page.wait_for_function("() => (document.getElementById('ac-status').textContent || '').includes('Winner by backtest')")
                    texts.append(page.inner_text("#construction"))
                    texts += page.eval_on_selector_all("#construction desc", "ds => ds.map(d => d.textContent)")
                    page.set_input_files("#ac-file", files=[{"name": "bad.csv", "mimeType": "text/csv",
                                                              "buffer": b"date,value\n2020-01,1\n2020-04,2\n"}])
                    page.wait_for_function("() => !document.getElementById('ac-error').hidden")
                    texts.append(page.inner_text("#ac-error"))
                    page.keyboard.press("Control+k")
                    page.wait_for_selector("dialog.palette[open]")
                    texts.append(page.inner_text("dialog.palette"))
                text = re.sub(r"\s+", " ", " ".join(texts))
                for name, rule in RULES:
                    found = hits(rule, judged(url, name, text))
                    rep.check(f"rendered {url}: {name}", bool(text.strip()) and not found,
                              "; ".join(repr(h) for h in found[:3]))
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
