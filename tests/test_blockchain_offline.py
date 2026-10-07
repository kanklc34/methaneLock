"""
Offline tests for Step 5 (settings, registry client, record CLI).
No network and no real key: web3 is replaced by mocks and the RPC endpoint is fake.

    python -m pytest tests/ -q
    python -B tests/test_blockchain_offline.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# earthengine-api is not needed for these tests; the import chain only needs the module name.
sys.modules.setdefault("ee", mock.MagicMock())

from web3 import Web3  # noqa: E402

from src.analysis import baseline as bl  # noqa: E402
from src.analysis import evidence_package as ep  # noqa: E402
from src.blockchain import config as cfg  # noqa: E402
from src.blockchain import record as rec  # noqa: E402
from src.blockchain import registry as reg  # noqa: E402
from src.data import fetch_sentinel as fs  # noqa: E402

SEPOLIA = 11155111
KEY = "0x" + "11" * 32
ADDR = "0x" + "ab" * 20
RPC = "https://sepolia.example.invalid/v3/SUPERSECRETPROJECTKEY"
HASH = hashlib.sha256(b"offline-report").hexdigest()
DATASET = "Sentinel-5P OFFL CH4"
GOOD_ENV = {"RPC_URL": RPC, "CHAIN_ID": "11155111", "PRIVATE_KEY": KEY, "CONTRACT_ADDRESS": ADDR}


def raises_exc(exc, fn):
    try:
        fn()
    except exc as e:
        return e
    return None


def _load(env):
    with mock.patch("src.blockchain.config.load_dotenv"), mock.patch.dict(os.environ, env, clear=True):
        return cfg.load_config()


def _config():
    return _load(GOOD_ENV)


# ---------- settings ----------

def test_config_loads_sepolia_settings():
    c = _load(GOOD_ENV)
    assert c.chain_id == SEPOLIA
    assert c.contract_address == Web3.to_checksum_address(ADDR)


def test_config_repr_hides_secrets():
    text = repr(_config())
    assert KEY[2:] not in text
    assert RPC not in text


def test_config_rejects_non_sepolia_chain():
    env = dict(GOOD_ENV, CHAIN_ID="1")
    assert raises_exc(cfg.ConfigError, lambda: _load(env)) is not None


def test_config_rejects_bad_key_without_echoing_it():
    bad = "0xdeadbeef"
    e = raises_exc(cfg.ConfigError, lambda: _load(dict(GOOD_ENV, PRIVATE_KEY=bad)))
    assert e is not None and bad not in str(e)


def test_config_requires_contract_address():
    env = dict(GOOD_ENV)
    env.pop("CONTRACT_ADDRESS")
    e = raises_exc(cfg.ConfigError, lambda: _load(env))
    assert e is not None and "CONTRACT_ADDRESS" in str(e)


# ---------- registry client (web3 mocked) ----------

def _w3(chain_id=SEPOLIA, code=b"\x60\x80", recorded=False, status=1):
    w3 = mock.MagicMock(name="w3")
    w3.is_connected.return_value = True
    w3.eth.chain_id = chain_id
    w3.eth.get_code.return_value = code
    account = mock.MagicMock(name="account")
    account.address = "0x" + "cd" * 20
    account.sign_transaction.return_value = mock.MagicMock(raw_transaction=b"raw")
    w3.eth.account.from_key.return_value = account
    contract = mock.MagicMock(name="contract")
    w3.eth.contract.return_value = contract
    contract.functions.isRecorded.return_value.call.return_value = recorded
    contract.functions.recordAnomaly.return_value.build_transaction.return_value = {"nonce": 7}
    w3.eth.get_transaction_count.return_value = 7
    tx_hash = mock.MagicMock(name="tx_hash")
    tx_hash.hex.return_value = "0xtxhash"
    w3.eth.send_raw_transaction.return_value = tx_hash
    w3.eth.wait_for_transaction_receipt.return_value = {"status": status, "blockNumber": 42}
    return w3, contract


def test_abi_has_expected_members():
    names = {(e["type"], e["name"]) for e in reg.REGISTRY_ABI}
    assert {("function", "recordAnomaly"), ("function", "isRecorded"),
            ("event", "AnomalyRecorded"), ("error", "AlreadyRecorded")} <= names
    ev = next(e for e in reg.REGISTRY_ABI if e["name"] == "AnomalyRecorded")
    assert [i["name"] for i in ev["inputs"]] == ["reportHash", "datasetId", "algorithmVersion", "timestamp", "submitter"]
    assert ev["inputs"][0]["indexed"] is True


def test_to_bytes32_validates_format():
    assert reg.to_bytes32(HASH) == bytes.fromhex(HASH)
    assert raises_exc(ValueError, lambda: reg.to_bytes32(HASH.upper())) is not None
    assert raises_exc(ValueError, lambda: reg.to_bytes32("0x" + HASH)) is not None
    assert raises_exc(ValueError, lambda: reg.to_bytes32("abc")) is not None


def test_client_refuses_wrong_chain():
    w3, _ = _w3(chain_id=1)
    assert raises_exc(reg.RegistryError, lambda: reg.MethaneRegistryClient(_config(), w3=w3)) is not None


def test_client_refuses_missing_contract_code():
    w3, _ = _w3(code=b"")
    assert raises_exc(reg.RegistryError, lambda: reg.MethaneRegistryClient(_config(), w3=w3)) is not None


def test_record_sends_mapped_args_and_returns_result():
    w3, contract = _w3()
    client = reg.MethaneRegistryClient(_config(), w3=w3)
    result = client.record(report_hash=HASH, dataset_id=DATASET, algorithm_version="1.0.0")
    contract.functions.recordAnomaly.assert_called_once_with(bytes.fromhex(HASH), DATASET, "1.0.0")
    w3.eth.send_raw_transaction.assert_called_once()
    assert result.tx_hash == "0xtxhash"
    assert result.block_number == 42
    assert result.submitter == "0x" + "cd" * 20


def test_record_refuses_duplicate_without_sending():
    w3, _ = _w3(recorded=True)
    client = reg.MethaneRegistryClient(_config(), w3=w3)
    assert raises_exc(reg.AlreadyRecordedError, lambda: client.record(HASH, DATASET, "1.0.0")) is not None
    w3.eth.send_raw_transaction.assert_not_called()


def test_record_reverted_status_raises():
    w3, _ = _w3(status=0)
    client = reg.MethaneRegistryClient(_config(), w3=w3)
    assert raises_exc(reg.RegistryError, lambda: client.record(HASH, DATASET, "1.0.0")) is not None


# ---------- record CLI ----------

def _package(tmp: Path):
    obs = fs.DailyCH4(date="2023-08-12", mean_ppb=1950.0, band=fs.PREFERRED_BAND, unit="ppb", image_ids=("x",))
    base = bl.Baseline(mean=1900.0, std=10.0, n_days=30)
    pkg = ep.build_package(
        region_id="turkmenistan_west_coast_og",
        bbox=[53.2, 38.4, 54.8, 39.6],
        observation=obs,
        baseline=base,
        git_commit="a" * 40,
        generated_at="2026-10-06T12:00:00+00:00",
    )
    return ep.save_package(pkg, tmp), pkg


def _run_cli(path, **patches):
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        for target, obj in patches.items():
            stack.enter_context(mock.patch.object(rec, target, obj))
        with contextlib.redirect_stdout(out):
            rc = rec.main([str(path)])
    return rc, out.getvalue()


def test_cli_records_mapped_fields():
    path, pkg = _package(Path(tempfile.mkdtemp()))
    client = mock.MagicMock()
    client.is_recorded.return_value = False
    client.submitter = "0x" + "cd" * 20
    client.record.return_value = reg.RecordResult(tx_hash="0xtx", block_number=9, submitter=client.submitter)
    rc, out = _run_cli(path, load_config=mock.MagicMock(return_value=_config()),
                       MethaneRegistryClient=mock.MagicMock(return_value=client))
    assert rc == 0
    client.record.assert_called_once_with(
        report_hash=pkg["report_hash"],
        dataset_id=DATASET,
        algorithm_version="1.0.0",
    )
    assert "0xtx" in out
    assert RPC not in out and KEY[2:] not in out


def test_cli_refuses_tampered_package_before_any_network():
    path, _ = _package(Path(tempfile.mkdtemp()))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["methane_value"] = 1.0
    path.write_text(json.dumps(data), encoding="utf-8")
    cls = mock.MagicMock()
    lc = mock.MagicMock()
    rc, _ = _run_cli(path, load_config=lc, MethaneRegistryClient=cls)
    assert rc == 1
    cls.assert_not_called()
    lc.assert_not_called()


def test_cli_already_recorded_sends_nothing():
    path, _ = _package(Path(tempfile.mkdtemp()))
    client = mock.MagicMock()
    client.is_recorded.return_value = True
    client.submitter = "0x" + "cd" * 20
    rc, _ = _run_cli(path, load_config=mock.MagicMock(return_value=_config()),
                     MethaneRegistryClient=mock.MagicMock(return_value=client))
    assert rc == 0
    client.record.assert_not_called()


def test_cli_redacts_endpoint_in_errors():
    path, _ = _package(Path(tempfile.mkdtemp()))
    failing = mock.MagicMock(side_effect=RuntimeError(f"connection failed for {RPC}"))
    rc, out = _run_cli(path, load_config=mock.MagicMock(return_value=_config()),
                       MethaneRegistryClient=failing)
    assert rc == 1
    assert RPC not in out
    assert "<redacted>" in out


def test_cli_missing_settings_returns_1():
    path, _ = _package(Path(tempfile.mkdtemp()))
    with mock.patch("src.blockchain.config.load_dotenv"), mock.patch.dict(os.environ, {}, clear=True):
        rc, out = _run_cli(path)
    assert rc == 1
    assert "is not set" in out


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\n{len(tests)} tests passed")
