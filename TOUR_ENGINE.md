# Tour Engine: vendored copy

| | |
|---|---|
| Source | github.com/willckim/tour-engine (private repo) |
| Commit | `7eefca5fd417a6dfd1de212579028e627c1f1916` |
| Commit date | 2026-09-27 19:58:05 -0500 |
| Vendored | 2026-09-27 |
| `tour.js` blob | `37aad171f43ce0cc07fa0c55987c83dc037b18f9` |
| Source sha256 | `c164abfff4e9b134a7861ab48a5888541a9c27cc2d73b4ad2d9341ed7333a629` |
| Deployed sha256 | `7e2e8402cd42f2e63e150beab4112558f72d4cd068be86b6701292f3dca040c7` |

The deployed `assets/tour/tour.js` is the source plus four patches that disable
record mode (listed in `tools/vendor_tour.py`), and a two-line header. The styles
travel inside `tour.js`, so `tour.css` is not copied. The site's host adapter is
`assets/tour/tour-host.js`.

Update: `py tools/vendor_tour.py <tour-engine checkout>`, then `py tests/check_tour.py`.
