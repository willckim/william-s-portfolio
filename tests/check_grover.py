"""Grover visualizer: the page's state-vector simulation agrees with the closed form.

The page never evaluates sin^2((2k+1)theta) to produce its probability: it applies
the oracle and the diffusion to 16 amplitudes and squares one. This check computes
the closed form here, in Python, and compares. The brief's gate is the optimal
iteration count within 1% of theory; every k from 0 to 8 is also checked, for three
marked states, and the drawn bars must be the vector (sum of squares 1).

Mutants of grover.js (a wrong reflection, the oracle removed) must each fail.

    py tests/check_grover.py
"""

from __future__ import annotations

import json
import math
import sys

from playwright.sync_api import sync_playwright

from sitekit import ROOT, Report, serve

QF = json.loads((ROOT / "tools" / "data" / "quantum_finance.json").read_text(encoding="utf-8"))
N = 2 ** QF["grover"]["qubits"]
THETA = math.asin(1 / math.sqrt(N))
OPTIMAL = math.floor(math.pi / (4 * THETA))
GROVER_JS = (ROOT / "assets" / "lab" / "grover.js").read_text(encoding="utf-8")
# Not a mutant: reversing the diffusion's sign (a[j] = a[j] - 2*mean) multiplies the
# whole vector by -1, a global phase, so every probability is unchanged. It was tried
# first and survived, correctly. A mutant has to change something measurable.
MUTANTS = {
    "reflection about half the mean": ("s.a[j] = 2 * mean - s.a[j];", "s.a[j] = mean - s.a[j];"),
    "oracle removed": ("function oracle() { s.a[s.target] = -s.a[s.target]; s.half = true; }",
                       "function oracle() { s.half = true; }"),
}


def theory(k: int) -> float:
    return math.sin((2 * k + 1) * THETA) ** 2


def run(page, target: int, steps: int) -> list[tuple[float, float]]:
    """P(target) and the drawn sum of squares after 0..steps full iterations."""
    page.select_option("#g-target", str(target))
    page.click("[data-g=reset]")
    out = []
    for k in range(steps + 1):
        if k:
            page.click("[data-g=step]")
        out.append(page.evaluate("""() => {
            const g = document.getElementById('grover');
            const drawn = [...g.querySelectorAll('.g-bar')].map(b =>
                parseFloat(b.style.transform.replace('scaleY(', '')) ** 2).reduce((a, b) => a + b, 0);
            return [+g.dataset.p, drawn]; }"""))
    return out


def main() -> int:
    rep = Report("Grover visualizer")
    base, server = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/lab")
            target = QF["grover"]["target"]
            opt = run(page, target, OPTIMAL)[OPTIMAL][0]
            rel = abs(opt - theory(OPTIMAL)) / theory(OPTIMAL)
            rep.check(f"optimal iterations ({OPTIMAL}) for marked state {target}: within 1% of theory",
                      rel < 0.01, f"page {opt:.6f}, theory {theory(OPTIMAL):.6f}, off by {rel:.2e}")
            for t in (target, 0, N - 1):
                series = run(page, t, 8)
                worst = max(abs(pk - theory(k)) for k, (pk, _) in enumerate(series))
                norm = max(abs(d - 1) for _, d in series)
                rep.check(f"marked state {t}: k = 0 to 8 all match the closed form", worst < 1e-9,
                          f"worst difference {worst:.1e}")
                rep.check(f"marked state {t}: the bars drawn are the state vector (sum of squares 1)",
                          norm < 2e-3, f"worst {norm:.1e}")
            page.click("[data-g=reset]")
            page.click("[data-g=oracle]")
            half = page.evaluate("+document.getElementById('grover').dataset.p")
            rep.check("the oracle alone changes a sign, not a probability", abs(half - 1 / N) < 1e-12,
                      f"{half}")
            shown = page.text_content(".g-optimal"), page.text_content(".g-repo-p")
            repo_iters = math.isqrt(N)
            rep.check("the page states the optimum and the repo's own iteration count correctly",
                      shown[0] == str(OPTIMAL) and shown[1] == f"{theory(repo_iters) * 100:.1f}%",
                      f"optimum {shown[0]}, repo p {shown[1]}")
            rep.check("no page errors", not errors, "; ".join(errors[:3]))

            rm = browser.new_context(reduced_motion="reduce").new_page()
            rm.goto(base + "/lab")
            dur = rm.eval_on_selector(".g-bar", "b => getComputedStyle(b).transitionDuration")
            rep.check("reduced motion: bars jump rather than animate", dur in ("0s", "0s, 0s"), dur)

            for label, (old, new) in MUTANTS.items():
                if GROVER_JS.count(old) != 1:
                    rep.check(f"mutant '{label}' applies", False, f"found {GROVER_JS.count(old)} times")
                    continue
                body = GROVER_JS.replace(old, new)
                m = browser.new_page()
                m.route("**/assets/lab/grover.js", lambda route, _req, b=body: route.fulfill(
                    status=200, content_type="text/javascript", body=b))
                m.goto(base + "/lab")
                got = run(m, target, OPTIMAL)[OPTIMAL][0]
                caught = abs(got - theory(OPTIMAL)) / theory(OPTIMAL) >= 0.01
                rep.check(f"mutant '{label}' fails the 1% gate", caught, f"page {got:.4f}")
                m.close()
            browser.close()
    finally:
        server.shutdown()
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
