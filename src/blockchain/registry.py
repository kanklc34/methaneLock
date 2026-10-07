"""
Client for MethaneRegistry on Sepolia: recordAnomaly and isRecorded.

Mapping from an Evidence Package (also in docs/evidence-package.md, On-chain record):
    reportHash       <- report_hash      (64 lowercase hex, sent as bytes32)
    datasetId        <- dataset          e.g. "Sentinel-5P OFFL CH4"
    algorithmVersion <- algorithm_version e.g. "1.0.0"

The client refuses to send a transaction when the hash is already recorded,
when the RPC chain is not CHAIN_ID, or when no contract code is at CONTRACT_ADDRESS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from web3 import Web3

from src.blockchain.config import BlockchainConfig

REGISTRY_ABI = [
    {
        "type": "function",
        "name": "recordAnomaly",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "reportHash", "type": "bytes32"},
            {"name": "datasetId", "type": "string"},
            {"name": "algorithmVersion", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "isRecorded",
        "stateMutability": "view",
        "inputs": [{"name": "reportHash", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "error",
        "name": "AlreadyRecorded",
        "inputs": [{"name": "reportHash", "type": "bytes32"}],
    },
    {
        "type": "event",
        "name": "AnomalyRecorded",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "reportHash", "type": "bytes32"},
            {"indexed": False, "name": "datasetId", "type": "string"},
            {"indexed": False, "name": "algorithmVersion", "type": "string"},
            {"indexed": False, "name": "timestamp", "type": "uint256"},
            {"indexed": False, "name": "submitter", "type": "address"},
        ],
    },
]

_HASH_RE = re.compile(r"[0-9a-f]{64}")


class RegistryError(RuntimeError):
    """The registry could not be used or the transaction failed."""


class AlreadyRecordedError(RegistryError):
    """The report hash is already recorded. Nothing was sent."""


@dataclass(frozen=True)
class RecordResult:
    tx_hash: str
    block_number: int
    submitter: str


def to_bytes32(report_hash: str) -> bytes:
    if not _HASH_RE.fullmatch(report_hash):
        raise ValueError("report_hash must be 64 lowercase hex characters")
    return bytes.fromhex(report_hash)


class MethaneRegistryClient:
    def __init__(self, config: BlockchainConfig, w3: Web3 | None = None, tx_timeout: int = 120):
        self._config = config
        self._tx_timeout = tx_timeout
        self._w3 = w3 or Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 30}))

        if not self._w3.is_connected():
            raise RegistryError("Cannot connect to the RPC endpoint.")
        chain_id = self._w3.eth.chain_id
        if chain_id != config.chain_id:
            raise RegistryError(f"RPC chain id {chain_id} does not match CHAIN_ID {config.chain_id}.")
        if self._w3.eth.get_code(config.contract_address) == b"":
            raise RegistryError("No contract code at CONTRACT_ADDRESS on this chain.")

        self._contract = self._w3.eth.contract(address=config.contract_address, abi=REGISTRY_ABI)
        self._account = self._w3.eth.account.from_key(config.private_key)

    @property
    def submitter(self) -> str:
        return self._account.address

    def is_recorded(self, report_hash: str) -> bool:
        return bool(self._contract.functions.isRecorded(to_bytes32(report_hash)).call())

    def record(self, report_hash: str, dataset_id: str, algorithm_version: str) -> RecordResult:
        h = to_bytes32(report_hash)
        if self.is_recorded(report_hash):
            raise AlreadyRecordedError(f"Report hash {report_hash} is already recorded. Nothing was sent.")

        nonce = self._w3.eth.get_transaction_count(self._account.address, "pending")
        tx = self._contract.functions.recordAnomaly(h, dataset_id, algorithm_version).build_transaction({
            "from": self._account.address,
            "nonce": nonce,
            "chainId": self._config.chain_id,
        })
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self._tx_timeout)
        if receipt["status"] != 1:
            raise RegistryError(f"Transaction {tx_hash.hex()} reverted.")
        return RecordResult(
            tx_hash=tx_hash.hex(),
            block_number=receipt["blockNumber"],
            submitter=self._account.address,
        )
