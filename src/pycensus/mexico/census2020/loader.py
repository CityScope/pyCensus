"""Loader for Mexico Census 2020, returning a common-schema GeoDataFrame.

Technical aspects:
    Similar to USA.acs.loader, this module provides a load() function that:
    1. Resolves the requested geographic level
    2. Determines which states to load (from AOI or explicit list)
    3. Uses the cache system to load only missing columns
    4. Fetches boundaries and attribute data as needed
    5. Returns a GeoDataFrame with GEOID, geometry, and census2020_prefixed columns

    The main difference from USA sources is that INEGI does not have a
    comprehensive API, so we download files on-demand to the cache directory
    and process them into the common schema.

Source:
    INEGI Census 2020: https://www.inegi.org.mx/programas/ccpv/2020/
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import requests
import zipfile

from ... import cache as cache_store
from ... import geometry_levels
from ...api_keys import resolve_api_key
from .. import constants, geography, utils
from .schema import SCHEMA


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    state: str,
    year: int,
    api_key: Optional[str],
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed``.
    
    Args:
        missing_prefixed: List of prefixed column names that need to be fetched.
        level: Geographic level (state, municipality, etc.).
        state: State code or name.
        year: Census year.
        api_key: Not used for INEGI (no API key required).
        cache_dir: Cache directory for storing raw data files.
    
    Returns:
        DataFrame with GEOID column plus the requested columns.
    """
    # Get column definitions for the missing columns
    missing_defs = [SCHEMA.columns[SCHEMA.strip_prefix(c)] for c in missing_prefixed]
    
    # Download and process the aggregated data file for this level
    csv_data, geoid_col = _download_aggregated_level_data(level, year, cache_dir)
    
    if csv_data is None:
        return pd.DataFrame({"GEOID": [], **{c: [] for c in missing_prefixed}})
    
    # Ensure GEOID column exists
    if geoid_col not in csv_data.columns:
        csv_data["GEOID"] = ""
    else:
        csv_data["GEOID"] = csv_data[geoid_col].astype(str)
    
    # Map raw INEGI column names to schema column names
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
    cache_dir: Optional[str] = None,
) -> tuple:
    """Download aggregated data for a specific level and return as DataFrame.
    
    Args:
        level: Geographic level (state, municipality, locality, ageb).
        year: Census year.
        cache_dir: Cache directory for storing raw data files.
    
    Returns:
        Tuple of (DataFrame, geoid_column_name) or (None, None) if download failed.
    """
    from pathlib import Path
    
    aggregated_urls = {
        "state": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/entidad/entidad_cpv2020_csv.zip",
        "municipality": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/municipio/municipio_cpv2020_csv.zip",
        "locality": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/localidad/localidad_cpv2020_csv.zip",
        "ageb": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb/ageb_cpv2020_csv.zip",
    }
    
    if level not in aggregated_urls:
        return None, None
    
    if cache_dir is None:
        cache_dir = cache_store.default_cache_dir()
    cache_dir = Path(cache_dir)
    
    raw_dir = cache_dir / "Mexico" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    zip_file = raw_dir / f"census2020_{level}_aggregated.zip"
    csv_file = raw_dir / f"census2020_{level}_aggregated.csv"
    
    if csv_file.exists():
        try:
            df = pd.read_csv(csv_file)
            geoid_col = _get_geoid_column_for_level(level, df)
            return df, geoid_col
        except Exception:
            return None, None
    
    url = aggregated_urls[level]
    
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(zip_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
            if not csv_files:
                if url.endswith('.csv'):
                    df = pd.read_csv(zip_file)
                    geoid_col = _get_geoid_column_for_level(level, df)
                    df.to_csv(csv_file, index=False)
                    zip_file.unlink()
                    return df, geoid_col
                return None, None
            
            with zip_ref.open(csv_files[0]) as csv_in:
                df = pd.read_csv(csv_in)
            
            df.to_csv(csv_file, index=False)
            zip_file.unlink()
            geoid_col = _get_geoid_column_for_level(level, df)
            return df, geoid_col
            
    except Exception as e:
        if zip_file.exists():
            zip_file.unlink()
        return None, None


def _get_geoid_column_for_level(level: str, df: pd.DataFrame) -> str:
    """Determine the appropriate GEOID column for a given level."""
    if level == "state":
        for col in ["CVE_ENT", "ENTIDAD", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "municipality":
        for col in ["CVE_MUN", "MUNICIPIO", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "locality":
        for col in ["CVE_LOC", "LOCALIDAD", "GEOID"]:
            if col in df.columns:
                return col
    elif level == "ageb":
        for col in ["CVE_AGEB", "AGEB", "GEOID"]:
            if col in df.columns:
                return col
    return "GEOID"


def _get_column_mapping() -> dict:
    """Get mapping from common schema names to INEGI column names."""
    return {
        "population": "POBTOTAL",
        "population_male": "POBHOMBRES",
        "population_female": "POBMUJERES",
        "households": "HOGARES",
        "household_size_mean": "TAMHOG",
        "population_indigenous": "POBINDIG",
        "population_speaks_indigenous_language": "HABLANTES",
        "population_catholic": "POBCATOL",
        "population_protestant": "POBPROTE",
        "population_other_christian": "POBOTRA_CRIST",
        "population_none": "POBSIN_RELIGION",
        "employed": "POCOCUP",
        "unemployed": "POCDESOC",
        "labor_force": "PEA",
        "population_15plus": "POB15YMAS",
        "population_literate": "POBALFABETA",
        "households_owner": "HOGPROP",
        "households_renter": "HOGROENTA",
        "households_internet": "HOGINTERNET",
        "vehicles_per_household": "VEHICULOS_HOGAR",
        "income_median_household": "INGRESO_MEDIO",
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

    The data is automatically downloaded on first use from INEGI's open data portal
    and cached for subsequent use.

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
        data_dir: Not used (kept for compatibility).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``census2020_``-prefixed
        column per logical column in :data:`pycensus.mexico.census2020.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``states`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    year = constants.LATEST_YEAR.get("census", 2020) if year == "latest" else int(year)
    
    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi, year)
    elif isinstance(states, str):
        states = [states]
    
    state_codes = [utils.state_code(s) for s in states]
    columns = [SCHEMA.prefixed(name) for name in SCHEMA.columns]
    
    state_frames = []
    for state_code in state_codes:
        path = cache_store.region_path(cache_dir, "Mexico", level, state_code)
        
        def fetch_boundary(state=state_code):
            return geography.load_boundaries(level, state, year)
        
        def fetch_columns(missing, state=state_code):
            return _fetch_missing(missing, level, state, year, api_key, cache_dir)
        
        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        state_frames.append(gdf)
    
    if not state_frames:
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
    
    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    
    return result


def download_census_data(
    data_type: str = "aggregated",
    level: str = "municipality",
    states: Optional[Union[str, List[str]]] = None,
    year: int = 2020,
    data_dir: Optional[str] = None,
    cache_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """Download INEGI Census 2020 data to the cache directory.

    Args:
        data_type: Type of data to download: "aggregated", "microdata", "boundaries"
        level: Geographic level for aggregated data.
        states: State code(s) to download.
        year: Census year (default 2020).
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
        _download_aggregated_level_data(level, year, cache_dir)
        return str(cache_dir)
    elif data_type == "microdata":
        if states is None:
            states = list(constants.STATE_CODES.keys())
        elif isinstance(states, str):
            states = [states]
        for state in states:
            for dataset in ["personas", "hogares", "viviendas"]:
                _download_microdata_dataset(dataset, state, year, cache_dir, overwrite)
        return str(cache_dir)
    elif data_type == "boundaries":
        if states is None:
            states = list(constants.STATE_CODES.keys())
        elif isinstance(states, str):
            states = [states]
        for state in states:
            _download_boundary_data(level, state, year, cache_dir, overwrite)
        return str(cache_dir)
    else:
        raise ValueError(f"Unknown data_type: '{data_type}'. Must be 'aggregated', 'microdata', or 'boundaries'.")


def _download_microdata_dataset(dataset: str, state: str, year: int, cache_dir: str, overwrite: bool) -> None:
    """Download a single microdata dataset for a state."""
    state_code = utils.state_code(state)
    cache_dir = Path(cache_dir)
    raw_dir = cache_dir / "Mexico" / "raw" / "microdata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"Note: Microdata for {dataset} {state_code} must be downloaded manually from https://www.inegi.org.mx/app/descarga/default.html")


def _download_boundary_data(level: str, state: str, year: int, cache_dir: str, overwrite: bool) -> None:
    """Download boundary data for a state and level."""
    state_code = utils.state_code(state)
    cache_dir = Path(cache_dir)
    raw_dir = cache_dir / "Mexico" / "raw" / "boundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"Note: Boundary data for {level} {state_code} must be downloaded manually from https://www.inegi.org.mx/temas/geografia/")


__all__ = ["load", "download_census_data"]
