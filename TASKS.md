# williamckim.com: tasks

Upgrade from a portfolio people read to one they use. Static HTML, no build step,
deployed on Vercel with clean URLs. Not deployed: this file, `tools/`, `tests/`,
`TOUR_ENGINE.md`.

## Sources of truth
- `resume.pdf` (September 2026 master): every claim on the site
- `willckim/quantum-finance` at 4fd2323: QAOA, Monte Carlo, forecaster, Grover values
  (`tools/extract_qf.py` runs the seeded scripts and parses their output)
- `quantum-finance/04_security/pqc_readiness` at 5345b40: Mosca inputs
  (`tools/extract_pqc.py`) and published results (graded by `tests/check_mosca.py`)
- `forecasting-engine` (private, never pushed) at the commit in `tools/data/construction.json`:
  Construction Forecast data, scenario model and Excel workbook (`tools/extract_construction.py`,
  refuses a dirty tree, FORECAST_DIR overrides ~/OneDrive/forecasting-engine). The page shows the
  commit hash and "Source is private for now", never a repo link.
- `willckim/tour-engine` at 7eefca5: vendored with the recorder disabled
  (cloned at ~/OneDrive/tour-engine for check_tour's recorder control; TOUR_ENGINE_SRC overrides)

## Regenerate
- `py tools/sitegen.py` rewrites the header on every page, the five case studies,
  the Lab's quantum and construction regions, `assets/lab/pqc-data.js`,
  `assets/lab/construction-data.js` and `sitemap.xml`
- `--check` fails if any committed page differs from what it would write

## Commits, in order
- [x] 1. Content and date corrections
- [x] 2. Case study pages
- [x] 3. Lab page and Mosca calculator
- [x] 4. Tour Engine integration
- [x] 5. Grover visualizer
- [x] 6. Command palette
- [x] 7. Dark mode
- [x] 8. Polish and performance
- [x] 9. Construction Forecast panel (Lab, between Tour Engine and Post-Quantum Readiness)
  - [x] extractor, generator, scenario engine port, panel, palette entry, /quick via Products row
  - [x] tests/check_construction.py: browser vs engine Python for every preset and two custom mixes,
        five mutants, keyboard, text alternatives, reduced motion, no network, download, dirty-tree refusal
  - [x] check_copy: "Prairie Ridge Builders" always followed by "(fictional)"
  - [x] full check suite and Lighthouse /lab 95+ (99/100/100/100 on 2026-10-04)
  - [x] check_mosca preset selector scoped to #m-presets (it matched the new panel's presets)
  - [x] check_pages fetches FRED with a script user agent (FRED drops cookieless browser agents)
- [x] 10. Forecast your own data (second tab in the same panel)
  - [x] assets/lab/autocast.js: parser and a port of the engine's src/autoforecast.py, nothing uploaded
  - [x] tests/check_autocast.py: three FRED samples and five synthetic fixtures against the engine's Python,
        parser formats, one bad file per error message, drop and choose with no network request, CSV download,
        keyboard tabs, live regions, deterministic race test, seven mutants
  - [x] check_tour: a card counts as shown only when visible (Firefox 15/20 false failures before), runs guarded
- [ ] 11. Final gates, then push the site (the forecasting engine stays private, no remote)

## Checks (all in tests/, Python Playwright; `npm --prefix tests install` for axe and Lighthouse)
- [x] check_copy: no em dashes, semicolons or stale CPA date in visible copy
- [x] check_case_studies: template, word counts, accessible theme-aware diagrams
- [x] check_mosca: presets match the published report, three mutants caught
- [x] check_tour: tour completes at desktop and phone width, recorder off (with control)
- [x] check_grover: optimal iteration within 1% of theory, two mutants caught
- [x] check_palette: opens, filters, navigates, traps focus, covers every page
- [x] check_themes: axe WCAG 2.1 AA on every page in both themes, token contrast, toggle
- [x] check_pages: zero console errors on every page
- [x] check_layers: at the bottom of every page, both themes, phone and desktop, no fixed or
      sticky layer but the header covers content (controls: an injected band, the old stage)
- [x] lighthouse: 95+ in all four categories, mobile, on Home, Work, a case study, Lab
- [x] check_pages links: tour-engine link removed (repo stays private). linkedin.com
      excluded, as it answers 999 to every signed-out request.

## Decided (2026-09-23)
- Tour Engine repo stays private: no links, "Source is private for now" line instead.
- LinkedIn is checked by hand, not by the automated link check.
- Mutation figure is the engine's own suites only: 111 of 111 across 143 checks
  (record 38/28, CSP 11/42, host 62/73), run against 7eefca5 on 2026-09-27.
  Was 109 of 109 across 140 at de22e29 until the click-step resume fix.
- Three production systems (Concur, Royalty, Time Tracker). Fast Close is a fix.
- Mosca inputs come from a clean checkout of the pushed toolkit (5345b40). Set
  PQC_DIR to it for tools/extract_pqc.py and tests/check_mosca.py.

## Flaky checks, investigated (2026-09-28)
Both were test problems, not site bugs. After the fixes: 30 of 30 each.
- check_motion view transition (11 of 30 failed): Playwright's bundled Chromium 145
  drops a cross-document view transition when the new page reveals within about 80 ms.
  Chrome 153 dropped 0 of 70, headed and headless, and bare two-page HTML never dropped
  it in 145. The row is now graded in installed Chrome, as check_tour already was.
- check_tour spotlight alignment (9 of 30 failed, 105 to 908 px): the browser at times
  delivers no frames for 150 to 450 ms while the page's threads sit idle. The spotlight's
  0.2 s glide and Lenis only advance on frames, so nothing moved, and two samples 100 ms
  apart passed for settled. Once frames resumed the spotlight landed exactly. The check
  now waits for Lenis idle, the glide finished and two rendered frames. Mutants caught:
  a spotlight that never follows a scroll (260 px) and one drawn 20 px off.

## Cinematic upgrade (started 2026-09-27)
Motion is enhancement only: every page reads in full without JavaScript, and under
prefers-reduced-motion it behaves like the calm version. /quick is the recruiter escape
hatch: text only, no script. Push only after all five phases pass the gates.
- [x] 1. Foundation and quick view (GSAP 3.15.0, Lenis 1.3.26, three 0.186.1 import map, /quick)
- [x] 2. Preloader and hero (intro once per session, 1.5 s cap, particle hero with bloom, split headline)
- [x] 3. Scroll story (sticky stage, 7 chapter sections, particle numbers graded against the proof strip)
- [x] 4. Work index previews (large-type list, 5 canvas loops, thumbnails on touch, diagrams draw in)
- [x] 5. Polish (ledger-line view transition with overlay fallback, cursor, magnetic buttons, display type, Lab and About reveals)
- Checks added: check_motion (quick, header link, reduced motion, CDN down, keyboard,
  transitions, mid-session reduced-motion teardown, hybrid touch cursor). Lighthouse
  gates are per page now (tests/lighthouse.py GATES).

## Open
- The résumé PDF still says "145 of 145". It is a PDF, so it needs updating at source.
