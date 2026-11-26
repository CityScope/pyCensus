"""Elevation (DEM) downloaders (``pycensus.geography.dem``): one function per use, sources in ``worldwide/`` (global) and ``countries/`` (a
national model finer than the global ones, when one is added).

    from pycensus.geography import dem
    path = dem.load(aoi, cache_dir)                    # a GeoTIFF of the AOI's bounding box (Copernicus GLO-30 by default), cached
    path = dem.load(aoi, cache_dir, source="SRTMGL1")  # another global model of OpenTopography
    dem.write_terrarium_tiles(path, "tiles/", bounds)  # the DEM as terrarium PNG tiles (z/x/y.png) for a map's 3D terrain

The global source (OpenTopography) needs a free API key: sign up at https://opentopography.org, then request a key on the account page. It is
read from the environment variable OPENTOPOGRAPHY_API_KEY or the entry ``opentopography`` of ``~/.config/ptlos/api_keys.json``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import geopandas as gpd

#: DEM models of the global source, by OpenTopography name: resolution and what they are
MODELS = {"COP30": "Copernicus GLO-30, 30 m (default)", "COP90": "Copernicus GLO-90, 90 m", "SRTMGL1": "SRTM, 30 m (60N-56S)",
          "SRTMGL3": "SRTM, 90 m (60N-56S)", "AW3D30": "ALOS World 3D, 30 m"}
DEFAULT_MODEL = "COP30"


def cache_root(cache_dir) -> Path:
    """The DEM cache folder (created): ``<cache_dir or the pycensus cache>/geography/dem``."""
    from pycensus.cache import default_cache_dir

    d = Path(cache_dir or default_cache_dir()) / "geography" / "dem"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(aoi: gpd.GeoDataFrame, cache_dir=None, source: str = DEFAULT_MODEL, margin: float = 0.05, refresh: bool = False) -> Path:
    """The GeoTIFF DEM of the AOI's bounding box (plus `margin` of its size), downloaded once (one request) and kept in the cache.

    Args:
        aoi: Area of interest.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        source: A key of ``MODELS``.
        margin: Extra border as a share of the box size.
        refresh: Download again even when cached.

    Returns:
        The path of the GeoTIFF.
    """
    from .worldwide.opentopography.loader import load as _load

    if source not in MODELS:
        raise ValueError(f"source must be one of {list(MODELS)}, not {source!r}")
    return _load(aoi, cache_root(cache_dir), source, margin, refresh)


from .tiles import write_terrarium_tiles  # noqa: E402,F401
