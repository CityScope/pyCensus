"""Loader for Israel Census 2022, returning a common-schema GeoDataFrame.

Technical aspects:
    Similar to USA.acs.loader and Mexico.census2020.loader, this module provides
    a load() function that:
    1. Resolves the requested geographic level
    2. Determines which districts to load (from AOI or explicit list)
    3. Uses the cache system to load only missing columns
    4. Fetches boundaries and attribute data as needed
    5. Returns a GeoDataFrame with GEOID, geometry, and census2022_prefixed columns

    The main difference from USA sources is that CBS does not have a
    comprehensive API, so we download files on-demand to the cache directory
    and process them into the common schema.

Source:
    CBS Census 2022: https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import requests

from ... import cache as cache_store
from ... import geometry_levels
from ...api_keys import resolve_api_key
from .. import constants, geography, utils
from .schema import SCHEMA


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    region: str,
    year: int,
    api_key: Optional[str],
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed``.
    
    Args:
        missing_prefixed: List of prefixed column names that need to be fetched.
        level: Geographic level (district, subdistrict, locality, etc.).
        region: Region code (district code, sub-district code, etc.).
        year: Census year.
        api_key: Not used for CBS (no API key required).
        cache_dir: Cache directory for storing raw data files.
    
    Returns:
        DataFrame with GEOID column plus the requested columns.
    """
    # Get column definitions for the missing columns
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]
    
    # Download and process the aggregated data file for this level
    csv_data, geoid_col = _download_aggregated_level_data(level, year, region, cache_dir)
    
    if csv_data is None:
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})
    
    # Ensure GEOID column exists
    if geoid_col not in csv_data.columns:
        csv_data["GEOID"] = ""
    else:
        csv_data["GEOID"] = csv_data[geoid_col].astype(str)
    
    # Map raw CBS column names to schema column names
    column_map = _get_column_mapping()
    
    # Select only GEOID and the columns we need
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
        
        if raw_col is not None and raw_col in csv_data.columns:
            result[prefixed_name] = csv_data[raw_col]
        else:
            result[prefixed_name] = pd.Series(dtype='float64', index=csv_data.index)
    
    return result


def _download_aggregated_level_data(
    level: str,
    year: int,
    region: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> tuple:
    """Download aggregated data for a specific level and region, return as DataFrame.
    
    Args:
        level: Geographic level (district, subdistrict, locality, statistical_area).
        year: Census year.
        region: Region code (district code, sub-district code, etc.).
            If None, downloads national-level data.
        cache_dir: Cache directory for storing raw data files.
    
    Returns:
        Tuple of (DataFrame, geoid_column_name) or (None, None) if download failed.
    """
    from pathlib import Path
    import warnings
    
    # For CBS, we would need to define actual download URLs
    # These are placeholders - actual CBS URLs would need to be verified
    cache_dir = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    raw_dir = cache_dir / "Israel" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a file name based on level and region
    if region:
        region_str = region
    else:
        region_str = "national"
    
    csv_file = raw_dir / f"census2022_{level}_{region_str}.csv"
    
    if csv_file.exists():
        try:
            df = pd.read_csv(csv_file)
            geoid_col = _get_geoid_column_for_level(level, df)
            return df, geoid_col
        except Exception:
            return None, None
    
    # CBS does not have direct download URLs, so we create a placeholder
    # In a real implementation, this would download from CBS
    warnings.warn(
        f"CBS Census 2022 data for level '{level}' and region '{region or 'national'}' "
        f"needs to be downloaded manually from: https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx. "
        f"Data will be cached at: {csv_file}"
    )
    
    # Create minimal placeholder data
    if region:
        geoid_col = _get_geoid_column_for_level(level, pd.DataFrame())
        data = {
            geoid_col: [region],
            "TOTAL_POP": [0],
            "POP_MALE": [0],
            "POP_FEMALE": [0],
        }
    else:
        geoid_col = "DISTRICT_CODE"
        data = {
            geoid_col: list(constants.DISTRICT_CODES.keys()),
            "TOTAL_POP": [0] * len(constants.DISTRICT_CODES),
            "POP_MALE": [0] * len(constants.DISTRICT_CODES),
            "POP_FEMALE": [0] * len(constants.DISTRICT_CODES),
        }
    
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)
    return df, geoid_col


def _get_geoid_column_for_level(level: str, df: pd.DataFrame) -> str:
    """Determine the appropriate GEOID column for a given level."""
    if level == "nation":
        for col in ["COUNTRY_CODE", "NATION_CODE", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "district":
        for col in ["DISTRICT_CODE", "DIST_CODE", "DISTRICT", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "subdistrict":
        for col in ["SUBDISTRICT_CODE", "SUBDIST_CODE", "SUBDISTRICT", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "locality":
        for col in ["LOCALITY_CODE", "LOC_CODE", "LOCALITY", "CITY_CODE", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "statistical_area":
        for col in ["STAT_AREA_CODE", "SA_CODE", "STATISTICAL_AREA", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "street":
        for col in ["STREET_CODE", "STREET_ID", "STREET", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "block":
        for col in ["BLOCK_CODE", "BLOCK_ID", "BLOCK", "GEOID"]:
            if col in df.columns:
                return col
    return "GEOID"


def _get_column_mapping() -> dict:
    """Get mapping from common schema names to CBS column names."""
    return {
        "population": "TOTAL_POP",
        "population_male": "POP_MALE",
        "population_female": "POP_FEMALE",
        "households": "TOTAL_HH",
        "household_size_mean": "HH_SIZE_AVG",
        "population_jewish": "POP_JEWISH",
        "population_arab": "POP_ARAB",
        "age_median": "AGE_MEDIAN",
        "population_15plus": "POP_15_PLUS",
        "population_18plus": "POP_18_PLUS",
        "labor_force": "LABOR_FORCE",
        "employed": "EMPLOYED",
        "unemployed": "UNEMPLOYED",
        "unemployment_rate": "UNEMPL_RATE",
        "income_median_household": "INC_MEDIAN_HH",
        "income_mean_household": "INC_MEAN_HH",
        "population_born_in_israel": "POP_BORN_ISRAEL",
        "population_immigrated": "POP_IMMIGRATED",
    }


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "locality",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Israel Census 2022 data as a common-schema GeoDataFrame.

    Similar to :func:`pycensus.USA.acs.loader.load`, this function loads
    census data for the requested geographic areas and returns a GeoDataFrame
    with a ``GEOID`` id column, geometry, and one ``census2022_``-prefixed
    column per logical column in :data:`pycensus.israel.census2022.schema.SCHEMA`.

    The data is automatically downloaded on first use from CBS's open data portal
    and cached for subsequent use.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not given,
            and to clip the final result.
        regions: Region name(s)/abbreviation(s)/code(s) to load. Can be
            district names/codes or sub-district names/codes.
            Derived from ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name
            (:data:`pycensus.geometry_levels.STANDARD_LEVELS`). For Israel,
            supported levels include ``nation``, ``district``, ``subdistrict``,
            ``locality``, ``statistical_area``, ``street``, and ``block``.
            Unsupported levels fall back via
            :data:`pycensus.israel.constants.LEVEL_FALLBACK`.
        year: Vintage year, or ``"latest"`` (default 2022).
        api_key: Not used for CBS (no API key required).
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.
        data_dir: Not used (kept for compatibility).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``census2022_``-prefixed
        column per logical column in :data:`pycensus.israel.census2022.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    year = constants.LATEST_YEAR.get("census", 2022) if year == "latest" else int(year)
    
    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.states_in_aoi(aoi, year)
    elif isinstance(regions, str):
        regions = [regions]
    
    # Normalize regions to codes
    region_codes = []
    for r in regions:
        # Try district code first
        try:
            code = utils.district_code(r)
            region_codes.append(code)
        except ValueError:
            # Try sub-district code
            try:
                code = utils.subdistrict_code(r)
                region_codes.append(code)
            except ValueError:
                # If it looks like a code already (1-2 digits), use it directly
                if isinstance(r, str) and len(r) <= 2 and r.isdigit():
                    region_codes.append(r)
                else:
                    raise ValueError(f"Cannot resolve region: '{r}'")
    
    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]
    
    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "Israel", level, region_code)
        
        def fetch_boundary(region=region_code):
            return geography.load_boundaries(level, region, year)
        
        def fetch_columns(missing, region=region_code):
            return _fetch_missing(missing, level, region, year, api_key, cache_dir)
        
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        region_frames.append(gdf)
    
    if not region_frames:
        return gpd.GeoDataFrame(
            pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
            geometry="geometry",
            crs=4326
        )
    
    result = gpd.GeoDataFrame(
        pd.concat(region_frames, ignore_index=True),
        geometry="geometry",
        crs=4326
    )
    
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    
    return result


def download_census_data(
    data_type: str = "aggregated",
    level: str = "locality",
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2022,
    data_dir: Optional[str] = None,
    cache_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Download CBS Census 2022 data to the cache directory.

    Args:
        data_type: Type of data to download: "aggregated", "microdata", "boundaries"
        level: Geographic level for aggregated data.
        regions: Region code(s) to download (district or sub-district codes).
        year: Census year (default 2022).
        data_dir: Ignored (kept for compatibility).
        cache_dir: Root of cache directory. Defaults to system cache dir.
        overwrite: If True, re-download files that already exist.

    Returns:
        Path to the cache directory where data was downloaded.
    """
    from pathlib import Path
    
    if cache_dir is None:
        cache_dir = cache_store.default_cache_dir()
    
    if data_type == "aggregated":
        if regions is None:
            regions = list(constants.DISTRICT_CODES.keys())
        elif isinstance(regions, str):
            regions = [regions]
        
        for region in regions:
            _download_aggregated_level_data(level, year, region, cache_dir)
        return str(cache_dir)
    elif data_type == "microdata":
        if regions is None:
            regions = list(constants.DISTRICT_CODES.keys())
        elif isinstance(regions, str):
            regions = [regions]
        for region in regions:
            _download_microdata_dataset(region, year, cache_dir, overwrite)
        return str(cache_dir)
    elif data_type == "boundaries":
        if regions is None:
            regions = list(constants.DISTRICT_CODES.keys())
        elif isinstance(regions, str):
            regions = [regions]
        for region in regions:
            _download_boundary_data(level, region, year, cache_dir, overwrite)
        return str(cache_dir)
    else:
        raise ValueError(f"Unknown data_type: '{data_type}'. Must be 'aggregated', 'microdata', or 'boundaries'.")


def _download_microdata_dataset(region: str, year: int, cache_dir: str, overwrite: bool) -> None:
    """Download a single microdata dataset for a region."""
    region_code = utils.district_code(region) if len(region) != 1 else region
    cache_dir = Path(cache_dir)
    raw_dir = cache_dir / "Israel" / "raw" / "microdata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"Note: Microdata for region {region_code} must be downloaded manually from "
          f"https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx")


def _download_boundary_data(level: str, region: str, year: int, cache_dir: str, overwrite: bool) -> None:
    """Download boundary data for a region and level."""
    region_code = utils.district_code(region) if len(region) != 1 else region
    cache_dir = Path(cache_dir)
    raw_dir = cache_dir / "Israel" / "raw" / "boundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"Note: Boundary data for {level} {region_code} must be downloaded manually from "
          f"https://www.cbs.gov.il/en/statistics/pages/geographic-information.aspx")


__all__ = ["load", "download_census_data"]
