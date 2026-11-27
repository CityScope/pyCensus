"""The cache regions a US census load needs: the counties that touch the AOI, instead of whole states.

A state at block or block-group level is hundreds of thousands of rows (Texas: millions) and an area is usually one county or a few. For the levels
finer than county each touched county is its own cache region and is fetched alone (`in=county:017` in the Census API); a state's own cache file, when
an earlier run made one, is used as it is, so no earlier download is wasted. State and county levels stay one region per state (they are small).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import geopandas as gpd

from pycensus import cache as cache_store
from pycensus.census.countries.usa import geography, utils

FINE_LEVELS = ("tract", "blockgroup", "block")


def region_units(aoi: Optional[gpd.GeoDataFrame], state: str, level: str, geo_year: int, cache_dir: Optional[str]) -> List[Tuple[str, Optional[str]]]:
    """`[(region code of the cache file, county FIPS or None)]` to load for this state: the state itself (code = its FIPS) for coarse levels, when no
    AOI is given, or when the state's cache file exists; otherwise one unit per county touching the AOI (code = 5-digit county FIPS)."""
    fips = utils.state_fips(state)
    if aoi is None or level not in FINE_LEVELS:
        return [(fips, None)]
    if Path(cache_store.region_path(cache_dir, "usa", level, fips)).exists():
        return [(fips, None)]
    counties = geography.load_boundaries("county", state, geo_year).to_crs(4326)
    hit = counties[counties.intersects(aoi.to_crs(4326).union_all())]["GEOID"].astype(str).tolist()
    return [(g, g[2:]) for g in hit] or [(fips, None)]


_STATE_BOUNDARIES: dict = {}


def state_boundaries(level: str, state: str, geo_year: int) -> gpd.GeoDataFrame:
    """A state's boundaries for a level, read once per run (each county of a state asks for them: reading a block file again for every county is slow)."""
    key = (level, utils.state_fips(state), geo_year)
    if key not in _STATE_BOUNDARIES:
        if len(_STATE_BOUNDARIES) >= 4:   # a few states at most in memory
            _STATE_BOUNDARIES.pop(next(iter(_STATE_BOUNDARIES)))
        _STATE_BOUNDARIES[key] = geography.load_boundaries(level, state, geo_year)
    return _STATE_BOUNDARIES[key]


def only_county(gdf: gpd.GeoDataFrame, county: Optional[str], state: str) -> gpd.GeoDataFrame:
    """The part of a state's boundaries inside one county (GEOIDs start with the 5-digit county code); unchanged when `county` is None."""
    if county is None:
        return gdf
    return gdf[gdf["GEOID"].astype(str).str.startswith(utils.state_fips(state) + county)].reset_index(drop=True)
