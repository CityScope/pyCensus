"""Loader for Mexico Census 2020, returning a common-schema GeoDataFrame.

Technical aspects:
    Similar to USA.acs.loader, this module provides a load() function that:
    1. Resolves the requested geographic level
    2. Determines which states to load (from AOI or explicit list)
    3. Uses the cache system to load only missing columns
    4. Fetches boundaries and attribute data as needed
    5. Returns a GeoDataFrame with GEOID, geometry, and census2020_prefixed columns

    The main difference from USA sources is that INEGI does not have a
    comprehensive API, so we use file-based downloads via mexico.api
    instead of direct API calls.

Source:
    INEGI Census 2020: https://www.inegi.org.mx/programas/ccpv/2020/
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from ... import cache as cache_store
from ... import geometry_levels
from ...api_keys import resolve_api_key
from .. import api, constants, geography, utils
from .schema import SCHEMA


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    state: str,
    year: int,
    api_key: Optional[str],
    data_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed``.
    
    Args:
        missing_prefixed: List of prefixed column names that need to be fetched.
        level: Geographic level (state, municipality, etc.).
        state: State code or name.
        year: Census year.
        api_key: Not used for INEGI (no API key required).
        data_dir: Base directory for data files.
    
    Returns:
        DataFrame with GEOID column plus the requested columns.
    """
    # Get column definitions for the missing columns
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]
    
    # For now, fetch the aggregated data file for this level
    csv_path = api.fetch_aggregated_data(level, year, data_dir, overwrite=False)
    
    if csv_path is None:
        # Fallback: create empty DataFrame with correct structure
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})
    
    # Read the CSV file
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading {csv_path}: {e}")
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})
    
    # Build GEOID column based on level
    if level == "state":
        if "CVE_ENT" in df.columns:
            df["GEOID"] = df["CVE_ENT"].astype(str)
        elif "ENTIDAD" in df.columns:
            df["GEOID"] = df["ENTIDAD"].astype(str)
        else:
            df["GEOID"] = ""
    elif level == "municipality":
        if "CVE_ENT" in df.columns and "CVE_MUN" in df.columns:
            df["GEOID"] = df["CVE_ENT"].astype(str) + df["CVE_MUN"].astype(str).str.zfill(3)
        elif "ENTIDAD" in df.columns and "MUNICIPIO" in df.columns:
            df["GEOID"] = df["ENTIDAD"].astype(str) + df["MUNICIPIO"].astype(str).str.zfill(3)
        else:
            df["GEOID"] = ""
    elif level == "locality":
        if "CVE_ENT" in df.columns and "CVE_MUN" in df.columns and "CVE_LOC" in df.columns:
            df["GEOID"] = (df["CVE_ENT"].astype(str) + 
                          df["CVE_MUN"].astype(str).str.zfill(3) + 
                          df["CVE_LOC"].astype(str).str.zfill(4))
        else:
            df["GEOID"] = ""
    elif level == "ageb":
        if "CVE_ENT" in df.columns and "CVE_MUN" in df.columns and "CVE_AGEB" in df.columns:
            df["GEOID"] = (df["CVE_ENT"].astype(str) + 
                          df["CVE_MUN"].astype(str).str.zfill(3) + 
                          df["CVE_AGEB"].astype(str).str.zfill(4))
        else:
            df["GEOID"] = ""
    else:
        df["GEOID"] = ""
    
    df["GEOID"] = df["GEOID"].astype(str)
    
    # Map raw INEGI column names to schema column names
    # This is a simplified mapping - actual INEGI column names vary
    column_map = _get_column_mapping()
    
    # Select only GEOID and the columns we need
    result = pd.DataFrame({"GEOID": df["GEOID"]})
    
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        col_def = SCHEMA.columns[col_name]
        
        # Try to find matching raw column
        raw_col = None
        for code in col_def.codes:
            if code in df.columns:
                raw_col = code
                break
            # Try case-insensitive
            for c in df.columns:
                if c.upper() == code.upper():
                    raw_col = c
                    break
            if raw_col:
                break
        
        # Try the column map
        if raw_col is None:
            raw_col = column_map.get(col_name)
        
        if raw_col is not None and raw_col in df.columns:
            result[prefixed_name] = df[raw_col]
        else:
            result[prefixed_name] = pd.Series(dtype='float64', index=df.index)
    
    return result


def _get_column_mapping() -> Dict[str, str]:
    """Get mapping from common schema names to INEGI column names."""
    return {
        "population": "POBTOTAL",
        "population_male": "POBHOMBRES",
        "population_female": "POBMUJERES",
        "households": "HOGARES",
        "population_indigenous": "POBINDIG",
        "population_speaks_indigenous_language": "HABLANTES",
        "population_catholic": "POBCATOL",
        "employed": "POCOCUP",
        "unemployed": "POCDESOC",
        "households_renter": "HOGROENTA",
        "households_owner": "HOGPROP",
        "households_internet": "HOGINTER",
    }


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    states: Optional[Union[str, List[str]]] = None,
    level: str = "municipality",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Mexico Census 2020 data as a common-schema GeoDataFrame.

    Similar to :func:`pycensus.USA.acs.loader.load`, this function loads
    census data for the requested geographic areas and returns a GeoDataFrame
    with a ``GEOID`` id column, geometry, and one ``census2020_``-prefixed
    column per logical column in :data:`pycensus.mexico.census2020.schema.SCHEMA`.

    Args:
        aoi: Area of interest. Used to auto-detect ``states`` if not given,
            and to clip the final result.
        states: State name(s)/abbreviation(s)/code(s) to load. Derived from
            ``aoi`` if omitted (``aoi`` is then required).
        level: Standard geometry level name
            (:data:`pycensus.geometry_levels.STANDARD_LEVELS`). For Mexico,
            supported levels include ``nation``, ``state``, ``municipality``,
            ``locality``, ``ageb`` (tract equivalent), and ``block`` (manzana).
            Unsupported levels fall back via
            :data:`pycensus.mexico.constants.LEVEL_FALLBACK`.
        year: Vintage year, or ``"latest"`` (default 2020).
        api_key: Not used for INEGI (no API key required).
        cache_dir: Root of pyCensus' parquet cache. Defaults to
            :func:`pycensus.cache.default_cache_dir`.
        cache: If ``False``, bypass the cache entirely -- always fetch
            fresh and don't persist the result.
        data_dir: Root directory for INEGI data files. Defaults to
            ``data/mexico``.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``census2020_``-prefixed
        column per logical column in :data:`pycensus.mexico.census2020.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``states`` nor ``aoi`` is given.
    """
    # Resolve level with fallbacks
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    
    # Resolve year
    year = constants.LATEST_YEAR.get("census", 2020) if year == "latest" else int(year)
    
    # Resolve states
    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi, year)
    elif isinstance(states, str):
        states = [states]
    
    # Convert states to codes
    state_codes = [utils.state_code(s) for s in states]
    
    # Get all column names from schema
    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]
    
    # Load data for each state
    state_frames = []
    for state_code in state_codes:
        # Build cache path: cache_dir/Mexico/level/state_code.parquet
        path = cache_store.region_path(cache_dir, "Mexico", level, state_code)
        
        # Define boundary fetch function
        def fetch_boundary(state=state_code):
            return geography.load_boundaries(level, state, year)
        
        # Define column fetch function
        def fetch_columns(missing, state=state_code):
            return _fetch_missing(missing, level, state, year, api_key, data_dir)
        
        # Load region data using cache
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        state_frames.append(gdf)
    
    # Concatenate all state dataframes
    if not state_frames:
        # Return empty GeoDataFrame with correct structure
        return gpd.GeoDataFrame(
            pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
            geometry="geometry",
            crs=4326
        )
    
    result = gpd.GeoDataFrame(
        pd.concat(state_frames, ignore_index=True),
        geometry="geometry",
        crs=4326
    )
    
    # Clip to AOI if provided
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    
    return result


def download_census_data(
    data_type: str = "aggregated",
    level: str = "municipality",
    states: Optional[Union[str, List[str]]] = None,
    year: int = 2020,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Download INEGI Census 2020 data to the local data directory.

    This is a convenience function that wraps the fetch functions from
    :mod:`pycensus.mexico.api`. For more fine-grained control, use the
    api functions directly.

    Args:
        data_type: Type of data to download:
            - ``"aggregated"``: Pre-aggregated tables by geographic level
            - ``"microdata"``: Person, household, or housing microdata
            - ``"boundaries"``: Geographic boundary files
        level: Geographic level for aggregated data (``"state"``,
            ``"municipality"``, ``"locality"``, ``"ageb"``). Only used if
            ``data_type == "aggregated"``.
        states: State code(s) to download. If None, downloads all states.
            Only used if ``data_type == "microdata"`` or ``"boundaries"``.
        year: Census year (default 2020).
        data_dir: Base directory for downloads. Defaults to ``data/mexico/``.
        overwrite: If ``True``, re-download files that already exist.

    Returns:
        Path to the directory where data was downloaded.

    Raises:
        ValueError: If ``data_type`` is not recognized.
    """
    from pathlib import Path
    
    if data_type == "aggregated":
        api.fetch_aggregated_data(level, year, data_dir, overwrite)
        return str(_get_data_dir(data_dir))
    elif data_type == "microdata":
        if states is None:
            states = list(constants.STATE_CODES.keys())
        elif isinstance(states, str):
            states = [states]
        
        for state in states:
            for dataset in ["personas", "hogares", "viviendas"]:
                api.fetch_microdata(dataset, state, year, data_dir, overwrite)
        return str(_get_data_dir(data_dir))
    elif data_type == "boundaries":
        if states is None:
            states = list(constants.STATE_CODES.keys())
        elif isinstance(states, str):
            states = [states]
        
        for state in states:
            api.fetch_boundaries(level, state, year, data_dir, overwrite)
        return str(_get_data_dir(data_dir))
    else:
        raise ValueError(
            f"Unknown data_type: '{data_type}'. "
            f"Must be 'aggregated', 'microdata', or 'boundaries'."
        )


def _get_data_dir(data_dir: Optional[str] = None) -> Path:
    """Get the data directory path."""
    if data_dir is None:
        data_dir = constants.DEFAULT_DATA_DIR
    return Path(data_dir)


__all__ = ["load", "download_census_data"]
