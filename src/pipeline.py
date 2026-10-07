"""
End-to-end run for Steps 2-3: fetch -> baseline -> anomaly -> Evidence Package.

Run from the repository root (Earth Engine auth and a git commit are required):
    python -m src.pipeline

For each demo region, writes one Evidence Package to data/evidence/.
A region that fails (no data, no valid baseline) writes nothing and the exit code is 1.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from src.analysis.anomaly import THRESHOLD, is_anomaly
from src.analysis.baseline import BASELINE_END, BASELINE_START, BaselineError, compute_baseline
from src.analysis.evidence_package import (
    EvidencePackageError,
    build_package,
    get_git_commit,
    save_package,
)
from src.data.fetch_sentinel import (
    DEMO_REGIONS,
    GEEAuthError,
    NoDataError,
    fetch_daily_series,
    init_earth_engine,
    select_observation_day,
)

# Observation rule (decided): nearest valid day within +/-7 days of the target.
TARGET_OBSERVATION_DATE = "2023-08-15"
OBSERVATION_WINDOW_DAYS = 7

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "evidence"


def run_region(region_id, bbox, git_commit, out_dir):
    # 1. Baseline from valid daily values in BASELINE_START..BASELINE_END.
    baseline_days = fetch_daily_series(bbox, BASELINE_START, BASELINE_END)
    baseline = compute_baseline(baseline_days)

    # 2. Observation: nearest valid day within +/-7 days of the target.
    target = date.fromisoformat(TARGET_OBSERVATION_DATE)
    window = timedelta(days=OBSERVATION_WINDOW_DAYS)
    candidates = fetch_daily_series(
        bbox, (target - window).isoformat(), (target + window).isoformat()
    )
    observation = select_observation_day(candidates, TARGET_OBSERVATION_DATE, OBSERVATION_WINDOW_DAYS)

    # 3. Z-score, severity and Evidence Package.
    package = build_package(
        region_id=region_id,
        bbox=bbox,
        observation=observation,
        baseline=baseline,
        git_commit=git_commit,
    )
    path = save_package(package, out_dir)
    return path, package


def main(out_dir: Path | None = None) -> int:
    out_dir = out_dir or OUT_DIR
    try:
        git_commit = get_git_commit(REPO_ROOT)  # checked first, before any Earth Engine call
    except EvidencePackageError as exc:
        print(f"ERROR: {exc}")
        return 1
    try:
        init_earth_engine()
    except GEEAuthError as exc:
        print(f"ERROR: {exc}")
        return 1

    failures = 0
    for region_id, bbox in DEMO_REGIONS.items():
        print(f"\n== {region_id} ==")
        try:
            path, pkg = run_region(region_id, bbox, git_commit, out_dir)
        except (NoDataError, BaselineError, EvidencePackageError) as exc:
            failures += 1
            print(f"  FAILED, no package written: {exc}")
            continue
        print(f"  observation_date: {pkg['observation_date']} (target {TARGET_OBSERVATION_DATE}, +/-{OBSERVATION_WINDOW_DAYS} days)")
        print(f"  methane_value:    {pkg['methane_value']:.2f} ppb")
        print(f"  baseline:         mean {pkg['baseline_mean']:.2f} ppb, std {pkg['baseline_std']:.2f} ppb")
        print(f"  z_score:          {pkg['z_score']:.3f}")
        print(f"  severity_flag:    {pkg['severity_flag']}")
        print(f"  anomaly (|z| >= {THRESHOLD}): {'yes' if is_anomaly(pkg['z_score']) else 'no'}")
        print(f"  report_hash:      {pkg['report_hash']}")
        print(f"  saved:            {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
