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

from ... import geometry_levels
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


def _erase_water_tolerant(gdf: gpd.GeoDataFrame, year: int) -> gpd.GeoDataFrame:
    """`pygris.utils.erase_water`, but a county whose area-water file can't be read is skipped.

    pygris aborts the whole call if any one nearby county's TIGER areawater
    zip is unreadable (e.g. a county without water ships an empty stub, such
    as CA's Mono 06051), which used to fail every county around it. Here
    that county simply contributes no water to erase.
    """
    import logging

    counties = pygris.counties(cb=True, resolution="500k", year=year).to_crs(gdf.crs)
    counties["county_id"] = counties["GEOID"]
    county_ids = counties.overlay(gdf, keep_geom_type=False)["county_id"].unique().tolist()
    if not county_ids:
        raise ValueError("Dataset does not appear to be in the United States.")

    water_parts = []
    for cid in county_ids:
        try:
            water_parts.append(pygris.area_water(state=cid[:2], county=cid[2:], year=year, cache=False).to_crs(gdf.crs))
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Skipping area water for county {cid}: {exc}")
    if not water_parts:
        return gdf
    all_water = pd.concat(water_parts, ignore_index=True)
    all_water["water_rank"] = all_water.AWATER.rank(pct=True)
    water = all_water.query("water_rank >= 0.75")
    return gdf.overlay(water, how="difference")


def _retry_tiger(fetch, attempts: int = 3):
    """Call a pygris fetch, discarding truncated cached TIGER zips and retrying on failure.

    A single bad Census response leaves a tiny stub zip in /tmp that pygris
    then keeps reusing, which used to fail every later county of the state.
    """
    import glob
    import os
    import time

    last = None
    for attempt in range(attempts):
        try:
            return fetch()
        except Exception as exc:  # pyogrio DataSourceError, HTTP errors, ...
            last = exc
            for path in glob.glob("/tmp/tl_*.zip"):
                try:
                    if os.path.getsize(path) < 1024:
                        os.remove(path)
                except OSError:
                    pass
            time.sleep(5 * (attempt + 1))
    raise last


def _retry_tiger_years(fetch_for_year, year: int):
    """`_retry_tiger` for `year`, then (if Census keeps rejecting it) for the adjacent vintages.

    Census occasionally serves a permanent "Request Rejected" stub for one
    state/year file (seen: ND blocks 2023) while neighbouring vintages are
    fine; the 2020-census block/tract geometries are the same across them.
    """
    last = None
    for y in (year, year + 1, year - 1):
        try:
            gdf = _retry_tiger(lambda: fetch_for_year(y), attempts=2)
            if y != year:
                import logging

                logging.getLogger(__name__).warning(f"TIGER {year} unavailable; used {y} instead")
            return gdf
        except Exception as exc:
            last = exc
    raise last


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
            through :data:`pycensus.usa.constants.LEVEL_FALLBACK` if the US
            has no native geography for it.
        state: State name, abbreviation, or FIPS code.
        year: TIGER/Line vintage year.
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`pycensus.usa.constants.ERASE_WATER` for the resolved level.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="usa")

    if level not in constants.GEOMETRY_FUNCS:
        raise KeyError(f"Unknown geography level '{level}'. Known: {sorted(constants.GEOMETRY_FUNCS)}")

    if erase_water is None:
        erase_water = constants.ERASE_WATER.get(level, False)

    func = constants.GEOMETRY_FUNCS[level]
    if level not in ("nation", "state") and utils.state_abbr(state) == "CT" and year >= 2022:
        # From TIGER 2022 Connecticut's 8 counties were replaced by 9 "planning regions" (new codes
        # 09110..09190), but the 2020 census/ACS/election data are still keyed by the legacy counties
        # (09001..09015) and their tracts: use the last legacy vintage so the GEOIDs match the data.
        year = 2021
    if level == "nation":
        # pygris.nation() covers the whole US in one call, takes no `state`
        # kwarg, and returns a single national polygon -- nothing to filter.
        gdf = func(year=year, cache=False).to_crs(4326)
    elif level == "state":
        # pygris.states() also takes no `state` kwarg (it always returns
        # every state), so fetch all of them and filter down to the one
        # requested -- load_boundaries is called once per state by a
        # multi-state loader.load(), and callers expect exactly one row back.
        all_states = func(year=year, cache=False).to_crs(4326)
        abbr = utils.state_abbr(state)
        gdf = all_states[all_states["STUSPS"] == abbr]
    else:
        gdf = _retry_tiger_years(lambda y: func(state=utils.state_abbr(state), year=y, cache=False), year).to_crs(4326)

    if erase_water:
        gdf = _erase_water_tolerant(gdf, year)

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
