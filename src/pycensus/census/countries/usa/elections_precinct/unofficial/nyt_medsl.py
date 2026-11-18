# -*- coding: utf-8 -*-
"""Precinct polygons from the New York Times 2024 precinct map joined to MEDSL precinct results by their vote counts -- UNOFFICIAL, cross-validated.

Neither source alone is official. They are independent compilations of the states' results, so a precinct whose Democratic and Republican
counts agree EXACTLY in both (within one county, and unique there) is the same precinct. That gives MEDSL's labelled results (the state's own precinct
names) the NYT polygon (``official_boundary`` says whether the NYT used the state's/county's boundary). A state is accepted only if at least
``MIN_MATCHED`` of its presidential votes match; the MEDSL votes of precincts that do not match (and of rows with no polygon) are shared among
the matched polygons of their county in proportion to votes, so every county keeps its MEDSL total (checked against Delaware's official report: 99.8% of votes matched).
"""

from __future__ import annotations

import gzip
import json

import geopandas as gpd
import pandas as pd
import requests

from pycensus.elections_common import default_elections_cache
from pycensus.census.countries.usa.elections_precinct.nyt2024 import STATE_ABBR
from pycensus.census.countries.usa.elections_precinct.unofficial import medsl

URL = "https://int.nyt.com/newsgraphics/elections/map-data/2024/national/{st}-precincts-with-results.geojson.gz"
MIN_MATCHED = 0.90
ATTRIBUTION = ("Precinct polygons: The New York Times 2024 presidential precinct map (nytimes/presidential-precinct-map-2024); results: MEDSL Precinct-Level "
               "Returns 2024 (doi:10.7910/DVN/NYTPDU), joined by exact precinct vote counts. Unofficial, cross-validated.")


def _nyt(st: str, cache_dir=None) -> gpd.GeoDataFrame:
    p = default_elections_cache(cache_dir) / "nyt_medsl" / f"{st}.gpkg"
    if p.is_file():
        return gpd.read_file(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(URL.format(st=st.upper()), headers={"User-Agent": "pycensus"}, timeout=600)
    r.raise_for_status()
    g = gpd.GeoDataFrame.from_features(json.loads(gzip.decompress(r.content))["features"], crs=4326)
    g.to_file(p, driver="GPKG")
    return g


def match_report(st: str, cache_dir=None):
    """(GeoDataFrame of matched precincts with MEDSL votes, share of MEDSL presidential votes matched, official_boundary share).

    Args:
        st: State abbreviation (lower case).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    g = _nyt(st, cache_dir)
    m = medsl.load_president(st, cache_dir)
    g["county_fips"] = g["GEOID"].astype(str).str[:5]
    for c in ("votes_dem", "votes_rep"):
        g[c] = pd.to_numeric(g[c], errors="coerce").round()
    m = m.assign(votes_dem=m["votes_dem"].round(), votes_rep=m["votes_rep"].round())
    key = ["county_fips", "votes_dem", "votes_rep"]
    gg = g.drop_duplicates(key, keep=False)
    mm = m.drop_duplicates(key, keep=False)
    cols = key + ["geometry"] + (["official_boundary"] if "official_boundary" in g else [])
    j = mm.merge(gg[cols], on=key, how="inner")
    share = float(j["votes_total"].sum() / m["votes_total"].sum())
    off = float(g["official_boundary"].astype(bool).mean()) if "official_boundary" in g else float("nan")
    return gpd.GeoDataFrame(j, geometry="geometry", crs=4326), m, share, off


def load(state_fips: str, cache_dir=None) -> gpd.GeoDataFrame:
    """MEDSL 2024 presidential votes matched to NYT precinct polygons (by county and vote counts); unmatched votes spread
    over the county's matched polygons.

    Args:
        state_fips: 2-digit state FIPS.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with votes.

    Raises:
        ValueError: If too few votes match.
    """
    st = STATE_ABBR[str(state_fips).zfill(2)].lower()
    j, m, share, _ = match_report(st, cache_dir)
    if share < MIN_MATCHED:
        raise ValueError(f"{st}: only {share:.1%} of MEDSL votes match an NYT polygon (< {MIN_MATCHED:.0%}); not used")
    # votes of unmatched MEDSL precincts go to the matched polygons of the same county, in proportion to votes
    want = m.groupby("county_fips")[["votes_dem", "votes_rep", "votes_total"]].sum()
    have = j.groupby("county_fips")[["votes_dem", "votes_rep", "votes_total"]].sum()
    extra = (want - have.reindex(want.index).fillna(0.0)).clip(lower=0.0)
    w = j["votes_total"] / j.groupby("county_fips")["votes_total"].transform("sum").replace(0, float("nan"))
    for c in ("votes_dem", "votes_rep", "votes_total"):
        j[c] = j[c] + w.fillna(0.0) * j["county_fips"].map(extra[c]).fillna(0.0)
    j["geometry"] = j.geometry.make_valid()
    return j[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
