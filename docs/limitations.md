# Limitations

This page lists what MethaneLock does not do and where its results can mislead. It describes the MVP as implemented. Nothing here is a plan.

## Status of the results

- **One live run.** The Earth Engine pipeline has been run once on real data (2026-10-19). Its two packages are in `data/evidence/`, and neither is flagged as an anomaly. Packages in `data/mock/` are synthetic: their `qa_note` begins with "MOCK DATA" and their `git_commit` is all zeros.
- **No on-chain record yet.** The contract has not been deployed to Sepolia and no hash has been recorded. The guarantees in the README describe the design.
- **Mock versus real in the dashboard.** The dashboard labels the source it reads from. Packages in `data/mock/` pass the integrity check like any other package, because their hash is valid. A passing check means "unchanged", not "real".

## Data and resolution

- **Footprint.** TROPOMI's ground footprint is about 7 × 7 km, and about 5.5 × 7 km since August 2019 (NASA GES DISC product description). The Earth Engine product is gridded finer (the code uses a 1113.2 m reduction scale taken from the catalog), but gridding does not add information. The effective resolution is the sensor footprint.
- **Large boxes.** Each demo bounding box is roughly 130–145 km across, so a mean covers several hundred footprints. A localized plume is averaged with a large background. The method can reflect broad regional deviations only. It cannot locate or identify a facility.
- **Partial coverage.** Each image is one orbit's grid, and coverage of a box varies by day. A day value is the mean over whichever pixels are valid that day, so different parts of the box are sampled on different days. This adds day-to-day variation unrelated to emissions. In a smoke test, per-orbit values for box A on 2023-08-01 ranged from about 1941 to 1972 ppb, a spread of roughly twice the baseline standard deviation of the daily means (15.62 ppb).
- **Equal image weights.** Images from the same date are combined by an unweighted mean of image means. Pixel counts are not used.
- **No quality filter.** The dataset has per-pixel validity information. This MVP does not use it, and the `qa_note` field says so. Cloud, surface and retrieval effects are not handled. Only pixels already masked by the dataset are excluded.
- **Data versions.** The package stores the asset ID but not the image IDs, and the source dataset can be reprocessed. Re-running the pipeline later may give a different value, and therefore a different hash, for the same date.

## Method

- **Pooled baseline.** The baseline mean and standard deviation come from all valid daily values in 2020–2022, with no seasonal and no long-term trend correction. Atmospheric methane has been rising and has a seasonal cycle, so an August 2023 value can sit above the baseline for reasons unrelated to local emissions. The control area C exists to show how large this effect is. In the first live run both z-scores are positive (1.094 in A, 0.578 in C), which is compatible with this effect, but one observation per region cannot separate it from chance.
- **One observation.** The result rests on a single day, the nearest valid day to 2023-08-15 within ±7 days. There is no check that a deviation persists. `observation_date` can differ from the target date.
- **Normality assumed.** A z-score is easiest to interpret for roughly normal, independent values. Daily satellite values are neither strictly. For a normal distribution, `|z| >= 2.5` happens by chance about 1.2% of the time (about 1 in 80). The real false-positive rate here is unknown.
- **False negatives.** A real but small or local emission will not move a box-wide mean. Absence of a flag says nothing about whether emissions occurred.
- **Two-sided rule.** `|z| >= 2.5` also flags unusually low values. The registry's name suggests enhancements, but the rule does not distinguish direction. The sign of `z_score` is in the package.
- **Severity is not a decision.** `severity_flag` describes magnitude only. A `low` flag with `|z|` below 2.5 is not an anomaly.
- **Observation day.** Both live packages use 2023-08-08, seven days before the 2023-08-15 target (the edge of the ±7 day window): no valid day was closer. The nearest-day rule breaks ties toward the earlier date, so 2023-08-22 may be equally distant. The cause of the gap was not investigated. The result describes one day, which may not be representative of the target date.
- **Fixed scenario.** Parameters (baseline, target date, threshold) are fixed. There is no sensitivity analysis.
- **Scenario choice.** Regions A and C were chosen as demo scenarios. They have not been compared with independent emission records.

## Evidence Package and hash

- **Python-only hash.** The hash rule is implemented and tested in Python only. No independent implementation has reproduced it yet (open item 1 in [evidence-package.md](evidence-package.md)).
- **Commit tracking.** `git_commit` records HEAD only. Uncommitted changes are not captured (open item 2).
- **Threshold value.** Schema validation checks that `threshold` is a finite number, not that it equals 2.5. The dashboard shows a warning when it differs (open item 4).
- **Package scope.** The hash covers the package content. It says nothing about the satellite data behind it.

## Blockchain

- **Hash only.** The contract stores whether a hash was recorded. The package must be kept and shared separately.
- **No access control.** Anyone can record any hash. A record does not show who produced the package or that it came from this pipeline. The submitter address is in the event log.
- **No removal.** A recorded hash cannot be withdrawn. A corrected package has a different hash and would be a separate record.
- **Time.** The block timestamp shows the hash existed by that time. It does not show when the analysis was run or when the data was observed.
- **Testnet.** Sepolia has no lasting economic security and testnets can be reset or retired. It is suitable for a demonstration, not for a durable record.
- **Transaction links in the dashboard.** The record command writes an optional `<package name>.tx.json` file next to the package after a successful record. The dashboard shows the hash from that file or a hash pasted by the user. It does not check what that transaction recorded. Only the `isRecorded` query checks the hash against the contract.

## Security notes

- `.env` holds a private key for a testnet account. Use a dedicated testnet account with test funds only. The code never prints the key or the RPC URL, but keeping `.env` out of version control is the user's responsibility.
