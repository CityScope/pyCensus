"""Census polygons -> H3 cells, weighted by built floor area (the normal maps' population assignment).

    from pycensus.dasymetric import polygons_to_cells
    counts, report = polygons_to_cells(polygons, cells, count_cols, weights={"res": w_res, "non": w_non}, groups=col_group)

Rules (documented in transitlos.grid_rules):
  * a cell belongs to the one polygon holding its centre (never to two);
  * each polygon's counts are split over its cells by built floor area: the cells' floor areas are rescaled so they add up to 1 inside the polygon
    (only the split uses them; the cells' real floor areas stay as they are). Columns of group "res" (residents, households, age groups, ...) use
    residential floor area, group "non" (jobs) non-residential floor area; each falls back to the total floor area, then to an equal split;
  * a polygon holding no cell centre contributes nothing here: its counts are reported (report["unplaced"]) for the caller's area-wide rescaling.
Every column of one group uses the same weights, so the shares between them (e.g. under-18 / residents) are the polygon's in every cell.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

import geopandas as gpd
import numpy as np
import pandas as pd


def _centres(cells: np.ndarray):
    import h3ronpy.vector as hv
    r = hv.cells_to_coordinates(np.asarray(cells, np.uint64))
    return np.asarray(r.column("lat")), np.asarray(r.column("lng"))


def polygons_to_cells(polygons: gpd.GeoDataFrame, cells: np.ndarray, count_cols: Iterable[str], weights: Optional[Dict[str, np.ndarray]] = None,
                      groups: Optional[Dict[str, str]] = None):
    """Counts per cell ([len(cells), n_cols] DataFrame, rows in `cells` order) and a report {column: {"total", "placed", "unplaced"}}.

    `cells`: uint64 H3 ids (any resolution). `weights`: {"res": floor area per cell, "non": ...} aligned with `cells` (None: equal split).
    `groups`: column -> "res" | "non" | "all" (total floor area: res + non) | any other key of `weights` (default "res").

    Args:
        polygons: Census polygons with count columns.
        cells: uint64 H3 ids.
        count_cols: Count columns to split.
        weights: ``{group: weight per cell}``.
        groups: ``{column: weight group}``.
    """
    cols = [c for c in count_cols if c in polygons.columns]
    out = np.zeros((len(cells), len(cols)))
    report = {}
    if not len(cells) or polygons is None or polygons.empty or not cols:
        return pd.DataFrame(out, columns=cols), report
    lat, lon = _centres(cells)
    p = polygons[cols + ["geometry"]].to_crs(4326).reset_index(drop=True)
    j = gpd.sjoin(gpd.GeoDataFrame({"ci": np.arange(len(cells))}, geometry=gpd.points_from_xy(lon, lat), crs=4326), p, how="inner", predicate="within")
    j = j[~j["ci"].duplicated()]
    bi, ci = j["index_right"].to_numpy(), j["ci"].to_numpy()
    n = np.bincount(bi, minlength=len(p))
    eq = 1.0 / n[bi]

    def share(w):
        if w is None:
            return np.full(len(ci), np.nan)
        wc = np.nan_to_num(np.asarray(w, float))[ci]
        tot = np.bincount(bi, weights=wc, minlength=len(p))[bi]
        return np.where(tot > 0, wc / np.where(tot > 0, tot, 1.0), np.nan)

    weights = {k: v for k, v in (weights or {}).items() if v is not None}
    total_w = sum(np.nan_to_num(np.asarray(weights[k], float)) for k in ("res", "non") if k in weights) if ("res" in weights or "non" in weights) else None
    s_all = share(total_w)
    s_all = np.where(np.isnan(s_all), eq, s_all)
    sh = {"all": s_all, "res": s_all, "non": s_all}
    for k, w in weights.items():
        sk = share(w)
        sh[k] = np.where(np.isnan(sk), s_all, sk)
    raw = p[cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    vals = np.nan_to_num(raw)
    placed_poly = n > 0
    for k, c in enumerate(cols):
        np.add.at(out[:, k], ci, vals[bi, k] * sh[(groups or {}).get(c, "res")])
        out[ci[np.isnan(raw[bi, k])], k] = np.nan   # the polygon has no value: the cell has none either (not a false 0)
        report[c] = {"total": float(vals[:, k].sum()), "placed": float(vals[placed_poly, k].sum()), "unplaced": float(vals[~placed_poly, k].sum())}
    return pd.DataFrame(out, columns=cols), report


def rescale_to_totals(counts: pd.DataFrame, keep: np.ndarray, totals: Dict[str, float], groups: Dict[str, str], anchor: Dict[str, str], log=print,
                      warn_share: float = 0.05, label: str = "", factors: Optional[dict] = None):
    """Drop the rows not in `keep` and put back what is missing (dropped rows + `totals` not placed at all) with ONE factor per group: the factor
    of the group's anchor column (anchor["res"] = e.g. "population", anchor["non"] = "jobs") is applied to every column of that group, so the
    shares inside a cell do not change. Logged per anchor, WARNING above `warn_share`. `factors` (a dict) receives, per group, the factor,
    the anchor's total and kept sum, and the columns it was applied to (original value = rescaled value / factor).

    Args:
        counts: Counts per cell.
        keep: Boolean mask of the cells kept.
        totals: ``{column: true total}``.
        groups: ``{column: group}``.
        anchor: ``{group: anchor column}``.
        log: Logging function.
        warn_share: Share rescaled above which a warning is logged.
        label: Text added to the log lines.
        factors: Optional dict that receives the factors.

    Returns:
        The kept, rescaled counts.
    """
    out = counts[keep].copy()
    for grp, key in anchor.items():
        cols = [c for c in out.columns if groups.get(c, "res") == grp]
        if key not in out.columns or not cols:
            continue
        total = float(totals.get(key, np.nansum(counts[key].to_numpy(float))))
        kept = float(np.nansum(out[key].to_numpy(float)))
        if total <= 0 or kept <= 0:
            continue
        f = total / kept
        share = (total - kept) / total
        msg = f"[rescale]{(' ' + label) if label else ''} {key}: {total - kept:,.0f} of {total:,.0f} ({share:.1%}) not on an active cell -- factor {f:.4f} on {len(cols)} columns"
        log(("WARNING " if share > warn_share else "") + msg)
        out[cols] = out[cols] * f
        if factors is not None:
            factors[grp] = {"anchor": key, "total": total, "kept_before_rescale": kept, "factor": f, "columns": cols}
    return out


def polygon_values_at_cells(polygons: gpd.GeoDataFrame, cells: np.ndarray, cols: Iterable[str]) -> pd.DataFrame:
    """Rate-style columns (means, medians, shares): each cell takes the value of the one polygon holding its centre (NaN outside every
    polygon). Rows in `cells` order.

    Args:
        polygons: Polygons with rate columns.
        cells: uint64 H3 ids.
        cols: Columns to copy.
    """
    cols = [c for c in cols if c in polygons.columns]
    out = np.full((len(cells), len(cols)), np.nan)
    if not len(cells) or polygons is None or polygons.empty or not cols:
        return pd.DataFrame(out, columns=cols)
    lat, lon = _centres(cells)
    p = polygons[cols + ["geometry"]].to_crs(4326).reset_index(drop=True)
    j = gpd.sjoin(gpd.GeoDataFrame({"ci": np.arange(len(cells))}, geometry=gpd.points_from_xy(lon, lat), crs=4326), p[["geometry"]], how="inner", predicate="within")
    j = j[~j["ci"].duplicated()]
    out[j["ci"].to_numpy()] = p[cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)[j["index_right"].to_numpy()]
    return pd.DataFrame(out, columns=cols)


def cells_to_polygons_mean(polygons: gpd.GeoDataFrame, cells: np.ndarray, values: np.ndarray, weights: Optional[Iterable[np.ndarray]] = None) -> np.ndarray:
    """Per polygon (in `polygons` order): the weighted mean of `values` over the cells whose centre lies inside it.

    `weights`: a sequence of weight arrays tried in turn (e.g. residents, then jobs): a polygon whose cells have no weight under the first
    uses the next; with none left, the plain mean. A polygon holding no cell centre (smaller than a cell) takes the value of the cell under its
    representative point when that cell is in `cells`; NaN otherwise. Used for the census geometries' level of service: the
    population-weighted mean of the finest cells (the map's rule).

    Args:
        polygons: Polygons.
        cells: uint64 H3 ids.
        values: Value per cell.
        weights: Weight arrays tried in turn.
    """
    import h3ronpy.vector as hv

    n = len(polygons)
    out = np.full(n, np.nan)
    if not n or not len(cells):
        return out
    cells = np.asarray(cells, np.uint64)
    values = np.asarray(values, float)
    lat, lon = _centres(cells)
    p = polygons[["geometry"]].to_crs(4326).reset_index(drop=True)
    j = gpd.sjoin(gpd.GeoDataFrame({"ci": np.arange(len(cells))}, geometry=gpd.points_from_xy(lon, lat), crs=4326), p, how="inner", predicate="within")
    j = j[~j["ci"].duplicated()]
    bi, ci = j["index_right"].to_numpy(), j["ci"].to_numpy()
    v = np.nan_to_num(values[ci])
    done = np.zeros(n, bool)
    for w in list(weights or []):
        w = np.nan_to_num(np.asarray(w, float))[ci]
        den = np.bincount(bi, weights=w, minlength=n)
        num = np.bincount(bi, weights=w * v, minlength=n)
        ok = (den > 0) & ~done
        out[ok] = num[ok] / den[ok]
        done |= ok
    cnt = np.bincount(bi, minlength=n)
    num = np.bincount(bi, weights=v, minlength=n)
    ok = (cnt > 0) & ~done
    out[ok] = num[ok] / cnt[ok]
    done |= cnt > 0
    if (~done).any():   # polygons smaller than a cell: the cell under the representative point
        rp = p.geometry[~done].representative_point()
        import h3

        res = h3.get_resolution(h3.int_to_str(int(cells[0])))
        rc = np.asarray(hv.coordinates_to_cells(rp.y.to_numpy(), rp.x.to_numpy(), res)).astype(np.uint64)
        order = np.argsort(cells); sc = cells[order]
        pos = np.searchsorted(sc, rc); hit = (pos < len(sc)) & (sc[np.minimum(pos, len(sc) - 1)] == rc)
        idx = np.flatnonzero(~done)
        out[idx[hit]] = values[order[pos[hit]]]
    return out
