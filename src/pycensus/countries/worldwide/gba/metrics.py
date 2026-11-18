"""Building metrics from GBA footprints, per h3 cell, per polygon or per raster pixel.

Per building: `height` (m), `footprint_m2`, `built_m2` = footprint_m2 x height / 3 (floor area, one floor per 3 m). A footprint without
a GBA height takes the median height of the footprints of its h3 res-8 cell (or of the whole set) -- `fill_heights`.

Per zone (a building belongs to the zone holding its centroid), with the global-schema names:

    buildingCount                  number of footprints
    buildingFootprintArea          sum of footprint_m2
    builtFloorArea                 sum of built_m2
    buildingHeightMax / Median     max / footprint-area-weighted median of height
    buildingFootprintMax / Median  max / footprint-area-weighted median of footprint_m2
    builtFloorAreaMax / Median     max / footprint-area-weighted median of built_m2 (per building)
"""
from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
FLOOR_HEIGHT_M = 3.0
METRIC_COLUMNS = ("buildingCount", "buildingFootprintArea", "builtFloorArea", "buildingHeightMax", "buildingHeightMedian",
                  "buildingFootprintMax", "buildingFootprintMedian", "builtFloorAreaMax", "builtFloorAreaMedian")


def fill_heights(b: gpd.GeoDataFrame, resolution: int = 8) -> gpd.GeoDataFrame:
    """Copy of `b` with `height` filled where GBA has none (median of its res-`resolution` h3 cell, else of all), `height_filled` flag,
    and `built_m2`.

    Args:
        b: GBA buildings.
        resolution: H3 resolution of the medians.
    """
    import h3

    b = b.copy()
    c = b.geometry.centroid
    b["_lat"], b["_lon"] = c.y.to_numpy(), c.x.to_numpy()
    miss = ~(b["height"].astype(float) > 0)
    b["height_filled"] = miss
    if miss.any():
        cell = pd.Series([h3.latlng_to_cell(a, o, resolution) for a, o in zip(b["_lat"], b["_lon"])], index=b.index)
        med = b.loc[~miss, "height"].groupby(cell[~miss]).median()
        overall = float(b.loc[~miss, "height"].median()) if (~miss).any() else 2 * FLOOR_HEIGHT_M
        b.loc[miss, "height"] = cell[miss].map(med).fillna(overall).to_numpy()
        logger.info(f"GBA heights filled for {int(miss.sum()):,} of {len(b):,} footprints ({miss.mean():.1%})")
    b["built_m2"] = b["footprint_m2"] * b["height"] / FLOOR_HEIGHT_M
    return b.drop(columns=["_lat", "_lon"])


def _weighted_median(values: np.ndarray, weights: np.ndarray, groups: np.ndarray) -> pd.Series:
    """Per group, the weighted median of `values` (the smallest value whose cumulative weight reaches half the group's weight)."""
    order = np.lexsort((values, groups))
    g, v, w = groups[order], values[order], weights[order]
    cum = pd.Series(w).groupby(g).cumsum().to_numpy()
    half = pd.Series(w).groupby(g).transform("sum").to_numpy() / 2
    first = pd.Series(np.where(cum >= half, np.arange(len(v)), len(v))).groupby(g).min()
    return pd.Series(v[first.to_numpy()], index=first.index)


def zone_metrics(b: gpd.GeoDataFrame, zone: pd.Series) -> pd.DataFrame:
    """`METRIC_COLUMNS` per zone id (`zone`: one id per building, NaN = outside every zone). `b` needs height, footprint_m2, built_m2.

    Args:
        b: Buildings with heights and areas.
        zone: Zone id per building.
    """
    ok = zone.notna().to_numpy()
    z = zone.to_numpy()[ok]
    if not len(z):
        return pd.DataFrame(columns=list(METRIC_COLUMNS))
    codes, uniq = pd.factorize(z)
    h, f, bm = (b[c].to_numpy(dtype=float)[ok] for c in ("height", "footprint_m2", "built_m2"))
    df = pd.DataFrame({"g": codes, "h": h, "f": f, "b": bm})
    agg = df.groupby("g").agg(buildingCount=("f", "size"), buildingFootprintArea=("f", "sum"), builtFloorArea=("b", "sum"),
                              buildingHeightMax=("h", "max"), buildingFootprintMax=("f", "max"), builtFloorAreaMax=("b", "max"))
    agg["buildingHeightMedian"] = _weighted_median(h, f, codes)
    agg["buildingFootprintMedian"] = _weighted_median(f, f, codes)
    agg["builtFloorAreaMedian"] = _weighted_median(bm, f, codes)
    agg.index = uniq[agg.index.to_numpy()]
    return agg[list(METRIC_COLUMNS)]


def h3_metrics(b: gpd.GeoDataFrame, resolution: int) -> pd.DataFrame:
    """`METRIC_COLUMNS` per h3 cell (index: cell id) at `resolution`, buildings by centroid.

    Args:
        b: Buildings with heights and areas.
        resolution: H3 resolution.
    """
    import h3ronpy
    import h3ronpy.vector as h3v

    c = b.geometry.centroid
    cells = h3ronpy.cells_to_string(h3v.coordinates_to_cells(c.y.to_numpy(), c.x.to_numpy(), resolution)).to_pylist()
    return zone_metrics(b, pd.Series(cells, index=b.index))


def polygon_metrics(b: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, id_col: str) -> pd.DataFrame:
    """`METRIC_COLUMNS` per polygon (index: `polygons[id_col]`), buildings by centroid.

    Args:
        b: Buildings with heights and areas.
        polygons: Zones.
        id_col: Zone id column.
    """
    pts = gpd.GeoDataFrame(geometry=b.geometry.centroid, crs=b.crs).to_crs(polygons.crs)
    j = gpd.sjoin(pts, polygons[[id_col, "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    return zone_metrics(b, j[id_col].reindex(b.index))


def built_area_raster(b: gpd.GeoDataFrame, template_tif: str, out_tif: Optional[str] = None, column: str = "built_m2"):
    """Sum of `column` per pixel of `template_tif`'s grid (e.g. the WorldPop raster), buildings by centroid. Returns (array, profile).

    Args:
        b: Buildings with ``built_m2``.
        template_tif: Raster whose grid is used.
        out_tif: Optional output GeoTIFF.
        column: Column summed.
    """
    import rasterio

    with rasterio.open(template_tif) as r:
        prof, tr, shape, crs = r.profile.copy(), r.transform, (r.height, r.width), r.crs
    c = gpd.GeoSeries(b.geometry.centroid, crs=b.crs).to_crs(crs)
    rows, cols = rasterio.transform.rowcol(tr, c.x.to_numpy(), c.y.to_numpy())
    rows, cols = np.asarray(rows), np.asarray(cols)
    ok = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    arr = np.zeros(shape, dtype="float64")
    np.add.at(arr, (rows[ok], cols[ok]), b[column].to_numpy(dtype=float)[ok])
    prof.update(dtype="float32", count=1, nodata=0, compress="deflate")
    if out_tif:
        with rasterio.open(out_tif, "w", **prof) as dst:
            dst.write(arr.astype("float32"), 1)
    return arr, prof
