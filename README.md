# MethaneLock

**Decentralized Methane Anomaly Registry**

Climate Data Analysis & Anomaly Detection, with a publicly verifiable, tamper-evident record.

> Status: data retrieval, baseline, anomaly, Evidence Package and the registry contract are implemented and tested offline. Live Earth Engine and Sepolia runs are pending. Dashboard not implemented yet.

## Overview

<!-- TODO: 2–3 sentences. What the project does, for whom, and what its output is. -->

## Climate problem

<!-- TODO: Methane as a potent greenhouse gas; why verifiable regional anomaly records help policymakers, environmental agencies and researchers. -->

## How it works

<!-- TODO: Sentinel-5P CH₄ → spatial mean over a bounding box → z-score anomaly → Evidence Package → SHA-256 hash → Sepolia testnet record -->

## Scope: what it does not do

<!-- TODO: Explicit out-of-scope list. -->

## What this system guarantees and does not guarantee

### Guarantees

<!-- TODO -->

### Does not guarantee

<!-- TODO: e.g. that a flagged anomaly is a confirmed emission, or identifies its source. -->

## Data

- Source: Sentinel-5P OFFL L3 CH₄, Google Earth Engine asset `COPERNICUS/S5P/OFFL/L3_CH4`
- Unit: ppb, stated explicitly in every output
- Spatial aggregation: mean over the selected bounding box
- Quality handling: no pixel-level QA/validity filter is applied in this MVP. The `qa_note` field of each Evidence Package states this.

## Method

<!-- TODO: zscore-v1 description -->

Fixed parameters: baseline 2020-01-01 to 2022-12-31; observation target 2023-08-15 (nearest valid date if no observation exists that day); threshold 2.5; severity bands by absolute z-score.

An observation is marked as an anomaly when the absolute value of `z_score` is at least the threshold (2.5). `severity_flag` describes the magnitude of the deviation and does not by itself decide whether an anomaly is present.

## Evidence Package

Each result is saved as one JSON object. Full schema and hash rule: [docs/evidence-package.md](docs/evidence-package.md).

## Blockchain

Contract: `contracts/MethaneRegistry.sol` (Solidity 0.8.24, Ethereum Sepolia). It records report hashes and nothing else: no token, no access control, no upgradeability, no marketplace.

- `recordAnomaly(bytes32 reportHash, string datasetId, string algorithmVersion)` records a hash once. A second call with the same hash reverts with `AlreadyRecorded(bytes32)`.
- `isRecorded(bytes32 reportHash) returns (bool)`
- `event AnomalyRecorded(bytes32 indexed reportHash, string datasetId, string algorithmVersion, uint256 timestamp, address submitter)`

Mapping from an Evidence Package (used by `src/blockchain/registry.py`):

- `reportHash` ← `report_hash`, as bytes32 with a `0x` prefix
- `datasetId` ← `dataset`, for example `Sentinel-5P OFFL CH4`. `source_uri` is not sent.
- `algorithmVersion` ← `algorithm_version`, for example `1.0.0`

Recording a saved package sends one transaction on Sepolia:

```bash
python -m src.blockchain.record data/evidence/<file>.json
```

Before sending, the command checks the package schema, recomputes `report_hash`, confirms that the RPC chain is Sepolia, and checks that the hash is not already recorded. It prints the transaction hash and an explorer link. The pipeline never records packages on its own.

## Dashboard

<!-- TODO: Streamlit. Region selection (A/C), Evidence Package view, severity flag, transaction hash and block explorer link. -->

## Demo regions

| Role | `region_id` | Bounding box `[min_lon, min_lat, max_lon, max_lat]` |
|---|---|---|
| A — main scenario | `turkmenistan_west_coast_og` | `[53.2, 38.4, 54.8, 39.6]` |
| C — control | `control_low_activity_demo` | `[56.0, 39.5, 57.5, 40.8]` |

## Repository structure

```
MethaneLock/
├── README.md
├── docs/
│   └── evidence-package.md
├── data/
├── src/
│   ├── pipeline.py
│   ├── data/
│   ├── analysis/
│   ├── blockchain/
│   │   ├── config.py
│   │   ├── registry.py
│   │   └── record.py
│   └── app/
├── contracts/
│   ├── MethaneRegistry.sol
│   └── script/
│       └── Deploy.s.sol
├── foundry.toml
├── tests/
│   ├── test_offline.py
│   ├── test_blockchain_offline.py
│   └── contracts/
│       └── MethaneRegistry.t.sol
├── .gitignore
├── requirements.txt
└── .env.example
```

## Setup

1. Create a Python environment and run `pip install -r requirements.txt`.
2. Register a Google Cloud project for Earth Engine access and note its project ID.
3. Authenticate once on your machine with `earthengine authenticate`. The code uses your user credentials, so no key file is needed.
4. Copy `.env.example` to `.env` and set `GEE_PROJECT_ID`. Keep `.env` local and never commit it.

Run the full pipeline (fetch, baseline, anomaly, Evidence Package) from the repository root with `python -m src.pipeline`. Packages are written to `data/evidence/`. Offline tests: `python -m pytest tests/`.

5. Install Foundry with `foundryup`. From the repository root, run `forge install foundry-rs/forge-std`. This requires the repository to be a git repository.
6. Run the contract tests with `forge test`.
7. Deploy to Sepolia. Load `.env` into the shell, then run the script:

   ```bash
   set -a; source .env; set +a
   forge script contracts/script/Deploy.s.sol --rpc-url sepolia --broadcast
   ```

   The script stops unless `CHAIN_ID` is 11155111 and the RPC reports that chain id. Record the deployed address in this README by hand. `out/`, `cache/` and `broadcast/` are git-ignored because they can contain sensitive values.

8. Put the deployed contract address in `.env` as `CONTRACT_ADDRESS`.
9. Record a saved Evidence Package on Sepolia with `python -m src.blockchain.record data/evidence/<file>.json`. The command needs `RPC_URL`, `CHAIN_ID`, `PRIVATE_KEY` and `CONTRACT_ADDRESS` in `.env`. It never prints the private key or the RPC URL.

<!-- TODO: Dashboard setup, added with that step. -->

## Limitations

<!-- TODO: Known limits of the method, the data and the demo scope. -->
