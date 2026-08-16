"""Loader for Germany Census 2022."""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Union
import geopandas as gpd
import pandas as pd
import warnings

from ... import cache as cache_store, geometry_levels
from .. import constants, geography, utils
from .schema import SCHEMA


def _fetch_missing(missing_prefixed, level, region, year, api_key, cache_dir):
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]
    csv_data, geoid_col = _download_aggregated_level_data(level, year, region, cache_dir)
    if csv_data is None:
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})
    csv_data["GEOID"] = csv_data[geoid_col].astype(str) if geoid_col in csv_data.columns else ""
    column_map = _get_column_mapping()
    result = pd.DataFrame({"GEOID": csv_data["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        raw_col = None
        for code in col_def.codes:
            if code in csv_data.columns:
                raw_col = code
                break
            for c in csv_data.columns:
                if c.upper() == code.upper():
                    raw_col = c
                    break
            if raw_col:
                break
        if raw_col is None:
            raw_col = column_map.get(col_name)
        result[prefixed_name] = csv_data[raw_col] if raw_col and raw_col in csv_data.columns else pd.Series(dtype='float64', index=csv_data.index)
    return result


def _download_aggregated_level_data(level, year, region, cache_dir):
    from pathlib import Path
    cache_dir = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    raw_dir = cache_dir / "Germany" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    region_str = region or "national"
    csv_file = raw_dir / f"census2022_{level}_{region_str}.csv"
    if csv_file.exists():
        try:
            df = pd.read_csv(csv_file)
            return df, _get_geoid_column_for_level(level, df)
        except Exception:
            return None, None
    warnings.warn(f"Destatis data for {level}/{region or 'national'} must be downloaded manually from https://www.destatis.de/")
    geoid_col = _get_geoid_column_for_level(level, pd.DataFrame())
    if region:
        data = {geoid_col: [region], "POP_TOTAL": [0], "POP_MALE": [0], "POP_FEMALE": [0]}
    else:
        data = {geoid_col: list(constants.STATE_CODES.keys()), "POP_TOTAL": [0]*16, "POP_MALE": [0]*16, "POP_FEMALE": [0]*16}
    pd.DataFrame(data).to_csv(csv_file, index=False)
    return pd.DataFrame(data), geoid_col


def _get_geoid_column_for_level(level, df):
    cols = {"nation": ["COUNTRY_CODE", "GEOID"], "state": ["STATE_CODE", "AGS", "GEOID"], "district": ["DIST_CODE", "AGS", "GEOID"], "municipality": ["MUN_CODE", "AGS", "GEOID"]}
    for c in cols.get(level, ["GEOID"]):
        if c in df.columns:
            return c
    return "GEOID"


def _get_column_mapping():
    return {"population": "POP_TOTAL", "population_male": "POP_MALE", "population_female": "POP_FEMALE", "households": "HH_TOTAL", "age_median": "AGE_MED", "population_german": "POP_GERMAN", "labor_force": "LABOR_F", "employed": "EMPLOYED", "income_median_household": "INC_MED_HH"}


def load(aoi=None, regions=None, level="municipality", year="latest", api_key=None, cache_dir=None, cache=True, data_dir=None):
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    year = constants.LATEST_YEAR.get("census", 2022) if year == "latest" else int(year)
    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi, year)
    elif isinstance(regions, str):
        regions = [regions]
    region_codes = [utils.state_code(r) for r in regions]
    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]
    region_frames = []
    for rc in region_codes:
        path = cache_store.region_path(cache_dir, "Germany", level, rc)
        gdf = cache_store.load_region(path, id_col="GEOID", columns=columns,
            fetch_boundary=lambda r=rc: geography.load_boundaries(level, r, year),
            fetch_columns=lambda m, r=rc: _fetch_missing(m, level, r, year, api_key, cache_dir),
            use_cache=cache)
        region_frames.append(gdf)
    if not region_frames:
        return gpd.GeoDataFrame(pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}), geometry="geometry", crs=4326)
    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return result


def download_census_data(data_type="aggregated", level="municipality", regions=None, year=2022, data_dir=None, cache_dir=None, overwrite=False):
    if cache_dir is None:
        cache_dir = cache_store.default_cache_dir()
    if data_type == "aggregated":
        if regions is None:
            regions = list(constants.STATE_CODES.keys())
        elif isinstance(regions, str):
            regions = [regions]
        for r in regions:
            _download_aggregated_level_data(level, year, r, cache_dir)
        return str(cache_dir)
    elif data_type in ["microdata", "boundaries"]:
        if regions is None:
            regions = list(constants.STATE_CODES.keys())
        elif isinstance(regions, str):
            regions = [regions]
        for r in regions:
            print(f"Note: {data_type} for {r} must be downloaded manually from https://www.destatis.de/")
        return str(cache_dir)
    else:
        raise ValueError(f"Unknown data_type: '{data_type}'")


__all__ = ["load", "download_census_data"]
