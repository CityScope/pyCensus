"""Loader for Taiwan's MOI RIS resident population, returning a common-schema GeoDataFrame.

Technical aspects:
    Population data (:mod:`pycensus.taiwan.api`) is real, keyless, and
    verified (see that module's docstring). Boundary geometry
    (:mod:`pycensus.taiwan.geography`) is implemented for ``county_city``
    (geoBoundaries.org's real Taiwan ADM1 layer), ``district``
    (geoBoundaries' real Taiwan ADM2 layer, matched to MOI RIS's
    district_code join key -- see
    :data:`pycensus.taiwan.constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE`
    for the verified derivation), and ``village`` (OpenStreetMap Overpass
    admin_level=9 relations, whose ``nat_ref`` tag IS MOI's own
    district_code -- verified against MOI's live village list on every
    fetch, see :mod:`pycensus.taiwan.geography` module docstring). NLSC's
    own official boundary files are cataloged real but their actual
    downloads are blocked by an HTTP 403 from TGOS, their file host
    (verified 2026-08-20), which is why ``geography`` uses these
    alternative real sources instead. :func:`load` works end-to-end for
    ``county_city``, ``district``, and ``village`` (pass explicit
    ``regions=`` for ``village`` -- there's no AOI auto-detection at that
    level yet, see ``regions`` below); ``nation`` still raises once it
    reaches :func:`pycensus.taiwan.geography.load_boundaries` -- expected
    and correct, not a bug: it fails loudly rather than fabricating
    geometry. (Aggregate ``county_city``-level population up to a national
    total in Python if needed -- :func:`_aggregate_to_level` supports it --
    rather than through a ``nation``-level geometry fetch, since no
    single-polygon national outline is verified/wired up here.)

    ``under18Population``/``adultPopulation``/``over65Population``/
    ``medianAge`` are computed from ODRP014's 101 real single-year-age
    buckets (:data:`pycensus.countries.taiwan.api.AGE_BUCKET_SUFFIXES`,
    top-coded at ``100up``). The three population splits are simple sums
    of age buckets and are additive across levels like any other count.
    ``medianAge`` is not additive -- averaging village-level medians would
    be wrong -- so it is instead computed once per requested level, after
    the age-bucket counts are themselves summed to that level (see
    :func:`_add_derived_age_columns`), directly from that level's own
    summed age distribution. Live-verified 2026-08-22: Taipei City's
    202 age-bucket columns sum exactly to ODRP013's ``people_total`` for
    Taipei (2,451,007, no discrepancy), and Taipei's resulting over-65
    share is 23.7% (580,555 / 2,451,007) -- plausible against Taipei's
    well-documented, unusually old age structure (Taiwan crossed the
    20%-"super-aged" threshold nationwide in 2025; Taipei's elderly share
    has been running several points above the national figure for years).

Source:
    MOI RIS ODRP013: https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/{yyymm}
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

_RAW_FILENAME_TEMPLATE = "resident_population_{yyymm}.json"
_RAW_HOUSEHOLDS_FILENAME_TEMPLATE = "village_households_{yyymm}.json"


def _raw_cache_path(yyymm: str, data_dir: Optional[str]) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "moi_ris"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / _RAW_FILENAME_TEMPLATE.format(yyymm=yyymm)


def _raw_households_cache_path(yyymm: str, data_dir: Optional[str]) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "moi_ris"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / _RAW_HOUSEHOLDS_FILENAME_TEMPLATE.format(yyymm=yyymm)


def _age_num(suffix: str) -> int:
    """``"017"`` -> 17, ``"100up"`` -> 100 (MOI's real top-coded bucket)."""
    return 100 if suffix == "100up" else int(suffix)


# Bucket-name lists used to build under18/adult/over65 totals -- split on
# the same 18/65 boundaries as global_schema.json's under18Population/
# adultPopulation/over65Population definitions.
_UNDER18_SUFFIXES = [s for s in api.AGE_BUCKET_SUFFIXES if _age_num(s) < 18]
_ADULT_SUFFIXES = [s for s in api.AGE_BUCKET_SUFFIXES if _age_num(s) >= 18]
_OVER65_SUFFIXES = [s for s in api.AGE_BUCKET_SUFFIXES if _age_num(s) >= 65]

# The combined (m+f) age-bucket column names carried through aggregation --
# these are what makes medianAge computable at any level: additive per-age
# counts, summed like any other count, with the median derived from the
# summed distribution *after* aggregation (not by averaging village
# medians, which would be wrong).
_AGE_TOTAL_COLS = [f"people_age_{suffix}_total" for suffix in api.AGE_BUCKET_SUFFIXES]


def _weighted_median_age(row: pd.Series) -> float:
    """Median age from a row's ``_AGE_TOTAL_COLS`` single-year-bucket counts.

    Standard discrete weighted median: walk buckets in age order, return
    the age at which the cumulative count first reaches half the total.
    The top bucket (``100up``) is treated as age 100 (MOI's own
    top-coding, not an approximation error).
    """
    total = row[_AGE_TOTAL_COLS].sum()
    if total <= 0:
        return float("nan")
    half = total / 2.0
    cum = 0.0
    for suffix in api.AGE_BUCKET_SUFFIXES:
        cum += row[f"people_age_{suffix}_total"]
        if cum >= half:
            return float(_age_num(suffix))
    return float(_age_num(api.AGE_BUCKET_SUFFIXES[-1]))


def _add_derived_age_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add under18_total/adult_total/over65_total/median_age from summed age buckets.

    Must run *after* the age-bucket counts have been summed to the target
    level (village/district/county_city/nation) -- under18/adult/over65
    are valid sums-of-sums, but median_age is only correct when computed
    from that level's own summed distribution, not by averaging
    lower-level medians.
    """
    if not all(c in df.columns for c in _AGE_TOTAL_COLS):
        return df
    df = df.copy()
    df["under18_total"] = df[[f"people_age_{s}_total" for s in _UNDER18_SUFFIXES]].sum(axis=1)
    df["adult_total"] = df[[f"people_age_{s}_total" for s in _ADULT_SUFFIXES]].sum(axis=1)
    df["over65_total"] = df[[f"people_age_{s}_total" for s in _OVER65_SUFFIXES]].sum(axis=1)
    df["median_age"] = df.apply(_weighted_median_age, axis=1)
    return df


def _fetch_all_villages(yyymm: str, data_dir: Optional[str]) -> pd.DataFrame:
    """Fetch (or read cached) the full nationwide village-level population table.

    Also merges in ODRP014's real ``household_no`` and 202 single-year-age
    fields (same ``district_code`` join key), computes ``indigenous_total``
    as the sum of ODRP013's real ``aborigine_plain_total_*``/
    ``aborigine_mountain_total_*`` fields, and combines each age bucket's
    ``_m``/``_f`` columns into one ``people_age_{suffix}_total`` column
    per :data:`api.AGE_BUCKET_SUFFIXES` -- see
    :mod:`pycensus.countries.taiwan.api` module docstring for the live
    verification of both source datasets.
    """
    village_df = api.fetch_resident_population(yyymm, raw_cache_path=_raw_cache_path(yyymm, data_dir))
    households_df = api.fetch_village_households(
        yyymm, raw_cache_path=_raw_households_cache_path(yyymm, data_dir)
    )
    village_df = village_df.merge(households_df, on="district_code", how="left")

    indig_cols = [
        "aborigine_plain_total_m",
        "aborigine_plain_total_f",
        "aborigine_mountain_total_m",
        "aborigine_mountain_total_f",
    ]
    village_df["indigenous_total"] = village_df[indig_cols].sum(axis=1)

    for suffix in api.AGE_BUCKET_SUFFIXES:
        m_col, f_col = f"people_age_{suffix}_m", f"people_age_{suffix}_f"
        if m_col in village_df.columns and f_col in village_df.columns:
            village_df[f"people_age_{suffix}_total"] = village_df[m_col] + village_df[f_col]

    return village_df


def _aggregate_to_level(village_df: pd.DataFrame, level: str, region: Optional[str]) -> pd.DataFrame:
    """Aggregate village-level population rows up to district/county_city/nation.

    Population fields are additive counts (``resampling_up: "sum"`` in
    ``schema.json``), so summing raw village rows by the requested level's
    ``district_code`` prefix reproduces the correct total. Single-year age
    buckets are summed the same way, then :func:`_add_derived_age_columns`
    turns the summed distribution into under18/adult/over65 totals and a
    real median age for that level.
    """
    df = village_df.copy()
    value_cols = [
        c
        for c in (
            "people_total",
            "people_total_m",
            "people_total_f",
            "household_no",
            "indigenous_total",
            *_AGE_TOTAL_COLS,
        )
        if c in df.columns
    ]

    if level == "village":
        out = df[["district_code", *value_cols]].rename(columns={"district_code": "GEOID"})
        if region:
            # region may be a full 11-digit village code, or a 5-/8-digit
            # county/district prefix requesting every village within it.
            out = out[out["GEOID"].str.startswith(region)]
        return _add_derived_age_columns(out)

    if level == "district":
        df["_key"] = df["district_code"].str[:8]
        if region:
            df = df[df["_key"].str.startswith(region[:5])] if len(region) == 5 else df[df["_key"] == region]
        grouped = df.groupby("_key", as_index=False)[value_cols].sum()
        return _add_derived_age_columns(grouped.rename(columns={"_key": "GEOID"}))

    if level == "county_city":
        df["_key"] = df["district_code"].str[:5]
        if region:
            df = df[df["_key"] == utils.county_code(region)]
        grouped = df.groupby("_key", as_index=False)[value_cols].sum()
        return _add_derived_age_columns(grouped.rename(columns={"_key": "GEOID"}))

    if level == "nation":
        totals = df[value_cols].sum()
        return _add_derived_age_columns(pd.DataFrame([{"GEOID": "TW", **totals.to_dict()}]))

    raise ValueError(f"Unsupported level for MOI RIS aggregation: '{level}'")


def _fetch_missing(
    missing_prefixed: List[str], level: str, region: str, yyymm: str, data_dir: Optional[str]
) -> pd.DataFrame:
    """Fetch and select just the logical columns in ``missing_prefixed``."""
    raw = _fetch_all_villages(yyymm, data_dir)
    aggregated = _aggregate_to_level(raw, level, region)

    result = pd.DataFrame({"GEOID": aggregated["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        raw_col = next((c for c in col_def.codes if c in aggregated.columns), None)
        if raw_col is None:
            result[prefixed_name] = pd.Series(dtype="float64", index=aggregated.index)
        else:
            result[prefixed_name] = pd.to_numeric(aggregated[raw_col], errors="coerce")
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "county_city",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load MOI RIS resident population data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if
            ``regions`` isn't given: at ``county_city`` level via
            :func:`pycensus.taiwan.geography.counties_in_aoi`, at
            ``district`` level via
            :func:`pycensus.taiwan.geography.districts_in_aoi`, and at
            ``village`` level via
            :func:`pycensus.taiwan.geography.villages_in_aoi` (all three
            have real boundary geometry, see
            :mod:`pycensus.taiwan.geography`).
        regions: Region code(s) matching ``level`` -- a 5-digit county/city
            code, 8-digit district code, or 11-digit village code (see
            :data:`pycensus.taiwan.constants.COUNTY_CODES`).
            ``regions`` is required today (see ``aoi`` above).
        level: Standard geometry level name. Taiwan supports ``nation``,
            ``county_city``, ``district``, ``village`` directly; other
            standard levels fall back via
            :data:`pycensus.taiwan.constants.LEVEL_FALLBACK`.
        year: ROC yyymm (e.g. ``"11407"``), or ``"latest"`` to use
            :data:`pycensus.taiwan.constants.LATEST_YEAR`.
        api_key: Not used -- MOI RIS's open-data API requires no API key.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Root directory for raw MOI downloads (separate from
            ``cache_dir``). Defaults to
            :data:`pycensus.taiwan.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``moi_``-prefixed
        column per logical column in :data:`pycensus.taiwan.moi.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
        NotImplementedError: If ``aoi`` is given without explicit
            ``regions`` at the ``nation`` level -- there's no boundary
            geometry to resolve an AOI against there (see
            :data:`pycensus.taiwan.geography.IMPLEMENTED_LEVELS`).
            ``county_city``, ``district``, and ``village`` all support AOI
            auto-detection.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="taiwan")
    yyymm = constants.LATEST_YEAR["census"] if year == "latest" else str(year)

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        if level == "district":
            regions = geography.districts_in_aoi(aoi, data_dir=data_dir)
        elif level == "county_city":
            regions = geography.counties_in_aoi(aoi, data_dir=data_dir)
        elif level == "village":
            regions = geography.villages_in_aoi(aoi, data_dir=data_dir)
        else:
            raise NotImplementedError(
                f"Cannot auto-detect 'regions' from 'aoi' at level '{level}' -- only "
                "'county_city', 'district', and 'village' have real boundary geometry "
                "to resolve an AOI against (see pycensus.taiwan.geography.IMPLEMENTED_LEVELS). "
                "Pass explicit 'regions=' instead."
            )
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = []
    for r in regions:
        if isinstance(r, str) and r.isdigit() and len(r) in (5, 8, 11):
            region_codes.append(r)
            continue
        region_codes.append(utils.county_code(r))

    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "taiwan", level, region_code)

        def fetch_boundary(region=region_code):
            return geography.load_boundaries(level, region, data_dir=data_dir)

        def fetch_columns(missing, region=region_code):
            return _fetch_missing(missing, level, region, yyymm, data_dir)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
                geometry="geometry",
                crs=4326,
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


def download_census_data(
    yyymm: Optional[str] = None,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Force a fresh download of MOI RIS's village-level population table to the raw cache.

    Args:
        yyymm: ROC year-month. Defaults to
            :data:`pycensus.taiwan.constants.LATEST_YEAR`.
        data_dir: Root directory for raw downloads.
        overwrite: If ``True``, delete the cached raw JSON file first so it
            is re-downloaded from MOI.

    Returns:
        Path to the raw cache file that was downloaded/refreshed.
    """
    yyymm = yyymm or constants.LATEST_YEAR["census"]
    raw_path = _raw_cache_path(yyymm, data_dir)
    if overwrite and raw_path.exists():
        raw_path.unlink()
    api.fetch_resident_population(yyymm, raw_cache_path=raw_path)
    return str(raw_path)


__all__ = ["load", "download_census_data"]
