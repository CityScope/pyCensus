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


CACHE_ENV_VAR = "PYCENSUS_CACHE_DIR"


def get_cache_dir(
    namespace: str = "",
    cache_dir: "Optional[Union[str, Path]]" = None,
    create: bool = True,
) -> Path:
    """Resolve a cache folder without ever touching the current working directory.

    Resolution order:

    1. ``cache_dir`` if given -- returned exactly as passed (no namespace added).
    2. Environment variable ``PYCENSUS_CACHE_DIR`` -> ``<env>/<namespace>``.
    3. A temporary folder: ``<tempdir>/pycensus-cache/<namespace>``.

    Args:
        namespace: Sub-folder name (may contain ``/``), e.g. ``"elections"`` or
            ``"data/spain"``. Ignored when ``cache_dir`` is explicit.
        cache_dir: Explicit folder (highest priority).
        create: Create the folder (and parents) if missing.
    """
    import os
    import tempfile

    if cache_dir:
        path = Path(cache_dir)
    else:
        env = os.environ.get(CACHE_ENV_VAR)
        root = Path(env).expanduser() if env else Path(tempfile.gettempdir()) / "pycensus-cache"
        path = root / namespace if namespace else root
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir(country: str, data_dir: "Optional[Union[str, Path]]" = None) -> Path:
    """Base folder for a country's raw downloads (``<base>/raw/<source>`` is added by loaders).

    Explicit ``data_dir`` is returned unchanged; otherwise
    ``PYCENSUS_CACHE_DIR/data/<country>`` or ``<tempdir>/pycensus-cache/data/<country>``.
    The folder is not created here; loaders create sub-folders when they write.

    Args:
        country: Country module name (``"usa"``, ``"eu"``...).
        data_dir: Explicit folder; returned as is.

    Returns:
        The folder (not created).
    """
    return get_cache_dir(f"data/{country}", data_dir, create=False)


WORLDPOP_ENV_VAR = "PYCENSUS_WORLDPOP_DIR"


def get_worldpop_dir(folder: "Optional[Union[str, Path]]" = None, create: bool = True) -> Path:
    """Folder for WorldPop rasters: explicit ``folder``, else ``$PYCENSUS_WORLDPOP_DIR``, else the ``worldpop`` cache namespace.

    Args:
        folder: Explicit folder.
        create: Create the folder if missing.

    Returns:
        The folder.
    """
    import os

    env = os.environ.get(WORLDPOP_ENV_VAR)
    return get_cache_dir("worldpop", folder or env, create)


def default_cache_dir() -> str:
    """Default root of the parquet cache (env var or temp folder; see :func:`get_cache_dir`)."""
    return str(get_cache_dir("parquet", create=False))


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
    """Read a cached GeoDataFrame, or ``None`` if the file doesn't exist yet.

    Args:
        path: Parquet file.

    Returns:
        The GeoDataFrame, or None.
    """
    path = Path(path)
    return gpd.read_parquet(path) if path.exists() else None


def write_cache(path: Union[str, Path], gdf: gpd.GeoDataFrame) -> None:
    """Write a GeoDataFrame to the cache, creating parent directories as needed.

    Args:
        path: Parquet file.
        gdf: Data to write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path)


def _with_missing_as_nan(gdf: gpd.GeoDataFrame, columns: List[str]) -> gpd.GeoDataFrame:
    """Add every requested column the fetch did not return, as NaN (the source does not publish it for this level / region)."""
    absent = [c for c in columns if c not in gdf.columns]
    if absent:
        gdf = gdf.assign(**{c: float("nan") for c in absent})
    return gdf


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
        gdf = _with_missing_as_nan(gdf, columns)
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
        cached = _with_missing_as_nan(cached, columns)   # a column the source does not publish at this level: NaN, never 0

    if missing or not path.exists():
        write_cache(path, cached)

    return cached[[id_col, cached.geometry.name, *columns]]
