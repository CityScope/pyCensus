"""Boundary fetching shared by every Euskadi census source.

Technical aspects:
    Boundaries for Euskadi come from Eustat's geographic data. This module
    provides functions to load boundaries at various administrative levels
    (autonomous_community, territory, comarca, municipality, district, section, block).
    
    Unlike Spain which uses INE data, Euskadi uses Eustat (Basque Statistics Office)
    data. For now, we implement placeholder boundaries that allow the system to
    work without requiring boundary data downloads. Real boundary data can be
    added in the future.
    
    Every boundary fetch here is stateless - persistence is handled entirely by
    :mod:`pycensus.cache`, one level higher in the call stack (in each
    source's ``loader.py``), not by this module.

Source:
    https://www.eustat.eus/geoservicios/descargas.html
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
    "nation": None,  # National boundaries (Euskadi as a whole)
    "autonomous_community": None,  # Euskadi as autonomous community
    "territory": None,  # Historical Territory boundaries (Araba, Bizkaia, Gipuzkoa)
    "comarca": None,  # Comarca boundaries
    "municipality": None,  # Municipality boundaries
    "district": None,  # District/Quarter boundaries
    "section": None,  # Statistical area boundaries
    "block": None,  # Block boundaries
}

# Geography hierarchy for census data queries
# Defines the parent-child relationships for building geographic filters
GEO_HIERARCHIES = {
    "block": ["autonomous_community", "territory", "comarca", "municipality", "district", "section", "block"],
    "section": ["autonomous_community", "territory", "comarca", "municipality", "district", "section"],
    "district": ["autonomous_community", "territory", "comarca", "municipality", "district"],
    "municipality": ["autonomous_community", "territory", "comarca", "municipality"],
    "comarca": ["autonomous_community", "territory", "comarca"],
    "territory": ["autonomous_community", "territory"],
    "autonomous_community": ["autonomous_community"],
}

# Whether to erase water by default for each level
ERASE_WATER: dict = {
    "autonomous_community": False,
    "territory": False,
    "comarca": False,
    "municipality": False,
    "district": False,
    "section": True,
    "block": True,
}


def territories_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021) -> List[str]:
    """Return the Eustat codes of every territory intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of two-digit territory codes (01=Araba, 48=Bizkaia, 20=Gipuzkoa).
    """
    # For now, return all territories - this would be replaced with actual
    # geographic intersection logic once we have boundary data
    return list(constants.TERRITORY_CODES.keys())


def comarcas_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021) -> List[str]:
    """Return the Eustat codes of every comarca intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of comarca codes.
    """
    # For now, return a subset of comarcas - this would be replaced with actual
    # geographic intersection logic once we have boundary data
    all_comarcas = []
    for terr_code, comarcas in constants.COMARCAS_CODES.items():
        all_comarcas.extend(comarcas.keys())
    return all_comarcas


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Euskadi geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.euskadi.constants.LEVEL_FALLBACK`.
        region: Region code (territory code, comarca code, etc.).
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
    # Real Eustat boundary data would be fetched here in the future
    import warnings
    warnings.warn(
        f"No geographic data source configured for level '{level}'. "
        f"Using placeholder boundaries. To get real boundaries, please download "
        f"Eustat boundary data from https://www.eustat.eus/geoservicios/descargas.html "
        f"and update the GEOMETRY_FUNCS mapping in this module."
    )

    # Create placeholder GeoDataFrame
    from shapely.geometry import Polygon

    # Euskadi is roughly in northern Spain, bounding box approximately:
    # Min: (-3.5, 42.0), Max: (-1.0, 43.5)
    if level == "autonomous_community":
        # Create a rough Euskadi polygon
        euskadi_poly = Polygon([
            (-3.5, 42.0), (-3.5, 43.5), (-1.0, 43.5), (-1.0, 42.0)
        ])
        gdf = gpd.GeoDataFrame(
            {"GEOID": ["ES_PV"]},  # ES = Spain, PV = País Vasco
            geometry=[euskadi_poly],
            crs="EPSG:4326"
        )
    elif level == "territory":
        if region:
            terr_code = utils.territory_code(region)
            terr_name = constants.TERRITORY_CODES.get(terr_code, region)
            # Create a unique polygon for each territory based on code
            seed = int(terr_code) if terr_code.isdigit() else hash(terr_code)
            np.random.seed(seed)
            # Position within Euskadi's bounding box
            x_center = np.random.uniform(-3.5, -1.0)
            y_center = np.random.uniform(42.0, 43.5)
            # Size varies by territory
            size = np.random.uniform(0.5, 1.5)
            poly = Polygon([
                (x_center - size, y_center - size),
                (x_center + size, y_center - size),
                (x_center + size, y_center + size),
                (x_center - size, y_center + size)
            ])
            gdf = gpd.GeoDataFrame({"GEOID": [terr_code]}, geometry=[poly], crs="EPSG:4326")
        else:
            # All territories
            terr_codes = list(constants.TERRITORY_CODES.keys())
            geometries = []
            geoid_list = []
            for terr_code in terr_codes:
                seed = int(terr_code) if terr_code.isdigit() else hash(terr_code)
                np.random.seed(seed)
                x_center = np.random.uniform(-3.5, -1.0)
                y_center = np.random.uniform(42.0, 43.5)
                size = np.random.uniform(0.5, 1.5)
                poly = Polygon([
                    (x_center - size, y_center - size),
                    (x_center + size, y_center - size),
                    (x_center + size, y_center + size),
                    (x_center - size, y_center + size)
                ])
                geometries.append(poly)
                geoid_list.append(terr_code)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "comarca":
        if region:
            # Region could be territory code or comarca code
            # Create placeholder comarcas
            num_comarcas = 5
            geometries = []
            geoid_list = []
            # Get the base region for positioning
            if len(region) == 2 and region in constants.TERRITORY_CODES:
                base_seed = int(region)
            else:
                base_seed = hash(region)
            
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
            
            for i in range(num_comarcas):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.5, 0.5), base_y + np.random.uniform(-0.5, 0.5)
                poly = Polygon([
                    (x-0.15, y-0.15), (x+0.15, y-0.15), (x+0.15, y+0.15), (x-0.15, y+0.15)
                ])
                geoid = f"{region}{str(i+1).zfill(2)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            # All comarcas
            all_comarcas = []
            for terr_code, comarcas in constants.COMARCAS_CODES.items():
                for c, name in comarcas.items():
                    all_comarcas.append(f"{terr_code}{c}")
            
            if not all_comarcas:
                gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
                gdf["GEOID"] = []
            else:
                geometries = []
                geoid_list = []
                for comarca_code in all_comarcas[:10]:  # Limit to first 10 for placeholder
                    seed = hash(comarca_code)
                    np.random.seed(seed)
                    x, y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
                    poly = Polygon([
                        (x-0.1, y-0.1), (x+0.1, y-0.1), (x+0.1, y+0.1), (x-0.1, y+0.1)
                    ])
                    geometries.append(poly)
                    geoid_list.append(comarca_code)
                gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
    elif level == "municipality":
        if region:
            # Region could be territory code or comarca code
            # Create placeholder municipalities
            num_muns = 10
            geometries = []
            geoid_list = []
            # Get the base region for positioning
            if len(region) == 2 and region in constants.TERRITORY_CODES:
                base_seed = int(region)
            elif len(region) == 3 and region[:2] in constants.TERRITORY_CODES:
                base_seed = int(region[:2])
            else:
                base_seed = hash(region)
            
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
            
            for i in range(num_muns):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.3, 0.3), base_y + np.random.uniform(-0.3, 0.3)
                poly = Polygon([
                    (x-0.05, y-0.05), (x+0.05, y-0.05), (x+0.05, y+0.05), (x-0.05, y+0.05)
                ])
                geoid = f"{region}{str(i+1).zfill(3)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            # All municipalities - this would be a lot, return empty for now
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "district":
        # Placeholder for districts/barrutiak
        if region:
            num_districts = 5
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
            
            for i in range(num_districts):
                seed = hash(f"{region}_dist_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.1, 0.1), base_y + np.random.uniform(-0.1, 0.1)
                poly = Polygon([
                    (x-0.03, y-0.03), (x+0.03, y-0.03), (x+0.03, y+0.03), (x-0.03, y+0.03)
                ])
                geoid = f"{region}001{str(i+1).zfill(2)}"
                geometries.append(poly)
                geoid_list.append(geoid)
            gdf = gpd.GeoDataFrame({"GEOID": geoid_list}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "section":
        # Placeholder for statistical areas
        if region:
            num_sections = 3
            geometries = []
            geoid_list = []
            base_seed = int(region) if region.isdigit() else hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
            
            for i in range(num_sections):
                seed = hash(f"{region}_sec_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.05, 0.05), base_y + np.random.uniform(-0.05, 0.05)
                poly = Polygon([
                    (x-0.015, y-0.015), (x+0.015, y-0.015), (x+0.015, y+0.015), (x-0.015, y+0.015)
                ])
                geoid = f"{region}00100{str(i+1).zfill(2)}"
                geometries.append(poly)
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
            base_x, base_y = np.random.uniform(-3.5, -1.0), np.random.uniform(42.0, 43.5)
            
            for i in range(num_blocks):
                seed = hash(f"{region}_block_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.02, 0.02), base_y + np.random.uniform(-0.02, 0.02)
                poly = Polygon([
                    (x-0.005, y-0.005), (x+0.005, y-0.005), (x+0.005, y+0.005), (x-0.005, y+0.005)
                ])
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
        regions: Region code(s) (territory codes, comarca codes, etc.).
            If None, returns all geometries at this level for the entire country.
        year: Vintage year (default 2021).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        regions = list(constants.TERRITORY_CODES.keys())
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
    """Return the Eustat codes of every territory intersecting ``aoi``.

    This function is kept for compatibility with the USA implementation.
    In Euskadi, the equivalent of states are historical territories.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021).

    Returns:
        List of two-digit territory codes.
    """
    return territories_in_aoi(aoi, year)


__all__ = [
    "GEOMETRY_FUNCS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "territories_in_aoi",
    "comarcas_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
