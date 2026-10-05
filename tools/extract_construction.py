"""Read the Construction Forecast panel's data from the forecasting engine.

    py tools/extract_construction.py [path to forecasting-engine]

Default path: $FORECAST_DIR, else ~/OneDrive/forecasting-engine. Writes
tools/data/construction.json and copies the Excel model to
assets/lab/prairie-ridge-model.xlsx.

Every number comes from files the engine's own scripts wrote and committed:

    construction/results/macro.json        the backtest and the published macro forecast
    construction/results/contractor.json   the scenario model's inputs and every preset's results
    construction/snapshots/<date>/         series titles, IDs and pull dates, recent actuals
    construction/sources.yaml              weather thresholds and their quoted sources
    construction/contractor.yaml           productivity factor sources and assumption labels

The page computes the scenarios itself, in JavaScript, from the model inputs.
The presets' Python results are kept here only so tests/check_construction.py
can compare the two. They are not shipped to the page.

The engine repository is private, so the page cannot link to it. It shows the
commit hash instead. A dirty working tree has no commit that matches what would
be published, so this script refuses one, with no override.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

SITE = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data" / "construction.json"
WORKBOOK_OUT = SITE / "assets" / "lab" / "prairie-ridge-model.xlsx"
DEFAULT_DIR = Path.home() / "OneDrive" / "forecasting-engine"
RECENT_MONTHS = 36


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def git(root: Path, *args: str) -> str:
    # check=True: a missing git or a folder that is not a repo must stop the run,
    # not print a blank commit on the site.
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def provenance(root: Path) -> dict:
    dirty = git(root, "status", "--porcelain")
    if dirty:
        raise SystemExit("the forecasting engine has uncommitted changes. Commit them first, then "
                         "extract, so the hash on the page is the code that produced the numbers:\n" + dirty)
    commit = git(root, "rev-parse", "--short", "HEAD")
    if not commit:
        raise SystemExit("could not read the engine's commit")
    return {"engine": "forecasting-engine (private)", "commit": commit,
            "commit_date": git(root, "log", "-1", "--format=%cs"), "uncommitted_changes": False}


def recent_actuals(snapshot: Path, series_id: str) -> list[dict]:
    with (snapshot / "fred" / f"{series_id}.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [{"date": r["date"], "value": float(r["value"])} for r in rows[-RECENT_MONTHS:]]


def usage(macro_spec: dict, cfg: dict, sources: dict) -> dict[str, str]:
    """What each series is actually used for, read from the engine's own configs."""
    used: dict[str, list[str]] = {}
    add = lambda sid, what: used.setdefault(sid, []).append(what)  # noqa: E731
    add(macro_spec["target"], "Forecast target")
    for f in macro_spec["drivers"]["features"]:
        add(f["id"], "Driver tested in the backtest")
    m = cfg["materials"]
    for sid in [m["input_ppi"], *m["regressors"]]:
        add(sid, "Tariff pass-through estimate")
    add(cfg["rates"]["policy"], "Rate path")
    add(cfg["rates"]["projection"], "Rate path")
    add(cfg["fuel"]["series"], "Fuel scenarios")
    for s in sources["fred"]["series"]:
        if s["role"] == "sample":
            add(s["id"], "Sample dataset")
    excluded = macro_spec["drivers"].get("excluded", {})
    out = {}
    for s in sources["fred"]["series"]:
        sid = s["id"]
        if sid in used:
            uses = list(dict.fromkeys(used[sid]))
            out[sid] = ", ".join([uses[0]] + [u[0].lower() + u[1:] for u in uses[1:]])
        elif sid in excluded:
            out[sid] = "Pulled, not used. " + excluded[sid]
        else:
            out[sid] = "Pulled for reference, not used in the model"
    return out


def sources_block(manifest: dict, sources: dict, used: dict[str, str]) -> dict:
    labels = {s["id"]: s for s in sources["fred"]["series"]}
    fred = [{"id": f["series_id"], "title": f["title"], "label": labels[f["series_id"]]["label"],
             "used_as": used[f["series_id"]], "pulled": f["pulled"], "first": f["first"], "last": f["last"],
             "rows": f["rows"], "url": f["page"]} for f in manifest["files"] if f["key"].startswith("fred:")]
    noaa = next(f for f in manifest["files"] if f["key"] == "noaa:daily")
    return {"snapshot": manifest["snapshot"], "api_keys_used": manifest["api_keys_used"], "fred": fred,
            "noaa": {"station": noaa["station"], "name": noaa["station_name"], "first": noaa["first"],
                     "last": noaa["last"], "rows": noaa["rows"], "pulled": noaa["pulled"]},
            "abi": manifest["manual"]["abi"],
            "weather_rules": [{k: c[k] for k in ("key", "element", "op", "threshold", "source", "url", "quote")}
                              for c in sources["weather"]["criteria"]],
            "climatology_years": manifest["weather"]["climatology_years"]}


def macro_block(macro: dict) -> dict:
    def table(variant: dict) -> list[dict]:
        return [{"key": r["key"], "name": r["name"], "mean_mape": r["mean_mape"], "mean_mae": r["mean_mae"],
                 "mean_mase": r["mean_mase"], "h1_mape": r["by_horizon"][0]["mape"],
                 "h12_mape": r["by_horizon"][-1]["mape"], "folds_h1": r["by_horizon"][0]["folds"],
                 "folds_h12": r["by_horizon"][-1]["folds"]} for r in variant["table"]]
    return {"target": macro["target"], "published": macro["published"],
            "variants": [{"publication_lag_months": v["publication_lag_months"], "backtest": v["backtest"],
                          "winner": v["winner"], "winner_vs_seasonal_naive_pct": v["winner_vs_seasonal_naive_pct"],
                          "table": table(v), "coverage": v["interval_coverage"]}
                         for v in macro["variants"]]}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else os.environ.get("FORECAST_DIR") or DEFAULT_DIR)
    prov = provenance(root)                       # refuse a dirty tree before reading anything
    results = root / "construction" / "results"
    for p in (results / "macro.json", results / "contractor.json", results / "samples.json",
              results / "prairie_ridge_model.xlsx"):
        if not p.exists():
            raise SystemExit(f"not found: {p}")
    # A clean status says nothing about ignored files, so require the results to be
    # tracked: then a clean tree means they are exactly what the commit holds.
    for name in ("macro.json", "contractor.json", "samples.json", "prairie_ridge_model.xlsx"):
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", f"construction/results/{name}"],
                                 capture_output=True, text=True)
        if tracked.returncode != 0:
            raise SystemExit(f"construction/results/{name} is not tracked by git, so the commit cannot vouch for it")
    macro = json.loads((results / "macro.json").read_text(encoding="utf-8"))
    contractor = json.loads((results / "contractor.json").read_text(encoding="utf-8"))
    samples = json.loads((results / "samples.json").read_text(encoding="utf-8"))
    if not macro["snapshot"] == contractor["snapshot"] == samples["snapshot"]:
        raise SystemExit("macro and contractor results come from different snapshots")
    snapshot = root / "construction" / "snapshots" / macro["snapshot"]
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    sources = yaml.safe_load((root / "construction" / "sources.yaml").read_text(encoding="utf-8"))
    cfg = yaml.safe_load((root / "construction" / "contractor.yaml").read_text(encoding="utf-8"))
    macro_spec = yaml.safe_load((root / "construction" / "macro.yaml").read_text(encoding="utf-8"))
    if contractor["company"] != "Prairie Ridge Builders (fictional)" or contractor["fictional"] is not True:
        raise SystemExit("the contractor must be labeled fictional")

    WORKBOOK_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(results / "prairie_ridge_model.xlsx", WORKBOOK_OUT)
    data = {
        "_generated_by": "tools/extract_construction.py",
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "provenance": {**prov, "files": {name: sha16(results / name) for name in
                                         ("macro.json", "contractor.json", "samples.json",
                                          "prairie_ridge_model.xlsx")}},
        "sources": sources_block(manifest, sources, usage(macro_spec, cfg, sources)),
        "macro": {**macro_block(macro), "recent_actuals": recent_actuals(snapshot, macro["target"]["id"])},
        "contractor": {
            "company": contractor["company"], "label": contractor["label"],
            "macro_model": contractor["macro_model"], "views": contractor["model_views"],
            "rates_source": contractor["rates_source"], "rates_caveats": contractor["rates_caveats"],
            "weather_factor_sources": cfg["weather"]["factor_sources"],
            "weather_tiers": cfg["weather"]["tiers"],
            "model": contractor["model"],
            "reference": contractor["presets"],         # for the parity check only, never shipped
        },
        "samples": samples,                             # dates and values ship, results are the parity reference
        "workbook": {"path": "/assets/lab/prairie-ridge-model.xlsx", "sha256_16": sha16(WORKBOOK_OUT),
                     "bytes": WORKBOOK_OUT.stat().st_size},
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUT.relative_to(SITE), "and", WORKBOOK_OUT.relative_to(SITE), "at engine commit", prov["commit"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
