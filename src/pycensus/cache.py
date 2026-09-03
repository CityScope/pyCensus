"""Shared on-disk parquet cache: geometry and attribute columns, merged per level/region.

Technical aspects:
    One parquet file per (country, level, region) -- e.g.
    ``cache_dir/usa/tract/25.parquet`` for Massachusetts tracts -- holds the
    id column, geometry, and every attribute column ever fetched for it
    across every source (``dhc_*``, ``acs_*``, ``lodes_rac_*``, ...).
    :func:`load_region` checks which requested columns are already in that
    file; only the columns actually missing are fetched (via a
    caller-supplied callback) and merged back in before the file is
    rewritten, so repeated loads -- even across different sources -- never
    re-fetch a column already on disk.

    This is deliberately independent of pygris' own cache: every pygris
    call this package makes uses ``cache=False``, so pygris never writes to
    disk itself -- this module is pyCensus' only persistent cache.

Source:
    Parquet chosen for compact columnar storage and native GeoParquet
    support via `geopandas.read_parquet` / `GeoDataFrame.to_parquet`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Union

import geopandas as gpd
import platformdirs

if TYPE_CHECKING:
    import pandas as pd


def default_cache_dir() -> str:
    """OS-appropriate default cache directory, e.g. ``~/.cache/pycensus`` on Linux."""
    return platformdirs.user_cache_dir("pycensus")


def region_path(cache_dir: Optional[str], country: str, level: str, region: str) -> Path:
    """Build the cache file path for one (country, level, region) combination.

    Args:
        cache_dir: Root cache directory. Defaults to :func:`default_cache_dir`.
        country: Country code, e.g. ``"usa"``.
        level: Geometry level name.
        region: Region key within that level (e.g. a state FIPS code).

    Returns:
        Path to the merged parquet cache file for that combination.
    """
    root = Path(cache_dir) if cache_dir else Path(default_cache_dir())
    return root / country / level / f"{region}.parquet"


def read_cache(path: Union[str, Path]) -> Optional[gpd.GeoDataFrame]:
    """Read a cached GeoDataFrame, or ``None`` if the file doesn't exist yet."""
    path = Path(path)
    return gpd.read_parquet(path) if path.exists() else None


def write_cache(path: Union[str, Path], gdf: gpd.GeoDataFrame) -> None:
    """Write a GeoDataFrame to the cache, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path)


def load_region(
    path: Union[str, Path],
    id_col: str,
    columns: List[str],
    fetch_boundary: Callable[[], gpd.GeoDataFrame],
    fetch_columns: Callable[[List[str]], "pd.DataFrame"],
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load one level/region, fetching and persisting only what's missing from the cache.

    Args:
        path: Cache file path, from :func:`region_path`.
        id_col: Id column shared by boundary and attribute data (e.g. ``"GEOID"``).
        columns: Attribute column names the caller needs.
        fetch_boundary: Called to fetch geometry -- only when ``use_cache``
            is ``False``, or when no cache file exists yet. Must return a
            GeoDataFrame with ``id_col`` and geometry.
        fetch_columns: Called with the subset of ``columns`` missing from
            the cache (never called with an empty list). Must return a
            DataFrame with ``id_col`` and those columns.
        use_cache: If ``False``, skip reading and writing the cache file
            entirely and always fetch fresh (boundary + every column).

    Returns:
        GeoDataFrame with ``id_col``, geometry, and every column in
        ``columns``.
    """
    if not use_cache:
        gdf = fetch_boundary()
        if columns:
            fetched = fetch_columns(list(columns))
            new_cols = [c for c in fetched.columns if c != id_col]
            gdf = gdf.merge(fetched[[id_col, *new_cols]], on=id_col, how="left")
        return gdf[[id_col, gdf.geometry.name, *columns]]

    path = Path(path)
    cached = read_cache(path)
    if cached is None:
        cached = fetch_boundary()

    missing = [c for c in columns if c not in cached.columns]
    if missing:
        fetched = fetch_columns(missing)
        new_cols = [c for c in fetched.columns if c != id_col]
        cached = cached.merge(fetched[[id_col, *new_cols]], on=id_col, how="left")

    if missing or not path.exists():
        write_cache(path, cached)

    return cached[[id_col, cached.geometry.name, *columns]]
