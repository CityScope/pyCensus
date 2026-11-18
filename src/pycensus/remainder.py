"""Complete a partial fine census level with the remainders of the coarser level that contains it.

Where a fine level only covers part of the land (Israel's statistical areas exist only in the larger localities), each coarse polygon
(the locality) minus the union of its fine polygons becomes a "remainder" polygon whose counts are the coarse counts minus the sum of
its fine polygons' (never below 0); rates and other non-count columns keep the coarse polygon's value. A coarse polygon without any
fine polygon becomes a remainder whole.

    from pycensus.remainder import add_remainders
    complete = add_remainders(stat_areas, localities, count_cols=["population", ...])
"""
from __future__ import annotations

from typing import Iterable, Optional

import geopandas as gpd
import numpy as np
import pandas as pd


def add_remainders(fine: gpd.GeoDataFrame, coarse: gpd.GeoDataFrame, count_cols: Iterable[str], id_col: str = "GEOID",
                   min_area_share: float = 0.001, suffix: str = "_rest", flag_col: Optional[str] = "is_remainder") -> gpd.GeoDataFrame:
    """`fine` plus one remainder polygon per `coarse` polygon (see the module docstring).

    Each fine polygon belongs to the coarse polygon that contains its representative point. A remainder smaller than `min_area_share`
    of its coarse polygon is dropped (slivers from boundary mismatches) unless it still holds people. The remainder's id is
    `<coarse id><suffix>`; `flag_col` (if given) marks remainders True.

    Args:
        fine: Fine polygons with counts.
        coarse: Coarse polygons with the same counts.
        count_cols: Count columns.
        id_col: Id column.
        min_area_share: Smallest remainder kept (share of its coarse polygon).
        suffix: Suffix of the remainder ids.
        flag_col: Column marking the remainders.
    """
    fine = fine.copy()
    coarse = coarse.to_crs(fine.crs).reset_index(drop=True)
    counts = [c for c in count_cols if c in fine.columns and c in coarse.columns]
    rp = gpd.GeoDataFrame(geometry=fine.geometry.representative_point(), crs=fine.crs)
    j = gpd.sjoin(rp, coarse[["geometry"]], how="left", predicate="within")
    parent = j[~j.index.duplicated()]["index_right"].reindex(fine.index)
    rows = []
    for ci, cpoly in coarse.iterrows():
        kids = fine[parent == ci]
        geom = cpoly.geometry if kids.empty else cpoly.geometry.difference(kids.geometry.union_all())
        if geom.is_empty:
            continue
        row = cpoly.copy()
        row["geometry"] = geom
        row[id_col] = f"{cpoly[id_col]}{suffix}"
        for c in counts:
            total = pd.to_numeric(pd.Series([cpoly[c]]), errors="coerce").iloc[0]
            used = pd.to_numeric(kids[c], errors="coerce").sum() if len(kids) else 0.0
            row[c] = max(float(total) - float(used), 0.0) if pd.notna(total) else np.nan
        keep_people = any(pd.notna(row[c]) and row[c] > 0 for c in counts)
        if not kids.empty and geom.area < min_area_share * cpoly.geometry.area and not keep_people:
            continue
        rows.append(row)
    if flag_col:
        fine[flag_col] = False
    if not rows:
        return fine
    rest = gpd.GeoDataFrame(rows, geometry="geometry", crs=fine.crs)
    if flag_col:
        rest[flag_col] = True
    cols = list(dict.fromkeys(list(fine.columns) + [c for c in rest.columns if c in fine.columns]))
    return gpd.GeoDataFrame(pd.concat([fine, rest[[c for c in cols if c in rest.columns]]], ignore_index=True), geometry="geometry", crs=fine.crs)
