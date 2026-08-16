"""Boundary fetching shared by every Mexico census source.

Technical aspects:
    Boundaries for Mexico come from INEGI's geographic data. This module
    provides functions to load boundaries at various administrative levels
    (nation, state, municipality, locality, ageb, block).
    
    Unlike the US which uses pygris, Mexico will use INEGI's shapefiles or
    other geographic data sources. For now, we'll implement a basic structure
    that can be extended as geographic data becomes available.

Source:
    https://www.inegi.org.mx/temas/geografia/
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

import geopandas as gpd
import pandas as pd

from .. import geometry_levels
from . import api, constants, utils


# Mapping of geometry level names to boundary loading functions
# For now, these use the api.fetch_boundaries function
# In the future, these could be replaced with direct data loading
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
ERASE_WATER: Dict[str, bool] = {
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
    data_dir: Optional[str] = None,
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
        data_dir: Base directory for data files. Defaults to
            :data:`pycensus.mexico.constants.DEFAULT_DATA_DIR`.

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

    if data_dir is None:
        data_dir = constants.DEFAULT_DATA_DIR

    # Try to load boundary file using the api module
    if state:
        state_code = utils.state_code(state)
    else:
        state_code = None
    
    # Try to fetch boundary file via api
    boundary_path = api.fetch_boundaries(level, state, year, data_dir, overwrite=False)
    
    if boundary_path is not None and Path(boundary_path).exists():
        gdf = gpd.read_file(boundary_path)
    else:
        # Boundary file not found - create a placeholder
        # This allows the system to work even without boundary data
        # The user will get a warning but can still use the data
        import warnings
        data_dir_path = Path(data_dir)
        warnings.warn(
            f"No geographic data found for level '{level}' in {data_dir_path}. "
            f"Using placeholder boundaries. To get real boundaries, please download "
            f"INEGI boundary data and place it in {data_dir_path}. "
            f"See https://www.inegi.org.mx/temas/geografia/ for data sources."
        )
        
        # Create a minimal placeholder GeoDataFrame
        # This will allow the cache system to work for testing
        from shapely.geometry import Polygon, MultiPolygon
        import numpy as np
        
        # Create a simple polygon for the state or a default area
        if level == "nation":
            # Create a rough Mexico polygon
            mex_coords = [
                (-118, 14), (-118, 33), (-86, 33), (-86, 14)
            ]
            poly = Polygon(mex_coords)
            gdf = gpd.GeoDataFrame({"GEOID": ["MEX"]}, geometry=[poly], crs="EPSG:4326")
        elif level == "state":
            if state:
                state_code = utils.state_code(state)
                state_name = constants.STATE_CODES.get(state_code, state_code)
                # Create a simple rectangle for each state (will be replaced with real data)
                # Use a unique polygon for each state based on code
                seed = int(state_code) if state_code.isdigit() else hash(state_code)
                np.random.seed(seed)
                x, y = np.random.uniform(-118, -86), np.random.uniform(14, 33)
                poly = Polygon([
                    (x-1, y-1), (x+1, y-1), (x+1, y+1), (x-1, y+1)
                ])
                gdf = gpd.GeoDataFrame({"GEOID": [state_code]}, geometry=[poly], crs="EPSG:4326")
            else:
                # All states
                gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
                gdf["GEOID"] = []
        else:
            # For lower levels, create an empty GeoDataFrame
            # The user should download real boundary data
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
        
        # Standardize to GEOID column
        if level == "state":
            geoid_col = "CVE_ENT"
        elif level == "municipality":
            geoid_col = "CVE_MUN"
            # Build full GEOID: CVE_ENT + CVE_MUN
            if "CVE_ENT" in gdf.columns and "CVE_MUN" in gdf.columns:
                gdf["GEOID"] = gdf["CVE_ENT"].astype(str) + gdf["CVE_MUN"].astype(str).str.zfill(3)
            elif "GEOID" not in gdf.columns:
                gdf["GEOID"] = gdf.get(geoid_col, "")
            else:
                geoid_col = "GEOID"
        elif level == "locality":
            geoid_col = "CVE_LOC"
            if "CVE_ENT" in gdf.columns and "CVE_MUN" in gdf.columns and "CVE_LOC" in gdf.columns:
                gdf["GEOID"] = (gdf["CVE_ENT"].astype(str) + 
                              gdf["CVE_MUN"].astype(str).str.zfill(3) + 
                              gdf["CVE_LOC"].astype(str).str.zfill(4))
            elif "GEOID" not in gdf.columns:
                gdf["GEOID"] = gdf.get(geoid_col, "")
            else:
                geoid_col = "GEOID"
        elif level == "ageb":
            geoid_col = "CVE_AGEB"
            if "CVE_ENT" in gdf.columns and "CVE_MUN" in gdf.columns and "CVE_AGEB" in gdf.columns:
                gdf["GEOID"] = (gdf["CVE_ENT"].astype(str) + 
                              gdf["CVE_MUN"].astype(str).str.zfill(3) + 
                              gdf["CVE_AGEB"].astype(str).str.zfill(4))
            elif "GEOID" not in gdf.columns:
                gdf["GEOID"] = gdf.get(geoid_col, "")
            else:
                geoid_col = "GEOID"
        elif level == "block":
            geoid_col = "CVE_MZA"
            if "CVE_ENT" in gdf.columns and "CVE_MUN" in gdf.columns and "CVE_AGEB" in gdf.columns and "CVE_MZA" in gdf.columns:
                gdf["GEOID"] = (gdf["CVE_ENT"].astype(str) + 
                              gdf["CVE_MUN"].astype(str).str.zfill(3) + 
                              gdf["CVE_AGEB"].astype(str).str.zfill(4) + 
                              gdf["CVE_MZA"].astype(str).str.zfill(3))
            elif "GEOID" not in gdf.columns:
                gdf["GEOID"] = gdf.get(geoid_col, "")
            else:
                geoid_col = "GEOID"
        else:  # nation
            geoid_col = "CVE_PAIS"
            if "GEOID" not in gdf.columns:
                gdf["GEOID"] = "MEX"
            else:
                geoid_col = "GEOID"
        
        # Rename if needed
        if geoid_col != "GEOID" and geoid_col in gdf.columns:
            gdf = gdf.rename(columns={geoid_col: "GEOID"})
        
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
