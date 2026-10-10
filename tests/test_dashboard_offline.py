"""
Offline tests for Step 6 (dashboard logic). No network, no Streamlit needed.

    python -m pytest tests/ -q
    python tests/test_dashboard_offline.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.modules.setdefault("ee", mock.MagicMock())
sys.modules["ee"].EEException = type("EEException", (Exception,), {})
sys.modules.setdefault("dotenv", mock.MagicMock())

from src.app import dashboard as db  # noqa: E402

A_FILE = ROOT / "data" / "mock" / "turkmenistan_west_coast_og_2023-08-15.json"
C_FILE = ROOT / "data" / "mock" / "control_low_activity_demo_2023-08-14.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_mock_packages_are_valid_and_labelled():
    for path in (A_FILE, C_FILE):
        pkg = _load(path)
        r = db.assess(pkg)
        assert r.schema_ok and r.hash_ok, path.name
        assert pkg["qa_note"].startswith("MOCK DATA")


def test_anomaly_uses_z_and_threshold_not_severity():
    a = db.assess(_load(A_FILE))
    c = db.assess(_load(C_FILE))
    assert a.is_anomaly is True and c.is_anomaly is False
    # severity 'low' with |z| between 2.0 and 2.5 must not be an anomaly
    pkg = _load(A_FILE)
    pkg["z_score"], pkg["severity_flag"] = 2.2, "low"
    assert db.assess(pkg).is_anomaly is False
    # negative z counts by absolute value
    pkg["z_score"] = -2.5
    assert db.assess(pkg).is_anomaly is True


def test_tampering_is_detected():
    pkg = _load(A_FILE)
    pkg["methane_value"] += 1.0
    r = db.assess(pkg)
    assert not r.hash_ok


def test_broken_package_does_not_crash():
    r = db.assess({"z_score": "x"})
    assert not r.schema_ok and not r.hash_ok and r.is_anomaly is None


def test_flatten_covers_every_field():
    pkg = _load(A_FILE)
    names = [n for n, _ in db.flatten_fields(pkg)]
    assert "location.region_id" in names and "baseline_period.start" in names
    for key in pkg:
        assert any(n == key or n.startswith(key + ".") for n in names), key


def test_tx_hash_normalisation_and_sidecar():
    h = "ab" * 32
    assert db.normalize_tx_hash(h) == "0x" + h
    assert db.normalize_tx_hash("0X" + h.upper()) is None  # only a lowercase 0x prefix is accepted
    assert db.normalize_tx_hash("0x" + h.upper()) == "0x" + h
    assert db.normalize_tx_hash("0x123") is None and db.normalize_tx_hash("") is None
    with tempfile.TemporaryDirectory() as d:
        pkg_path = Path(d) / "x_2023-08-15.json"
        pkg_path.write_text("{}", encoding="utf-8")
        assert db.read_tx_sidecar(pkg_path) is None
        (Path(d) / "x_2023-08-15.tx.json").write_text(json.dumps({"tx_hash": h}), encoding="utf-8")
        assert db.read_tx_sidecar(pkg_path) == "0x" + h


def test_list_packages_skips_bad_files_and_sidecars():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "good.json").write_text(A_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        (d / "good.tx.json").write_text("{}", encoding="utf-8")
        (d / "bad.json").write_text("not json", encoding="utf-8")
        entries, skipped = db.list_packages(d)
    assert [e.path.name for e in entries] == ["good.json"]
    assert [n for n, _ in skipped] == ["bad.json"]
    assert db.list_packages(Path("/nonexistent-dir")) == ([], [])


def test_onchain_disabled_without_settings():
    s = db.onchain_settings({})
    assert not s.available and "not set" in s.reason
    s = db.onchain_settings({"RPC_URL": "https://secret.example/key123"})
    assert not s.available and "CONTRACT_ADDRESS" in s.reason and "secret" not in s.reason
    s = db.onchain_settings({"RPC_URL": "https://x", "CONTRACT_ADDRESS": "nope"})
    assert not s.available


def test_is_recorded_error_has_no_rpc_url():
    s = db.OnchainSettings(True, None, rpc_url="https://secret.example/key123",
                           contract_address="0x" + "11" * 20)
    try:
        db.check_is_recorded(s, "ab" * 32)
    except RuntimeError as exc:
        assert "secret" not in str(exc) and "key123" not in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failed else 0)
