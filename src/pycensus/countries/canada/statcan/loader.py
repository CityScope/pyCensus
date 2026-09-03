"""Loader for StatCan 2021 Census Population and Dwelling Counts, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.mexico.inegi.loader`'s shape: reads as much as
    possible from pyCensus' parquet cache (:mod:`pycensus.cache`),
    fetching only the logical columns actually missing. Like Mexico,
    StatCan's Full Table Download has no per-region query -- the whole
    Census Profile table (PID 98-10-0002) is downloaded once and cached
    on disk (:mod:`pycensus.canada.api`) the first time any column is
    requested, then every subsequent request is served from that file.

    ``province``, ``municipality``, ``dissemination-area``, and
    ``dissemination-block`` levels are implemented. Dissemination-area
    population comes from a separate, companion Full Table Download cube
    (PID 98-10-0015 -- 98100002 stops at the census-subdivision level) --
    see :func:`pycensus.canada.api.fetch_dissemination_area_totals`.
    Dissemination-block population comes from a different source again --
    the 2021 Geographic Attribute File (catalogue 92-151-X), StatCan's
    finest unit is not part of the Full Table Download cube family -- see
    :func:`pycensus.canada.api.fetch_block_totals`. This was live-verified
    2026-08-22 to be real per-block population/dwelling *counts*, not a
    populated/unpopulated boolean flag: summing the GAF's DB-level
    population over every one of Toronto's 3,743 real dissemination areas
    exactly reproduces PID 98-10-0015's own published DA-level population
    (0 mismatches across all 3,743 DAs), and the grand total across all
    matched Toronto blocks (2,794,356) exactly matches the City of
    Toronto's published CSD population. Spot-checked individually across
    4 different Toronto neighborhoods (downtown core DA 35204609,
    North York DA 35204196, Scarborough DA 35203712, Etobicoke DA
    35201868) -- each DA's block-level population sum matched its
    official DA-level population exactly.

Source:
    StatCan 2021 Census: https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import api, constants, geography
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

_FETCH_TOTALS_NAMES = {
    "province": "fetch_province_totals",
    "municipality": "fetch_municipality_totals",
    "dissemination-area": "fetch_dissemination_area_totals",
    "dissemination-block": "fetch_block_totals",
}


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    province: str,
    data_dir: Optional[str],
) -> pd.DataFrame:
    """Fetch and select just the logical columns in ``missing_prefixed`` from the Census Profile table."""
    fetch_name = _FETCH_TOTALS_NAMES.get(level)
    if fetch_name is None:
        raise ValueError(
            f"StatCan attribute data for level '{level}' is not implemented -- only "
            f"{sorted(_FETCH_TOTALS_NAMES)} are wired up (see pycensus.canada.api module docstring)."
        )
    # Looked up dynamically (not bound at import time) so tests can
    # monkeypatch pycensus.canada.api.fetch_province_totals/etc.
    fetch_totals = getattr(api, fetch_name)

    raw = fetch_totals(province, data_dir)
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]

    # Census-subdivision real workplace-located jobs (distinct from
    # residence-based Census Profile data -- see
    # pycensus.countries.canada.api.fetch_workplace_jobs_totals's
    # docstring) come from a second real source (PID 98-10-0459), merged
    # in for whichever requested columns aren't already covered by `raw`,
    # same pattern as the dissemination-area Census Profile merge below.
    if level == "municipality":
        needed_workplace_names = [
            code for col in missing_defs if not any(c in raw.columns for c in col.codes) for code in col.codes
        ]
        if any(name == api._WORKPLACE_JOBS_COLUMN for name in needed_workplace_names):
            jobs = api.fetch_workplace_jobs_totals(data_dir)
            raw = raw.merge(jobs, on="GEOID", how="left")

    # Dissemination-area household size / income / education / tenure /
    # commute-mode fields come from a second real source (catalogue
    # 98-401-X2021006, Ontario only so far -- see
    # pycensus.countries.canada.api.fetch_census_profile_da_totals) rather
    # than the basic PID 98-10-0015 totals table. Merge it in for whichever
    # requested columns aren't already covered by `raw`.
    if level == "dissemination-area":
        needed_profile_names = [
            code
            for col in missing_defs
            if not any(c in raw.columns for c in col.codes)
            for code in col.codes
            # `statcan_jobsTotal`'s code is the census-subdivision
            # workplace-jobs sentinel (PID 98-10-0459, see the
            # `level == "municipality"` branch above) -- it is not a real
            # 98-401-X2021006 CHARACTERISTIC_NAME and never will be, since
            # that source has no dissemination-area-level workplace jobs
            # figure at all. Asking `fetch_census_profile_da_totals` to
            # match it would always fail for this one name while every
            # other requested name succeeds -- previously that silently
            # dropped just the jobsTotal column (correct, since it's
            # genuinely inapplicable at this level), but it defeats the
            # "did any real characteristic name silently fail to match"
            # validation in fetch_census_profile_da_totals by always
            # tripping it, for a name that was never supposed to be asked
            # for here in the first place. Exclude it so that validation
            # can mean something for the real DA-level fields.
            if code != api._WORKPLACE_JOBS_COLUMN
        ]
        if needed_profile_names:
            try:
                profile = api.fetch_census_profile_da_totals(province, needed_profile_names, data_dir)
                raw = raw.merge(profile, on="GEOID", how="left")
            except NotImplementedError:
                # Real source not downloaded/verified for this province yet
                # (only Ontario is) -- columns fall through to the
                # missing-column NaN branch below, never fabricated.
                pass

    result = pd.DataFrame({"GEOID": raw["GEOID"]})
    for col in missing_defs:
        prefixed = SCHEMA.column_label(col.name)
        raw_col = next((c for c in col.codes if c in raw.columns), None)
        if raw_col is None:
            result[prefixed] = pd.Series(dtype="float64", index=raw.index)
        else:
            result[prefixed] = pd.to_numeric(raw[raw_col], errors="coerce")
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    provinces: Optional[Union[str, List[str]]] = None,
    level: str = "municipality",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load StatCan 2021 Census data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``provinces`` if not
            given (via :func:`pycensus.canada.geography.provinces_in_aoi`),
            and to clip the final result.
        provinces: Province name(s)/abbreviation(s)/PRUID(s) to load.
            Derived from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name. Only ``"province"`` and
            ``"municipality"`` are implemented; other standard levels
            fall back onto one of those two via
            :data:`pycensus.canada.constants.LEVEL_FALLBACK` where
            possible, else raise.
        year: Vintage year, or ``"latest"``. Only 2021 is available.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the parquet cache entirely -- always
            fetch fresh and don't persist the result. StatCan's own raw
            Full Table Download / boundary downloads
            (:mod:`pycensus.canada.api`, :mod:`pycensus.canada.geography`)
            are cached on disk independently of this flag.
        data_dir: Base directory for StatCan's raw downloaded files
            (Census Profile CSV, boundary zips). Defaults to
            :data:`pycensus.canada.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``statcan_``-prefixed
        column per logical column in :data:`pycensus.canada.statcan.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``provinces`` nor ``aoi`` is given, or
            ``level`` has no implemented data source.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="canada")
    year = constants.LATEST_YEAR.get("census", 2021) if year == "latest" else int(year)

    if provinces is None:
        if aoi is None:
            raise ValueError("Either 'provinces' or 'aoi' is required")
        provinces = geography.provinces_in_aoi(aoi, year, data_dir)
    elif isinstance(provinces, str):
        provinces = [provinces]

    pruids = [constants.province_code(p) for p in provinces]
    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    province_frames = []
    for pruid in pruids:
        path = cache_store.region_path(cache_dir, "canada", level, pruid)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda province=pruid: geography.load_boundaries(
                level, province, year, data_dir=data_dir
            ),
            fetch_columns=lambda missing, province=pruid: _fetch_missing(
                missing, level, province, data_dir
            ),
            use_cache=cache,
        )
        province_frames.append(gdf)

    if not province_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
                geometry=gpd.GeoSeries([], crs=4326),
                crs=4326,
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(province_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
