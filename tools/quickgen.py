"""The /quick page: the whole site on one fast, text-only page, with no JavaScript.

Nothing here is retyped. Every fact is read from where the site already states it:
the five Ortho items and their numbers from sitegen's CASES (the case studies' own
data), the summary and proof strip from index.html, the products from the Work
page's Products table, credentials from About, and contact details from Contact.
If a source page changes, `sitegen.py --check` reports /quick as stale.

The page carries its own small stylesheet and no script at all, so it renders in
full with JavaScript off. It follows the system light or dark setting.
"""

from __future__ import annotations

import re
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def _one(rx: str, html: str, what: str) -> re.Match:
    m = re.search(rx, html, re.S)
    if not m:
        raise SystemExit(f"quickgen: could not find {what}")
    return m


def _all(rx: str, html: str, what: str, at_least: int = 1) -> list:
    found = re.findall(rx, html, re.S)
    if len(found) < at_least:
        raise SystemExit(f"quickgen: expected at least {at_least} {what}, found {len(found)}")
    return found


def summary() -> tuple[list[str], str, list[tuple[str, str, str]]]:
    home = _read("index.html")
    status = _one(r'<div class="status">(.*?)</div>', home, "the hero status line").group(1)
    lines = [_text(s) for s in _all(r"<span>(.*?)</span>", status, "status items", 3)]
    lede = _text(_one(r'<p class="lede">(.*?)</p>', home, "the hero lede").group(1))
    proof = _one(r'<section class="proof"[^>]*>(.*?)</section>', home, "the proof strip").group(1)
    cells = _all(r'<a href="([^"]+)"[^>]*><span class="num">(.*?)</span><span class="label">(.*?)</span>',
                 proof, "proof cells", 4)
    return lines, lede, [(href, _text(n), _text(lbl)) for href, n, lbl in cells]


def products() -> list[tuple[str, str, str, list[tuple[str, str]]]]:
    work = _read("work.html")
    panel = _one(r'<section class="panel" id="products".*?<tbody>(.*?)</tbody>', work, "the Products table")
    out = []
    for row in _all(r"<tr>(.*?)</tr>", panel.group(1), "product rows", 5):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        name = _text(re.sub(r'<span class="kind">.*?</span>', "", tds[0]))
        kind = _text(_one(r'<span class="kind">(.*?)</span>', tds[0], "a product kind").group(1))
        links = [(href, _text(t)) for href, t in re.findall(r'<a href="([^"]+)">(.*?)</a>', tds[3])]
        out.append((name, kind, _text(tds[1]), links))
    return out


def credentials() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    about = _read("about.html")
    timeline = _one(r'<ul class="timeline">(.*?)</ul>', about, "the About timeline").group(1)
    study = [(_text(what), _text(when)) for when, what in
             re.findall(r'<span class="when">(.*?)</span><div><strong>(.*?)</strong>', timeline)
             if re.search(r"B\.S\.|Certificate|CPA exams", what)]
    if len(study) != 3:
        raise SystemExit(f"quickgen: expected the degree, the certificate and the CPA exams, found {study}")
    certs = _one(r'<ul class="certs">(.*?)</ul>', about, "the certifications list").group(1)
    found = _all(r'<a href="([^"]+)">(.*?)</a><span class="when">(.*?)</span>', certs, "certifications", 6)
    return study, [(href, _text(t), _text(w)) for href, t, w in found]


def contact() -> list[tuple[str, str, str]]:
    page = _read("contact.html")
    items = _one(r'<ul class="contact-list">(.*?)</ul>', page, "the contact list").group(1)
    found = _all(r'<span class="k">(.*?)</span><span><a href="([^"]+)">(.*?)</a>', items, "contact rows", 4)
    return [(_text(k), href, _text(t)) for k, href, t in found]


CSS = """
:root{--bg:#f2f3f0;--card:#fbfbf9;--ink:#131517;--ink2:#3c4045;--ink3:#6a6f75;--rule:#c9ccc6;--accent:#1e6b47}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#121416;--card:#1a1d20;--ink:#e9ebe7;--ink2:#c4c8c3;--ink3:#9aa09a;--rule:#3a3f44;--accent:#5cc28c}}
@font-face{font-family:"IBM Plex Sans";font-weight:400 700;font-display:swap;src:url(/assets/fonts/ibm-plex-sans-latin.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Mono";font-weight:500;font-display:swap;src:url(/assets/fonts/ibm-plex-mono-500-latin.woff2) format("woff2")}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--ink);text-decoration-color:var(--accent);text-underline-offset:3px}
a:hover{color:var(--accent)}
a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.skip{position:absolute;left:-999px;top:8px;background:var(--ink);color:var(--bg);padding:8px 12px}
.skip:focus{left:8px}
.top,main,footer{max-width:760px;margin:0 auto;padding:0 20px}
.top{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center;justify-content:space-between;padding-top:18px;padding-bottom:14px;border-bottom:1px solid var(--rule)}
.top strong{font-size:17px}
.top nav{display:flex;gap:18px;font-size:15px}
h1{font-size:34px;line-height:1.1;letter-spacing:-.02em;margin:28px 0 8px}
h2{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);margin:36px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--accent)}
h3{font-size:18px;margin:0}
p{margin:0 0 10px}
.status{color:var(--ink2);font-size:15px}
ul{list-style:none;margin:0;padding:0}
.proof li,.items>li{padding:12px 0;border-bottom:1px solid var(--rule)}
.num{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-weight:500;color:var(--accent)}
.proof .num{display:inline-block;min-width:8.5ch;margin-right:8px}
.kind{color:var(--ink3);font-size:14px;margin:2px 0 6px}
.muted{color:var(--ink2);font-size:15px}
.results{margin:6px 0 0;display:flex;flex-wrap:wrap;gap:4px 18px;font-size:15px}
.results li span{color:var(--ink2)}
.creds li,.contact li{display:flex;justify-content:space-between;gap:16px;padding:9px 0;border-bottom:1px solid var(--rule)}
.creds .when,.contact .k{color:var(--ink3);font-size:14px;white-space:nowrap}
.contact li{justify-content:flex-start}
.contact .k{min-width:80px}
footer{padding-top:28px;padding-bottom:40px;color:var(--ink3);font-size:14px}
""".strip()


def page(cases, favicon: str) -> str:
    status, lede, proof = summary()
    prods = products()
    study, certs = credentials()
    reach = contact()

    proof_li = "\n".join(f'      <li><a href="{escape(h)}"><span class="num">{escape(n)}</span></a> {escape(lbl)}</li>'
                         for h, n, lbl in proof)

    def case_li(c) -> str:
        res = "".join(f'<li><span class="num">{escape(r.value)}</span> <span>{escape(r.label)}</span></li>'
                      if r.numeric else f'<li><strong>{escape(r.value)}</strong> <span>{escape(r.label)}</span></li>'
                      for r in c.results)
        return (f'      <li><h3><a href="/work/{c.slug}">{escape(c.name)}</a></h3>'
                f'<p class="kind">{escape(c.kind)}</p><p class="muted">{escape(c.dek)}</p>'
                f'<ul class="results">{res}</ul></li>')

    def prod_li(p) -> str:
        name, kind, what, links = p
        ls = " · ".join(f'<a href="{escape(h)}">{escape(t)}</a>' for h, t in links)
        return (f'      <li><h3>{escape(name)}</h3><p class="kind">{escape(kind)}</p>'
                f'<p class="muted">{escape(what)}</p><p>{ls}</p></li>')

    study_li = "\n".join(f'      <li><span>{escape(w)}</span><span class="when">{escape(d)}</span></li>'
                         for w, d in study)
    cert_li = "\n".join(f'      <li><a href="{escape(h)}">{escape(t)}</a><span class="when">{escape(w)}</span></li>'
                        for h, t, w in certs)
    reach_li = "\n".join(f'      <li><span class="k">{escape(k)}</span><a href="{escape(h)}">{escape(t)}</a></li>'
                         for k, h, t in reach)
    status_line = ". ".join(escape(s) for s in status) + "."

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quick view · William Kim</title>
  <meta name="description" content="William Kim on one page: summary, the five Ortho projects and their numbers, products, credentials, contact and résumé. Text only.">
  <link rel="canonical" href="https://www.williamckim.com/quick">
  <meta name="theme-color" content="#f2f3f0">
  <!-- Generated by tools/quickgen.py from the site's own pages. No JavaScript, by design. -->
  <link rel="icon" href="{favicon}" />
  <link rel="preload" href="/assets/fonts/ibm-plex-sans-latin.woff2" as="font" type="font/woff2" crossorigin>
  <style>{CSS}</style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="top">
    <strong>William Kim</strong>
    <nav aria-label="Quick view"><a href="/">Full site</a><a href="/resume.pdf">Résumé (PDF)</a><a href="/contact">Contact</a></nav>
  </header>
  <main id="main">
    <h1>William Kim</h1>
    <p class="status">{status_line}</p>
    <p>{escape(lede)}</p>
    <ul class="proof" aria-label="Results">
{proof_li}
    </ul>

    <h2>At Ortho</h2>
    <ul class="items">
{chr(10).join(case_li(c) for c in cases)}
    </ul>

    <h2>Projects</h2>
    <ul class="items">
{chr(10).join(prod_li(p) for p in prods)}
    </ul>

    <h2>Credentials</h2>
    <ul class="creds">
{study_li}
{cert_li}
    </ul>

    <h2>Contact</h2>
    <ul class="contact">
{reach_li}
    </ul>
  </main>
  <footer><a href="/">Back to the full site</a></footer>
</body>
</html>
'''
