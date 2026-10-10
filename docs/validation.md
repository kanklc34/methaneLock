# Validation

This page states what has been checked, how, and what has not.

## Summary

| Question | Status |
|---|---|
| Does the code implement the stated rules correctly? | Checked with offline tests on synthetic data |
| Does the Evidence Package hash behave as specified? | Checked in Python only; no independent implementation yet |
| Does the registry contract behave as specified? | Checked with Foundry tests (7 tests) |
| Does the method detect real methane anomalies? | **Not checked.** No live data has been analysed |
| Is anything recorded on Sepolia? | **No** |

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

## Scenario table

Scenario A is the main demo area and C is the control. The mock rows are the packages in `data/mock/`. Their values were chosen by hand to exercise the rules (one clear anomaly, one clear non-anomaly, and an observation date that differs from the target). They are not measurements.

| | A: `turkmenistan_west_coast_og` | C: `control_low_activity_demo` |
|---|---|---|
| **Mock package** | `data/mock/turkmenistan_west_coast_og_2023-08-15.json` | `data/mock/control_low_activity_demo_2023-08-14.json` |
| `observation_date` | 2023-08-15 | 2023-08-14 |
| `methane_value` (ppb) | 1925.0 | 1881.5 |
| Baseline mean ± std (ppb) | 1880.0 ± 12.0 | 1878.0 ± 11.0 |
| `z_score` | 3.750 | 0.318 |
| `severity_flag` | medium | none |
| Anomaly (`abs(z) >= 2.5`) | yes | no |
| `report_hash` | `20d93a0c0e20bd94c7bfea604226a6275caa35f09ece0ed6c473842553526f80` | `9212a7db42220286571b224b386e6c03080adc0d399424ec7f16def4777b8c2b` |
| **Live Earth Engine result** | pending | pending |
| **On-chain record** | none | none |

The live rows will be filled in with whatever the pipeline returns. A non-anomaly in A, or an anomaly in C, is a valid outcome and will be reported as it is. An anomaly in C would point to the baseline limitations described in [limitations.md](limitations.md), such as the missing seasonal and trend correction.

## What remains to be checked

1. **Live run.** Run `python -m src.pipeline` and record the real results for A and C in the table above, including `baseline_std`, `observation_date` and the number of baseline days.
2. **Spot check against Earth Engine.** Compute one daily spatial mean for one box by hand in the Earth Engine Code Editor and compare it with the pipeline value.
3. **Independent hash.** Reproduce one package's `report_hash` with a second implementation (for example in another language) from the specification alone.
4. **On-chain round trip.** Deploy to Sepolia, record one package, confirm `isRecorded` returns true in the dashboard, and confirm a second attempt to record the same package is refused.
