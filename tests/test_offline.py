"""
Offline tests for Steps 2-3. Earth Engine is replaced by a mock, so these run
without network access or credentials.

    python -m pytest tests/ -q          # if pytest is installed
    python tests/test_offline.py        # plain run, no pytest needed
"""

from __future__ import annotations

import math
import re
import statistics
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.modules["ee"] = mock.MagicMock()
sys.modules["ee"].EEException = type("EEException", (Exception,), {})
sys.modules["dotenv"] = mock.MagicMock()

from src.analysis import anomaly as an  # noqa: E402
from src.analysis import baseline as bl  # noqa: E402
from src.analysis import evidence_package as ep  # noqa: E402
from src.data import fetch_sentinel as fs  # noqa: E402
import src.pipeline as pl  # noqa: E402

B = fs.PREFERRED_BAND
BBOX_A = [53.2, 38.4, 54.8, 39.6]
CONTROL = fs.DEMO_REGIONS["control_low_activity_demo"]


def D(day, value, ids=("img",)):
    return fs.DailyCH4(date=day, mean_ppb=value, band=B, unit="ppb", image_ids=tuple(ids))


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


def expected_severity(z):
    a = abs(z)
    if a < 2:
        return "none"
    if a < 3:
        return "low"
    if a < 4:
        return "medium"
    return "high"


# ---------- Step 2: fetch helpers ----------

def test_fetch_groups_images_by_day():
    obs = [
        fs.CH4Observation(date="2023-08-10", mean_ppb=1900.0, band=B, unit="ppb", image_id="a"),
        fs.CH4Observation(date="2023-08-10", mean_ppb=1902.0, band=B, unit="ppb", image_id="b"),
        fs.CH4Observation(date="2023-08-12", mean_ppb=1910.0, band=B, unit="ppb", image_id="c"),
    ]
    with mock.patch.object(fs, "fetch_daily_means", return_value=obs):
        days = fs.fetch_daily_series(BBOX_A, "2023-08-08", "2023-08-22")
    assert [d.date for d in days] == ["2023-08-10", "2023-08-12"]
    assert abs(days[0].mean_ppb - 1901.0) < 1e-12
    assert days[0].image_ids == ("a", "b")


def test_select_nearest_inside_window():
    days = [D("2023-08-16", 1.0), D("2023-08-22", 2.0), D("2023-08-30", 3.0)]
    assert fs.select_observation_day(days, "2023-08-15", 7).date == "2023-08-16"


def test_select_tie_goes_to_earlier_day():
    days = [D("2023-08-16", 1.0), D("2023-08-14", 2.0)]
    assert fs.select_observation_day(days, "2023-08-15", 7).date == "2023-08-14"


def test_select_window_edges():
    assert fs.select_observation_day([D("2023-08-22", 2.0)], "2023-08-15", 7).date == "2023-08-22"
    assert fs.select_observation_day([D("2023-08-08", 2.0)], "2023-08-15", 7).date == "2023-08-08"
    assert raises(fs.NoDataError, lambda: fs.select_observation_day([D("2023-08-23", 2.0)], "2023-08-15", 7))
    assert raises(fs.NoDataError, lambda: fs.select_observation_day([D("2023-08-07", 2.0)], "2023-08-15", 7))


def test_select_nothing_in_window_raises():
    assert raises(fs.NoDataError, lambda: fs.select_observation_day([], "2023-08-15", 7))


# ---------- Step 3: baseline and anomaly ----------

def test_baseline_mean_and_sample_std():
    days = [D(f"2021-01-0{i}", float(v)) for i, v in enumerate([1, 2, 3, 4, 5], start=1)]
    b = bl.compute_baseline(days)
    assert abs(b.mean - 3.0) < 1e-12
    assert abs(b.std - math.sqrt(2.5)) < 1e-12
    assert b.n_days == 5


def test_baseline_ignores_dates_outside_period():
    days = [D("2019-12-31", 100.0), D("2021-01-01", 1.0), D("2021-01-02", 3.0), D("2023-08-15", 1e6)]
    b = bl.compute_baseline(days)
    assert abs(b.mean - 2.0) < 1e-12
    assert b.n_days == 2


def test_baseline_needs_two_days_and_nonzero_std():
    assert raises(bl.BaselineError, lambda: bl.compute_baseline([D("2021-01-01", 1.0)]))
    assert raises(bl.BaselineError, lambda: bl.compute_baseline([D("2021-01-01", 5.0), D("2021-01-02", 5.0)]))


def test_z_score_formula():
    b0 = bl.Baseline(mean=1900.0, std=10.0, n_days=30)
    assert abs(an.z_score(1925.0, b0) - 2.5) < 1e-12


def test_severity_bands():
    cases = [(0.0, "none"), (1.9999, "none"), (-1.9999, "none"), (2.0, "low"), (2.9999, "low"),
             (-2.5, "low"), (3.0, "medium"), (3.9999, "medium"), (4.0, "high"), (-4.0, "high"), (-7.2, "high")]
    for z, expected in cases:
        assert an.severity_flag(z) == expected, (z, expected)


def test_anomaly_threshold():
    assert an.is_anomaly(2.5) and an.is_anomaly(-2.5)
    assert not an.is_anomaly(2.4999)


def test_nonfinite_values_rejected():
    assert raises(ValueError, lambda: an.severity_flag(float("nan")))
    assert raises(ValueError, lambda: an.is_anomaly(float("inf")))


# ---------- Evidence Package ----------

B0 = bl.Baseline(mean=1900.0, std=10.0, n_days=30)
OBS = fs.DailyCH4(date="2023-08-16", mean_ppb=1925.0, band=B, unit="ppb", image_ids=("x", "y"))


def _pkg():
    return ep.build_package(
        region_id="turkmenistan_west_coast_og",
        bbox=BBOX_A,
        observation=OBS,
        baseline=B0,
        git_commit="a" * 40,
        generated_at="2026-10-06T12:00:00+00:00",
    )


def test_package_matches_schema_and_hash():
    pkg = _pkg()
    assert tuple(pkg.keys()) == ep.SCHEMA_KEYS
    assert re.fullmatch(r"[0-9a-f]{64}", pkg["report_hash"]) is not None
    assert ep.verify_package(pkg)


def test_package_values():
    pkg = _pkg()
    assert abs(pkg["z_score"] - 2.5) < 1e-12
    assert pkg["severity_flag"] == "low"
    assert pkg["threshold"] == 2.5
    assert pkg["observation_date"] == "2023-08-16"
    assert pkg["methane_value"] == 1925.0
    assert pkg["unit"] == "ppb"
    assert pkg["baseline_period"] == {"start": "2020-01-01", "end": "2022-12-31"}
    assert abs(pkg["location"]["lat"] - 39.0) < 1e-9   # (38.4 + 39.6) / 2
    assert abs(pkg["location"]["lon"] - 54.0) < 1e-9   # (53.2 + 54.8) / 2
    assert pkg["qa_note"].startswith(
        "No pixel-level QA/validity filter applied in this MVP. "
        "Result is spatial mean over available pixels in bbox."
    )
    assert B in pkg["qa_note"]


def test_hash_canonical_rules():
    assert ep.canonical_bytes({"b": 1, "a": {"d": 2, "c": 3}}) == b'{"a":{"c":3,"d":2},"b":1}'
    assert ep.canonical_bytes({"a": "\u015f"}) == b'{"a":"\\u015f"}'
    assert raises(ep.EvidencePackageError, lambda: ep.compute_report_hash({"a": float("nan")}))


def test_tamper_and_key_order():
    pkg = _pkg()
    tampered = dict(pkg)
    tampered["methane_value"] = 1926.0
    assert not ep.verify_package(tampered)
    reordered = {k: pkg[k] for k in reversed(list(pkg.keys()))}
    assert ep.compute_report_hash(reordered) == pkg["report_hash"]


def test_save_and_reload():
    pkg = _pkg()
    out = Path(tempfile.mkdtemp())
    path = ep.save_package(pkg, out)
    assert path.name == "turkmenistan_west_coast_og_2023-08-16.json"
    loaded = ep.load_package(path)
    assert ep.verify_package(loaded)
    assert loaded == pkg


def test_git_commit_missing_raises():
    assert raises(ep.EvidencePackageError, lambda: ep.get_git_commit(Path(tempfile.mkdtemp())))


# ---------- End to end, synthetic data (tests the plumbing, NOT real CH4 values) ----------

def _synthetic_store():
    store = []
    d = date(2019, 12, 1)
    while d <= date(2023, 9, 30):
        if date(2020, 1, 1) <= d <= date(2022, 12, 31):
            store.append(D(d.isoformat(), 1900.0 + (d.toordinal() % 7) * 3.0))
        d = date.fromordinal(d.toordinal() + 1)
    store.append(D("2023-08-01", 9999.0))  # outside the +/-7 window: must never be chosen
    store.append(D("2023-08-12", 1950.0))  # 3 days before target: nearest valid day
    store.append(D("2023-08-19", 1960.0))  # 4 days after target
    return store


def _fake_fetch(store):
    def fake(bbox, start, end):
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        return [x for x in store if s <= date.fromisoformat(x.date) <= e]
    return fake


def test_pipeline_end_to_end_synthetic():
    store = _synthetic_store()
    out = Path(tempfile.mkdtemp())
    with mock.patch.object(pl, "fetch_daily_series", side_effect=_fake_fetch(store)):
        path, pkg = pl.run_region("turkmenistan_west_coast_og", BBOX_A, "b" * 40, out)

    base_vals = [x.mean_ppb for x in store if date(2020, 1, 1) <= date.fromisoformat(x.date) <= date(2022, 12, 31)]
    mean, std = statistics.fmean(base_vals), statistics.stdev(base_vals)
    z = (1950.0 - mean) / std

    assert pkg["observation_date"] == "2023-08-12"
    assert pkg["methane_value"] == 1950.0
    assert abs(pkg["baseline_mean"] - mean) < 1e-9
    assert abs(pkg["baseline_std"] - std) < 1e-9
    assert abs(pkg["z_score"] - z) < 1e-9
    assert pkg["severity_flag"] == expected_severity(z)

    loaded = ep.load_package(path)
    assert tuple(loaded.keys()) == ep.SCHEMA_KEYS
    assert ep.verify_package(loaded)


def test_pipeline_no_window_writes_nothing():
    store = [x for x in _synthetic_store() if x.date < "2023-01-01"]  # baseline only
    out = Path(tempfile.mkdtemp())
    with mock.patch.object(pl, "fetch_daily_series", side_effect=_fake_fetch(store)):
        assert raises(fs.NoDataError, lambda: pl.run_region("turkmenistan_west_coast_og", BBOX_A, "b" * 40, out))
    assert list(out.glob("*.json")) == []


def test_main_exit_codes():
    store = _synthetic_store()
    fake = _fake_fetch(store)

    def regional(bbox, start, end):
        if bbox == CONTROL and start >= "2023-01-01":
            return []  # control region has no window data -> NoDataError
        return fake(bbox, start, end)

    out = Path(tempfile.mkdtemp())
    with mock.patch.object(pl, "get_git_commit", return_value="c" * 40), \
         mock.patch.object(pl, "init_earth_engine"), \
         mock.patch.object(pl, "fetch_daily_series", side_effect=regional):
        rc = pl.main(out_dir=out)
    assert rc == 1
    assert len(list(out.glob("*.json"))) == 1

    with mock.patch.object(pl, "get_git_commit", side_effect=ep.EvidencePackageError("no commit")), \
         mock.patch.object(pl, "init_earth_engine") as init, \
         mock.patch.object(pl, "fetch_daily_series") as fetch:
        rc2 = pl.main(out_dir=out)
    assert rc2 == 1 and not fetch.called and not init.called


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\n{len(tests)} tests passed")
