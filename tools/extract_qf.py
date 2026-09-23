"""Read the quantum-finance results the Lab shows, by running the repo's own scripts.

    py tools/extract_qf.py <path to a quantum-finance checkout> [python for Qiskit]

The repo commits its charts as PNGs and prints its numbers, it does not save them.
So this runs the three finance scripts exactly as committed (each has a fixed seed),
parses what they print, and writes tools/data/quantum_finance.json with the commit
it ran and the interpreter versions. Nothing here computes a result of its own.

A run is checked against the committed chart it reproduces only by eye: the PNG
bytes differ between matplotlib builds even when every plotted value is equal.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "quantum_finance.json"


def run(py: str, script: Path) -> str:
    # A copy, so the charts the scripts write never touch the checkout.
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / script.name
        shutil.copy(script, dst)
        r = subprocess.run([py, "-X", "utf8", str(dst)], capture_output=True, text=True,
                           encoding="utf-8", cwd=tmp, timeout=1800)
    if r.returncode:
        raise SystemExit(f"{script.name} failed:\n{r.stderr[-2000:]}")
    return r.stdout


def need(rx: str, text: str, what: str) -> re.Match:
    m = re.search(rx, text, re.S | re.M)
    if not m:
        raise SystemExit(f"could not find {what} in the script output")
    return m


def monte_carlo(out: str) -> dict:
    table = need(r"CONVERGENCE TABLE\n-+\n.*?\n(.*?)\n\n", out, "the convergence table").group(1)
    classical, quantum = [], []
    for line in table.splitlines():
        cells = [c.replace(",", "") for c in line.split()]
        classical.append([int(cells[0]), float(cells[1])])
        if len(cells) == 4:
            quantum.append([int(cells[2]), float(cells[3])])
    return {
        "reference_p": float(need(r"Reference probability \(classical, ([\d,]+) sims\): ([\d.]+)",
                                  out, "the reference probability").group(2)),
        "reference_sims": int(need(r"Reference probability \(classical, ([\d,]+) sims\)", out,
                                   "the reference run size").group(1).replace(",", "")),
        "target_accuracy": need(r"COST TO REACH \|error\| <= ([\d.]+%)", out, "the accuracy target").group(1),
        "classical_to_target": int(need(r"Classical Monte Carlo  : ([\d,]+) samples", out,
                                        "the classical cost").group(1).replace(",", "")),
        "quantum_to_target": int(need(r"Quantum amplitude est\. : ([\d,]+) oracle queries", out,
                                      "the quantum cost").group(1).replace(",", "")),
        "classical": classical,
        "quantum": quantum,
    }


def portfolio(out: str) -> dict:
    blocks = re.split(r"\n(?=CLASSICAL  --|QUANTUM    --)", out)
    def side(label: str) -> dict:
        b = next(x for x in blocks if x.startswith(label))
        return {
            "holdings": re.findall(r"^\s{4}([A-Z]+)\s+\$", b, re.M),
            "return": need(r"Expected portfolio return : ([\d.]+%)", b, f"{label} return").group(1),
            "risk": need(r"Expected portfolio risk   : ([\d.]+%)", b, f"{label} risk").group(1),
            "evaluated": int(need(r"Combinations evaluated    : ([\d,]+)", b,
                                  f"{label} count").group(1).replace(",", "")),
        }
    held = int(need(r"exactly (\d+) held", out, "the holding count").group(1))
    for label in ("CLASSICAL", "QUANTUM"):
        if len(side(label)["holdings"]) != held:
            raise SystemExit(f"{label}: parsed {len(side(label)['holdings'])} holdings, expected {held}")
    return {
        "stocks": int(need(r"\| (\d+) stocks \|", out, "the stock count").group(1)),
        "held": int(need(r"exactly (\d+) held", out, "the holding count").group(1)),
        "target": need(r"target (\d+%)", out, "the return target").group(1),
        "matched": need(r"QAOA matched the exact optimum: (YES|NO)", out, "the verdict").group(1) == "YES",
        "circuit_evaluations": int(need(r"tuned its angles\s+with (\d+) evaluations", out,
                                        "the evaluation count").group(1)),
        "classical": side("CLASSICAL"),
        "quantum": side("QUANTUM"),
    }


def forecaster(out: str) -> dict:
    rows = re.findall(r"^\s+(\d+) \|\s+\$([\d,]+) \|\s+\$([\d,]+)$", out, re.M)
    if len(rows) != 3:
        raise SystemExit("could not find the three forecast rows")
    last = re.findall(r"Month (\d+): \$\s*([\d,]+)", out)
    return {
        "last_actual": {"month": int(last[-1][0]), "revenue": int(last[-1][1].replace(",", ""))},
        "forecast": [{"month": int(m), "classical": int(c.replace(",", "")),
                      "quantum": int(q.replace(",", ""))} for m, c, q in rows],
    }


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    repo = Path(sys.argv[1]).resolve()
    py = sys.argv[2] if len(sys.argv) > 2 else sys.executable
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True,  # noqa: E731
                                    text=True, check=True).stdout.strip()
    versions = subprocess.run(
        [py, "-c", "import sys, qiskit, numpy; print(sys.version.split()[0], qiskit.__version__, "
                   "numpy.__version__)"], capture_output=True, text=True).stdout.split()
    fin = repo / "03_finance"
    commit = git("rev-parse", "HEAD")
    if not commit:
        raise SystemExit("could not read the repo's commit")
    data = {
        "_generated_by": "tools/extract_qf.py",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "repo": "https://github.com/willckim/quantum-finance",
        "commit": commit,
        "dirty": bool(git("status", "--porcelain", "03_finance", "02_algorithms")),
        "python": versions[0], "qiskit": versions[1], "numpy": versions[2],
        "grover": {  # read from the source: there is no printed number to parse
            "target": int(need(r"^target = (\d+)", (repo / "02_algorithms" / "grover_search.py")
                               .read_text(encoding="utf-8"), "the Grover target").group(1)),
            "qubits": int(need(r"^num_qubits = (\d+)", (repo / "02_algorithms" / "grover_search.py")
                               .read_text(encoding="utf-8"), "the Grover qubit count").group(1)),
            "iterations_rule": need(r"^num_iterations = ([^\r\n]+)", (repo / "02_algorithms" / "grover_search.py")
                                    .read_text(encoding="utf-8"), "the iteration rule").group(1).strip(),
            "shots": int(need(r"shots=(\d+)", (repo / "02_algorithms" / "grover_search.py")
                              .read_text(encoding="utf-8"), "the Grover shot count").group(1)),
        },
        "monte_carlo": monte_carlo(run(py, fin / "quantum_monte_carlo.py")),
        "forecaster": forecaster(run(py, fin / "quantum_forecaster.py")),
        "portfolio": portfolio(run(py, fin / "portfolio_optimizer.py")),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
