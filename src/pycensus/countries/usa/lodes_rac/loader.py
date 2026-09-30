"""Loader for LODES RAC (Residence Area Characteristics) job counts.

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

from .... import cache as cache_store
from .... import geometry_levels
from .. import constants, geography, utils
from .schema import NATIVE_LEVELS, SCHEMA, ColumnSchema
from pycensus.canonical import apply_canonical_names

_AGG_LEVEL = {"blockgroup": "block group", "state": "county"}
_GEOCODE_COL = "h_geocode"
_LODES_TYPE = "rac"


def _fetch_missing(
    missing_prefixed: List[str],
    schema: ColumnSchema,
    level: str,
    state: str,
    year: int,
) -> pd.DataFrame:
    """Fetch the full LODES RAC file for one state and compute just the columns in ``missing_prefixed``."""
    agg_level = _AGG_LEVEL.get(level, level)

    raw = (
        pl.from_pandas(
            get_lodes(
                version="LODES8",
                state=utils.state_abbr(state).lower(),
                year=year,
                lodes_type=_LODES_TYPE,
                agg_level=agg_level,
                cache=False,
            )
        )
        .rename({_GEOCODE_COL: "GEOID"})
        .with_columns(pl.col("GEOID").cast(pl.Utf8))
    )

    missing_defs = [schema.columns[schema.strip_prefix(c)] for c in missing_prefixed]
    exprs = [
        pl.sum_horizontal(
            [pl.col(c).cast(pl.Float64, strict=False) for c in col.codes if c in raw.columns]
        ).alias(schema.column_label(col.name))
        for col in missing_defs
    ]
    logical = raw.with_columns(exprs).select(["GEOID", *[schema.column_label(c.name) for c in missing_defs]])
    return logical.to_pandas()


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
        :data:`pycensus.usa.lodes_rac.schema.SCHEMA`.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="usa")
    year_ = constants.LATEST_YEAR["lodes"] if year == "latest" else int(year)
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
            fetch_columns=lambda missing, state=state: _fetch_missing(
                missing, SCHEMA, level, state, year_
            ),
            use_cache=cache,
        )
        state_frames.append(gdf)

    result = gpd.GeoDataFrame(pd.concat(state_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    final = apply_canonical_names(result, SCHEMA)
    # Metadata only (per geometry_levels.is_native_level) -- never a
    # column, so it can't be silently overwritten/resampled downstream
    # like a real data column could.
    final.attrs["native_level"] = level in NATIVE_LEVELS
    return final
