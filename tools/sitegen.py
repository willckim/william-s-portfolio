"""Generate the shared site header on every page, and the five case study pages.

    py tools/sitegen.py            rewrite the header everywhere, regenerate work/*.html
    py tools/sitegen.py --check    exit 1 if any page differs from what this would write

The site has no build step on Vercel: the output of this script is committed, and
the pages are plain HTML. This file is the one place the header and the case study
template live, so the five case studies cannot drift apart.

CONTENT RULE: every fact in CASES comes from the September 2026 résumé. Ortho
confidentiality: no internal code, screenshots, vendor contract details, data or
names. "What I'd do next" is a proposal, phrased as one.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagram import Diagram, Group, Stage, render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- header -----
NAV = (
    ("home", "/", "ledger", "Home"),
    ("work", "/work", "blueprint", "Work"),
    ("about", "/about", "violet", "About"),
    ("contact", "/contact", "coral", "Contact"),
)

PAGES = {  # file -> the nav tab it sits under
    "index.html": "home",
    "work.html": "work",
    "about.html": "about",
    "contact.html": "contact",
}


def header(current: str) -> str:
    items = "\n".join(
        f'          <li><a href="{href}" data-accent="{accent}"'
        f'{" aria-current=" + chr(34) + "page" + chr(34) if key == current else ""}>{label}</a></li>'
        for key, href, accent, label in NAV)
    return f'''<header class="site-header">
    <div class="wrap">
      <a class="brand" href="/"><span class="mark">WK</span>William Kim<span class="sub">Finance × Engineering</span></a>
      <button class="menu-btn" aria-expanded="false" aria-controls="nav">Menu</button>
      <nav aria-label="Primary">
        <ul class="tabs" id="nav">
{items}
        </ul>
      </nav>
    </div>
  </header>'''


HEADER_RX = re.compile(r'<header class="site-header">.*?</header>', re.S)

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='7' fill='%23f5f1ea'/%3E%3Cpath d='M6 9l5 15 5-10 5 10 "
           "5-15' fill='none' stroke='%23b6451a' stroke-width='3' stroke-linecap='round' "
           "stroke-linejoin='round'/%3E%3C/svg%3E")

# ----------------------------------------------------------- case studies -----


@dataclass(frozen=True)
class Result:
    value: str
    label: str
    numeric: bool = True        # IBM Plex Mono is for numbers only


@dataclass(frozen=True)
class Case:
    slug: str
    name: str
    kind: str
    dek: str
    description: str
    problem: tuple[str, ...]
    did: tuple[str, ...]
    how: str
    diagram: Diagram
    results: tuple[Result, ...]
    nxt: str
    stack: tuple[str, ...]


CASES = (
    Case(
        slug="concur",
        name="Concur Automation",
        kind="Production · LLM system",
        dek="An LLM-assisted classifier for corporate card transactions, built so the model can suggest "
            "but never decide.",
        description="Case study: an LLM-assisted classifier for about 1,900 corporate card transactions "
                    "per cycle, inside deterministic rule guardrails. 36 hours to 10 minutes.",
        problem=(
            "Every cycle, about 1,900 corporate card transactions had to be reviewed and classified before "
            "the close could move. The monthly review took 36 hours, inside a five-day close across two "
            "legal entities.",
        ),
        did=(
            "I gathered requirements from accounting, IT, and BI, then built the classifier in C#/.NET on "
            "Azure Functions. The OpenAI API proposes a classification for each transaction, and "
            "deterministic rules sit around every call.",
            "Then I benchmarked it against the human reviewers, transaction by transaction. Humans still "
            "post, and every run writes an audit log.",
        ),
        how="The model's answer is an input to the rules, not an output of the system. Nothing reaches "
            "posting without passing the rules and a person.",
        diagram=Diagram(
            title="Concur Automation: guardrail design",
            desc="Corporate card transactions from SAP Concur, about 1,900 per cycle, go to an Azure "
                 "Function written in C#/.NET. Inside deterministic rule guardrails, the OpenAI API "
                 "proposes a classification and deterministic rules check every proposal. An accountant "
                 "then reviews the classified transactions, and a person posts them. The model never "
                 "posts, and every step writes to the audit log.",
            flow=(
                Stage("source", "SAP Concur corporate card transactions, about 1,900 per cycle"),
                Stage("processing", "Azure Function in C#/.NET prepares each transaction"),
                Group("Deterministic rule guardrails", (
                    Stage("model", "OpenAI API proposes a classification"),
                    Stage("guardrail", "Deterministic rules check every proposal", strong=True),
                )),
                Stage("review", "An accountant reviews the classified transactions"),
                Stage("output", "A person posts. The model never posts."),
            ),
            footnote="Every step writes to the audit log.",
        ),
        results=(
            Result("36 h → 10 min", "Monthly review time"),
            Result("95–97%", "Exact match to human reviewers"),
            Result("0", "Misclassifications in the benchmark"),
            Result("~1,900", "Transactions per cycle"),
        ),
        nxt="Re-run the human benchmark on a fresh cycle each quarter, so the match rate stays a measured "
            "number rather than a launch-day one. Then test the same guardrail pattern, one phase at a "
            "time, on the next manual review in the close.",
        stack=("C#/.NET", "Azure Functions", "OpenAI API", "SAP Concur", "Deterministic rules",
               "Audit log"),
    ),
    Case(
        slug="royalty",
        name="Royalty Calculation Pipeline",
        kind="Production",
        dek="A rule-based pipeline that replaced a manual Excel and pivot table workflow for a monthly "
            "royalty report.",
        description="Case study: a rule-based C#/.NET pipeline on Azure Functions with per-family rate "
                    "logic and validation checks. Monthly royalty check from about 30 to 10 minutes.",
        problem=(
            "A month-end royalty report was built by hand in Excel and pivot tables. The rate logic "
            "differs by family, and checking the result each month took about 30 minutes.",
        ),
        did=(
            "I designed and shipped a rule-based system in C#/.NET on Azure Functions. It applies the "
            "per-family rate logic to the month's activity data, then runs automated validation checks "
            "before anyone reads the numbers.",
            "There is no model in it. The rules are the whole system, and they are written down.",
        ),
        how="Validation sits between the calculation and the person, so the review starts from numbers "
            "that have already passed their checks.",
        diagram=Diagram(
            title="Royalty Calculation Pipeline: architecture",
            desc="Monthly activity data goes to an Azure Function written in C#/.NET, which applies the "
                 "per-family rate logic. Automated validation checks run on every result. An accountant "
                 "then checks the royalty report, and the output is the monthly royalty report that "
                 "replaced the Excel and pivot table workflow.",
            flow=(
                Stage("source", "Monthly activity data"),
                Stage("processing", "Azure Function in C#/.NET applies the per-family rate logic"),
                Stage("guardrail", "Automated validation checks run on every result", strong=True),
                Stage("review", "An accountant checks the royalty report"),
                Stage("output", "Monthly royalty report, replacing the Excel and pivot table workflow"),
            ),
        ),
        results=(
            Result("~30 → ~10 min", "Monthly royalty check"),
        ),
        nxt="Compare each month's output with the prior verified month before the report goes out, so a "
            "shift in the input data is caught by a check rather than by a reader.",
        stack=("C#/.NET", "Azure Functions", "Rule-based rate logic", "Validation checks"),
    ),
    Case(
        slug="fast-close",
        name="Fast Close Report Fix",
        kind="Financial systems",
        dek="A SQL-based close report that produced wrong data for months, traced to its defect and "
            "followed until it ran clean.",
        description="Case study: isolating a defect in the SQL-based Fast Close report, handing BI the "
                    "exact fix, and following through four months until the August close ran clean.",
        problem=(
            "The Fast Close report is SQL-based, and it had produced wrong data for months. Wrong numbers "
            "in a close report are worse than none, because people act on them.",
        ),
        did=(
            "I wrote the SQL myself to isolate the defect, then gave the BI team the exact fix to apply.",
            "Then I followed through for four months, close by close, until the August close ran clean.",
        ),
        how="The diagnosis was mine and the change went through BI, so the fix was applied by the people "
            "who maintain the report.",
        diagram=Diagram(
            title="Fast Close Report Fix: how the defect was closed",
            desc="The SQL-based Fast Close report had produced wrong data for months. Diagnostic SQL "
                 "isolated the defect. The exact fix was handed to BI to apply. Four months of "
                 "follow-through, close by close, confirmed it, and the August close ran clean.",
            flow=(
                Stage("source", "Fast Close report, SQL-based, wrong data for months"),
                Stage("processing", "Diagnostic SQL isolates the defect"),
                Stage("guardrail", "The exact fix, applied by BI", strong=True),
                Stage("review", "Four months of follow-through, close by close"),
                Stage("output", "The August close ran clean"),
            ),
        ),
        results=(
            Result("4 months", "Of follow-through, close by close"),
            Result("Clean", "August close", numeric=False),
        ),
        nxt="Turn the diagnostic SQL into a standing check that runs before each close, so a regression "
            "shows up in hours instead of months.",
        stack=("T-SQL", "Diagnostic queries", "BI partnership"),
    ),
    Case(
        slug="time-tracker",
        name="Accounting Time Tracker",
        kind="Production",
        dek="A timekeeping tool for the accounting building, with an approval workflow and an audit "
            "trail, rebuilt after IT review.",
        description="Case study: an Azure Function timekeeping tool with approval workflow and audit "
                    "trail. Piloted, rebuilt after IT review, now in production.",
        problem=(
            "The accounting building needed a timekeeping tool with an approval step and an audit trail "
            "behind every entry.",
        ),
        did=(
            "I designed and built it as an Azure Function, with an approval workflow and a full audit "
            "trail.",
            "It was piloted first, then rebuilt after IT review, and the rebuilt version is the one in "
            "production. A tool the accounting team depends on should meet the same bar as any system IT "
            "supports.",
        ),
        how="Every entry is logged before it can be approved, so the approval is always of something with "
            "a trail behind it.",
        diagram=Diagram(
            title="Accounting Time Tracker: architecture",
            desc="Time entries from the accounting building go to an Azure Function timekeeping tool. "
                 "Every entry is written to the audit trail. The approval workflow is the human review "
                 "step, and the output is approved time, in production after a pilot and a rebuild for "
                 "IT review.",
            flow=(
                Stage("source", "Time entries from the accounting building"),
                Stage("processing", "Azure Function timekeeping tool"),
                Stage("guardrail", "Audit trail on every entry", strong=True),
                Stage("review", "Approval workflow"),
                Stage("output", "Approved time, in production after IT review"),
            ),
        ),
        results=(
            Result("In production", "After a pilot and a rebuild for IT review", numeric=False),
        ),
        nxt="Use the approved hours to rank which close tasks to automate next, so the automation queue "
            "is ordered by measured time rather than by guesswork.",
        stack=("Azure Functions", "C#/.NET", "Approval workflow", "Audit trail"),
    ),
    Case(
        slug="consolidation",
        name="Practitioner Website Consolidation",
        kind="Cross-functional · launching December 31, 2026",
        dek="Three practitioner platforms becoming one, with the specification layer written between "
            "Marketing and IT.",
        description="Case study: authoring the specification layer for consolidating three practitioner "
                    "platforms into one, and surfacing a tax compliance requirement no document had.",
        problem=(
            "Three practitioner platforms are being consolidated into one. The project spans IT, "
            "Accounting, and Marketing, and it needed a precise written account of what the consolidated "
            "platform must do, in terms both Marketing and IT could build from.",
        ),
        did=(
            "I was selected as the cross-functional bridge between IT, Accounting, and Marketing. I author "
            "the specification layer: a workflows document, a decisions sheet, and a clickable HTML "
            "prototype.",
            "Along the way I surfaced a tax compliance requirement missing from all project documentation, "
            "W-9/TIN and verified banking before proceeds accrue, and drove it into the ERP design.",
        ),
        how="The specification is where a requirement either gets written down or gets missed, so the tax "
            "requirement sits there as a gate on the design.",
        diagram=Diagram(
            title="Practitioner Website Consolidation: specification flow",
            desc="Three practitioner platforms feed a specification layer made of a workflows document, a "
                 "decisions sheet, and a clickable HTML prototype. A tax compliance requirement, W-9/TIN "
                 "and verified banking before proceeds accrue, acts as the guardrail. Marketing and IT "
                 "work from one specification, and the output is one platform, launching December 31, "
                 "2026, with the requirement in the ERP design.",
            flow=(
                Stage("source", "Three practitioner platforms"),
                Stage("processing", "Specification layer: workflows document, decisions sheet, clickable "
                                    "HTML prototype"),
                Stage("guardrail", "Tax compliance requirement: W-9/TIN and verified banking before "
                                   "proceeds accrue", strong=True),
                Stage("review", "Marketing and IT work from one specification"),
                Stage("output", "One platform, launching December 31, 2026, with the requirement in the "
                                "ERP design"),
            ),
        ),
        results=(
            Result("3 → 1", "Practitioner platforms"),
            Result("Dec 31, 2026", "Launch"),
            Result("1", "Tax compliance requirement surfaced that no project document had"),
        ),
        nxt="Turn the tax compliance requirement into test cases, so the launch is checked against it, not "
            "only designed for it.",
        stack=("Specification writing", "Workflows document", "Decisions sheet", "HTML prototype",
               "ERP design"),
    ),
)


def _paras(ps: tuple[str, ...]) -> str:
    return "\n".join(f"          <p>{escape(p)}</p>" for p in ps)


def case_page(i: int) -> str:
    c = CASES[i]
    prev_c, next_c = CASES[i - 1], CASES[(i + 1) % len(CASES)]
    results = "\n".join(
        f'          <div><dt>{escape(r.label)}</dt>'
        f'<dd class="{"num" if r.numeric else "word"}">{escape(r.value)}</dd></div>' for r in c.results)
    chips = "\n".join(f"          <li>{escape(s)}</li>" for s in c.stack)
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(c.name)} · Case study · William Kim</title>
  <meta name="description" content="{escape(c.description)}">
  <link rel="canonical" href="https://www.williamckim.com/work/{c.slug}">
  <meta name="theme-color" content="#f2f3f0">
  <!-- Generated by tools/sitegen.py. Edit the content there, then run it. -->
  <link rel="icon" href="{FAVICON}" />
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body data-accent="blueprint" data-page="case-{c.slug}">
  <a class="skip" href="#main">Skip to content</a>

  {header("work")}

  <main id="main">
    <div class="wrap case">
      <nav class="crumbs" aria-label="Breadcrumb"><a href="/work">Work</a><span aria-hidden="true"> / </span><span aria-current="page">{escape(c.name)}</span></nav>
      <div class="page-head">
        <p class="kind">{escape(c.kind)}</p>
        <h1>{escape(c.name)}</h1>
        <p>{escape(c.dek)}</p>
      </div>

      <section class="ledger" aria-labelledby="problem-h">
        <aside><h2 id="problem-h">Problem</h2></aside>
        <div class="prose">
{_paras(c.problem)}
        </div>
      </section>

      <section class="ledger" aria-labelledby="did-h">
        <aside><h2 id="did-h">What I did</h2></aside>
        <div class="prose">
{_paras(c.did)}
        </div>
      </section>

      <section class="ledger" aria-labelledby="how-h">
        <aside><h2 id="how-h">How it works</h2><p>{escape(c.how)}</p></aside>
        <figure class="diagram-wrap">
          {render(c.diagram, "dg")}
        </figure>
      </section>

      <section class="ledger" aria-labelledby="results-h">
        <aside><h2 id="results-h">Results</h2><p>As stated on the résumé.</p></aside>
        <dl class="results">
{results}
        </dl>
      </section>

      <section class="ledger" aria-labelledby="next-h">
        <aside><h2 id="next-h">What I'd do next</h2></aside>
        <div class="prose">
          <p>{escape(c.nxt)}</p>
        </div>
      </section>

      <section class="ledger" aria-labelledby="stack-h">
        <aside><h2 id="stack-h">Stack</h2></aside>
        <ul class="chips">
{chips}
        </ul>
      </section>

      <nav class="case-nav" aria-label="Case studies">
        <a href="/work/{prev_c.slug}"><span>Previous</span>{escape(prev_c.name)}</a>
        <a href="/work/{next_c.slug}"><span>Next</span>{escape(next_c.name)}</a>
      </nav>
    </div>
  </main>

  <footer class="site-footer">
    <div class="wrap">
      <span>© 2026 William Kim</span>
      <span><a href="/work">All work</a></span>
    </div>
  </footer>

  <script src="/assets/site.js"></script>
</body>
</html>
'''


# ---------------------------------------------------------------- driver -----
def expected() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for name, key in PAGES.items():
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        if len(HEADER_RX.findall(text)) != 1:
            raise SystemExit(f"{name}: expected exactly one site header")
        out[path] = HEADER_RX.sub(lambda m: header(key), text)
    for i, c in enumerate(CASES):
        out[ROOT / "work" / f"{c.slug}.html"] = case_page(i)
    return out


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, text in expected().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path.relative_to(ROOT).as_posix())
        if not check:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if check:
        print("stale: " + ", ".join(stale) if stale else "all generated pages are current")
        return 1 if stale else 0
    print("wrote: " + (", ".join(stale) or "nothing, all current"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
