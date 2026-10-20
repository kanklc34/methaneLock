# Validation

This page states what has been checked, how, and what has not.

## Summary

| Question | Status |
|---|---|
| Does the code implement the stated rules correctly? | Checked with offline tests on synthetic data |
| Does the pipeline run end to end on real data? | Yes, once (2026-10-19): two packages produced |
| Does the Evidence Package hash behave as specified? | Both live packages verify with the Python implementation; no independent implementation yet |
| Does the registry contract behave as specified? | Checked with Foundry tests (7 tests) |
| Does the method detect real methane anomalies? | **Not established.** One observation per region, and neither was flagged |
| Is anything recorded on Sepolia? | **Yes, one package** (`turkmenistan_west_coast_og`, 2026-10-20). `isRecorded` returns true. The control package is not recorded |

## Offline tests

Run `python -m pytest tests/ -q` for the Python tests and `forge test` for the contract. The Python tests use synthetic values, with Earth Engine and web3 mocked, so they need no network.

| Area | What is checked |
|---|---|
| Daily values | Images from one date are combined into one value |
| Observation day | Nearest valid day inside ±7 days; ties go to the earlier day; window edges; no valid day raises an error and nothing is substituted |
| Baseline | Mean and sample standard deviation (n − 1); days outside 2020–2022 ignored; fewer than 2 days or zero std raises an error |
| Z-score and severity | Formula; severity bands; anomaly decided by `abs(z) >= 2.5`; non-finite values rejected |
| Evidence Package | Schema; hash recomputation; canonical-form rules; key order does not change the hash; editing a value changes it; save and reload |
| Pipeline | End-to-end run on synthetic data; no output when no day lies in the window; exit codes |
| Blockchain client | Settings loading and secret redaction; Sepolia-only; correct argument mapping; duplicate and wrong-chain refusals; tampered package refused before any network call |
| Contract (Foundry) | Record then `isRecorded`; event contents; submitter; duplicate reverts, including from another sender; different hashes are independent |
| Dashboard logic | Mock packages valid; anomaly from `z_score` and `threshold`, not severity; tampering detected; unreadable files skipped; transaction hash handling; on-chain query disabled without settings and free of endpoint details in errors |

These tests show that the code does what the specification says. They do not show that the specification is a good detector.

## Live run (2026-10-19)

The pipeline was run once against Google Earth Engine (`COPERNICUS/S5P/OFFL/L3_CH4`) with the fixed parameters: baseline 2020-01-01 to 2022-12-31, target date 2023-08-15, threshold 2.5. The packages are in `data/evidence/`.

| | A: `turkmenistan_west_coast_og` | C: `control_low_activity_demo` |
|---|---|---|
| **Package** | `data/evidence/turkmenistan_west_coast_og_2023-08-08.json` | `data/evidence/control_low_activity_demo_2023-08-08.json` |
| `observation_date` | 2023-08-08 (target 2023-08-15) | 2023-08-08 (target 2023-08-15) |
| `methane_value` (ppb) | 1953.02 | 1924.10 |
| Baseline mean ± std (ppb) | 1935.92 ± 15.62 | 1916.20 ± 13.67 |
| `z_score` | 1.094 | 0.578 |
| `severity_flag` | none | none |
| Anomaly (`abs(z) >= 2.5`) | no | no |
| `report_hash` | `dd498a3b25dd7485bac337792ceab2aff0a739c384bc099d8aa236132d18c6aa` | `b8f324584f62e54c820872007dc6feeed7689eb7497b37d456e0abce15be969d` |
| `generated_at` (UTC) | 2026-10-19T06:29:08 | 2026-10-19T06:29:48 |
| `git_commit` | `019c8fb270366ecaf5a0361a0ca2164341ca4141` | `019c8fb270366ecaf5a0361a0ca2164341ca4141` |
| Integrity check | schema valid, hash matches | schema valid, hash matches |
| On-chain record | recorded in transaction `0xf180c1cb65e25686c6bf1fd78683d5716a26e62a16c3422da8acb6db6b74afe5` (contract `0xa2348898ac5548cFEfB9D2a07a4d2c352be3E9Ea`) | none |

### What this shows

- The pipeline runs end to end on real data and produces packages that pass schema and hash checks.
- Neither region exceeded the threshold. This is a valid result and is reported as it came out. Parameters were not changed after seeing it.

### What this does not show

- It does not show that the method detects real emissions, and it does not show that it fails to. A single observation per region cannot do either.
- The control result is not a calibration. One unflagged control day says little about the false-positive rate.
- Both z-scores are positive. That is compatible with the missing seasonal and trend correction described in [limitations.md](limitations.md), but two values cannot confirm it.
- The observation day was 2023-08-08 in both regions, seven days before the target and at the edge of the ±7 day window. No valid day was closer. The nearest-day rule prefers the earlier date in a tie, so 2023-08-22 may be equally distant. The cause of the gap was not investigated.

## Mock packages (illustration only)

`data/mock/` holds two synthetic packages used for offline demonstration. Their values were chosen by hand to exercise the rules (one flagged result, one unflagged, and an observation date that differs from the target). They are not measurements. Their `qa_note` starts with "MOCK DATA" and their `git_commit` is all zeros.

| | A (mock) | C (mock) |
|---|---|---|
| `observation_date` | 2023-08-15 | 2023-08-14 |
| `methane_value` (ppb) | 1925.0 | 1881.5 |
| Baseline mean ± std (ppb) | 1880.0 ± 12.0 | 1878.0 ± 11.0 |
| `z_score` | 3.750 | 0.318 |
| `severity_flag` | medium | none |
| Anomaly (`abs(z) >= 2.5`) | yes | no |

## What remains to be checked

1. **Spot check against Earth Engine.** Compute one daily spatial mean for one box by hand in the Earth Engine Code Editor and compare it with the pipeline value.
2. **Independent hash.** Reproduce one package's `report_hash` with a second implementation (for example in another language) from the specification alone.
3. **Observation day.** Find out why no valid day lies closer than seven days to the target date in either box.
4. **Contract-level duplicate revert on Sepolia.** The round trip is done for one package (deployed, recorded, `isRecorded` true with `cast call` and in the dashboard). Running the record command again for the same package on 2026-10-20 printed "already recorded on this contract. Nothing was sent.": the command checks `isRecorded` before sending, so the contract's own `AlreadyRecorded` revert was not triggered on Sepolia. That revert is covered by the Foundry tests only.
