"""
Evidence Package: build, canonical hash, verify, save (docs/evidence-package.md).

Hash rule (fixed):
  1. remove the report_hash key
  2. json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
  3. encode as UTF-8, SHA-256, lowercase hex

allow_nan=False makes NaN and Infinity raise an error instead of producing invalid JSON.

Saved files are pretty-printed for reading. Verification always recomputes the
hash from the canonical form, so whitespace in the file does not matter.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.anomaly import ALGORITHM, ALGORITHM_VERSION, THRESHOLD, severity_flag, z_score
from src.analysis.baseline import BASELINE_END, BASELINE_START, Baseline
from src.data.fetch_sentinel import COLLECTION_ID, DailyCH4, validate_bbox

SCHEMA_VERSION = "1.0"
DATASET_NAME = "Sentinel-5P OFFL CH4"
UNIT = "ppb"
QA_NOTE_FIXED = (
    "No pixel-level QA/validity filter applied in this MVP. "
    "Result is spatial mean over available pixels in bbox."
)
SCHEMA_KEYS = (
    "schema_version",
    "dataset",
    "source_uri",
    "observation_date",
    "location",
    "methane_value",
    "unit",
    "baseline_period",
    "baseline_mean",
    "baseline_std",
    "z_score",
    "threshold",
    "qa_note",
    "algorithm",
    "algorithm_version",
    "git_commit",
    "generated_at",
    "severity_flag",
    "report_hash",
)
SEVERITY_VALUES = ("none", "low", "medium", "high")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class EvidencePackageError(ValueError):
    """The package cannot be built, validated, saved or verified."""


def canonical_bytes(obj: dict) -> bytes:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return text.encode("utf-8")


def compute_report_hash(package: dict) -> str:
    body = {k: v for k, v in package.items() if k != "report_hash"}
    try:
        data = canonical_bytes(body)
    except ValueError as exc:
        raise EvidencePackageError(f"Package is not canonically serialisable: {exc}") from exc
    return hashlib.sha256(data).hexdigest()


def verify_package(package: dict) -> bool:
    """True if the stored report_hash equals the hash recomputed from the content."""
    stored = package.get("report_hash")
    return isinstance(stored, str) and stored == compute_report_hash(package)


def validate_schema(package: dict) -> None:
    if tuple(package.keys()) != SCHEMA_KEYS:
        raise EvidencePackageError(f"Keys or key order differ from the schema: {tuple(package.keys())}")
    if package["schema_version"] != SCHEMA_VERSION:
        raise EvidencePackageError("schema_version mismatch")
    if package["unit"] != UNIT:
        raise EvidencePackageError("unit must be 'ppb'")
    if package["severity_flag"] not in SEVERITY_VALUES:
        raise EvidencePackageError(f"Invalid severity_flag: {package['severity_flag']}")
    if len(package["location"]["bbox"]) != 4:
        raise EvidencePackageError("location.bbox must have 4 values")
    if not _HEX64.fullmatch(str(package["report_hash"])):
        raise EvidencePackageError("report_hash must be 64 lowercase hex characters")
    for key in ("methane_value", "baseline_mean", "baseline_std", "z_score", "threshold"):
        value = package[key]
        if not isinstance(value, float) or not math.isfinite(value):
            raise EvidencePackageError(f"{key} must be a finite float")


def get_git_commit(repo_root: Path) -> str:
    """HEAD commit hash of the repository. Raises if it cannot be read."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvidencePackageError(
            f"Cannot read the git commit in {repo_root}. Initialise the repository and commit "
            "before generating Evidence Packages."
        ) from exc
    return result.stdout.strip()


def _require_finite(name: str, x) -> None:
    if not isinstance(x, (int, float)) or not math.isfinite(x):
        raise EvidencePackageError(f"{name} must be a finite number, got {x!r}")


def build_package(
    *,
    region_id: str,
    bbox,
    observation: DailyCH4,
    baseline: Baseline,
    git_commit: str,
    generated_at: str | None = None,
) -> dict:
    min_lon, min_lat, max_lon, max_lat = validate_bbox(bbox)
    _require_finite("methane_value", observation.mean_ppb)
    _require_finite("baseline_mean", baseline.mean)
    _require_finite("baseline_std", baseline.std)

    z = z_score(observation.mean_ppb, baseline)
    sev = severity_flag(z)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    package = {
        "schema_version": SCHEMA_VERSION,
        "dataset": DATASET_NAME,
        "source_uri": COLLECTION_ID,
        "observation_date": observation.date,
        "location": {
            "lat": (min_lat + max_lat) / 2,
            "lon": (min_lon + max_lon) / 2,
            "region_id": region_id,
            "bbox": [min_lon, min_lat, max_lon, max_lat],
        },
        "methane_value": float(observation.mean_ppb),
        "unit": UNIT,
        "baseline_period": {"start": BASELINE_START, "end": BASELINE_END},
        "baseline_mean": float(baseline.mean),
        "baseline_std": float(baseline.std),
        "z_score": float(z),
        "threshold": float(THRESHOLD),
        "qa_note": (
            f"{QA_NOTE_FIXED} Band: {observation.band}. "
            f"Source unit: {observation.unit}; no unit conversion applied."
        ),
        "algorithm": ALGORITHM,
        "algorithm_version": ALGORITHM_VERSION,
        "git_commit": git_commit,
        "generated_at": generated_at,
        "severity_flag": sev,
        "report_hash": "",
    }
    package["report_hash"] = compute_report_hash(package)
    validate_schema(package)
    return package


def load_package(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_package(package: dict, out_dir: Path) -> Path:
    """Validate, write as pretty JSON, reload and verify. Returns the file path."""
    validate_schema(package)
    if not verify_package(package):
        raise EvidencePackageError("report_hash does not match the package content.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{package['location']['region_id']}_{package['observation_date']}.json"
    path.write_text(json.dumps(package, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    reloaded = load_package(path)
    if not verify_package(reloaded):
        raise EvidencePackageError(f"Saved file failed hash verification: {path}")
    return path
