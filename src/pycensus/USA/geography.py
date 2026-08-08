"""Boundary fetching shared by every US census source (ACS, DHC, LODES, ...).

Technical aspects:
    Boundaries come from `pygris <https://walker-data.com/pygris/>`_, which
    wraps the Census Bureau's TIGER/Line shapefiles. Every pygris call here
    uses ``cache=False`` -- persistence is handled entirely by
    :mod:`pycensus.cache`, one level higher in the call stack (in each
    source's ``loader.py``), not by pygris' own shapefile cache. This
    module only adds: a normalized ``GEOID`` column, optional water erasure
    (`pygris.utils.erase_water`), and standard-level fallback resolution
    (:func:`pycensus.geometry_levels.resolve_level`) -- the pieces every
    source needs identically.

Source:
    https://walker-data.com/pygris/
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import pygris
import pygris.utils

from .. import geometry_levels
from . import constants, utils


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int) -> List[str]:
    """Return the USPS abbreviations of every state intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: TIGER/Line vintage year for the state boundaries.

    Returns:
        List of two-letter state abbreviations.
    """
    states_gdf = pygris.states(year=year, cache=False).to_crs(4326)
    aoi_union = aoi.to_crs(4326).union_all()
    return states_gdf.loc[states_gdf.geometry.intersects(aoi_union), "STUSPS"].tolist()


def load_boundaries(
    level: str,
    state: str,
    year: int,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch a single state's boundaries for one census geography level.

    Args:
        level: Standard geometry level name
            (:data:`pycensus.geometry_levels.STANDARD_LEVELS`), resolved
            through :data:`pycensus.USA.constants.LEVEL_FALLBACK` if the US
            has no native geography for it.
        state: State name, abbreviation, or FIPS code.
        year: TIGER/Line vintage year.
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`pycensus.USA.constants.ERASE_WATER` for the resolved level.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)

    if level not in constants.GEOMETRY_FUNCS:
        raise KeyError(f"Unknown geography level '{level}'. Known: {sorted(constants.GEOMETRY_FUNCS)}")

    if erase_water is None:
        erase_water = constants.ERASE_WATER.get(level, False)

    func = constants.GEOMETRY_FUNCS[level]
    gdf = func(state=utils.state_abbr(state), year=year, cache=False).to_crs(4326)

    if erase_water:
        gdf = pygris.utils.erase_water(gdf, year=year, cache=False)

    geoid_col = utils.pick_geoid_column(gdf.columns)
    gdf = gdf.rename(columns={geoid_col: "GEOID"}) if geoid_col != "GEOID" else gdf
    gdf["GEOID"] = gdf["GEOID"].astype(str)

    return gdf[["GEOID", "geometry"]]


def load_boundaries_multi(
    level: str,
    states: Union[str, List[str]],
    year: int,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more states, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        states: State name(s)/abbreviation(s)/FIPS code(s).
        year: TIGER/Line vintage year.
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    states = [states] if isinstance(states, str) else states
    parts = [load_boundaries(level, s, year, erase_water) for s in states]
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        gdf = gdf[gdf.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return gdf
