"""Boundary fetching shared by every Spain census source.

Technical aspects:
    Boundaries for Spain come from INE's geographic data. This module
    provides functions to load boundaries at various administrative levels
    (nation, autonomous_community, province, municipality, section, block).
    
    Unlike the US which uses pygris, Spain uses INE's shapefiles or
    other geographic data sources. For now, we implement placeholder boundaries
    that allow the system to work without requiring boundary data downloads.
    Real boundary data can be added in the future.

    Every boundary fetch here is stateless - persistence is handled entirely by
    :mod:`pycensus.cache`, one level higher in the call stack (in each
    source's ``loader.py``), not by this module.

Source:
    https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780&menu=ultiDatos
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
    "nation": None,  # National boundaries (single polygon for Spain)
    "autonomous_community": None,  # Autonomous community boundaries
    "province": None,  # Province boundaries
    "municipality": None,  # Municipality boundaries
    "district": None,  # District boundaries (within municipalities)
    "section": None,  # Census section (sección censal) boundaries
    "block": None,  # Block (manzana) boundaries
}

# Geography hierarchy for census data queries
# Defines the parent-child relationships for building geographic filters
GEO_HIERARCHIES = {
    "block": ["nation", "autonomous_community", "province", "municipality", "district", "section", "block"],
    "section": ["nation", "autonomous_community", "province", "municipality", "district", "section"],
    "district": ["nation", "autonomous_community", "province", "municipality", "district"],
    "municipality": ["nation", "autonomous_community", "province", "municipality"],
    "province": ["nation", "autonomous_community", "province"],
    "autonomous_community": ["nation", "autonomous_community"],
    "nation": ["nation"],
}

# Whether to erase water by default for each level
# Similar to USA.constants.ERASE_WATER
ERASE_WATER: dict = {
    "nation": False,
    "autonomous_community": False,
    "province": False,
    "municipality": False,
    "district": False,
    "section": True,
    "block": True,
}


def autonomous_communities_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021) -> List[str]:
    """Return the INE codes of every autonomous community intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of two-digit autonomous community codes.
    """
    # For now, return all autonomous communities - this would be replaced with actual
    # geographic intersection logic once we have boundary data
    return list(constants.AUTONOMOUS_COMMUNITY_CODES.keys())


def provinces_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021) -> List[str]:
    """Return the INE codes of every province intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of two-digit province codes.
    """
    # For now, return all provinces - this would be replaced with actual
    # geographic intersection logic once we have boundary data
    return list(constants.PROVINCE_CODES.keys())


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Spain geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.spain.constants.LEVEL_FALLBACK`.
        region: Region code (autonomous community code, province code, etc.).
            If None, returns all geometries at this level for the entire country.
        year: Vintage year (default 2021).
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
    # Real INE boundary data would be fetched here in the future
    import warnings
    warnings.warn(
        f"No geographic data source configured for level '{level}'. "
        f"Using placeholder boundaries. To get real boundaries, please download "
        f"INE boundary data from https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780 "
        f"and update the GEOMETRY_FUNCS mapping in this module."
    )

    # Create placeholder GeoDataFrame
    from shapely.geometry import Polygon

    if level == "nation":
        # Create a rough Spain polygon (including Balearic and Canary Islands)
        # Mainland Spain approximate bounding box
        mainland = Polygon([
            (-9.5, 35.9), (-9.5, 43.9), (3.3, 43.9), (3.3, 35.9)
        ])
        # Balearic Islands
        balearic = Polygon([
            (1.0, 38.5), (1.5, 38.5), (1.5, 39.5), (1.0, 39.5)
        ])
        # Canary Islands
        canary = Polygon([
            (-18.5, 27.5), (-13.5, 27.5), (-13.5, 29.5), (-18.5, 29.5)
        ])
        gdf = gpd.GeoDataFrame(
            {"GEOID": ["ESP"]},
            geometry=[mainland.union(balearic).union(canary)],
            crs="EPSG:4326"
        )
    elif level == "autonomous_community":
        if region:
            ac_code = utils.autonomous_community_code(region)
            ac_name = constants.AUTONOMOUS_COMMUNITY_CODES.get(ac_code, region)
            # Create a unique polygon for each autonomous community based on code
            seed = int(ac_code) if ac_code.isdigit() else hash(ac_code)
            np.random.seed(seed)
            # Position roughly within Spain's bounding box
            x_center = np.random.uniform(-9.5, 3.3)
            y_center = np.random.uniform(35.9, 43.9)
            # Size varies by community
            size = np.random.uniform(0.5, 2.0)
            poly = Polygon([
                (x_center - size, y_center - size),
                (x_center + size, y_center - size),
                (x_center + size, y_center + size),
                (x_center - size, y_center + size)
            ])
            gdf = gpd.GeoDataFrame({"GEOID": [ac_code]}, geometry=[poly], crs="EPSG:4326")
        else:
            # All autonomous communities
            ac_codes = list(constants.AUTONOMOUS_COMMUNITY_CODES.keys())
            geometries = []
            geoid_list = []
            for ac_code in ac_codes:
                seed = int(ac_code) if ac_code.isdigit() else hash(ac_code)
                np.random.seed(seed)
                x_center = np.random.uniform(-9.5, 3.3)
                y_center = np.random.uniform(35.9, 43.9)
                size = np.random.uniform(0.5, 2.0)
                poly = Polygon([
                    (x_center - size, y_center - size),
                    (x_center + size, y_center - size),
                    (x_center + size, y_center + size),
                    (x_center - size, y_center + size)
                ])
                geometries.append(poly)
                geoid_list.append(ac_code)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "province":
        if region:
            prov_code = utils.province_code(region)
            prov_name = constants.PROVINCE_CODES.get(prov_code, region)
            # Create a unique polygon for each province based on code
            seed = int(prov_code) if prov_code.isdigit() else hash(prov_code)
            np.random.seed(seed)
            x_center = np.random.uniform(-9.5, 3.3)
            y_center = np.random.uniform(35.9, 43.9)
            size = np.random.uniform(0.3, 1.5)
            poly = Polygon([
                (x_center - size, y_center - size),
                (x_center + size, y_center - size),
                (x_center + size, y_center + size),
                (x_center - size, y_center + size)
            ])
            gdf = gpd.GeoDataFrame({"GEOID": [prov_code]}, geometry=[poly], crs="EPSG:4326")
        else:
            # All provinces
            prov_codes = list(constants.PROVINCE_CODES.keys())
            geometries = []
            geoid_list = []
            for prov_code in prov_codes:
                seed = int(prov_code) if prov_code.isdigit() else hash(prov_code)
                np.random.seed(seed)
                x_center = np.random.uniform(-9.5, 3.3)
                y_center = np.random.uniform(35.9, 43.9)
                size = np.random.uniform(0.3, 1.5)
                poly = Polygon([
                    (x_center - size, y_center - size),
                    (x_center + size, y_center - size),
                    (x_center + size, y_center + size),
                    (x_center - size, y_center + size)
                ])
                geometries.append(poly)
                geoid_list.append(prov_code)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "municipality":
        if region:
            # Region could be autonomous community or province code
            # Create placeholder municipalities
            num_muns = 10
            geometries = []
            geoid_list = []
            # Get the base region for positioning
            if len(region) == 2 and region in constants.AUTONOMOUS_COMMUNITY_CODES:
                base_seed = int(region)
            elif len(region) == 2 and region in constants.PROVINCE_CODES:
                base_seed = int(region)
            else:
                base_seed = hash(region)
            
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-9.5, 3.3), np.random.uniform(35.9, 43.9)
            
            for i in range(num_muns):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-1, 1), base_y + np.random.uniform(-1, 1)
                poly = Polygon([
                    (x-0.1, y-0.1), (x+0.1, y-0.1), (x+0.1, y+0.1), (x-0.1, y+0.1)
                ])
                # GEOID format: COD_AUT + COD_PROV + COD_MUN (3 digits)
                # For placeholder, use region code + sequential number
                geoid = f"{region}{str(i+1).zfill(3)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            # All municipalities - this would be a lot, return empty for now
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "district":
        # Placeholder for districts
        if region:
            num_districts = 5
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-9.5, 3.3), np.random.uniform(35.9, 43.9)
            
            for i in range(num_districts):
                seed = hash(f"{region}_dist_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.5, 0.5), base_y + np.random.uniform(-0.5, 0.5)
                poly = Polygon([
                    (x-0.05, y-0.05), (x+0.05, y-0.05), (x+0.05, y+0.05), (x-0.05, y+0.05)
                ])
                # GEOID format: COD_AUT + COD_PROV + COD_MUN + COD_DIST (2 digits)
                geoid = f"{region}001{str(i+1).zfill(2)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "section":
        # Placeholder for census sections (secciones censales)
        if region:
            num_sections = 3
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-9.5, 3.3), np.random.uniform(35.9, 43.9)
            
            for i in range(num_sections):
                seed = hash(f"{region}_sec_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.2, 0.2), base_y + np.random.uniform(-0.2, 0.2)
                poly = Polygon([
                    (x-0.02, y-0.02), (x+0.02, y-0.02), (x+0.02, y+0.02), (x-0.02, y+0.02)
                ])
                # GEOID format: COD_AUT + COD_PROV + COD_MUN + COD_SEC (4 digits)
                geoid = f"{region}00100{str(i+1).zfill(2)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "block":
        # Placeholder for blocks (manzanas)
        if region:
            num_blocks = 2
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-9.5, 3.3), np.random.uniform(35.9, 43.9)
            
            for i in range(num_blocks):
                seed = hash(f"{region}_block_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.05, 0.05), base_y + np.random.uniform(-0.05, 0.05)
                poly = Polygon([
                    (x-0.01, y-0.01), (x+0.01, y-0.01), (x+0.01, y+0.01), (x-0.01, y+0.01)
                ])
                # GEOID format: COD_AUT + COD_PROV + COD_MUN + COD_SEC + COD_MZA (3 digits)
                geoid = f"{region}0010001{str(i+1).zfill(2)}"
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
    year: int = 2021,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region code(s) (autonomous community codes, province codes, etc.).
            If None, returns all geometries at this level for the entire country.
        year: Vintage year (default 2021).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        regions = list(constants.AUTONOMOUS_COMMUNITY_CODES.keys())
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


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021) -> List[str]:
    """Return the INE codes of every autonomous community intersecting ``aoi``.

    This function is kept for compatibility with the USA implementation.
    In Spain, the equivalent of states are autonomous communities.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of two-digit autonomous community codes.
    """
    return autonomous_communities_in_aoi(aoi, year)


__all__ = [
    "GEOMETRY_FUNCS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "autonomous_communities_in_aoi",
    "provinces_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
