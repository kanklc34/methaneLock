"""
Baseline statistics for zscore-v1 (Step 3).

Baseline series: valid daily values (fetch_sentinel.fetch_daily_series, so
same-day images are already averaged) with BASELINE_START <= date <= BASELINE_END.

mean : arithmetic mean of the baseline daily values, ppb
std  : sample standard deviation (denominator n - 1), ppb

Requires at least 2 valid baseline days and std > 0. Otherwise BaselineError is
raised and no value is substituted.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date

from src.data.fetch_sentinel import DailyCH4

BASELINE_START = "2020-01-01"
BASELINE_END = "2022-12-31"


class BaselineError(RuntimeError):
    """The baseline cannot be computed from the available valid days."""


@dataclass(frozen=True)
class Baseline:
    mean: float  # ppb
    std: float   # ppb, sample standard deviation
    n_days: int  # number of valid baseline days used


def compute_baseline(days: list[DailyCH4]) -> Baseline:
    start = date.fromisoformat(BASELINE_START)
    end = date.fromisoformat(BASELINE_END)
    values = [d.mean_ppb for d in days if start <= date.fromisoformat(d.date) <= end]
    n = len(values)
    if n < 2:
        raise BaselineError(
            f"Need at least 2 valid baseline days, found {n} in {BASELINE_START}..{BASELINE_END}."
        )
    mean = statistics.fmean(values)
    std = statistics.stdev(values)
    if not math.isfinite(std) or std == 0:
        raise BaselineError(f"Baseline std is {std}; the z-score is undefined.")
    return Baseline(mean=mean, std=std, n_days=n)
