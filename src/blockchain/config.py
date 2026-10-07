"""
Blockchain settings for MethaneRegistry on Ethereum Sepolia (Step 5).

Read from the environment, and from .env through python-dotenv:
    RPC_URL           Sepolia JSON-RPC endpoint (may contain a provider key)
    CHAIN_ID          must be 11155111
    PRIVATE_KEY       0x-prefixed hex key of the submitter account, testnet only
    CONTRACT_ADDRESS  MethaneRegistry address, set after deployment

Secrets are never printed. The private key is excluded from repr().
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from web3 import Web3

SEPOLIA_CHAIN_ID = 11155111
_PRIVATE_KEY_RE = re.compile(r"0x[0-9a-fA-F]{64}")


class ConfigError(RuntimeError):
    """A required blockchain setting is missing or invalid."""


@dataclass(frozen=True)
class BlockchainConfig:
    rpc_url: str = field(repr=False)
    chain_id: int
    contract_address: str  # checksummed
    private_key: str = field(repr=False)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. See .env.example.")
    return value


def load_config() -> BlockchainConfig:
    load_dotenv()

    rpc_url = _required("RPC_URL")

    chain_raw = _required("CHAIN_ID")
    try:
        chain_id = int(chain_raw)
    except ValueError as exc:
        raise ConfigError("CHAIN_ID must be an integer.") from exc
    if chain_id != SEPOLIA_CHAIN_ID:
        raise ConfigError(f"CHAIN_ID must be {SEPOLIA_CHAIN_ID} (Sepolia), not {chain_id}.")

    private_key = _required("PRIVATE_KEY")
    if not _PRIVATE_KEY_RE.fullmatch(private_key):
        raise ConfigError("PRIVATE_KEY must be a 0x-prefixed hex string of 64 characters.")

    address_raw = _required("CONTRACT_ADDRESS")
    if not Web3.is_address(address_raw):
        raise ConfigError("CONTRACT_ADDRESS is not a valid Ethereum address.")

    return BlockchainConfig(
        rpc_url=rpc_url,
        chain_id=chain_id,
        contract_address=Web3.to_checksum_address(address_raw),
        private_key=private_key,
    )
