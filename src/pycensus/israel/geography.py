"""Boundary fetching shared by every Israel census source.

Technical aspects:
    Boundaries for Israel come from CBS's geographic data. This module
    provides functions to load boundaries at various administrative levels
    (nation, district, subdistrict, locality, statistical_area, street, block).
    
    Unlike the US which uses pygris, Israel uses CBS's shapefiles or
    other geographic data sources. For now, we implement placeholder boundaries
    that allow the system to work without requiring boundary data downloads.
    Real boundary data can be added in the future.

    Every boundary fetch here is stateless - persistence is handled entirely by
    :mod:`pycensus.cache`, one level higher in the call stack (in each
    source's ``loader.py``), not by this module.

Source:
    https://www.cbs.gov.il/en/statistics/pages/geographic-information.aspx
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
    "nation": None,  # National boundaries (single polygon for Israel)
    "district": None,  # District boundaries
    "subdistrict": None,  # Sub-district boundaries
    "locality": None,  # Locality/city boundaries
    "statistical_area": None,  # Statistical area boundaries
    "street": None,  # Street boundaries
    "block": None,  # Block boundaries
}

# Geography hierarchy for census data queries
# Defines the parent-child relationships for building geographic filters
GEO_HIERARCHIES = {
    "block": ["nation", "district", "subdistrict", "locality", "statistical_area", "street", "block"],
    "street": ["nation", "district", "subdistrict", "locality", "statistical_area", "street"],
    "statistical_area": ["nation", "district", "subdistrict", "locality", "statistical_area"],
    "locality": ["nation", "district", "subdistrict", "locality"],
    "subdistrict": ["nation", "district", "subdistrict"],
    "district": ["nation", "district"],
    "nation": ["nation"],
}

# Whether to erase water by default for each level
ERASE_WATER: dict = {
    "nation": False,
    "district": False,
    "subdistrict": False,
    "locality": False,
    "statistical_area": True,
    "street": True,
    "block": True,
}


def districts_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2022) -> List[str]:
    """Return the CBS codes of every district intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2022).

    Returns:
        List of one-digit district codes.
    """
    # For now, return all districts - this would be replaced with actual
    # geographic intersection logic once we have boundary data
    return list(constants.DISTRICT_CODES.keys())


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2022,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Israel geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.israel.constants.LEVEL_FALLBACK`.
        region: Region code (district code, sub-district code, etc.).
            If None, returns all geometries at this level for the entire country.
        year: Vintage year (default 2022).
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

    # For now, create placeholder boundaries
    # Real CBS boundary data would be fetched here in the future
    import warnings
    warnings.warn(
        f"No geographic data source configured for level '{level}'. "
        f"Using placeholder boundaries. To get real boundaries, please download "
        f"CBS boundary data from https://www.cbs.gov.il/en/statistics/pages/geographic-information.aspx "
        f"and update the GEOMETRY_FUNCS mapping in this module."
    )

    # Create placeholder GeoDataFrame
    from shapely.geometry import Polygon

    if level == "nation":
        # Create a rough Israel polygon (including Golan Heights)
        # Mainland Israel approximate bounding box
        mainland = Polygon([
            (34.2, 29.5), (34.2, 33.3), (35.9, 33.3), (35.9, 29.5)
        ])
        # Golan Heights
        golan = Polygon([
            (35.5, 32.5), (35.9, 32.5), (35.9, 33.3), (35.5, 33.3)
        ])
        gdf = gpd.GeoDataFrame(
            {"GEOID": ["ISR"]},
            geometry=[mainland.union(golan)],
            crs="EPSG:4326"
        )
    elif level == "district":
        if region:
            dist_code = utils.district_code(region)
            dist_name = constants.DISTRICT_CODES.get(dist_code, region)
            # Create a unique polygon for each district based on code
            seed = int(dist_code) if dist_code.isdigit() else hash(dist_code)
            np.random.seed(seed)
            # Position roughly within Israel's bounding box
            x_center = np.random.uniform(34.2, 35.9)
            y_center = np.random.uniform(29.5, 33.3)
            # Size varies by district
            size = np.random.uniform(0.3, 1.0)
            poly = Polygon([
                (x_center - size, y_center - size),
                (x_center + size, y_center - size),
                (x_center + size, y_center + size),
                (x_center - size, y_center + size)
            ])
            gdf = gpd.GeoDataFrame({"GEOID": [dist_code]}, geometry=[poly], crs="EPSG:4326")
        else:
            # All districts
            dist_codes = list(constants.DISTRICT_CODES.keys())
            geometries = []
            geoid_list = []
            for dist_code in dist_codes:
                seed = int(dist_code) if dist_code.isdigit() else hash(dist_code)
                np.random.seed(seed)
                x_center = np.random.uniform(34.2, 35.9)
                y_center = np.random.uniform(29.5, 33.3)
                size = np.random.uniform(0.3, 1.0)
                poly = Polygon([
                    (x_center - size, y_center - size),
                    (x_center + size, y_center - size),
                    (x_center + size, y_center + size),
                    (x_center - size, y_center + size)
                ])
                geometries.append(poly)
                geoid_list.append(dist_code)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "subdistrict":
        if region:
            # Region could be district code or sub-district code
            # Create placeholder sub-districts
            num_subdists = 5
            geometries = []
            geoid_list = []
            
            # Get the base region for positioning
            if len(region) == 1 and region in constants.DISTRICT_CODES:
                base_seed = int(region)
            elif len(region) == 2 and region in constants.SUBDISTRICT_CODES:
                base_seed = int(region)
            else:
                base_seed = hash(region)
            
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(34.2, 35.9), np.random.uniform(29.5, 33.3)
            
            for i in range(num_subdists):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.5, 0.5), base_y + np.random.uniform(-0.5, 0.5)
                poly = Polygon([
                    (x-0.2, y-0.2), (x+0.2, y-0.2), (x+0.2, y+0.2), (x-0.2, y+0.2)
                ])
                # GEOID format: DISTRICT + SUBDISTRICT (2 digits)
                geoid = f"{region}{str(i+1).zfill(2)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "locality":
        if region:
            # Create placeholder localities
            num_locs = 10
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(34.2, 35.9), np.random.uniform(29.5, 33.3)
            
            for i in range(num_locs):
                seed = hash(f"{region}_loc_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.3, 0.3), base_y + np.random.uniform(-0.3, 0.3)
                poly = Polygon([
                    (x-0.05, y-0.05), (x+0.05, y-0.05), (x+0.05, y+0.05), (x-0.05, y+0.05)
                ])
                # GEOID format: 4-5 digit locality code
                geoid = f"{str(i+1000).zfill(4)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "statistical_area":
        # Placeholder for statistical areas
        if region:
            num_areas = 3
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(34.2, 35.9), np.random.uniform(29.5, 33.3)
            
            for i in range(num_areas):
                seed = hash(f"{region}_area_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.1, 0.1), base_y + np.random.uniform(-0.1, 0.1)
                poly = Polygon([
                    (x-0.02, y-0.02), (x+0.02, y-0.02), (x+0.02, y+0.02), (x-0.02, y+0.02)
                ])
                # GEOID format: region + area number
                geoid = f"{region}{str(i+1).zfill(3)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "street":
        if region:
            num_streets = 2
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(34.2, 35.9), np.random.uniform(29.5, 33.3)
            
            for i in range(num_streets):
                seed = hash(f"{region}_street_{i}")
                np.random.seed(seed)
                # Create line geometries for streets
                from shapely.geometry import LineString
                x1, y1 = base_x + np.random.uniform(-0.01, 0.01), base_y + np.random.uniform(-0.01, 0.01)
                x2, y2 = base_x + np.random.uniform(-0.01, 0.01), base_y + np.random.uniform(-0.01, 0.01)
                line = LineString([(x1, y1), (x2, y2)])
                geoid = f"{region}_STREET_{i+1}"
                geometries.append(line)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "block":
        # Placeholder for blocks
        if region:
            num_blocks = 2
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(34.2, 35.9), np.random.uniform(29.5, 33.3)
            
            for i in range(num_blocks):
                seed = hash(f"{region}_block_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.01, 0.01), base_y + np.random.uniform(-0.01, 0.01)
                poly = Polygon([
                    (x-0.005, y-0.005), (x+0.005, y-0.005), (x+0.005, y+0.005), (x-0.005, y+0.005)
                ])
                # GEOID format: region + block number
                geoid = f"{region}{str(i+1).zfill(4)}"
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
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2022,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region code(s) (district codes, sub-district codes, etc.).
            If None, returns all geometries at this level for the entire country.
        year: Vintage year (default 2022).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        regions = list(constants.DISTRICT_CODES.keys())
    elif isinstance(regions, str):
        regions = [regions]

    parts = []
    for region in regions:
        try:
            gdf = load_boundaries(level, region, year, erase_water)
            parts.append(gdf)
        except Exception as e:
            print(f"Warning: Could not load boundaries for region {region}: {e}")
            continue

    if not parts:
        raise ValueError(f"No boundaries could be loaded for any of the requested regions: {regions}")

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2022) -> List[str]:
    """Return the CBS codes of every district intersecting ``aoi``.

    This function is kept for compatibility with the USA implementation.
    In Israel, the equivalent of states are districts.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2022).

    Returns:
        List of one-digit district codes.
    """
    return districts_in_aoi(aoi, year)


__all__ = [
    "GEOMETRY_FUNCS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "districts_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
