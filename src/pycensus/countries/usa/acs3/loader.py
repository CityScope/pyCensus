"""Loader for the ACS 3-year estimates (historical, through 2013), returning a common-schema GeoDataFrame.

Technical aspects:
    For each requested state, :func:`load` reads as much as it can from
    pyCensus' parquet cache (:mod:`pycensus.cache`, one file per
    level/region shared across every US source) and only fetches the
    columns actually missing via :func:`pycensus.usa.api.fetch_variables`,
    summing each logical column's raw codes with Polars before merging back
    into the cache. Output columns are prefixed ``acs3_`` so the result works
    directly with :meth:`geohierarchy.GeoHierarchy.add_level` (using
    ``SCHEMA.aggregations()`` for the ``agg`` argument) and with the
    ``gdf.acs3[...]`` accessor registered in :mod:`pycensus.usa.acs3`.

Note:
    ACS 3-year estimates were discontinued after 2013. This is a historical dataset.
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import polars as pl

from .... import cache as cache_store
from .... import geometry_levels
from ....api_keys import resolve_api_key
from .. import api, constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names


def _acs_code(code: str) -> str:
    """Append the ACS estimate suffix (``E``) to a detailed-table variable code."""
    return code if code.endswith("E") else f"{code}E"


def _fetch_missing(
    missing_prefixed: List[str], level: str, state: str, year: int, api_key: Optional[str]
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed``."""
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]
    codes = sorted({_acs_code(c) for col in missing_defs for c in col.codes})

    raw = api.fetch_variables("acs/acs3", year, level, state, codes, api_key)
    exprs = [
        pl.sum_horizontal(
            [pl.col(_acs_code(c)).cast(pl.Float64, strict=False) for c in col.codes],
            # "mean"-kind columns (medians, rates) are usually a single
            # code: a null there is a suppressed estimate, not a zero.
            ignore_nulls=col.agg != "mean",
        ).alias(SCHEMA.column_label(col.name))
        for col in missing_defs
    ]
    logical = raw.with_columns(exprs).select(["GEOID", *[SCHEMA.column_label(c.name) for c in missing_defs]])
    return logical.to_pandas()


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    states: Optional[Union[str, List[str]]] = None,
    level: str = "tract",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load ACS 3-year estimates as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``states`` if not given,
            and to clip the final result.
        states: State name(s)/abbreviation(s)/FIPS code(s) to load. Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level
            (:data:`pycensus.geometry_levels.STANDARD_LEVELS`); ``"acs/acs3"``
            is available down to ``"blockgroup"``.
        year: Vintage year, or ``"latest"``.
        api_key: Census API key. Resolved via
            :func:`pycensus.api_keys.resolve_api_key` if not given.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``acs3_``-prefixed
        column per logical column in :data:`pycensus.usa.acs3.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``states`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="usa")
    year = constants.LATEST_YEAR["acs3"] if year == "latest" else int(year)
    api_key = resolve_api_key("us_census", "US_CENSUS_API_KEY", api_key)
    geo_year = constants.LATEST_YEAR["geography"]

    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi, geo_year)
    elif isinstance(states, str):
        states = [states]

    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    state_frames = []
    for state in states:
        path = cache_store.region_path(cache_dir, "usa", level, utils.state_fips(state))
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda state=state: geography.load_boundaries(level, state, geo_year),
            fetch_columns=lambda missing, state=state: _fetch_missing(missing, level, state, year, api_key),
            use_cache=cache,
        )
        state_frames.append(gdf)

    result = gpd.GeoDataFrame(pd.concat(state_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)
