"""Country-agnostic helpers for election-result loaders (counts -> shares, polygons <-> H3 res 8).

Counts convention (all additive, so they can be resampled): ``eligible``, ``ballots`` (voters who cast a ballot), ``valid`` (valid votes),
``left``, ``right``, ``other`` (valid votes by bloc) and ``party_<slug>`` (valid votes per party / candidate). :func:`finalize` turns them into
the project columns ``elec_<tag>_total_votes`` (= valid votes), ``_turnout_rate`` (= ballots / eligible), ``_left_share``/``_right_share``/
``_other_share`` and ``_party_<slug>_share`` (shares of valid votes, 0-1).

Resampling is AREA-WEIGHTED (documented choice, no population raster needed): a polygon's count is split among the H3 res-8 cells it overlaps in
proportion to the intersection area / polygon area (mass conserving); cells -> target polygons the same way (cell count x intersection / cell area).
Counts, never shares, are resampled; shares are recomputed afterwards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

H3_RES = 8
BASE_COUNTS = ["eligible", "ballots", "valid", "left", "right", "other"]


def slugify(s: str) -> str:
    """Lower-case slug of a name.

    Args:
        s: Any text.

    Returns:
        The slug (``"x"`` when empty).
    """
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


def load_blocs(path: Path) -> dict:
    """The party-to-bloc file.

    Args:
        path: JSON file.

    Returns:
        The file's dict.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def count_cols(df: pd.DataFrame) -> List[str]:
    """The count columns of a frame (base counts and ``party_*``).

    Args:
        df: Counts table.

    Returns:
        Column names.
    """
    return [c for c in BASE_COUNTS + [c for c in df.columns if c.startswith("party_")] if c in df.columns]


def finalize(counts: pd.DataFrame, tag: str, key: str, party_slugs: Iterable[str]) -> pd.DataFrame:
    """Counts frame (``key`` + count columns) -> project columns ``elec_<tag>_*`` (shares 0-1).

    Args:
        counts: Counts table.
        tag: Election tag of the output columns.
        key: Key column.
        party_slugs: Parties given their own columns.
    """
    p = f"elec_{tag}_"
    out = pd.DataFrame({key: counts[key].values})
    v = counts["valid"].astype(float).values
    with np.errstate(divide="ignore", invalid="ignore"):
        out[p + "total_votes"] = counts["valid"].values
        out[p + "turnout_rate"] = np.where(counts["eligible"] > 0, counts["ballots"] / counts["eligible"], np.nan)
        for b in ("left", "right", "other"):
            out[p + f"{b}_share"] = np.where(v > 0, counts[b] / v, np.nan)
        for s in party_slugs:
            out[p + f"party_{s}_share"] = np.where(v > 0, counts[f"party_{s}"] / v, np.nan)
    return out


def _utm(gdf: gpd.GeoDataFrame):
    return gdf.estimate_utm_crs()


def cells_for(gdf: gpd.GeoDataFrame, res: int = H3_RES) -> gpd.GeoDataFrame:
    """H3 cells (``h3_cell``, hex polygons in EPSG:4326) covering ``gdf`` (any cell touching a polygon, via cell-centre cover + neighbours).

    Args:
        gdf: Polygons.
        res: H3 resolution.
    """
    g = gdf.to_crs(4326)
    cells = set()
    for geom in g.geometry:
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for pg in polys:
            shp = h3.LatLngPoly([(y, x) for x, y in pg.exterior.coords], *[[(y, x) for x, y in r.coords] for r in pg.interiors])
            c = set(h3.polygon_to_cells(shp, res))
            if not c:
                c = {h3.latlng_to_cell(pg.centroid.y, pg.centroid.x, res)}
            cells |= c
    ring = set()
    for c in cells:
        ring |= set(h3.grid_disk(c, 1))
    cells |= ring
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells]
    return gpd.GeoDataFrame({"h3_cell": list(cells)}, geometry=polys, crs=4326)


def polygons_to_h3(gdf: gpd.GeoDataFrame, cols: List[str], res: int = H3_RES) -> pd.DataFrame:
    """Area-weighted, mass-conserving split of polygon counts ``cols`` onto H3 cells. Returns ``h3_cell`` + ``cols``.

    Args:
        gdf: Polygons with counts.
        cols: Count columns.
        res: H3 resolution.
    """
    hexes = cells_for(gdf, res)
    crs = _utm(gdf)
    a = gdf[cols + ["geometry"]].to_crs(crs).reset_index(drop=True)
    a["_area"] = a.geometry.area
    inter = gpd.overlay(a, hexes.to_crs(crs), how="intersection", keep_geom_type=True)
    inter["_w"] = inter.geometry.area / inter["_area"]
    for c in cols:
        inter[c] = inter[c] * inter["_w"]
    return inter.groupby("h3_cell", as_index=False)[cols].sum()


def h3_to_polygons(h3df: pd.DataFrame, target: gpd.GeoDataFrame, key: str, cols: List[str]) -> pd.DataFrame:
    """Area-weighted split of H3-cell counts ``cols`` onto ``target`` polygons (``key`` column). Mass is conserved for cells fully covered.

    Args:
        h3df: Counts per H3 cell.
        target: Target polygons.
        key: Target id column.
        cols: Count columns.
    """
    cells = h3df["h3_cell"].tolist()
    hexes = gpd.GeoDataFrame(h3df[["h3_cell"] + cols].copy(),
                             geometry=[Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells], crs=4326)
    crs = _utm(target)
    hx = hexes.to_crs(crs)
    hx["_area"] = hx.geometry.area
    t = target[[key, "geometry"]].to_crs(crs)
    inter = gpd.overlay(hx, t, how="intersection", keep_geom_type=True)
    w = inter.geometry.area / inter["_area"]
    for c in cols:
        inter[c] = inter[c] * w
    return inter.groupby(key, as_index=False)[cols].sum()


def points_to_h3(points: pd.DataFrame, cols: List[str], res: int = H3_RES, lat: str = "lat", lng: str = "lng") -> pd.DataFrame:
    """Counts located at a point (e.g. polling station) -> the H3 cell containing it.

    Args:
        points: Table with coordinates.
        cols: Count columns.
        res: H3 resolution.
        lat: Latitude column.
        lng: Longitude column.

    Returns:
        Counts per H3 cell.
    """
    d = points.copy()
    d["h3_cell"] = [h3.latlng_to_cell(a, b, res) for a, b in zip(d[lat], d[lng])]
    return d.groupby("h3_cell", as_index=False)[cols].sum()
