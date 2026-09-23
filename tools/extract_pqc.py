"""Read the Mosca calculator's inputs from the Post-Quantum Readiness Toolkit.

    py tools/extract_pqc.py [path to quantum-finance/04_security/pqc_readiness]

Default path: $PQC_DIR, else the local clone at ~/OneDrive/quantum. Writes
tools/data/pqc.json. Every value comes from the toolkit's own files:

    pqc_config.yaml   as-of year, migration time, each record type's shelf life and
                      basis, and the three scenario windows with their planning years
    sources.py        the citation behind each source key

Nothing is read from the toolkit's report here. The report is the toolkit's OUTPUT,
and tests/check_mosca.py compares the calculator against it, so the expected results
are never derived from the same place as the inputs the page computes with.

The only text this file adds is RULE_LABELS, the short name shown for each source
key. It fails loudly on a key it has no label for, rather than guessing one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent / "data" / "pqc.json"
DEFAULT_DIR = Path.home() / "OneDrive" / "quantum" / "04_security" / "pqc_readiness"

RULE_LABELS = {
    "IRC-197": "IRC 197", "IRS-RECORDS": "IRS", "IRC-6501": "IRC 6501",
    "SEC-2-06": "SEC Rule 2-06", "PCAOB-1215": "PCAOB AS 1215",
    "ERISA-107": "ERISA 107", "OSHA-1910-1020": "OSHA 1910.1020",
    "BSA-1010-430": "BSA", "PCI-FAQ-RETENTION": "PCI DSS",
    "UCC-2-725": "UCC 2-725", "IRS-EMPTAX": "IRS", "FLSA-516": "FLSA", "FLSA-516-6": "FLSA",
    "NIST-800-57": "NIST SP 800-57", "NIST-800-63B": "NIST SP 800-63B",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PQC_DIR") or DEFAULT_DIR)
    cfg_path, src_path = root / "pqc_config.yaml", root / "sources.py"
    for p in (cfg_path, src_path):
        if not p.exists():
            raise SystemExit(f"not found: {p}")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("pqc_sources", src_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod        # dataclasses looks its module up while decorating
    spec.loader.exec_module(mod)
    sources = mod.SOURCES

    def rules(keys: list[str]) -> list[str]:
        missing = [k for k in keys if k not in RULE_LABELS]
        if missing:
            raise SystemExit(f"no short label for source keys {missing}: add them to RULE_LABELS")
        return list(dict.fromkeys(RULE_LABELS[k] for k in keys))

    for dt in cfg["data_types"]:
        unknown = [k for k in dt["sources"] if k not in sources]
        if unknown:
            raise SystemExit(f"{dt['name']}: source keys not in sources.py: {unknown}")

    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True,  # noqa: E731
                                    text=True).stdout.strip()
    run_log = json.loads((root / "pqc_run_log.json").read_text(encoding="utf-8"))
    data = {
        "_generated_by": "tools/extract_pqc.py",
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "provenance": {
            "toolkit": "quantum-finance/04_security/pqc_readiness",
            "commit": git("rev-parse", "--short", "HEAD"),
            "uncommitted_changes": bool(git("status", "--porcelain", ".")),
            "pqc_config.yaml": sha(cfg_path),
            "sources.py": sha(src_path),
            "toolkit_version": run_log.get("version"),
            "toolkit_run": run_log.get("run_timestamp"),
        },
        "as_of_year": cfg["as_of_year"],
        "migration_years": cfg["migration"]["years"],
        "data_types": [{
            "name": dt["name"],
            "shelf_life": dt["shelf_life_years"],
            "basis": dt["basis"],
            "basis_type": dt["basis_type"],
            "rules": rules(dt["sources"]),
        } for dt in cfg["data_types"]],
        "scenarios": [{
            "name": s["name"],
            "window": s["window"],
            "planning_year": s["planning_year"],
        } for s in cfg["scenarios"]],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
