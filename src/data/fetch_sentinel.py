"""
Sentinel-5P OFFL CH4 retrieval (Steps 2-3).

Scope: daily spatial-mean CH4 over a bounding box, from Google Earth Engine.
This module does not compute baselines, z-scores, Evidence Packages or
blockchain records.

Authentication
--------------
Method: Earth Engine user credentials (browser OAuth). No service-account key
file is used or stored in this repository.

One-time setup on the machine:
    earthengine authenticate

Project: read from GEE_PROJECT_ID in .env and passed to
ee.Initialize(project=...). Copy .env.example to .env and fill it in first.

Data
----
Collection   COPERNICUS/S5P/OFFL/L3_CH4
Band         CH4_column_volume_mixing_ratio_dry_air
             Column-averaged dry-air mixing ratio of methane. The GEE catalog
             lists its unit as ppb, so no unit conversion is applied.
Pixel size   1113.2 m (catalog), used as the reduction scale.
Revisit      About 2 days (catalog). Each image is one orbit's grid, so coverage
             of a given bbox varies by date. Images with no valid pixel inside
             the bbox are skipped.
QA           No pixel-level QA/validity filter is applied in this MVP (decided).
             The qa_note field of the Evidence Package states this.

Image-level and day-level values
--------------------------------
fetch_daily_means returns one value per image (spatial mean over the bbox).
fetch_daily_series combines images of the same date by arithmetic mean
(each image weighted equally, pixel counts not used).

Usage
-----
    from src.data.fetch_sentinel import init_earth_engine, fetch_daily_series

    init_earth_engine()
    days = fetch_daily_series([53.2, 38.4, 54.8, 39.6], "2023-08-08", "2023-08-22")

Run the raw-data demo from the repository root:
    python -m src.data.fetch_sentinel
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

import ee
from dotenv import load_dotenv

COLLECTION_ID = "COPERNICUS/S5P/OFFL/L3_CH4"
PREFERRED_BAND = "CH4_column_volume_mixing_ratio_dry_air"
SOURCE_UNIT = "ppb"
NATIVE_SCALE_M = 1113.2
MAX_PIXELS = 1e8

# Demo regions, fixed by the project spec.
DEMO_REGIONS = {
    "turkmenistan_west_coast_og": [53.2, 38.4, 54.8, 39.6],  # Scenario A
    "control_low_activity_demo": [56.0, 39.5, 57.5, 40.8],   # Scenario C
}


class GEEAuthError(RuntimeError):
    """Earth Engine could not be initialised."""


class NoDataError(RuntimeError):
    """No valid CH4 observation for the requested bbox and dates. No value is substituted."""


@dataclass(frozen=True)
class CH4Observation:
    date: str        # YYYY-MM-DD, date of the source image
    mean_ppb: float  # spatial mean of the band over the bbox, this image only
    band: str        # band actually used
    unit: str        # always "ppb"
    image_id: str    # Earth Engine system:index, for traceability


@dataclass(frozen=True)
class DailyCH4:
    date: str                 # YYYY-MM-DD
    mean_ppb: float           # arithmetic mean of the valid image means on this date
    band: str
    unit: str                 # always "ppb"
    image_ids: tuple[str, ...]


def validate_bbox(bbox) -> tuple[float, float, float, float]:
    """Check [min_lon, min_lat, max_lon, max_lat] and return it as floats."""
    if len(bbox) != 4:
        raise ValueError("bbox must have 4 values: [min_lon, min_lat, max_lon, max_lat]")
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    if not (-180 <= min_lon < max_lon <= 180):
        raise ValueError(f"Invalid longitude range in bbox: {bbox}")
    if not (-90 <= min_lat < max_lat <= 90):
        raise ValueError(f"Invalid latitude range in bbox: {bbox}")
    return min_lon, min_lat, max_lon, max_lat


def validate_dates(start: str, end: str) -> tuple[date, date]:
    """Parse YYYY-MM-DD strings and check that start <= end."""
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Dates must be YYYY-MM-DD strings, got {start!r} and {end!r}") from exc
    if end_d < start_d:
        raise ValueError(f"end date {end} is before start date {start}")
    return start_d, end_d


def init_earth_engine() -> None:
    """Initialise Earth Engine with user credentials and GEE_PROJECT_ID from .env."""
    load_dotenv()
    project = os.getenv("GEE_PROJECT_ID", "").strip()
    if not project:
        raise GEEAuthError("GEE_PROJECT_ID is not set. Copy .env.example to .env and fill it in.")
    try:
        ee.Initialize(project=project)
    except Exception as exc:  # the ee client raises several exception types
        raise GEEAuthError(
            "Earth Engine initialisation failed. Run `earthengine authenticate` once, "
            "check that GEE_PROJECT_ID is a Cloud project registered for Earth Engine, "
            f"then retry. Original error: {exc}"
        ) from exc


def _resolve_band(collection: ee.ImageCollection) -> str:
    """Return PREFERRED_BAND if present; otherwise the single CH4 mixing-ratio band."""
    names = collection.first().bandNames().getInfo()
    if PREFERRED_BAND in names:
        return PREFERRED_BAND
    candidates = [
        n for n in names
        if "CH4" in n and "mixing_ratio" in n and not n.endswith("_validity")
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(
        f"Band {PREFERRED_BAND!r} not found and no unique CH4 mixing-ratio fallback. "
        f"Available bands: {names}"
    )


def fetch_daily_means(bbox, start: str, end: str) -> list[CH4Observation]:
    """
    Return one spatial-mean CH4 value (ppb) per source image in [start, end]
    (both inclusive) whose footprint intersects bbox and that has valid pixels inside it.

    Raises NoDataError if no valid observation is found.
    """
    min_lon, min_lat, max_lon, max_lat = validate_bbox(bbox)
    start_d, end_d = validate_dates(start, end)
    geom = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])

    base = (
        ee.ImageCollection(COLLECTION_ID)
        .filterDate(start_d.isoformat(), (end_d + timedelta(days=1)).isoformat())  # end exclusive
        .filterBounds(geom)
    )
    if base.size().getInfo() == 0:
        raise NoDataError(
            f"No {COLLECTION_ID} images for bbox {bbox} between {start} and {end}. "
            "Widen the date range or check the bbox."
        )

    band = _resolve_band(base)
    col = base.select(band)

    def _tag(img):
        img = ee.Image(img)
        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=NATIVE_SCALE_M,
            maxPixels=MAX_PIXELS,
        )
        return img.set({
            "mean_ppb": stats.get(band),
            "obs_date": img.date().format("YYYY-MM-dd"),
        })

    tagged = col.map(_tag)
    try:
        table = ee.Dictionary({
            "mean_ppb": tagged.aggregate_array("mean_ppb"),
            "obs_date": tagged.aggregate_array("obs_date"),
            "image_id": tagged.aggregate_array("system:index"),
        }).getInfo()
    except ee.EEException as exc:
        raise RuntimeError(f"Earth Engine request failed: {exc}") from exc

    observations = []
    for value, obs_date, image_id in zip(table["mean_ppb"], table["obs_date"], table["image_id"]):
        if value is None:  # no valid pixels inside the bbox on this image
            continue
        observations.append(CH4Observation(
            date=obs_date,
            mean_ppb=float(value),
            band=band,
            unit=SOURCE_UNIT,
            image_id=image_id,
        ))

    if not observations:
        raise NoDataError(
            f"Images exist for bbox {bbox} between {start} and {end}, but none has valid "
            "CH4 pixels inside the bbox. Try a different date range."
        )
    observations.sort(key=lambda o: (o.date, o.image_id))
    return observations


def fetch_daily_series(bbox, start: str, end: str) -> list[DailyCH4]:
    """
    One value per date with at least one valid image: the arithmetic mean of the
    image-level spatial means for that date. Dates are inclusive of start and end.
    """
    images = fetch_daily_means(bbox, start, end)
    by_date: dict[str, list[CH4Observation]] = {}
    for o in images:
        by_date.setdefault(o.date, []).append(o)

    days = []
    for day in sorted(by_date):
        group = by_date[day]
        days.append(DailyCH4(
            date=day,
            mean_ppb=statistics.fmean(o.mean_ppb for o in group),
            band=group[0].band,
            unit=SOURCE_UNIT,
            image_ids=tuple(o.image_id for o in group),
        ))
    return days


def select_observation_day(days: list[DailyCH4], target: str, window_days: int) -> DailyCH4:
    """
    Pick the valid day closest to `target`, searching +/- window_days (inclusive).
    If two days are equally close, the earlier date is used.
    Raises NoDataError if no valid day lies inside the window. No value is substituted.
    """
    target_d = date.fromisoformat(target)
    scored = []
    for d in days:
        offset = abs((date.fromisoformat(d.date) - target_d).days)
        if offset <= window_days:
            scored.append((offset, d.date, d))
    if not scored:
        raise NoDataError(
            f"No valid CH4 day within +/-{window_days} days of {target}. No value was substituted."
        )
    return min(scored, key=lambda t: (t[0], t[1]))[2]


def main() -> None:
    init_earth_engine()
    start, end = "2023-08-01", "2023-08-31"
    for region_id, bbox in DEMO_REGIONS.items():
        print(f"\n{region_id}  bbox={bbox}  window={start}..{end}")
        try:
            observations = fetch_daily_means(bbox, start, end)
        except NoDataError as exc:
            print(f"  NO DATA: {exc}")
            continue
        for o in observations:
            print(f"  {o.date}  {o.mean_ppb:8.2f} {o.unit}  band={o.band}  image={o.image_id}")


if __name__ == "__main__":
    main()
