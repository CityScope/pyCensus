"""Loader for LODES RAC/WAC job counts, returning a common-schema GeoDataFrame.

Technical aspects:
    Reads as much as possible from pyCensus' parquet cache
    (:mod:`pycensus.cache`, shared with ACS/DHC for the same level/region),
    fetching pre-aggregated block-level LODES data with
    `pygris.data.get_lodes` only when a requested column is missing. LODES
    ships one flat file per state/type/year (no per-variable selection), so
    a single missing column still triggers a full state fetch -- but that
    fetch only happens once per level/region/type, ever, thanks to the
    cache. ``agg_level`` asks pygris to pre-sum blocks up to the requested
    level before the data even reaches this loader.

Source:
    https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.3.pdf
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import polars as pl
from pygris.data import get_lodes

from ... import cache as cache_store
from ... import geometry_levels
from .. import constants, geography, utils
from .schema import RAC_SCHEMA, WAC_SCHEMA, ColumnSchema

_AGG_LEVEL = {"blockgroup": "block group", "state": "county"}
_GEOCODE_COL = {"rac": "h_geocode", "wac": "w_geocode"}


def _fetch_missing(
    missing_prefixed: List[str],
    schema: ColumnSchema,
    lodes_type: str,
    level: str,
    state: str,
    year: int,
) -> pd.DataFrame:
    """Fetch the full LODES file for one state and compute just the columns in ``missing_prefixed``."""
    geocode_col = _GEOCODE_COL[lodes_type]
    agg_level = _AGG_LEVEL.get(level, level)

    raw = (
        pl.from_pandas(
            get_lodes(
                version="LODES8",
                state=utils.state_abbr(state).lower(),
                year=year,
                lodes_type=lodes_type,
                agg_level=agg_level,
                cache=False,
            )
        )
        .rename({geocode_col: "GEOID"})
        .with_columns(pl.col("GEOID").cast(pl.Utf8))
    )

    missing_defs = [schema.columns[schema.strip_prefix(c)] for c in missing_prefixed]
    exprs = [
        pl.sum_horizontal(
            [pl.col(c).cast(pl.Float64, strict=False) for c in col.codes if c in raw.columns]
        ).alias(schema.prefixed(col.name))
        for col in missing_defs
    ]
    logical = raw.with_columns(exprs).select(["GEOID", *[schema.prefixed(c.name) for c in missing_defs]])
    return logical.to_pandas()


def _load(
    lodes_type: str,
    schema: ColumnSchema,
    aoi: Optional[gpd.GeoDataFrame],
    states: Optional[Union[str, List[str]]],
    level: str,
    year: Union[int, str],
    cache_dir: Optional[str],
    cache: bool,
) -> gpd.GeoDataFrame:
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    year = constants.LATEST_YEAR["lodes"] if year == "latest" else int(year)
    geo_year = constants.LATEST_YEAR["geography"]

    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi, geo_year)
    elif isinstance(states, str):
        states = [states]

    columns = [schema.prefixed(name) for name in schema.columns]

    state_frames = []
    for state in states:
        path = cache_store.region_path(cache_dir, "USA", level, utils.state_fips(state))
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda state=state: geography.load_boundaries(level, state, geo_year),
            fetch_columns=lambda missing, state=state: _fetch_missing(
                missing, schema, lodes_type, level, state, year
            ),
            use_cache=cache,
        )
        state_frames.append(gdf)

    result = gpd.GeoDataFrame(pd.concat(state_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def load_rac(
    aoi: Optional[gpd.GeoDataFrame] = None,
    states: Optional[Union[str, List[str]]] = None,
    level: str = "blockgroup",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load LODES Residence Area Characteristics (jobs held by residents) data.

    Args:
        aoi: Area of interest. Used to auto-detect ``states`` if not given,
            and to clip the final result.
        states: State name(s)/abbreviation(s)/FIPS code(s) to load. Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level to pre-aggregate LODES blocks to.
        year: Vintage year, or ``"latest"``.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one
        ``lodes_rac_``-prefixed column per logical column in
        :data:`pycensus.USA.lodes.schema.RAC_SCHEMA`.
    """
    return _load("rac", RAC_SCHEMA, aoi, states, level, year, cache_dir, cache)


def load_wac(
    aoi: Optional[gpd.GeoDataFrame] = None,
    states: Optional[Union[str, List[str]]] = None,
    level: str = "blockgroup",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load LODES Workplace Area Characteristics (jobs located in the block) data.

    Args:
        aoi: Area of interest. Used to auto-detect ``states`` if not given,
            and to clip the final result.
        states: State name(s)/abbreviation(s)/FIPS code(s) to load. Derived
            from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level to pre-aggregate LODES blocks to.
        year: Vintage year, or ``"latest"``.
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one
        ``lodes_wac_``-prefixed column per logical column in
        :data:`pycensus.USA.lodes.schema.WAC_SCHEMA`.
    """
    return _load("wac", WAC_SCHEMA, aoi, states, level, year, cache_dir, cache)
