# Evidence Package Specification

Version 1.0. `schema_version` is `"1.0"`, `algorithm` is `"zscore-v1"`, `algorithm_version` is `"1.0.0"`.

## Purpose

An Evidence Package is the complete, machine-readable record of one analysis result. Its `report_hash` is a SHA-256 digest of the rest of the package. Anyone holding a package can recompute the digest and compare it with the hash stored on the Sepolia testnet. If the two match, the package has not changed since it was registered.

The package makes the analysis verifiable. It does not establish that the measured anomaly is real, that it has a particular cause, or that it comes from a particular facility. See the README section "What the blockchain guarantees and does not guarantee" and [limitations.md](limitations.md).

## Schema

The block below is the template. Placeholders on the right-hand side are replaced with concrete values in the real file.

```json
{
  "schema_version": "1.0",
  "dataset": "Sentinel-5P OFFL CH4",
  "source_uri": "COPERNICUS/S5P/OFFL/L3_CH4",
  "observation_date": "YYYY-MM-DD",
  "location": {
    "lat": number,
    "lon": number,
    "region_id": "string",
    "bbox": [min_lon, min_lat, max_lon, max_lat]
  },
  "methane_value": number,
  "unit": "ppb",
  "baseline_period": { "start": "2020-01-01", "end": "2022-12-31" },
  "baseline_mean": number,
  "baseline_std": number,
  "z_score": number,
  "threshold": 2.5,
  "qa_note": "string",
  "algorithm": "zscore-v1",
  "algorithm_version": "1.0.0",
  "git_commit": "string",
  "generated_at": "ISO-8601",
  "severity_flag": "none|low|medium|high",
  "report_hash": "sha256-hex"
}
```

## Source data

- Collection: `COPERNICUS/S5P/OFFL/L3_CH4` (Sentinel-5P OFFL, Google Earth Engine).
- Band: `CH4_column_volume_mixing_ratio_dry_air`, the column-averaged dry-air mixing ratio of methane. This is the preferred band. The GEE catalog lists its unit as ppb.
- Band fallback: if the preferred band is missing from the collection, the code uses the single band whose name contains `CH4` and `mixing_ratio` and does not end in `_validity`. If there is no unique match, the code fails and lists the available bands. The band actually used is stored with each observation and named in `qa_note`.
- Unit: `ppb`. No conversion is applied. Any future conversion must be stated in `qa_note`.
- Reduction scale: 1113.2 m, the native pixel size listed in the catalog.
- Image-level value: arithmetic mean of the valid pixels inside `bbox` for one image, as returned by the Earth Engine reducer. Pixels masked by the dataset are excluded.
- Revisit: about 2 days, per the catalog. Each image is one orbit's grid, so coverage of a given bbox varies by date. Images with no valid pixels inside the bbox are skipped.
- Pixel-level QA: no QA/validity filter is applied in this MVP. The `qa_note` field states this.

## Daily value and observation date

- Day value: all valid image-level values for the same date are combined by arithmetic mean. Each image counts equally; pixel counts are not used. A day is valid if at least one image on that date is valid.
- Target: 2023-08-15.
- Window: valid days within ±7 days of the target, that is 2023-08-08 to 2023-08-22 inclusive.
- Selection: the valid day with the smallest absolute offset from the target is used. If two days are equally close, the earlier date is used.
- `observation_date` is the actual date of the selected day, not the target.
- If no valid day lies inside the window, the pipeline stops with an error and no package is produced. No value is substituted.
- `methane_value` is the day value of the selected day.

## Baseline

- Period: 2020-01-01 to 2022-12-31.
- Series: the valid day values inside the period, defined as above.
- `baseline_mean`: arithmetic mean of the series.
- `baseline_std`: sample standard deviation of the series, denominator n − 1.
- The baseline requires at least 2 valid days and a standard deviation greater than 0. Otherwise the pipeline stops with an error and no package is produced.

## Field reference

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Schema version. Currently `"1.0"`. |
| `dataset` | string | Human-readable dataset name. |
| `source_uri` | string | Google Earth Engine asset ID of the source data. |
| `observation_date` | string, `YYYY-MM-DD` | Actual date of the observation used. Lies within ±7 days of 2023-08-15 (see Daily value and observation date). |
| `location.lat`, `location.lon` | number | Centre of `bbox`: `lat = (min_lat + max_lat) / 2` and `lon = (min_lon + max_lon) / 2`. |
| `location.region_id` | string | Demo region identifier. |
| `location.bbox` | array of 4 numbers | `[min_lon, min_lat, max_lon, max_lat]`. The area over which the spatial mean is taken. |
| `methane_value` | number | Day value on `observation_date`, in ppb. |
| `unit` | string | Always `"ppb"`. |
| `baseline_period` | object | Baseline start and end dates, fixed at 2020-01-01 to 2022-12-31. |
| `baseline_mean` | number | Arithmetic mean of the valid daily values in the baseline period, in ppb. |
| `baseline_std` | number | Sample standard deviation (n − 1) of the valid daily values in the baseline period, in ppb. |
| `z_score` | number | `(methane_value − baseline_mean) / baseline_std`. |
| `threshold` | number | Anomaly cutoff, fixed at 2.5. A result is an anomaly when the absolute value of `z_score` is at least this value. |
| `qa_note` | string | Fixed sentence "No pixel-level QA/validity filter applied in this MVP. Result is spatial mean over available pixels in bbox.", followed by the band used and the unit statement. Mock packages begin with "MOCK DATA" (see Mock packages). |
| `algorithm` | string | Always `"zscore-v1"`. |
| `algorithm_version` | string | `"1.0.0"`. |
| `git_commit` | string | HEAD commit of the repository at generation time. Generation fails if no commit can be read. |
| `generated_at` | string, ISO-8601 | UTC creation time of the package. |
| `severity_flag` | enum | `none`, `low`, `medium` or `high`, describing the magnitude of the absolute value of `z_score`. Does not by itself mark an anomaly (see below). |
| `report_hash` | string, 64 hex characters | SHA-256 of the canonical form (see Hash rule). |

## Anomaly decision and severity

An observation is an anomaly when the absolute value of `z_score` is at least `threshold`, which is 2.5.

Severity bands, by the absolute value of `z_score`:

| Absolute value of `z_score` | `severity_flag` |
|---|---|
| below 2.0 | `none` |
| 2.0 up to below 3.0 | `low` |
| 3.0 up to below 4.0 | `medium` |
| 4.0 or above | `high` |

The two rules are independent. A result with an absolute z-score between 2.0 and 2.5 receives `severity_flag` `low` but is not an anomaly, because it is below the threshold. The rule is two-sided: it uses the absolute value, so a large negative `z_score` is also an anomaly. Anyone reading an Evidence Package must check `threshold` and `z_score` together with `severity_flag`. The flag alone is not an anomaly decision.

## Hash rule

1. Take the complete Evidence Package object.
2. Remove the `report_hash` key entirely, meaning the key and its value.
3. Serialize the remaining object with:

   `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`

   - Keys are sorted alphabetically at every nesting level.
   - The separators contain no spaces, so the output is compact.
   - Non-ASCII characters are escaped as `\uXXXX`, so the output contains only ASCII characters.
   - Floats use the default `json` output, with no extra formatting or rounding.
   - `NaN`, `Infinity` and `-Infinity` raise an error. A package containing them is never produced.
   - Array order is preserved.
4. Encode the resulting string as UTF-8 bytes. Because the output is ASCII-only, these bytes equal the ASCII bytes.
5. Compute SHA-256 and write the lowercase hex digest into `report_hash`.

Verification uses the same steps. If the recomputed digest equals `report_hash`, and that digest equals the value recorded on the testnet, the package is unchanged since registration.

## File format

The saved file is pretty-printed JSON (indent 2, ASCII) at `data/evidence/<region_id>_<observation_date>.json`. The hash is computed on the canonical form, not on the file bytes, so whitespace in the file does not affect verification. After saving, the pipeline reloads the file and verifies its hash.

## Mock packages

`data/mock/` holds two synthetic packages (scenarios A and C) for offline demonstration. They use the same schema and a valid hash, so they pass verification. They are marked in two ways: `qa_note` begins with "MOCK DATA for offline dashboard demo, not derived from Sentinel-5P." before the fixed sentence, and `git_commit` is 40 zeros. Their values are not measurements. The pipeline never writes to this directory, and real packages go to `data/evidence/`.

## On-chain record

`src/blockchain/record.py` records a saved package on MethaneRegistry (Sepolia). The mapping is:

- `reportHash` ← `report_hash`, as bytes32 with a `0x` prefix
- `datasetId` ← `dataset` (for example `Sentinel-5P OFFL CH4`). `source_uri` is not sent.
- `algorithmVersion` ← `algorithm_version` (for example `1.0.0`)

Before any transaction, the command checks the schema, recomputes `report_hash`, confirms that the RPC chain id is 11155111 and that `CONTRACT_ADDRESS` holds contract code, and checks `isRecorded`. A hash that is already recorded is not sent again. The on-chain record shows that a hash was registered at a given block time. It does not show that the anomaly is real. The command prints the transaction hash but does not save it. The dashboard can read it from an optional `<package name>.tx.json` file next to the package, containing `{"tx_hash": "0x..."}`.

## Open items

These points are not decided. They must be resolved before the step that depends on them.

1. **Cross-implementation hash check.** The hash rule is implemented and tested in Python only. An independent implementation must reproduce the same digest for the same package before independent verification is claimed.
2. **Uncommitted changes.** `git_commit` records the HEAD commit only. Uncommitted changes are not captured. It is undecided whether generation should refuse to run on a dirty working tree.
3. **Confirmation of implementation choices.** The following choices are implemented as described above and remain in effect until changed explicitly: the baseline uses day-level values, the standard deviation is the sample standard deviation (n − 1), and a tie in the observation window goes to the earlier date.
4. **Threshold value not enforced.** Schema validation checks that `threshold` is a finite number but not that it equals 2.5. The dashboard warns when a package carries a different value. It is undecided whether validation should reject it.
