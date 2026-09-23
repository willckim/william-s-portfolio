# Tour Engine: vendored copy

| | |
|---|---|
| Source | github.com/willckim/tour-engine (private repo) |
| Commit | `de22e299057a22b2d330c116bff0826b507b46ac` |
| Commit date | 2026-09-19 15:00:46 -0500 |
| Vendored | 2026-09-23 |
| `tour.js` blob | `e8f133549b17bd24e9148f48a34e46d7294d227d` |
| Source sha256 | `1b3cb02ede2cc74d41f54d9f0b7b6e37d03a83fbee6e5f5fe563743ceea25af8` |
| Deployed sha256 | `298011d4982bdda7acf0194eb3c8d25197c1320a1e62f4629437848ace666d35` |

The deployed `assets/tour/tour.js` is the source plus four patches that disable
record mode (listed in `tools/vendor_tour.py`), and a two-line header. The styles
travel inside `tour.js`, so `tour.css` is not copied. The site's host adapter is
`assets/tour/tour-host.js`.

Update: `py tools/vendor_tour.py <tour-engine checkout>`, then `py tests/check_tour.py`.
