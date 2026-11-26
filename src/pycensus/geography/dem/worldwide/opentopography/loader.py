"""OpenTopography global DEM API: one GeoTIFF per bounding box."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import geopandas as gpd
import numpy as np

API_URL = "https://portal.opentopography.org/API/globaldem"


def load(aoi: gpd.GeoDataFrame, cache: Path, model: str, margin: float, refresh: bool) -> Path:
    """Download (once) the DEM `model` of the AOI's box plus `margin`; returns the cached GeoTIFF."""
    import requests

    from pycensus.api_keys import resolve_api_key

    w, s, e, n = aoi.to_crs(4326).total_bounds
    dx, dy = (e - w) * margin, (n - s) * margin
    box = np.round([w - dx, s - dy, e + dx, n + dy], 5)
    path = cache / f"{model}_{hashlib.sha1(box.tobytes()).hexdigest()[:12]}.tif"
    if path.is_file() and not refresh:
        return path
    key = resolve_api_key("opentopography", "OPENTOPOGRAPHY_API_KEY")
    if not key:
        raise RuntimeError("No OpenTopography API key: get a free one at https://opentopography.org (account page, request an API key) and save it "
                           "as 'opentopography' in ~/.config/ptlos/api_keys.json or set OPENTOPOGRAPHY_API_KEY.")
    params = {"demtype": model, "west": box[0], "south": box[1], "east": box[2], "north": box[3], "outputFormat": "GTiff", "API_Key": key}
    r = requests.get(API_URL, params=params, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(f"OpenTopography download failed (HTTP {r.status_code}): {r.text[:200]}")
    path.write_bytes(r.content)
    time.sleep(1.0)   # never a burst of requests
    return path
