"""
Record a saved Evidence Package on MethaneRegistry (Sepolia). Step 5.

    python -m src.blockchain.record data/evidence/<region>_<date>.json

Checks before any transaction is sent:
  1. the package schema, and report_hash recomputed from the content
  2. the settings (Sepolia chain id, key format, contract address)
  3. the RPC chain id, and contract code at CONTRACT_ADDRESS
  4. the report hash is not already recorded

Errors are printed with the RPC URL and the private key redacted.
The pipeline does not call this command; recording is always an explicit step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.analysis.evidence_package import load_package, validate_schema, verify_package
from src.blockchain.config import BlockchainConfig, ConfigError, load_config
from src.blockchain.registry import MethaneRegistryClient

EXPLORER_TX_URL = "https://sepolia.etherscan.io/tx/{}"


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

    print(f"tx_hash:   {result.tx_hash}")
    print(f"block:     {result.block_number}")
    print(f"explorer:  {EXPLORER_TX_URL.format(result.tx_hash)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
