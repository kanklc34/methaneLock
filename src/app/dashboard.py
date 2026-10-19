"""
MethaneLock dashboard (Step 6). Read-only view of one saved Evidence Package.

Run from the repository root:
    streamlit run src/app/dashboard.py

Works offline. Packages are read from data/evidence/ (real pipeline output) or
data/mock/ (hash-valid demo packages, labelled MOCK on screen). Nothing here
calls Earth Engine, sends a transaction or needs PRIVATE_KEY.

Rules shown on screen:
  * anomaly decision: abs(z_score) >= threshold (2.5). severity_flag is shown
    separately and is never used as the anomaly decision.
  * integrity: schema check and report_hash recomputed from the content.
  * on-chain: tx hash and explorer link if known; otherwise "Not recorded
    on-chain yet". The isRecorded query is optional, runs only on a button
    press, and needs RPC_URL and CONTRACT_ADDRESS (no key).

Where the tx hash comes from (optional input; the recorder writes the sidecar after a successful record):
  * a sidecar file next to the package: <package name>.tx.json = {"tx_hash": "0x..."}
  * or pasted into the page for this session only
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.evidence_package import (  # noqa: E402
    SCHEMA_KEYS,
    EvidencePackageError,
    load_package,
    validate_schema,
    verify_package,
)

EVIDENCE_DIR = ROOT / "data" / "evidence"
MOCK_DIR = ROOT / "data" / "mock"

SCENARIOS = {
    "A: turkmenistan_west_coast_og": "turkmenistan_west_coast_og",
    "C: control_low_activity_demo": "control_low_activity_demo",
}

SEVERITY_COLORS = {  # background, text
    "none": ("#2e7d32", "#ffffff"),
    "low": ("#f9a825", "#000000"),
    "medium": ("#ef6c00", "#ffffff"),
    "high": ("#c62828", "#ffffff"),
}

SEPOLIA_CHAIN_ID = 11155111
EXPLORER_TX_URL = "https://sepolia.etherscan.io/tx/{}"
EXPLORER_ADDRESS_URL = "https://sepolia.etherscan.io/address/{}"
NOT_RECORDED_TEXT = "Not recorded on-chain yet"

_TX_RE = re.compile(r"(0x)?([0-9a-fA-F]{64})")
_HEX64 = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------- package loading

@dataclass(frozen=True)
class PackageEntry:
    path: Path
    package: dict
    region_id: str


def list_packages(directory: Path) -> tuple[list[PackageEntry], list[tuple[str, str]]]:
    """Valid-looking packages in a directory, and (file name, reason) for files that were skipped.

    A file is skipped only when it is unreadable or has no region_id. Schema and hash
    problems are not hidden here: they are shown on screen for the selected package.
    """
    entries: list[PackageEntry] = []
    skipped: list[tuple[str, str]] = []
    if not directory.is_dir():
        return entries, skipped
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".tx.json"):
            continue
        try:
            package = load_package(path)
            region_id = package["location"]["region_id"]
            if not isinstance(region_id, str):
                raise ValueError("location.region_id is not a string")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue
        entries.append(PackageEntry(path=path, package=package, region_id=region_id))
    return entries, skipped


# ---------------------------------------------------------------- assessment

@dataclass(frozen=True)
class Assessment:
    schema_ok: bool
    schema_error: str | None
    hash_ok: bool
    is_anomaly: bool | None  # None if z_score or threshold cannot be read as numbers
    abs_z: float | None
    threshold: float | None
    threshold_note: str | None


def _number(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def assess(package: dict) -> Assessment:
    """Integrity checks and the anomaly decision, from z_score and threshold only."""
    schema_error = None
    try:
        validate_schema(package)
    except (EvidencePackageError, KeyError, TypeError) as exc:
        schema_error = str(exc)

    try:
        hash_ok = verify_package(package)
    except (EvidencePackageError, TypeError):
        hash_ok = False

    z = _number(package.get("z_score"))
    thr = _number(package.get("threshold"))
    anomaly = None
    abs_z = None
    note = None
    if z is not None and thr is not None:
        abs_z = abs(z)
        anomaly = abs_z >= thr
        if thr != 2.5:
            note = f"Package threshold is {thr}, not the fixed 2.5. The decision above uses the package value."
    return Assessment(
        schema_ok=schema_error is None,
        schema_error=schema_error,
        hash_ok=hash_ok,
        is_anomaly=anomaly,
        abs_z=abs_z,
        threshold=thr,
        threshold_note=note,
    )


def flatten_fields(package: dict) -> list[tuple[str, str]]:
    """All package fields as (name, text) rows, in schema order, nested objects expanded."""
    rows: list[tuple[str, str]] = []
    keys = [k for k in SCHEMA_KEYS if k in package] + [k for k in package if k not in SCHEMA_KEYS]
    for key in keys:
        value = package[key]
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                rows.append((f"{key}.{sub_key}", json.dumps(sub_value) if not isinstance(sub_value, str) else sub_value))
        elif isinstance(value, str):
            rows.append((key, value))
        else:
            rows.append((key, json.dumps(value)))
    return rows


# ---------------------------------------------------------------- transaction hash

def normalize_tx_hash(raw: str | None) -> str | None:
    """'0x' + 64 hex, lowercase. Accepts a missing 0x prefix. None if not a tx hash."""
    if not raw:
        return None
    m = _TX_RE.fullmatch(raw.strip())
    if not m:
        return None
    return "0x" + m.group(2).lower()


def explorer_tx_url(tx_hash: str) -> str:
    return EXPLORER_TX_URL.format(tx_hash)


def read_tx_sidecar(package_path: Path) -> str | None:
    """tx hash from <package name>.tx.json, or None if the file is absent or unusable."""
    sidecar = package_path.with_suffix(".tx.json")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return normalize_tx_hash(data.get("tx_hash"))
    except (OSError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- optional isRecorded query

@dataclass(frozen=True)
class OnchainSettings:
    available: bool
    reason: str | None  # why it is unavailable; never contains the RPC URL
    rpc_url: str = ""
    contract_address: str = ""


def onchain_settings(env: dict | None = None) -> OnchainSettings:
    """RPC_URL and CONTRACT_ADDRESS from the environment / .env. No private key is read."""
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        env = os.environ
    rpc_url = str(env.get("RPC_URL", "")).strip()
    address = str(env.get("CONTRACT_ADDRESS", "")).strip()
    if not rpc_url and not address:
        return OnchainSettings(False, "RPC_URL and CONTRACT_ADDRESS are not set.")
    if not rpc_url:
        return OnchainSettings(False, "RPC_URL is not set.")
    if not address:
        return OnchainSettings(False, "CONTRACT_ADDRESS is not set (the contract is not deployed or not configured yet).")
    try:
        from web3 import Web3
    except ImportError:
        return OnchainSettings(False, "web3 is not installed (pip install -r requirements.txt).")
    if not Web3.is_address(address):
        return OnchainSettings(False, "CONTRACT_ADDRESS is not a valid Ethereum address.")
    return OnchainSettings(True, None, rpc_url=rpc_url, contract_address=Web3.to_checksum_address(address))


def check_is_recorded(settings: OnchainSettings, report_hash: str) -> bool:
    """Read-only isRecorded call. Raises RuntimeError with a message that holds no secrets."""
    if not settings.available:
        raise RuntimeError(settings.reason or "On-chain query is not configured.")
    if not _HEX64.fullmatch(report_hash):
        raise RuntimeError("report_hash must be 64 lowercase hex characters.")
    from web3 import Web3

    from src.blockchain.registry import REGISTRY_ABI

    try:
        w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            raise RuntimeError("Cannot connect to the RPC endpoint.")
        chain_id = w3.eth.chain_id
        if chain_id != SEPOLIA_CHAIN_ID:
            raise RuntimeError(f"RPC chain id is {chain_id}, expected {SEPOLIA_CHAIN_ID} (Sepolia).")
        if w3.eth.get_code(settings.contract_address) == b"":
            raise RuntimeError("No contract code at CONTRACT_ADDRESS on this chain.")
        contract = w3.eth.contract(address=settings.contract_address, abi=REGISTRY_ABI)
        return bool(contract.functions.isRecorded(bytes.fromhex(report_hash)).call())
    except RuntimeError:
        raise
    except Exception as exc:  # RPC errors can echo the endpoint URL, so keep only the type
        raise RuntimeError(f"RPC call failed ({type(exc).__name__}).") from None


# ---------------------------------------------------------------- UI

def _badge(text: str, background: str, color: str, size: str = "1.4rem") -> str:
    return (
        f'<span style="background:{background};color:{color};padding:0.35rem 0.9rem;'
        f'border-radius:0.5rem;font-weight:700;font-size:{size};letter-spacing:0.04em;">'
        f"{html.escape(text)}</span>"
    )


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="MethaneLock", page_icon=None, layout="wide")
    st.title("MethaneLock")
    st.caption(
        "Evidence Package viewer. Shows what a saved package says and whether it is unchanged. "
        "It does not show that an anomaly is real or what caused it."
    )

    # ---- source and scenario
    evidence_entries, evidence_skipped = list_packages(EVIDENCE_DIR)
    mock_entries, mock_skipped = list_packages(MOCK_DIR)

    c1, c2, c3 = st.columns([1.2, 1.4, 2.4])
    with c1:
        source_options = ["data/evidence (pipeline output)", "data/mock (offline demo)"]
        source = st.radio("Source", source_options, index=0 if evidence_entries else 1)
    is_mock = source == source_options[1]
    entries = mock_entries if is_mock else evidence_entries
    skipped = mock_skipped if is_mock else evidence_skipped
    folder = MOCK_DIR if is_mock else EVIDENCE_DIR

    with c2:
        scenario_label = st.radio("Scenario", list(SCENARIOS))
    region_id = SCENARIOS[scenario_label]
    matching = [e for e in entries if e.region_id == region_id]

    with c3:
        if matching:
            chosen_name = st.selectbox(
                f"Evidence Package ({len(matching)} for this scenario)",
                [e.path.name for e in matching],
            )
            chosen = next(e for e in matching if e.path.name == chosen_name)
        else:
            chosen = None
            st.selectbox("Evidence Package", ["(none)"], disabled=True)

    if is_mock:
        st.warning(
            "MOCK DATA. These packages are hash-valid demo files, not derived from Sentinel-5P. "
            "Their qa_note says so."
        )
    if skipped:
        with st.expander(f"{len(skipped)} file(s) in {folder.name}/ could not be read and were skipped"):
            for name, reason in skipped:
                st.text(f"{name}: {reason}")

    if chosen is None:
        if not entries:
            st.info(
                f"No packages found in data/{folder.name}/. "
                "Generate them with `python -m src.pipeline`, or switch the source to the mock demo."
            )
        else:
            st.info(f"No package for scenario {scenario_label} in data/{folder.name}/.")
        return

    package = chosen.package
    result = assess(package)

    # ---- integrity banner
    if result.schema_ok and result.hash_ok:
        st.success("Integrity OK: schema is valid and report_hash matches the package content.")
    else:
        if not result.hash_ok:
            st.error("report_hash does NOT match the package content. This package has been changed or is damaged.")
        if not result.schema_ok:
            st.error(f"Schema check failed: {result.schema_error}")

    # ---- severity, z-score, anomaly decision
    severity = package.get("severity_flag")
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown("**severity_flag**")
        bg, fg = SEVERITY_COLORS.get(str(severity), ("#616161", "#ffffff"))
        st.markdown(_badge(str(severity).upper(), bg, fg, "2rem"), unsafe_allow_html=True)
        st.caption("Magnitude of |z_score| only. Not an anomaly decision.")
    with k2:
        st.markdown("**z_score**")
        z = _number(package.get("z_score"))
        st.markdown(f"## {z:.3f}" if z is not None else "## n/a")
        st.caption(
            f"methane_value {package.get('methane_value')} {package.get('unit')} vs baseline "
            f"{package.get('baseline_mean')} ± {package.get('baseline_std')}"
        )
    with k3:
        st.markdown("**is_anomaly**")
        if result.is_anomaly is None:
            st.markdown(_badge("UNKNOWN", "#616161", "#ffffff", "2rem"), unsafe_allow_html=True)
            st.caption("z_score or threshold is not a number.")
        else:
            label, bg = ("YES", "#c62828") if result.is_anomaly else ("NO", "#2e7d32")
            st.markdown(_badge(label, bg, "#ffffff", "2rem"), unsafe_allow_html=True)
            op = "≥" if result.is_anomaly else "<"
            st.caption(f"|z_score| = {result.abs_z:.3f} {op} threshold {result.threshold:g}")
        if result.threshold_note:
            st.warning(result.threshold_note)

    if result.is_anomaly is False and severity in ("low", "medium", "high"):
        st.info(
            f"severity_flag is '{severity}' but |z_score| is below the threshold, so this is not an anomaly. "
            "The two rules are independent."
        )

    # ---- report hash
    st.subheader("report_hash")
    st.code(str(package.get("report_hash")), language=None)
    st.caption(
        "SHA-256 of the canonical JSON without this field. "
        + ("Recomputed from the content: matches." if result.hash_ok else "Recomputed from the content: DOES NOT MATCH.")
    )

    # ---- on-chain
    st.subheader("On-chain record (Sepolia)")
    settings = onchain_settings()
    report_hash = str(package.get("report_hash"))

    tx_hash = read_tx_sidecar(chosen.path)
    tx_source = "sidecar file" if tx_hash else None
    pasted = st.text_input(
        "Transaction hash (optional, this session only)",
        key=f"tx_{chosen.path.name}",
        placeholder="0x…  printed by python -m src.blockchain.record",
    )
    if pasted.strip():
        normalized = normalize_tx_hash(pasted)
        if normalized:
            tx_hash, tx_source = normalized, "pasted"
        else:
            st.warning("That is not a transaction hash (expected 64 hex characters, with or without 0x).")

    state_key = f"recorded_{chosen.path.name}_{report_hash}"
    recorded = st.session_state.get(state_key)  # None = not queried, True/False = query result

    if tx_hash:
        st.markdown(f"**tx hash** ({tx_source}): `{tx_hash}`")
        st.markdown(f"[Open in Sepolia explorer]({explorer_tx_url(tx_hash)})")
        if recorded is False:
            st.warning("A tx hash is known, but isRecorded returned false for this report_hash on the configured contract.")
    elif recorded is True:
        st.markdown("**tx hash:** not known locally (isRecorded is true, so the hash is on the configured contract).")
    else:
        st.markdown(f"**{NOT_RECORDED_TEXT}**")
        st.caption("No transaction hash is known for this package. This does not query the chain.")

    st.markdown("**isRecorded query** (optional)")
    if not settings.available:
        st.warning(f"Disabled: {settings.reason} Everything above works without it.")
    elif not (result.schema_ok and result.hash_ok):
        st.warning("Disabled: the package failed its integrity check, so its hash is not queried.")
    else:
        st.caption(f"Contract {settings.contract_address}")
    if st.button("Check isRecorded", disabled=not (settings.available and result.schema_ok and result.hash_ok)):
        try:
            with st.spinner("Querying Sepolia…"):
                st.session_state[state_key] = check_is_recorded(settings, report_hash)
        except RuntimeError as exc:
            st.session_state.pop(state_key, None)
            st.error(str(exc))
        recorded = st.session_state.get(state_key)
    if recorded is True:
        st.success("isRecorded = true: this report_hash is registered on the contract.")
    elif recorded is False:
        st.info("isRecorded = false: this report_hash is not registered on the contract.")

    # ---- all fields
    st.subheader("All fields")
    rows = flatten_fields(package)
    st.dataframe(
        {"field": [r[0] for r in rows], "value": [r[1] for r in rows]},
        hide_index=True,
    )
    with st.expander("Raw JSON"):
        st.json(package)
    st.caption(f"File: data/{folder.name}/{chosen.path.name}")


if __name__ == "__main__":
    main()
