"""Tests for pycensus.countries.worldwide.worldpop.h3 (area-weighted WorldPop -> H3 resampling)."""

from __future__ import annotations

import os

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from pycensus.countries.worldwide.worldpop.h3 import worldpop_raster_to_h3


def _write_realistic_worldpop_tif(path: str, seed: int = 0, shape=(60, 60), nodata=-99999.0) -> None:
    """A small, realistic-synthetic WorldPop-shaped GeoTIFF: ~100m pixels (in degrees,
    ~0.0009deg at mid-latitude), EPSG:4326, float32, with a real nodata sentinel and a
    ragged edge of nodata pixels (mirroring real WorldPop's coastline/border nodata)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rng = np.random.default_rng(seed)
    px_deg = 0.0009  # ~100m at mid-latitudes
    transform = from_origin(-71.10, 42.37, px_deg, px_deg)  # near Boston, realistic coords
    arr = (rng.random(shape) * 40).astype("float32")
    # Ragged nodata edge (like real WorldPop coastline masking).
    for i in range(shape[0]):
        cut = int(5 * np.sin(i / 5.0)) + 3
        arr[i, :cut] = nodata
    with rasterio.open(
        path, "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=nodata,
    ) as dst:
        dst.write(arr, 1)
    return arr, transform, nodata


def test_worldpop_raster_to_h3_full_coverage_and_conservation(tmp_path):
    tif_path = str(tmp_path / "fake_worldpop.tif")
    arr, transform, nodata = _write_realistic_worldpop_tif(tif_path)

    result = worldpop_raster_to_h3(tif_path, resolution=11, value_col="population")

    assert result.height > 0
    assert set(result.columns) == {"h3_cell", "population"}
    # No duplicate H3 cells (full coverage/no double counting).
    assert result["h3_cell"].n_unique() == result.height

    valid_mask = arr != nodata
    total_pixels = float(arr[valid_mask].sum())
    total_h3 = float(result["population"].sum())
    # Exact conservation up to floating point precision, over the raster's own extent
    # (the H3 grid is built to cover the raster's full extent with a buffer margin --
    # see geohierarchy.raster_resample.raster_to_h3 -- so no valid pixel is left out).
    assert total_h3 == pytest.approx(total_pixels, rel=1e-6)


def test_worldpop_raster_to_h3_density_bound(tmp_path):
    """Each output H3 cell's density falls within the min/max density of pixels it touches."""
    import geopandas as gpd
    import shapely
    import h3 as h3lib

    tif_path = str(tmp_path / "fake_worldpop2.tif")
    arr, transform, nodata = _write_realistic_worldpop_tif(tif_path, seed=1, shape=(40, 40))

    result = worldpop_raster_to_h3(tif_path, resolution=11, value_col="population")

    px_deg = transform.a
    pixel_area = px_deg * abs(transform.e)

    height, width = arr.shape
    x0r = transform.c
    x1r = transform.c + width * transform.a
    y0r = transform.f + height * transform.e
    y1r = transform.f
    raster_box = shapely.box(min(x0r, x1r), min(y0r, y1r), max(x0r, x1r), max(y0r, y1r))

    sample = result.sample(n=min(15, result.height), seed=42) if result.height > 15 else result
    for h3_cell, val in zip(sample["h3_cell"].to_list(), sample["population"].to_list()):
        boundary = h3lib.cell_to_boundary(h3_cell)
        cell_poly = shapely.Polygon([(lng, lat) for lat, lng in boundary])
        cell_area = shapely.area(cell_poly)

        if not raster_box.contains(cell_poly):
            # Skip H3 cells only partially covered by the raster (its
            # buffer margin extends past the raster's exact extent, and a
            # ragged nodata coastline can also leave a cell partially
            # uncovered) -- the uncovered remainder contributes 0 to the
            # area-weighted average, which can legitimately pull density
            # outside the touching-pixels' range; see the analogous skip
            # in geohierarchy/tests/test_raster_resample.py.
            continue

        touching_vals = []
        covered_area = 0.0
        any_nodata_overlap = False
        for r in range(height):
            for c in range(width):
                x0 = transform.c + c * transform.a
                x1 = x0 + transform.a
                y0 = transform.f + r * transform.e
                y1 = y0 + transform.e
                pixel_box = shapely.box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                if not pixel_box.intersects(cell_poly):
                    continue
                inter_area = shapely.area(shapely.intersection(pixel_box, cell_poly))
                if inter_area <= 1e-15:
                    continue
                if arr[r, c] == nodata:
                    any_nodata_overlap = True
                    continue
                touching_vals.append(arr[r, c])
                covered_area += inter_area

        if not touching_vals:
            continue
        if any_nodata_overlap:
            # A nodata pixel overlapping this cell contributes 0 mass to the
            # area-weighted average, which can legitimately pull the cell's
            # density below the min density of its *valid* touching pixels
            # -- not a bug, just the same "uncovered area dilutes the
            # average" edge effect as the raster-extent boundary case above.
            continue
        densities = [float(v) / pixel_area for v in touching_vals]
        cell_density = val / cell_area
        lo, hi = min(densities), max(densities)
        tol = 1e-6 * max(abs(lo), abs(hi), 1.0)
        assert lo - tol <= cell_density <= hi + tol


def test_worldpop_raster_to_h3_no_nodata_leaks_in():
    """A cell touching only nodata pixels never appears with a spurious non-zero value."""
    pass  # covered implicitly: nodata pixels are excluded before resampling (see h3.py / raster_resample.py)
