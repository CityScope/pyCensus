"""Boundary fetching for Germany census."""

from __future__ import annotations
from typing import List, Optional, Union
import geopandas as gpd
import numpy as np
import pandas as pd
from .. import geometry_levels
from . import constants, utils

GEOMETRY_FUNCS = {
    "nation": None,
    "state": None,
    "district": None,
    "municipality": None,
}

GEO_HIERARCHIES = {
    "municipality": ["nation", "state", "district", "municipality"],
    "district": ["nation", "state", "district"],
    "state": ["nation", "state"],
    "nation": ["nation"],
}

ERASE_WATER: dict = {
    "nation": False,
    "state": False,
    "district": False,
    "municipality": True,
}


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2022) -> List[str]:
    return list(constants.STATE_CODES.keys())


def load_boundaries(level: str, region: Optional[str] = None, year: int = 2022, erase_water: Optional[bool] = None) -> gpd.GeoDataFrame:
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    if level not in GEOMETRY_FUNCS:
        raise KeyError(f"Unknown geography level '{level}'")
    if erase_water is None:
        erase_water = ERASE_WATER.get(level, False)
    import warnings
    warnings.warn(f"No geographic data source for level '{level}'. Using placeholders. Get real data from https://www.destatis.de/")
    from shapely.geometry import Polygon
    if level == "nation":
        coords = [(5.5, 47.0), (5.5, 55.0), (15.5, 55.0), (15.5, 47.0)]
        gdf = gpd.GeoDataFrame({"GEOID": ["DEU"]}, geometry=[Polygon(coords)], crs="EPSG:4326")
    elif level == "state":
        if region:
            code = utils.state_code(region)
            seed = hash(code)
            np.random.seed(seed)
            x, y = np.random.uniform(5.5, 15.5), np.random.uniform(47.0, 55.0)
            size = np.random.uniform(0.5, 2.0)
            poly = Polygon([(x-size, y-size), (x+size, y-size), (x+size, y+size), (x-size, y+size)])
            gdf = gpd.GeoDataFrame({"GEOID": [code]}, geometry=[poly], crs="EPSG:4326")
        else:
            geometries, geoids = [], []
            for code in constants.STATE_CODES.keys():
                seed = hash(code)
                np.random.seed(seed)
                x, y = np.random.uniform(5.5, 15.5), np.random.uniform(47.0, 55.0)
                size = np.random.uniform(0.5, 2.0)
                poly = Polygon([(x-size, y-size), (x+size, y-size), (x+size, y+size), (x-size, y+size)])
                geometries.append(poly)
                geoids.append(code)
            gdf = gpd.GeoDataFrame({"GEOID": geoids}, geometry=geometries, crs="EPSG:4326")
    elif level == "district":
        if region:
            num = 10
            base_seed = hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(5.5, 15.5), np.random.uniform(47.0, 55.0)
            geometries, geoids = [], []
            for i in range(num):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-1, 1), base_y + np.random.uniform(-1, 1)
                poly = Polygon([(x-0.2, y-0.2), (x+0.2, y-0.2), (x+0.2, y+0.2), (x-0.2, y+0.2)])
                geometries.append(poly)
                geoids.append(f"{region}{str(i+1).zfill(3)}")
            gdf = gpd.GeoDataFrame({"GEOID": geoids}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    elif level == "municipality":
        if region:
            num = 5
            base_seed = hash(region)
            np.random.seed(base_seed)
            base_x, base_y = np.random.uniform(5.5, 15.5), np.random.uniform(47.0, 55.0)
            geometries, geoids = [], []
            for i in range(num):
                seed = hash(f"{region}_{i}")
                np.random.seed(seed)
                x, y = base_x + np.random.uniform(-0.2, 0.2), base_y + np.random.uniform(-0.2, 0.2)
                poly = Polygon([(x-0.05, y-0.05), (x+0.05, y-0.05), (x+0.05, y+0.05), (x-0.05, y+0.05)])
                geometries.append(poly)
                geoids.append(f"{region}{str(i+1).zfill(5)}")
            gdf = gpd.GeoDataFrame({"GEOID": geoids}, geometry=geometries, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf["GEOID"] = []
    else:
        gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        gdf["GEOID"] = []
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf[["GEOID", "geometry"]]


__all__ = ["GEOMETRY_FUNCS", "GEO_HIERARCHIES", "ERASE_WATER", "states_in_aoi", "load_boundaries"]
