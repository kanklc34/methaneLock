"""
Record a saved Evidence Package on MethaneRegistry (Sepolia). Step 5.

    python -m src.blockchain.record data/evidence/<region>_<date>.json

Checks before any transaction is sent:
  1. the package schema, and report_hash recomputed from the content
  2. the settings (Sepolia chain id, key format, contract address)
  3. the RPC chain id, and contract code at CONTRACT_ADDRESS
  4. the report hash is not already recorded

After a successful record, a small file <package name>.tx.json (tx_hash,
block_number, explorer_url) is written next to the package. It is optional:
the dashboard reads it if present and otherwise accepts a pasted tx hash.
Nothing is written when the hash was already recorded and nothing was sent.

Errors are printed with the RPC URL and the private key redacted.
The pipeline does not call this command; recording is always an explicit step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.analysis.evidence_package import load_package, validate_schema, verify_package
from src.blockchain.config import BlockchainConfig, ConfigError, load_config
from src.blockchain.registry import MethaneRegistryClient

EXPLORER_TX_URL = "https://sepolia.etherscan.io/tx/{}"


def _with_0x(tx_hash: str) -> str:
    """Always '0x'-prefixed. Older hexbytes returns '0x...' from .hex(), newer returns bare hex."""
    tx_hash = tx_hash.strip()
    if tx_hash[:2].lower() == "0x":
        return "0x" + tx_hash[2:]
    return "0x" + tx_hash


def _write_tx_sidecar(package_path: Path, tx_hash: str, block_number: int) -> Path:
    """Write <package name>.tx.json next to the package (the name the dashboard reads)."""
    sidecar = package_path.with_suffix(".tx.json")
    payload = {
        "tx_hash": tx_hash,
        "block_number": block_number,
        "explorer_url": EXPLORER_TX_URL.format(tx_hash),
    }
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return sidecar


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record an Evidence Package on MethaneRegistry (Sepolia).")
    parser.add_argument("package", type=Path, help="path to an Evidence Package JSON file")
    args = parser.parse_args(argv)

    try:
        package = load_package(args.package)
        validate_schema(package)
    except (OSError, ValueError) as exc:
        print(f"ERROR: not a valid Evidence Package: {exc}")
        return 1
    if not verify_package(package):
        print("ERROR: report_hash does not match the package content. Nothing was sent.")
        return 1

    try:
        config: BlockchainConfig = load_config()
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 1

    secrets = [config.rpc_url, config.private_key]
    try:
        client = MethaneRegistryClient(config)
        print(f"contract:  {config.contract_address}")
        print(f"submitter: {client.submitter}")

        if client.is_recorded(package["report_hash"]):
            print("already recorded on this contract. Nothing was sent.")
            return 0

        result = client.record(
            report_hash=package["report_hash"],
            dataset_id=package["dataset"],
            algorithm_version=package["algorithm_version"],
        )
    except Exception as exc:  # RPC errors can echo the endpoint, so redact before printing
        print(f"ERROR: {type(exc).__name__}: {_redact(str(exc), secrets)}")
        return 1

    tx_hash = _with_0x(result.tx_hash)
    print(f"tx_hash:   {tx_hash}")
    print(f"block:     {result.block_number}")
    print(f"explorer:  {EXPLORER_TX_URL.format(tx_hash)}")

    # The transaction is already confirmed here, so a failed sidecar write must not fail the command.
    try:
        sidecar = _write_tx_sidecar(args.package, tx_hash, result.block_number)
        print(f"saved:     {sidecar}")
    except OSError as exc:
        print(f"WARNING: could not write the .tx.json file ({type(exc).__name__}). The transaction was recorded; keep the tx hash above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
