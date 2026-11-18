"""Building-stock columns per zone (H3 cell, census polygon, raster pixel) from unified cadaster buildings (pycensus.cadaster).

A building belongs to the zone holding its centroid (its point for point sources). Columns (global-schema names):

    buildingCount, builtFloorArea (m2), builtFloorAreaResidential, builtFloorAreaNonResidential, buildingFootprintArea (m2),
    dwellings, dwellingsPerBuilding, builtAreaPerDwelling (residential m2 / dwelling), floorsMean (footprint-weighted),
    floorsMax, heightMax / heightMedian (footprint-weighted), residentialBuiltShare, yearBuiltMedian (built-area-weighted),
    populationNightCadaster / populationDayCadaster (sources that estimate it, e.g. NSI)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RESIDENTIAL = {"residential", "mixed"}


def _wmedian(v, w, g):
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return pd.Series(dtype=float)
    v, w, g = v[ok], w[ok], g[ok]
    o = np.lexsort((v, g)); v, w, g = v[o], w[o], g[o]
    cum = pd.Series(w).groupby(g).cumsum().to_numpy()
    half = pd.Series(w).groupby(g).transform("sum").to_numpy() / 2
    first = pd.Series(np.where(cum >= half, np.arange(len(v)), len(v))).groupby(g).min()
    return pd.Series(v[first.to_numpy()], index=first.index)


def zone_metrics(b, zone: pd.Series) -> pd.DataFrame:
    """Building-stock columns per zone id (`zone`: one id per building row, NaN = outside every zone).

    Args:
        b: Buildings (unified schema).
        zone: Zone id per building.

    Returns:
        One row per zone.
    """
    ok = zone.notna().to_numpy()
    z = zone.to_numpy()[ok]
    codes, uniq = pd.factorize(z)
    num = lambda c: pd.to_numeric(b[c], errors="coerce").to_numpy(dtype=float)[ok]  # noqa: E731
    ba, fp, fl, h, dw = num("built_area_m2"), num("footprint_m2"), num("floors_above"), num("height_m"), num("dwellings")
    res = b["use_class"].isin(RESIDENTIAL).to_numpy()[ok]
    df = pd.DataFrame({"g": codes, "ba": np.nan_to_num(ba), "fp": np.nan_to_num(fp), "dw": np.nan_to_num(dw),
                       "bar": np.where(res, np.nan_to_num(ba), 0.0), "fl_w": np.nan_to_num(fl) * np.nan_to_num(fp), "fp_fl": np.where(np.isfinite(fl), np.nan_to_num(fp), 0.0),
                       "fl": fl, "h": h, "pn": num("population_night"), "pd": num("population_day")})
    gr = df.groupby("g")
    out = pd.DataFrame({"buildingCount": gr.size(), "builtFloorArea": gr["ba"].sum(), "builtFloorAreaResidential": gr["bar"].sum(),
                        "buildingFootprintArea": gr["fp"].sum(), "dwellings": gr["dw"].sum(), "floorsMax": gr["fl"].max(), "heightMax": gr["h"].max()})
    out["builtFloorAreaNonResidential"] = out["builtFloorArea"] - out["builtFloorAreaResidential"]
    out["dwellingsPerBuilding"] = out["dwellings"] / out["buildingCount"]
    out["builtAreaPerDwelling"] = out["builtFloorAreaResidential"] / out["dwellings"].where(out["dwellings"] > 0)
    out["floorsMean"] = gr["fl_w"].sum() / gr["fp_fl"].sum().where(gr["fp_fl"].sum() > 0)
    out["residentialBuiltShare"] = out["builtFloorAreaResidential"] / out["builtFloorArea"].where(out["builtFloorArea"] > 0)
    out["heightMedian"] = _wmedian(h, np.nan_to_num(fp), codes)
    out["yearBuiltMedian"] = _wmedian(num("year_built"), np.nan_to_num(ba), codes)
    if np.isfinite(df["pn"]).any():
        out["populationNightCadaster"] = gr["pn"].sum(min_count=1)
        out["populationDayCadaster"] = gr["pd"].sum(min_count=1)
    out.index = uniq[out.index.to_numpy()]
    return out


def h3_zone(b, resolution: int) -> pd.Series:
    """H3 cell id (string) of each building's centroid / point.

    Args:
        b: Buildings.
        resolution: H3 resolution.

    Returns:
        Series of H3 ids.
    """
    import h3ronpy
    import h3ronpy.vector as hv

    c = b.geometry if b.geom_type.iloc[0] == "Point" else b.geometry.representative_point()
    cells = h3ronpy.cells_to_string(hv.coordinates_to_cells(c.y.to_numpy(), c.x.to_numpy(), resolution)).to_pylist()
    return pd.Series(cells, index=b.index)


def cell_floor_area(b, resolution: int):
    """(cells, residential floor area, other floor area) per H3 cell holding a building's centroid / point: sorted uint64 cell ids
    with at least one building. Residential = use_class residential or mixed (gross floor area, built_area_m2).

    Args:
        b: Buildings (unified schema).
        resolution: H3 resolution.
    """
    import h3ronpy.vector as hv

    if b is None or not len(b):
        return np.zeros(0, np.uint64), np.zeros(0), np.zeros(0)
    c = b.geometry if b.geom_type.iloc[0] == "Point" else b.geometry.representative_point()
    cells = np.asarray(hv.coordinates_to_cells(c.y.to_numpy(), c.x.to_numpy(), resolution)).astype(np.uint64)
    ba = np.nan_to_num(pd.to_numeric(b["built_area_m2"], errors="coerce").to_numpy(float))
    res = b["use_class"].isin(RESIDENTIAL).to_numpy()
    u, inv = np.unique(cells, return_inverse=True)
    return u, np.bincount(inv, weights=np.where(res, ba, 0.0), minlength=len(u)), np.bincount(inv, weights=np.where(res, 0.0, ba), minlength=len(u))
