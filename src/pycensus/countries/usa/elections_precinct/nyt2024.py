# -*- coding: utf-8 -*-
"""Nationwide 2024 presidential results at PRECINCT level (The New York Times precinct map data).

Source: ``github.com/nytimes/presidential-precinct-map-2024`` -- one GeoJSON per state with the precinct polygon and
``votes_dem`` (Harris), ``votes_rep`` (Trump), ``votes_total`` and a 5-digit county FIPS prefix in ``GEOID``. Official precinct
boundaries are used where the states/counties publish them, estimated ones otherwise (``official_boundary`` False). Alaska and a
few counties are missing (countywide absentee tabulations); callers fall back to the county result there.

``allocate_to_polygons`` moves the precinct votes onto any finer or coarser polygon set (blocks, block groups, tracts, H3 cells)
dasymetrically: each precinct's votes are shared among the target polygons it overlaps in proportion to the target's population
inside the overlap (population spread evenly over each target polygon).
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd

from ....elections_common import default_elections_cache, download

logger = logging.getLogger(__name__)

URL = "https://int.nyt.com/newsgraphics/elections/map-data/2024/national/{st}-precincts-with-results.geojson.gz"
ATTRIBUTION = "2024 Precinct-Level Election Results, New York Times (nytimes/presidential-precinct-map-2024)."

STATE_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}


def load_state_precincts(state_fips: str, cache_dir: Optional[str] = None) -> Optional[gpd.GeoDataFrame]:
    """Precinct polygons (EPSG:4326) of one state with ``county_fips``, ``votes_dem``, ``votes_rep``, ``votes_total``; None if unavailable.

    Args:
        state_fips: 2-digit state FIPS.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    abbr = STATE_ABBR.get(str(state_fips).zfill(2))
    if abbr is None:
        return None
    root = default_elections_cache(cache_dir) / "nyt_precincts_2024"
    parquet = root / f"{abbr}.parquet"
    if parquet.is_file():
        return gpd.read_parquet(parquet)
    try:
        raw = download(URL.format(st=abbr), root / f"{abbr}.geojson.gz")
        with gzip.open(raw, "rt", encoding="utf-8") as fh:
            gdf = gpd.GeoDataFrame.from_features(json.load(fh)["features"], crs=4326)
    except Exception as exc:  # noqa: BLE001 - a missing state simply falls back to the county result
        logger.warning("NYT 2024 precinct data unavailable for %s: %s", abbr, exc)
        return None
    gdf["county_fips"] = gdf["GEOID"].astype(str).str[:5]
    for c in ("votes_dem", "votes_rep", "votes_total"):
        gdf[c] = pd.to_numeric(gdf[c], errors="coerce").fillna(0.0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty][["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]]
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf.reset_index(drop=True)
    root.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(parquet)
    return gdf


def allocate_to_polygons(targets: gpd.GeoDataFrame, precincts: gpd.GeoDataFrame, pop_col: str = "population") -> Optional[pd.DataFrame]:
    """Votes (dem / rep / total) per target polygon, index-aligned with ``targets``.

    Precincts with no population inside any target (or targets no precinct reaches) contribute nothing / get NaN, so the caller can fall back to the
    county result for them.

    Args:
        targets: Target polygons with population.
        precincts: Precincts with votes.
        pop_col: Population column of the targets.
    """
    if targets.empty or precincts is None or precincts.empty or pop_col not in targets.columns:
        return None
    crs = 5070   # US equal-area (Conus Albers): fine for area ratios everywhere the study maps
    t = targets[[pop_col, "geometry"]].copy()
    t["_t"] = np.arange(len(t))
    t["_pop"] = pd.to_numeric(t[pop_col], errors="coerce").fillna(0.0)
    t = t.to_crs(crs)
    t["geometry"] = t.geometry.make_valid().buffer(0)
    t["_area"] = t.geometry.area.replace(0, np.nan)
    p = precincts.to_crs(crs).reset_index(drop=True)
    p["geometry"] = p.geometry.make_valid().buffer(0)   # reprojection can leave slivers/self-touches that break the overlay
    p["_p"] = np.arange(len(p))
    pieces = gpd.overlay(t[["_t", "_pop", "_area", "geometry"]], p[["_p", "votes_dem", "votes_rep", "votes_total", "geometry"]],
                         how="intersection", keep_geom_type=False)
    if pieces.empty:
        return None
    pieces["_pop_piece"] = pieces["_pop"] * (pieces.geometry.area / pieces["_area"]).fillna(0.0)
    precinct_pop = pieces.groupby("_p")["_pop_piece"].transform("sum")
    # A precinct without population in the targets splits by area instead, so its votes are not lost.
    precinct_area = pieces.assign(_a=pieces.geometry.area).groupby("_p")["_a"].transform("sum")
    frac = np.where(precinct_pop > 0, pieces["_pop_piece"] / precinct_pop.replace(0, np.nan), pieces.geometry.area / precinct_area.replace(0, np.nan))
    frac = pd.Series(frac, index=pieces.index).fillna(0.0)
    out = pd.DataFrame({
        "_t": pieces["_t"].to_numpy(),
        "votes_dem": (pieces["votes_dem"] * frac).to_numpy(),
        "votes_rep": (pieces["votes_rep"] * frac).to_numpy(),
        "votes_total": (pieces["votes_total"] * frac).to_numpy(),
    }).groupby("_t").sum()
    return out.reindex(np.arange(len(targets)))
