# williamckim.com: tasks

Upgrade from a portfolio people read to one they use. Static HTML, no build step,
deployed on Vercel with clean URLs. Not deployed: this file, `tools/`, `tests/`.

## Sources of truth
- `resume.pdf` (September 2026 master): every claim on the site
- `willckim/quantum-finance`: QAOA, Monte Carlo, forecaster, Grover values
- `quantum-finance/04_security/pqc_readiness`: Mosca inputs and published results
  (local clone only, not yet on GitHub: see Open questions)
- `willckim/tour-engine`: the engine, vendored with the recorder disabled

## Commits, in order
- [ ] 1. Content and date corrections (CPA December 2026, Now block, How I work, chips)
- [ ] 2. Case study pages: /work/concur, royalty, fast-close, time-tracker, consolidation
- [ ] 3. Lab page and Mosca calculator, with preset check and mutation test
- [ ] 4. Tour Engine integration: host adapter, site tour, end-to-end check
- [ ] 5. Grover visualizer, with the 1% theory check
- [ ] 6. Command palette (Cmd/Ctrl+K), with open/filter/navigate check
- [ ] 7. Dark mode: tokens, toggle, hero retune, 4.5:1 contrast check
- [ ] 8. Polish and performance: type scale, view transitions, Lighthouse, links

## Gates before push
- [ ] Lighthouse mobile 95+ (Perf, A11y, BP, SEO): Home, Work, one case study, Lab
- [ ] Zero console errors on every page
- [ ] Every external link returns 200
- [ ] Mosca presets match the repo output, and a flipped comparison fails the check
- [ ] Grover target probability at the optimal iteration within 1% of theory
- [ ] Tour completes end to end
- [ ] Command palette opens, filters, navigates

## Open questions (need William)
- `04_security` exists only in the local quantum clone (commit d452e61 unpushed, plus
  uncommitted v2 edits). The Lab links to it, so the link 404s until it is pushed.
- `tour-engine` is a private repo, so the Lab's repo link 404s for visitors.
