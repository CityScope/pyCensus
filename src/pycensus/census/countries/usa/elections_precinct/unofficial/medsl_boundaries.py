# -*- coding: utf-8 -*-
"""Official state precinct BOUNDARIES + MEDSL 2024 precinct VOTES -- votes UNOFFICIAL, polygons official.

For a state whose NYT precinct file is incomplete (Oklahoma) the state publishes its own precinct polygons; MEDSL's precinct label equals the polygon's
precinct code, so the votes join exactly. MEDSL rows with no polygon (central absentee / provisional counting precincts, codes ``*9999``) are spread over
the precincts of the same county in proportion to their votes, so every county keeps the MEDSL county total (the county total of the official result).
"""

from __future__ import annotations

import io

import geopandas as gpd
import numpy as np
import requests

from pycensus.census.countries.usa.elections_precinct.unofficial import medsl

OK_SERVICE = "https://map11.incog.org/arcgis11wa/rest/services/PCT_OK_State/MapServer/0/query"
ATTRIBUTION = {
    "40": ("Precinct polygons: Oklahoma statewide voting precincts (University of Oklahoma Center for Spatial Analysis with the County Election Boards / State Election Board, "
           "map11.incog.org PCT_OK_State). Votes: MEDSL Precinct-Level Returns 2024 (doi:10.7910/DVN/NYTPDU), unofficial; central-count rows spread over the county's precincts."),
}


def _ok_polygons(cache_dir=None) -> gpd.GeoDataFrame:
    from pycensus.elections_common import default_elections_cache

    path = default_elections_cache(cache_dir) / "ok_precincts.geojson"
    if not path.is_file():
        params = dict(where="1=1", outFields="PCT_CEB,CO_FIPS", outSR=4326, f="geojson", resultRecordCount=2000)
        r = requests.get(OK_SERVICE, params=params, headers={"User-Agent": "pycensus"}, timeout=600)
        r.raise_for_status()
        path.write_bytes(r.content)
    g = gpd.read_file(path)
    g["key"] = g["PCT_CEB"].astype(str).str.lstrip("0")
    g["county_fips"] = "40" + g["CO_FIPS"].astype(str).str.zfill(3)
    return g


def load(state_fips: str, cache_dir=None):
    """MEDSL 2024 presidential votes joined to official precinct polygons (Oklahoma only), per-county totals kept.

    Args:
        state_fips: State FIPS (``"40"``).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with votes.

    Raises:
        ValueError: For another state.
    """
    if state_fips != "40":
        raise ValueError(f"no official boundary source configured for state {state_fips}")
    g = _ok_polygons(cache_dir)
    m = medsl.load_president("ok", cache_dir)
    m["key"] = m["precinct"].astype(str).str.lstrip("0")
    cols = ["votes_dem", "votes_rep", "votes_total"]
    want = m.groupby("county_fips")[cols].sum()
    j = g.merge(m[["key", "county_fips"] + cols].rename(columns={"county_fips": "m_county"}), on="key", how="inner")
    j = j[j["county_fips"] == j["m_county"]].copy()
    have = j.groupby("county_fips")[cols].transform("sum")
    for c in cols:
        f = j["county_fips"].map(want[c]) / have[c].replace(0, np.nan)
        j[c] = j[c] * f.fillna(1.0)
    j["geometry"] = j.geometry.make_valid()
    return gpd.GeoDataFrame(j[["county_fips"] + cols + ["geometry"]].reset_index(drop=True), geometry="geometry", crs=g.crs)
