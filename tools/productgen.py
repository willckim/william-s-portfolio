"""The two 3D product case studies and their live demos, rendered with the case study template.

Personal projects, no client claims, and no source links: both repos stay private.
Every number here is read from tools/data/demos.json, the pin tools/build_demos.py
writes for the build in demos/, so the test counts and download sizes are the ones
of the code the page actually runs.

Each page shows a poster and a "Launch the demo" button. Nothing from demos/ loads
until the button is pressed (assets/demo-launch.js). The Quote Engine is started with
its real 2-line embed snippet, the apartment studio in a frame with a full screen
button, at the lighter quality on phones.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from casemodel import Case, Result
from diagram import Diagram, Stage

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "tools" / "data" / "demos.json").read_text(encoding="utf-8"))
RESULTS_NOTE = "From the test runs on the source commit this demo was built from."
EMBED_SRC = "/demos/quote-engine/quote-builder-embed.js"
SNIPPET = f'<script src="{EMBED_SRC}"></script>\n<custom-quote-builder demo-mode></custom-quote-builder>'


def mb(n: int) -> str:
    return f"{round(n / 1_000_000)} MB"


QE, APT = PINS["quote-engine"], PINS["lakeview"]

CASES = (
    Case(
        slug="quote-engine",
        name="3D Quote Engine",
        kind="Personal project · 3D configurator and instant quote",
        dek="A white-label 3D configurator and instant quote tool that contractors embed on their own site "
            "with a 2-line snippet.",
        description="Case study and live demo: a white-label 3D configurator and instant quote tool, "
                    "embedded with a 2-line snippet. The demo is a luxury louvered pergola.",
        problem=(
            "A contractor's website usually ends at a contact form. A visitor who wants to know what a "
            "pergola would cost, and how it would look, has to wait for a call back.",
        ),
        did=(
            "I built a configurator that runs inside the contractor's own site. The demo is a luxury "
            "louvered pergola with an optional outdoor kitchen. The price range updates live with an "
            "itemized breakdown, add-ons appear in the 3D scene, and the scene has day, sunset and night "
            "modes.",
            "The visitor leaves with a branded PDF quote. The widget runs in Shadow DOM, so the host site's "
            "styles cannot break it.",
        ),
        how="One script tag and one element. Prices live in a config file beside the script, so a "
            "contractor changes a price without touching code.",
        diagram=Diagram(
            title="3D Quote Engine: from snippet to quote",
            desc="A contractor's own site, on any CMS, adds a 2-line snippet that loads the widget inside "
                 "Shadow DOM. Every price and rule comes from one validated pricing file. The visitor "
                 "configures the pergola and sees a live itemized price range, and leaves with a branded "
                 "PDF quote.",
            flow=(
                Stage("source", "The contractor's own site, on any CMS"),
                Stage("processing", "A 2-line snippet loads the widget inside Shadow DOM"),
                Stage("guardrail", "Every price and rule from one validated pricing file", strong=True),
                Stage("review", "The visitor configures it, with a live itemized price range"),
                Stage("output", "A branded PDF quote"),
            ),
        ),
        results=(
            Result(str(QE["tests"]["unit"]), "Unit tests"),
            Result(str(QE["tests"]["browser"]), "Browser checks"),
            Result("2 lines", "To embed it on a site"),
        ),
        nxt="Ship a second niche from the same engine, so the claim that only the config changes is tested "
            "by a real swap rather than stated.",
        stack=("TypeScript", "three.js", "Web Components", "Shadow DOM", "jsPDF", "Vite", "Vitest",
               "Playwright"),
    ),
    Case(
        slug="apartment-studio",
        name="Apartment Walkthrough Studio",
        kind="Personal project · 3D walkthrough",
        dek="Turns a floor plan into a 3D apartment you can walk through first-person.",
        description="Case study and live demo: a floor plan turned into a 3D apartment you can walk "
                    "through, with a dollhouse view, finish swapping and a PDF design book.",
        problem=(
            "A floor plan shows where the walls are, not what the place feels like. Choosing finishes and "
            "placing furniture from a flat drawing is guesswork.",
        ),
        did=(
            "I built a studio that turns a floor plan into a 3D apartment. The demo is The Lakeview "
            "One-Bedroom. You walk it first-person, or switch to a dollhouse view to move furniture.",
            "You can swap finishes, upload photos onto surfaces, set the room lights, and export a PDF "
            "design book.",
        ),
        how="The floor plan is a layout file. The studio builds the rooms and furniture from it, then "
            "renders them in the browser.",
        diagram=Diagram(
            title="Apartment Walkthrough Studio: from floor plan to design book",
            desc="A floor plan, stored as a layout file, becomes a 3D apartment in the browser. You walk "
                 "it first-person or move furniture in the dollhouse view, customize finishes, photos on "
                 "surfaces and room lights, and export a PDF design book.",
            flow=(
                Stage("source", "A floor plan, stored as a layout file"),
                Stage("processing", "The studio builds a 3D apartment in the browser"),
                Stage("review", "Walk it first-person, or move furniture in the dollhouse view"),
                Stage("processing", "Customize finishes, photos on surfaces and room lights", strong=True),
                Stage("output", "A PDF design book"),
            ),
        ),
        results=(
            Result(str(APT["tests"]["unit"]), "Unit tests"),
            Result(str(APT["tests"]["browser"]), "Browser checks"),
            Result(mb(APT["download_bytes"]["high"]), "Download at full quality"),
        ),
        nxt="Load a second floor plan, one the studio was not built around, so the layout format is tested "
            "by a plan it has never seen.",
        stack=("TypeScript", "three.js", "glTF", "WebGL", "jsPDF", "Vite", "Vitest", "Playwright"),
    ),
)

POSTER_ALT = {
    "quote-engine": "The pergola demo at sunset, with the outdoor kitchen added under the roof and its "
                    "width, length and height marked",
    "apartment-studio": "The Lakeview One-Bedroom in dollhouse view, with the studio's design panel beside it",
}
POSTER = {"quote-engine": "quote-engine", "apartment-studio": "lakeview"}
TRY = {
    "quote-engine": "Drag the sliders, add the outdoor kitchen, download your quote.",
    "apartment-studio": "Press V to walk, E to customize a surface. On a phone, tap First-Person Mode.",
}


def note(slug: str) -> str:
    if slug == "quote-engine":
        return "Demo only, nothing you enter is sent anywhere."
    sizes = APT["download_bytes"]
    return (f"About {mb(sizes['high'])} to download. Phones get the lighter quality setting, about "
            f"{mb(sizes['low'])}.")


def demo_block(slug: str) -> str:
    name = POSTER[slug]
    poster = (f'<img class="demo-poster" src="/assets/work/{name}-poster-1200.webp" '
              f'srcset="/assets/work/{name}-poster-640.webp 640w, /assets/work/{name}-poster-1200.webp 1200w" '
              f'sizes="(min-width: 1180px) 1100px, 100vw" width="1200" height="675" '
              f'alt="{escape(POSTER_ALT[slug])}" fetchpriority="high">')
    embed = ""
    if slug == "quote-engine":
        embed = (f'\n        <p class="demo-embed">The demo starts with the embed exactly as a contractor would paste it:</p>'
                 f'\n        <pre class="demo-snippet"><code>{escape(SNIPPET)}</code></pre>')
    return f'''<section class="demo" aria-label="Live demo" data-demo="{slug}">
        <div class="demo-stage">
          {poster}
          <div class="demo-cta">
            <p class="demo-try">{escape(TRY[slug])}</p>
            <button class="btn primary" type="button" data-demo-launch>Launch the demo</button>
            <p class="demo-note">{escape(note(slug))}</p>
            <noscript><p class="demo-note">The demo needs JavaScript.</p></noscript>
          </div>
        </div>{embed}
      </section>'''
