"""A DEM GeoTIFF (from `pycensus.geography.dem.load`) cut into terrarium PNG tiles, for the 3D view of a map.

`write_terrarium_tiles(dem, out_dir, bounds, zmin, zmax)`   `<out_dir>/{z}/{x}/{y}.png` in the terrarium encoding (R*256 + G + B/256 - 32768 metres)
                            that MapLibre's raster-dem source reads (`encoding: "terrarium"`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np



def _encode(elev: np.ndarray) -> np.ndarray:
    v = np.clip(elev, -11000, 9000) + 32768.0
    r = np.floor(v / 256.0)
    g = np.floor(v % 256.0)
    b = np.floor((v - np.floor(v)) * 256.0)
    return np.dstack([r, g, b]).astype(np.uint8)


def write_terrarium_tiles(dem, out_dir, bounds, zmin: int = 7, zmax: int = 11) -> dict:
    """Cut the DEM (a GeoTIFF) into terrarium tiles over `bounds` (west, south, east, north) for zooms `zmin`..`zmax`; returns `{tiles, mb}`."""
    import mercantile
    import rasterio
    from PIL import Image
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, reproject

    out, count, size = Path(out_dir), 0, 0
    with rasterio.open(dem) as src:
        band = src.read(1).astype("float32")
        if src.nodata is not None:
            band[band == src.nodata] = 0.0
        band = np.nan_to_num(band, nan=0.0)
        for t in mercantile.tiles(*bounds, range(zmin, zmax + 1)):
            xy = mercantile.xy_bounds(t)
            dst = np.zeros((256, 256), np.float32)
            reproject(band, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=from_bounds(*xy, 256, 256), dst_crs="EPSG:3857",
                      resampling=Resampling.bilinear)
            f = out / str(t.z) / str(t.x) / f"{t.y}.png"
            f.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(_encode(dst)).save(f, optimize=True)
            count += 1
            size += f.stat().st_size
    return {"tiles": count, "mb": round(size / 1e6, 1)}
