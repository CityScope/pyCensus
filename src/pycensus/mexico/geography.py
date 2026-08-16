"""Boundary fetching shared by every Mexico census source.

Technical aspects:
    Boundaries for Mexico come from INEGI's geographic data. This module
    provides functions to load boundaries at various administrative levels
    (nation, state, municipality, locality, ageb, block).
    
    Unlike the US which uses pygris, Mexico uses INEGI's shapefiles or
    other geographic data sources. For now, we implement placeholder boundaries
    that allow the system to work without requiring boundary data downloads.
    Real boundary data can be added in the future.

    Every boundary fetch here is stateless - persistence is handled entirely by
    :mod:`pycensus.cache`, one level higher in the call stack (in each
    source's ``loader.py``), not by this module.

Source:
    https://www.inegi.org.mx/temas/geografia/
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import geometry_levels
from . import constants, utils


# Mapping of geometry level names to boundary loading functions
# For now, these return placeholders - in the future, they could fetch real data
GEOMETRY_FUNCS = {
    "nation": None,  # National boundaries (single polygon for Mexico)
    "state": None,  # State boundaries
    "municipality": None,  # Municipality boundaries
    "locality": None,  # Locality/city boundaries
    "ageb": None,  # AGEB (Area Geoestadistica Basica) boundaries
    "block": None,  # Block (manzana) boundaries
}

# Geography hierarchy for census data queries
# Defines the parent-child relationships for building geographic filters
GEO_HIERARCHIES = {
    "block": ["state", "municipality", "locality", "ageb", "block"],
    "ageb": ["state", "municipality", "locality", "ageb"],
    "locality": ["state", "municipality", "locality"],
    "municipality": ["state", "municipality"],
    "state": ["state"],
    "nation": ["nation"],
}

# Whether to erase water by default for each level
# Similar to USA.constants.ERASE_WATER
ERASE_WATER: dict = {
    "nation": False,
    "state": False,
    "municipality": False,
    "locality": False,
    "ageb": True,
    "block": True,
}


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2020) -> List[str]:
    """Return the INEGI codes of every state intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2020).

    Returns:
        List of two-digit state codes.
    """
    # For now, return all states - this would be replaced with actual
    # geographic intersection logic once we have state boundary data
    return list(constants.STATE_CODES.keys())


def load_boundaries(
    level: str,
    state: Optional[str] = None,
    year: int = 2020,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Mexico geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.mexico.constants.LEVEL_FALLBACK`.
        state: State code, name, or abbreviation. If None, returns all
            geometries at this level for the entire country.
        year: Vintage year (default 2020).
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`ERASE_WATER` for the resolved level.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
        ValueError: If no geographic data is available for the requested level.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)

    if level not in GEOMETRY_FUNCS:
        raise KeyError(f"Unknown geography level '{level}'. Known: {sorted(GEOMETRY_FUNCS)}")

    if erase_water is None:
        erase_water = ERASE_WATER.get(level, False)

    if state:
        state_code = utils.state_code(state)
    else:
        state_code = None

    # For now, create placeholder boundaries
    # Real INEGI boundary data would be fetched here in the future
    import warnings
    warnings.warn(
        f"No geographic data source configured for level '{level}'. "
        f"Using placeholder boundaries. To get real boundaries, please download "
        f"INEGI boundary data from https://www.inegi.org.mx/temas/geografia/ "
        f"and update the GEOMETRY_FUNCS mapping in this module."
    )

    # Create placeholder GeoDataFrame
    from shapely.geometry import Polygon

    if level == "nation":
        # Create a rough Mexico polygon
        mex_coords = [
            (-118, 14), (-118, 33), (-86, 33), (-86, 14)
        ]
        poly = Polygon(mex_coords)
        gdf = gpd.GeoDataFrame({"GEOID": ["MEX"]}, geometry=[poly], crs="EPSG:4326")
    elif level == "state":
        if state_code:
            state_name = constants.STATE_CODES.get(state_code, state_code)
            # Create a unique polygon for each state based on code
            seed = int(state_code) if state_code.isdigit() else hash(state_code)
            np.random.seed(seed)
            x, y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
            poly = Polygon([
                (x-1, y-1), (x+1, y-1), (x+1, y+1), (x-1, y+1)
            ])
            gdf = gpd.GeoDataFrame({"GEOID": [state_code]}, geometry=[poly], crs="EPSG:4326")
        else:
            # All states
            state_codes = list(constants.STATE_CODES.keys())
            geometries = []
            geoid_list = []
            for sc in state_codes:
                seed = int(sc) if sc.isdigit() else hash(sc)
                np.random.seed(seed)
                x, y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                poly = Polygon([
                    (x-1, y-1), (x+1, y-1), (x+1, y+1), (x-1, y+1)
                ])
                geometries.append(poly)
                geoid_list.append(sc)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "municipality":
        # Create placeholder municipalities for the state
        # In reality, each state has many municipalities
        # For placeholder, create a few per state
        if state_code:
            # Create ~10 placeholder municipalities per state
            num_muns = 10
            geometries = []
            geoid_list = []
            for i in range(num_muns):
                seed = hash(f"{state_code}_{i}")
                np.random.seed(seed)
                # Position within a rough area for the state
                state_seed = int(state_code) if state_code.isdigit() else hash(state_code)
                np.random.seed(state_seed)
                state_x, state_y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                np.random.seed(seed)
                x, y = state_x + np.random.uniform(-1, 1), state_y + np.random.uniform(-1, 1)
                poly = Polygon([
                    (x-0.2, y-0.2), (x+0.2, y-0.2), (x+0.2, y+0.2), (x-0.2, y+0.2)
                ])
                # GEOID format: CVE_ENT + CVE_MUN (3 digits)
                geoid = f"{state_code}{str(i+1).zfill(3)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            # All municipalities - this would be a lot, return empty for now
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "locality":
        # Placeholder for localities
        if state_code:
            num_locs = 5
            geometries = []
            geoid_list = []
            for i in range(num_locs):
                seed = hash(f"{state_code}_loc_{i}")
                np.random.seed(seed)
                state_seed = int(state_code) if state_code.isdigit() else hash(state_code)
                np.random.seed(state_seed)
                state_x, state_y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                np.random.seed(seed)
                x, y = state_x + np.random.uniform(-0.5, 0.5), state_y + np.random.uniform(-0.5, 0.5)
                poly = Polygon([
                    (x-0.1, y-0.1), (x+0.1, y-0.1), (x+0.1, y+0.1), (x-0.1, y+0.1)
                ])
                # GEOID format: CVE_ENT + CVE_MUN + CVE_LOC (4 digits)
                geoid = f"{state_code}001{str(i+1).zfill(4)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "ageb":
        # Placeholder for AGEB (tract equivalent)
        if state_code:
            num_agebs = 3
            geometries = []
            geoid_list = []
            for i in range(num_agebs):
                seed = hash(f"{state_code}_ageb_{i}")
                np.random.seed(seed)
                state_seed = int(state_code) if state_code.isdigit() else hash(state_code)
                np.random.seed(state_seed)
                state_x, state_y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                np.random.seed(seed)
                x, y = state_x + np.random.uniform(-0.2, 0.2), state_y + np.random.uniform(-0.2, 0.2)
                poly = Polygon([
                    (x-0.05, y-0.05), (x+0.05, y-0.05), (x+0.05, y+0.05), (x-0.05, y+0.05)
                ])
                # GEOID format: CVE_ENT + CVE_MUN + CVE_AGEB (4 digits)
                geoid = f"{state_code}001{str(i+1).zfill(4)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "block":
        # Placeholder for blocks (manzanas)
        if state_code:
            num_blocks = 2
            geometries = []
            geoid_list = []
            for i in range(num_blocks):
                seed = hash(f"{state_code}_block_{i}")
                np.random.seed(seed)
                state_seed = int(state_code) if state_code.isdigit() else hash(state_code)
                np.random.seed(state_seed)
                state_x, state_y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                np.random.seed(seed)
                x, y = state_x + np.random.uniform(-0.1, 0.1), state_y + np.random.uniform(-0.1, 0.1)
                poly = Polygon([
                    (x-0.02, y-0.2), (x+0.02, y-0.02), (x+0.02, y+0.02), (x-0.02, y+0.02)
                ])
                # GEOID format: CVE_ENT + CVE_MUN + CVE_AGEB + CVE_MZA (3 digits)
                geoid = f"{state_code}0010001{str(i+1).zfill(3)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    else:
        gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        gdf["GEOID"] = []

    # Ensure GEOID is string type
    gdf["GEOID"] = gdf["GEOID"].astype(str)

    # Ensure CRS is EPSG:4326
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    return gdf[["GEOID", "geometry"]]


def load_boundaries_multi(
    level: str,
    states: Optional[Union[str, List[str]]] = None,
    year: int = 2020,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more states, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        states: State code(s), name(s), or abbreviation(s). If None, returns all
            geometries at this level for the entire country.
        year: Vintage year (default 2020).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if states is None:
        states = list(constants.STATE_CODES.keys())
    elif isinstance(states, str):
        states = [states]

    # Convert all states to codes
    state_codes = [utils.state_code(s) for s in states]

    parts = []
    for state_code in state_codes:
        try:
            gdf = load_boundaries(level, state_code, year, erase_water)
            parts.append(gdf)
        except Exception as e:
            print(f"Warning: Could not load boundaries for state {state_code}: {e}")
            continue

    if not parts:
        raise ValueError(f"No boundaries could be loaded for any of the requested states: {states}")

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


__all__ = [
    "GEOMETRY_FUNCS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "states_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
]
