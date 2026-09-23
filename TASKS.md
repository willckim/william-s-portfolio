# williamckim.com: tasks

Upgrade from a portfolio people read to one they use. Static HTML, no build step,
deployed on Vercel with clean URLs. Not deployed: this file, `tools/`, `tests/`,
`TOUR_ENGINE.md`.

## Sources of truth
- `resume.pdf` (September 2026 master): every claim on the site
- `willckim/quantum-finance` at 4fd2323: QAOA, Monte Carlo, forecaster, Grover values
  (`tools/extract_qf.py` runs the seeded scripts and parses their output)
- `quantum-finance/04_security/pqc_readiness` at c57a2e0: Mosca inputs
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
- [ ] check_pages links: tour-engine repo is private (404), LinkedIn returns 999 to
      signed-out visitors. Push is held until William decides both.

## Open questions (need William)
- Make `willckim/tour-engine` public, or drop the Lab's repo link.
- LinkedIn cannot pass an automated 200 check. Waive it, or verify by hand.
- Home proof strip: "~40 hrs" and "4 production systems" are aggregates, so they link
  to the Ortho ledger, not one case study. "4" is not stated on the résumé.
