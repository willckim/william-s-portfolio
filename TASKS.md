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
- `willckim/tour-engine` at de22e29: vendored with the recorder disabled

## Regenerate
- `py tools/sitegen.py` rewrites the header on every page, the five case studies,
  the Lab's quantum region, `assets/lab/pqc-data.js` and `sitemap.xml`
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

## Checks (all in tests/, Python Playwright; `npm --prefix tests install` for axe and Lighthouse)
- [x] check_copy: no em dashes, semicolons or stale CPA date in visible copy
- [x] check_case_studies: template, word counts, accessible theme-aware diagrams
- [x] check_mosca: presets match the published report, three mutants caught
- [x] check_tour: tour completes at desktop and phone width, recorder off (with control)
- [x] check_grover: optimal iteration within 1% of theory, two mutants caught
- [x] check_palette: opens, filters, navigates, traps focus, covers every page
- [x] check_themes: axe WCAG 2.1 AA on every page in both themes, token contrast, toggle
- [x] check_pages: zero console errors on every page
- [x] lighthouse: 95+ in all four categories, mobile, on Home, Work, a case study, Lab
- [x] check_pages links: tour-engine link removed (repo stays private). linkedin.com
      excluded, as it answers 999 to every signed-out request.

## Decided (2026-09-23)
- Tour Engine repo stays private: no links, "Source is private for now" line instead.
- LinkedIn is checked by hand, not by the automated link check.
- Mutation figure is the engine's own suites only: 109 of 109 across 140 checks
  (record 38/28, CSP 11/42, host 60/70), run against de22e29 on 2026-09-23.
- Three production systems (Concur, Royalty, Time Tracker). Fast Close is a fix.
- Mosca inputs come from a clean checkout of the pushed toolkit (5345b40). Set
  PQC_DIR to it for tools/extract_pqc.py and tests/check_mosca.py.

## Cinematic upgrade (started 2026-09-27)
Motion is enhancement only: every page reads in full without JavaScript, and under
prefers-reduced-motion it behaves like the calm version. /quick is the recruiter escape
hatch: text only, no script. Push only after all five phases pass the gates.
- [x] 1. Foundation and quick view (GSAP 3.15.0, Lenis 1.3.26, three 0.186.1 import map, /quick)
- [x] 2. Preloader and hero (intro once per session, 1.5 s cap, particle hero with bloom, split headline)
- [x] 3. Scroll story (sticky stage, 7 chapter sections, particle numbers graded against the proof strip)
- [ ] 4. Work index previews
- [ ] 5. Polish
- Checks added: check_motion (quick, header link, reduced motion, CDN down). Lighthouse
  gates are per page now (tests/lighthouse.py GATES).

## Open
- The résumé PDF still says "145 of 145". It is a PDF, so it needs updating at source.
