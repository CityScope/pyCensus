"""A population source from built floor area: people per built m2 (calibrated on WorldPop and the census) x built m2, on WorldPop's grid.

    from pycensus.countries.worldwide.gba import built_surface_population
    est, info = built_surface_population(built, worldpop, profile, census=census_polys, census_col="population", out_tif="...")

`built` / `worldpop`: arrays on the same grid (`gba.metrics.built_area_raster` onto the WorldPop raster). Per pixel:

  * inside a census polygon k: its census total C_k spread by built area, C_k * B / sum_k(B) (rate r_k = C_k / sum_k(B) people per
    built m2); a polygon without detected buildings keeps WorldPop's pattern, scaled to C_k;
  * outside the census (or with no census): WorldPop where it agrees with the built area (W >= `min_ratio` * r * B); where WorldPop is
    missing or far too low for what is built ("incongruent", e.g. villages WorldPop's settlement mask misses) r * B, with r the
    LOCAL rate: the built-area-weighted rate of the `k_nearest` census polygons (people per m2 differ a lot between, say, a city of
    apartment blocks and a town of large-family houses), or -- without a census -- WorldPop's own built-weighted median rate;
  * no building detected: WorldPop.

`info` reports the totals (WorldPop, census, estimate), the rates, and how many people the estimate adds where WorldPop was incongruent.
"""
from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)


def _weighted_median(v: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(v)
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, c[-1] / 2)]) if len(v) and c[-1] > 0 else float("nan")


def built_surface_population(built: np.ndarray, worldpop: np.ndarray, profile: dict, census: Optional[gpd.GeoDataFrame] = None,
                             census_col: str = "population", min_ratio: float = 0.25, k_nearest: int = 5,
                             out_tif: Optional[str] = None):
    """See the module docstring. Returns (estimate array, info dict).

    Args:
        built: Built floor area per pixel.
        worldpop: WorldPop population per pixel (same grid).
        profile: Raster profile of the grid.
        census: Optional census polygons with population.
        census_col: Census population column.
        min_ratio: WorldPop below this share of the built-surface estimate counts as missing.
        k_nearest: Census polygons used to calibrate a pixel outside the census.
        out_tif: Optional output GeoTIFF.
    """
    import rasterio
    from rasterio import features
    from scipy.spatial import cKDTree

    B = np.nan_to_num(np.asarray(built, dtype="float64"))
    W = np.nan_to_num(np.asarray(worldpop, dtype="float64"))
    W[W < 0] = 0
    tr, crs = profile["transform"], profile["crs"]
    est = W.copy()
    info = {"worldpop_total": float(W.sum()), "built_m2_total": float(B.sum())}
    both = (W > 0) & (B > 0)
    info["worldpop_rate_median"] = _weighted_median(W[both] / B[both], B[both]) if both.any() else float("nan")

    zone = np.full(B.shape, -1, dtype="int64")
    rates = None
    if census is not None and len(census):
        c = census.to_crs(crs).reset_index(drop=True)
        C = c[census_col].astype(float).fillna(0).to_numpy()
        zone = features.rasterize(((g, i) for i, g in enumerate(c.geometry)), out_shape=B.shape, transform=tr, fill=-1, dtype="int32").astype("int64")
        inz = zone >= 0
        sumB = np.bincount(zone[inz], weights=B[inz], minlength=len(c))
        sumW = np.bincount(zone[inz], weights=W[inz], minlength=len(c))
        rates = np.where(sumB > 0, C / np.where(sumB > 0, sumB, 1), np.nan)
        zi = zone[inz]
        est[inz] = np.where(sumB[zi] > 0, rates[zi] * B[inz], np.where(sumW[zi] > 0, W[inz] * C[zi] / np.where(sumW[zi] > 0, sumW[zi], 1), 0.0))
        info.update(census_total=float(C.sum()), census_in_grid=float(est[inz].sum()),
                    census_rate_median=_weighted_median(rates[np.isfinite(rates)], sumB[np.isfinite(rates)]))
        # the local rate of every pixel outside the census: the k nearest census polygons with buildings, weighted by their built area
        ok = np.isfinite(rates) & (sumB > 0)
        cen = c.geometry.representative_point()
        tree = cKDTree(np.column_stack([cen.x.to_numpy()[ok], cen.y.to_numpy()[ok]]))
        rr, ww = rates[ok], sumB[ok]
    out = (zone < 0) & (B > 0)
    if out.any():
        rows, cols = np.nonzero(out)
        if rates is not None and len(rr):
            xs, ys = rasterio.transform.xy(tr, rows, cols)
            k = min(k_nearest, len(rr))
            _, nn = tree.query(np.column_stack([xs, ys]), k=k)
            nn = nn.reshape(len(rows), k)
            r_local = (rr[nn] * ww[nn]).sum(1) / ww[nn].sum(1)
        else:
            r_local = np.full(len(rows), info["worldpop_rate_median"])
        expected = r_local * B[rows, cols]
        bad = ~(W[rows, cols] >= min_ratio * expected) & np.isfinite(expected)
        est[rows[bad], cols[bad]] = expected[bad]
        info.update(outside_census_worldpop=float(W[out].sum()), outside_census_estimate=float(est[out].sum()),
                    incongruent_pixels=int(bad.sum()), incongruent_worldpop=float(W[rows[bad], cols[bad]].sum()),
                    incongruent_estimate=float(expected[bad].sum()))
    info["estimate_total"] = float(est.sum())
    logger.info("built-surface population: " + ", ".join(f"{k} {v:,.4g}" for k, v in info.items()))
    if out_tif:
        p = dict(profile)
        p.update(dtype="float32", count=1, nodata=0, compress="deflate")
        with rasterio.open(out_tif, "w", **p) as dst:
            dst.write(est.astype("float32"), 1)
    return est, info
