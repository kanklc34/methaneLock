# MethaneLock

**Decentralized Methane Anomaly Registry**

Climate Data Analysis and transparent statistical anomaly detection on public satellite methane data, with a tamper-evident record of each result.

> **Status:** the analysis pipeline, Evidence Package, registry contract and dashboard are implemented and tested offline. The pipeline has been run once on real Sentinel-5P data (2026-10-19): two Evidence Packages are in `data/evidence/`, and **neither is flagged as an anomaly**. The registry contract is deployed on Sepolia and the hash of the `turkmenistan_west_coast_og` package is recorded there (2026-10-20); the control package is not recorded. A record shows that a hash existed on the contract. It does not show that the analysis finds real anomalies. The packages in `data/mock/` are synthetic and labelled as such. See [Project status](#project-status).

## Problem

Methane is a strong greenhouse gas, and claims about regional methane increases are hard to check after the fact. Satellite data is public, but an analysis result is usually just a file or a chart: the exact method, parameters and data source are often not stated with it, and the file can be edited or silently replaced later.

## Solution

MethaneLock covers one narrow workflow:

1. For a chosen bounding box, take the Sentinel-5P CH₄ column average for one day and compare it with a fixed 2020–2022 baseline using a z-score.
2. Save the result, with every parameter that produced it, as one JSON **Evidence Package**.
3. Compute the SHA-256 hash of that package (the `report_hash`).
4. On an explicit command, register the hash on an Ethereum **Sepolia testnet** contract.
5. Show the package, its integrity check and its on-chain status in a dashboard.

The method is a plain statistical rule, fully described below. There is no trained model and no machine learning.

**Out of scope:** marketplace, tokens or NFTs, carbon credits, model training, mainnet, operator alerts, and identifying the facility or cause behind an anomaly.

## What the blockchain guarantees and does not guarantee

The contract stores one thing: whether a given hash was recorded. The Evidence Package itself stays off-chain, in a file.

### Guarantees

- **Change detection.** Anyone holding a package can recompute its SHA-256 and compare it with `report_hash`. Any edit to the package content changes the hash.
- **Registration.** If `isRecorded(report_hash)` is true on the contract, a transaction registered exactly that hash, and the block timestamp is an upper bound on when it existed. A hash can be recorded only once; a second attempt reverts.
- **Open verification.** `isRecorded` is a public read-only call. Checking it does not require trusting this project.
- **Stated method.** The algorithm, parameters, data source and band are fixed in the code and written into every package.

### Does not guarantee

- **That an anomaly is real.** A flagged result is a statistical deviation from a baseline. It is not a confirmed emission, and it does not identify a source, facility or cause.
- **That the data is correct.** No pixel-level quality filter is applied in this MVP (see [docs/limitations.md](docs/limitations.md)).
- **Who produced the package.** The contract has no access control, so anyone can record any hash. A recorded hash does not show that this pipeline created it.
- **That the analysis can be re-derived from the package alone.** The package does not list the satellite image IDs, and the source dataset can be reprocessed.
- **Permanence.** Sepolia is a testnet. It is not a durable archive.
- **Content availability.** Only the hash is on-chain. If the package file is lost, it cannot be recovered from the chain.

## Evidence Package

One JSON object per result. Full schema, field reference and hash rule: [docs/evidence-package.md](docs/evidence-package.md).

| Group | Fields |
|---|---|
| Source | `dataset`, `source_uri`, `observation_date`, `unit` |
| Location | `location.lat`, `location.lon`, `location.region_id`, `location.bbox` |
| Measurement | `methane_value` (ppb), `baseline_period`, `baseline_mean`, `baseline_std` |
| Decision | `z_score`, `threshold` (2.5), `severity_flag` |
| Provenance | `qa_note`, `algorithm`, `algorithm_version`, `git_commit`, `generated_at`, `schema_version` |
| Integrity | `report_hash` |

**Hash rule (short form):** remove `report_hash`, serialize with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`, encode as UTF-8, take SHA-256. The exact rule is in [docs/evidence-package.md](docs/evidence-package.md#hash-rule).

**Anomaly rule:** an observation is an anomaly when `|z_score| >= threshold` (2.5). The rule is two-sided, so a large negative deviation also counts. `severity_flag` (`none` below 2.0, `low` 2.0 to 3.0, `medium` 3.0 to 4.0, `high` 4.0 and above) describes magnitude only. A result with `|z|` between 2.0 and 2.5 is flagged `low` but is **not** an anomaly.

## How it works

```
Sentinel-5P OFFL L3 CH4 (Google Earth Engine)
   │  spatial mean over the bounding box, one value per day
   ▼
Baseline 2020-01-01 .. 2022-12-31   (mean, sample std of daily values)
Observation: nearest valid day to 2023-08-15, within ±7 days
   │  z = (value − mean) / std
   ▼
Evidence Package (JSON)  ──►  SHA-256 report_hash        saved in data/evidence/
   │                                   │
   │ read-only                         │ explicit command only, never automatic
   ▼                                   ▼
Dashboard                      MethaneRegistry on Sepolia (hash only)
```

Fixed parameters: baseline 2020-01-01 to 2022-12-31; observation target 2023-08-15; threshold 2.5. Data: `COPERNICUS/S5P/OFFL/L3_CH4`, band `CH4_column_volume_mixing_ratio_dry_air`, unit ppb (no conversion). Images from the same date are combined by an unweighted mean.

Demo regions:

| Role | `region_id` | Bounding box `[min_lon, min_lat, max_lon, max_lat]` |
|---|---|---|
| A: main scenario | `turkmenistan_west_coast_og` | `[53.2, 38.4, 54.8, 39.6]` |
| C: control | `control_low_activity_demo` | `[56.0, 39.5, 57.5, 40.8]` |

The two areas were chosen as demo scenarios. Neither choice has been checked against independent emission records.

## Limitations

The full list, with the reasoning, is in [docs/limitations.md](docs/limitations.md). The main points:

- **Coarse, regional signal.** The sensor footprint is about 5.5 × 7 km, and the bounding boxes are roughly 130–145 km across. The method can only reflect large regional deviations. It cannot see a single facility.
- **No quality filter.** Pixel-level validity information is not used. Clouds, surface conditions and retrieval bias are not handled.
- **Simple baseline.** The baseline pools all days of 2020–2022 with no seasonal or long-term trend correction, so a single August 2023 value can differ from it for reasons unrelated to local emissions.
- **False positives are expected.** One observation, a fixed threshold and no persistence check. Even with perfectly normal data, about 1 in 80 observations would exceed 2.5 by chance.
- **One run, two regions.** The live result is a single observation per region. The observation day was seven days from the target date in both regions. Packages in `data/mock/` are synthetic and are not results.

## Validation

Details and the scenario table: [docs/validation.md](docs/validation.md).

Two kinds of validation exist today. The logic is checked offline with synthetic data (tests). The pipeline has also been run once on real data, giving the two packages below. Both pass the integrity check and neither exceeds the threshold. **One observation per region does not show that the method detects real emissions, and it does not show that it fails to.**

Live run, 2026-10-19 (`data/evidence/`):

| Scenario | Observation date | `methane_value` (ppb) | Baseline mean ± std (ppb) | `z_score` | `severity_flag` | Anomaly (`abs(z) >= 2.5`) |
|---|---|---|---|---|---|---|
| A: `turkmenistan_west_coast_og` | 2023-08-08 | 1953.02 | 1935.92 ± 15.62 | 1.094 | none | no |
| C: `control_low_activity_demo` | 2023-08-08 | 1924.10 | 1916.20 ± 13.67 | 0.578 | none | no |

The target date was 2023-08-15. The nearest valid day to it was 2023-08-08 in both regions. Report hashes and the full table are in [docs/validation.md](docs/validation.md). The synthetic packages in `data/mock/` exist only to show what a flagged package looks like in the dashboard.

## How to run

### Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate        macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # Windows: copy .env.example .env
```

`.env` is local and must never be committed. Which settings are needed for what:

| Task | Required `.env` values |
|---|---|
| Dashboard with mock or saved packages | none |
| Dashboard `isRecorded` query (optional) | `RPC_URL`, `CONTRACT_ADDRESS` |
| Live pipeline | `GEE_PROJECT_ID` (plus `earthengine authenticate` once) |
| Recording a package | `RPC_URL`, `CHAIN_ID`, `PRIVATE_KEY`, `CONTRACT_ADDRESS` |

### Offline demo (no Earth Engine, no Sepolia)

```bash
streamlit run src/app/dashboard.py
```

The dashboard opens on `data/evidence/` (the live packages). If that folder is empty it opens on the synthetic packages in `data/mock/` and shows a "MOCK DATA" warning. Suggested walkthrough:

1. Source `data/evidence`, scenario **A**. Point out the `severity_flag` badge (`none`), the `z_score` (1.094), and the separate **is_anomaly** box (`|z| = 1.094 < threshold 2.5`, so `NO`).
2. Show `report_hash` and the green integrity banner (schema valid, hash recomputed and matching).
3. Show the on-chain area: no transaction is known, so it reads **Not recorded on-chain yet**. The `isRecorded` button is disabled with a reason while `RPC_URL` or `CONTRACT_ADDRESS` is missing.
4. Choose scenario **C** and compare: severity `none`, anomaly `NO`.
5. To see a flagged package, switch the source to `data/mock` (a yellow MOCK warning appears) and choose **A**: severity `medium`, `z = 3.750`, anomaly `YES`. This package is synthetic and is only an illustration.
6. Integrity demo: copy a live package under a new name in `data/evidence/`, change one number such as `methane_value`, and reload the dashboard. The banner turns red because the hash no longer matches. Delete the copy afterwards.

**Offline and the pipeline.** The pipeline itself needs live Earth Engine access; it has no offline mode. The offline paths are the test suite (synthetic data, Earth Engine and web3 mocked) and the saved packages in `data/evidence/` and `data/mock/`.

### Pipeline (live Earth Engine)

```bash
earthengine authenticate      # once
python -m src.pipeline
```

Run from the repository root. A git commit must exist, because `git_commit` is written into each package. For each demo region the pipeline writes one package to `data/evidence/`. A region with no valid data or no valid baseline writes nothing and the exit code is 1. The pipeline never records anything on-chain.

### Dashboard

```bash
streamlit run src/app/dashboard.py
```

- Choose the source (`data/evidence` or `data/mock`), the scenario (A or C) and a package.
- The page shows all package fields, the severity flag, the anomaly decision, `report_hash` with its verification result, and the on-chain status.
- The anomaly decision is computed from `z_score` and `threshold` only, never from `severity_flag`.
- **Transaction hash:** after a successful record, `record.py` writes `<package name>.tx.json` next to the package (`tx_hash`, `block_number`, `explorer_url`). The dashboard reads `tx_hash` from that optional file, or accepts a hash pasted into the page for the current session. It then shows a Sepolia explorer link. Without either it shows "Not recorded on-chain yet". The dashboard shows the hash it is given; it does not check what that transaction recorded. Only `isRecorded` does that.
- **isRecorded query:** optional, runs only when the button is pressed, needs `RPC_URL` and `CONTRACT_ADDRESS` (no private key), and checks that the RPC chain is Sepolia.

### Sepolia runbook

Needs: [Foundry](https://book.getfoundry.sh/), a Sepolia RPC URL, and a **testnet-only** account that holds Sepolia ETH. Never use a key that controls real funds.

**1. Fill `.env`** (copy of `.env.example`; never commit it):

| Field | Value |
|---|---|
| `RPC_URL` | Sepolia JSON-RPC endpoint |
| `CHAIN_ID` | `11155111` (fixed; the deploy script and `record.py` refuse anything else) |
| `PRIVATE_KEY` | `0x`-prefixed 64-hex key of the testnet account |
| `CONTRACT_ADDRESS` | leave empty until step 3 |

**2. Deploy the contract.** forge-std is not vendored in this repository and no git submodule is required. After cloning, install it once:

```bash
forge install foundry-rs/forge-std
forge test
# Load .env into the shell (bash; on Windows use Git Bash, or set the variables yourself)
set -a; source .env; set +a
forge script contracts/script/Deploy.s.sol --rpc-url sepolia --broadcast --gas-estimate-multiplier 850
```

The deploy script stops unless `CHAIN_ID` is 11155111 and the RPC reports that chain id. It prints `MethaneRegistry deployed at: 0x...`. `out/`, `cache/` and `broadcast/` are git-ignored because they can contain sensitive values.

`--gas-estimate-multiplier 850` is needed on Sepolia: forge's local simulation estimates about 300k gas for the contract creation, while the network asked for about 1.97M (`cast estimate --create` shows the real figure). With forge's default multiplier the transaction was mined but failed (`[Failed]`, status 0, all gas used) and left no code at the printed address. Unused gas is refunded, so the real cost stays tiny. A successful run shows `[Success]` for the transaction; confirm with `cast code <address> --rpc-url "$RPC_URL"`, which must print more than `0x`. Do not use an address from a failed deployment.

**3. Set `CONTRACT_ADDRESS`.** Copy the printed address into `.env`. Check it on `https://sepolia.etherscan.io/address/<address>`: the contract creation transaction should be listed.

**4. Record one package** (explicit command; the pipeline never does this):

```bash
python -m src.blockchain.record data/evidence/<file>.json
```

Before sending, the command checks the package schema, recomputes `report_hash`, confirms that the RPC chain is Sepolia and that the address holds code, and checks that the hash is not already recorded. It prints `tx_hash` (always `0x`-prefixed), the block number and an explorer link, then writes `data/evidence/<file>.tx.json` next to the package. That file is optional: without it the dashboard still works with a pasted hash. Nothing is written when the hash was already recorded. The private key and the RPC URL are never printed.

The registry stores the hash of a result whatever its decision. The two live packages are both `not anomaly`, and recording them is valid; the event name `AnomalyRecorded` does not mean a package is flagged. `is_anomaly` is read from the package, not from the chain.

**5. Check the event on the explorer.** Open the `explorer` link printed by the command, or paste the `tx_hash` into `https://sepolia.etherscan.io`:

- Status is **Success**, and the block number matches the output.
- The **Logs** tab shows one `AnomalyRecorded` event from `CONTRACT_ADDRESS`.
- The event's indexed `reportHash` (Topic 1) equals `0x` + the package's `report_hash`. If the contract is not verified on Etherscan, the log is shown undecoded: Topic 1 is the hash, and `datasetId` (`Sentinel-5P OFFL CH4`), `algorithmVersion`, `timestamp` and `submitter` are ABI-encoded in the Data field.
- Optionally, press the `isRecorded` button in the dashboard (needs `RPC_URL` and `CONTRACT_ADDRESS`, no private key).

### Tests

```bash
python -m pytest tests/ -q
```

The Python tests run offline. See [docs/validation.md](docs/validation.md) for what they cover.

## Architecture

```
MethaneLock/
├── README.md
├── docs/
│   ├── evidence-package.md      schema, field reference, hash rule
│   ├── limitations.md
│   └── validation.md
├── data/
│   ├── evidence/                pipeline output (real runs)
│   └── mock/                    synthetic demo packages, labelled MOCK
├── src/
│   ├── pipeline.py              fetch → baseline → anomaly → package, per demo region
│   ├── data/fetch_sentinel.py   Earth Engine retrieval, daily spatial means
│   ├── analysis/
│   │   ├── baseline.py          mean and sample std of the baseline period
│   │   ├── anomaly.py           z-score, threshold, severity bands
│   │   └── evidence_package.py  build, validate, canonical hash, save and load
│   ├── blockchain/
│   │   ├── config.py            settings from .env, secrets never printed
│   │   ├── registry.py          contract client
│   │   └── record.py            explicit record command
│   └── app/dashboard.py         Streamlit, read-only
├── contracts/
│   ├── MethaneRegistry.sol
│   └── script/Deploy.s.sol
├── tests/                       offline Python tests and Foundry tests
├── foundry.toml
├── requirements.txt
└── .env.example
```

**Contract.** `contracts/MethaneRegistry.sol` (Solidity 0.8.24, Ethereum Sepolia) records report hashes and nothing else: no token, no access control, no upgradeability, no marketplace.

- `recordAnomaly(bytes32 reportHash, string datasetId, string algorithmVersion)` records a hash once. A second call with the same hash reverts with `AlreadyRecorded(bytes32)`.
- `isRecorded(bytes32 reportHash) returns (bool)`
- `event AnomalyRecorded(bytes32 indexed reportHash, string datasetId, string algorithmVersion, uint256 timestamp, address submitter)`

Mapping from a package: `reportHash` ← `report_hash`, `datasetId` ← `dataset` (not `source_uri`), `algorithmVersion` ← `algorithm_version`.

## Tech stack

- Python 3: `earthengine-api` (Sentinel-5P access), `web3` (Sepolia), `python-dotenv`, `streamlit` (dashboard), `pytest`
- Solidity 0.8.24 and Foundry (contract and its tests)
- Data: Sentinel-5P OFFL L3 CH₄ via Google Earth Engine
- Network: Ethereum Sepolia testnet

## Project status

| Component | State |
|---|---|
| Data retrieval (Earth Engine) | implemented; tested offline with mocked Earth Engine |
| Baseline, z-score, severity | implemented and tested offline |
| Evidence Package and hash | implemented and tested offline (Python only; see open items in [docs/evidence-package.md](docs/evidence-package.md)) |
| Registry contract | implemented; `forge test` passes locally |
| Record command | implemented; tested offline with a mocked chain |
| Dashboard | implemented; works with mock or saved packages |
| Live Earth Engine run | done once (2026-10-19): two packages in `data/evidence/`, no anomaly flagged |
| **Sepolia deployment and first on-chain record** | done (2026-10-20): contract [`0xa2348898ac5548cFEfB9D2a07a4d2c352be3E9Ea`](https://sepolia.etherscan.io/address/0xa2348898ac5548cFEfB9D2a07a4d2c352be3E9Ea); the `turkmenistan_west_coast_og` package is recorded in transaction [`0xf180c1cb65e25686c6bf1fd78683d5716a26e62a16c3422da8acb6db6b74afe5`](https://sepolia.etherscan.io/tx/0xf180c1cb65e25686c6bf1fd78683d5716a26e62a16c3422da8acb6db6b74afe5); `isRecorded` returns true (checked with `cast call` and in the dashboard). The control package is not recorded |

The on-chain guarantees above are demonstrated for one record on a testnet. They say nothing about whether the analysis detects real anomalies: the live analysis rests on one observation per region, and neither was flagged.
