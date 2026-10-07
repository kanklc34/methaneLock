"""
Z-score anomaly and fixed severity bands (zscore-v1, algorithm_version 1.0.0).

z_score       = (value - baseline_mean) / baseline_std
threshold     = 2.5. A result is an anomaly when abs(z) >= threshold.
severity_flag describes the magnitude only, from abs(z):
    below 2.0      -> none
    2.0 to < 3.0   -> low
    3.0 to < 4.0   -> medium
    4.0 or above   -> high
The anomaly decision and the severity flag are independent (see docs).
"""

from __future__ import annotations

import math

from src.analysis.baseline import Baseline

ALGORITHM = "zscore-v1"
ALGORITHM_VERSION = "1.0.0"
THRESHOLD = 2.5


def _require_finite(name: str, x: float) -> None:
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite, got {x}")


def z_score(value: float, baseline: Baseline) -> float:
    _require_finite("value", value)
    if baseline.std <= 0:
        raise ValueError(f"baseline std must be > 0, got {baseline.std}")
    return (value - baseline.mean) / baseline.std


def severity_flag(z: float) -> str:
    _require_finite("z_score", z)
    a = abs(z)
    if a < 2.0:
        return "none"
    if a < 3.0:
        return "low"
    if a < 4.0:
        return "medium"
    return "high"


def is_anomaly(z: float) -> bool:
    _require_finite("z_score", z)
    return abs(z) >= THRESHOLD
