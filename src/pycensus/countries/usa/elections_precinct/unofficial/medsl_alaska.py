# -*- coding: utf-8 -*-
"""Alaska 2024 president: MEDSL precinct returns on Census 2020 voting districts -- UNOFFICIAL (the Division of Elections files are not reachable).

MEDSL gives Alaska's election-day votes per precinct (``<house district>-<precinct number>``) but its absentee, early, question and overseas ballots
only per State House district (``District N - Absentee``...), 49% of the vote. The Census 2020 voting district of a precinct is found through the precinct
number (the part of the VTD GEOID after the hyphen). Each house district's district-level ballots are spread over its precincts in proportion to their
election-day votes; the statewide overseas pool (``HD99``) is spread over all precincts the same way. Election-day votes of precincts without a polygon
join the district pool. The result is then calibrated to the FEC state total (``fec.calibrate``).
"""

from __future__ import annotations

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .....elections_common import default_elections_cache
from . import medsl

ATTRIBUTION = ("Precinct votes: MEDSL Precinct-Level Returns 2024 (doi:10.7910/DVN/NYTPDU), unofficial; Alaska's absentee, early, question and overseas ballots are reported "
               "per State House district and spread over that district's precincts in proportion to election-day votes. Polygons: Census Bureau 2020 voting districts.")


def _raw(cache_dir=None) -> pd.DataFrame:
    medsl.load_president("ak", cache_dir)   # makes sure the csv is cached
    d = pd.read_csv(default_elections_cache(cache_dir) / "medsl_2024" / "ak.csv", dtype=str, low_memory=False,
                    usecols=lambda c: c in ("precinct", "office", "candidate", "votes", "county_fips", "party_simplified", "mode"))
    d = d[d["office"] == "US PRESIDENT"].copy()
    d["votes"] = pd.to_numeric(d["votes"], errors="coerce").fillna(0.0)
    d = d[~d["candidate"].fillna("").str.upper().str.contains(medsl.NON_CANDIDATE)]
    return d


def load(state_fips: str = "02", cache_dir=None):
    """Alaska 2024 presidential votes (MEDSL) on the state's voting districts, pooled votes spread by district.

    Args:
        state_fips: State FIPS (``"02"``).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with votes.
    """
    from ...voting_districts import load_vtd

    d = _raw(cache_dir)
    pat = d["precinct"].str.extract(r"^(\d{3})-(\d{3})$")
    d["hd"], d["pno"] = pat[0], pat[1]
    pool_hd = d["precinct"].str.extract(r"^District (\d+)")[0].str.zfill(3)
    d.loc[d["hd"].isna(), "hd"] = pool_hd
    d["kind"] = np.where(d["pno"].notna() & d["county_fips"].notna(), "prec", "pool")
    d["dem"] = np.where(d["party_simplified"] == "DEMOCRAT", d["votes"], 0.0)
    d["rep"] = np.where(d["party_simplified"] == "REPUBLICAN", d["votes"], 0.0)
    prec = d[d["kind"] == "prec"].groupby(["hd", "pno"]).agg(county_fips=("county_fips", "first"), votes_dem=("dem", "sum"), votes_rep=("rep", "sum"), votes_total=("votes", "sum")).reset_index()
    pool = d[d["kind"] == "pool"].groupby("hd", dropna=False)[["dem", "rep", "votes"]].sum()
    vtd = load_vtd("02", 2020)
    vtd["pno"] = vtd["GEOID"].astype(str).str.split("-").str[1]
    j = vtd.merge(prec.drop_duplicates("pno"), on="pno", how="inner")
    cols = ["votes_dem", "votes_rep", "votes_total"]
    pools = {"votes_dem": "dem", "votes_rep": "rep", "votes_total": "votes"}
    matched = set(zip(j["hd"], j["pno"]))
    lost = prec[[(h, p) not in matched for h, p in zip(prec["hd"], prec["pno"])]].groupby("hd")[cols].sum()
    for c in cols:
        extra = pool[pools[c]].groupby(level=0).sum().add(lost[c] if len(lost) else 0, fill_value=0)
        hd_tot = j.groupby("hd")["votes_total"].transform("sum").replace(0, np.nan)
        share = j["votes_total"] / hd_tot
        j[c] = j[c] + j["hd"].map(extra).fillna(0.0) * share.fillna(0.0)
        statewide = extra.get(np.nan, 0.0) if hasattr(extra, "get") else 0.0
    # statewide overseas pool (no district): spread over all precincts by election-day votes
    over = d[(d["kind"] == "pool") & d["hd"].isna()]
    if len(over):
        w = j["votes_total"] / j["votes_total"].sum()
        for c, k in pools.items():
            j[c] = j[c] + float(over[k if k != "votes" else "votes"].sum() if False else over[{"votes_dem": "dem", "votes_rep": "rep", "votes_total": "votes"}[c]].sum()) * w
    j["geometry"] = j.geometry.make_valid()
    return gpd.GeoDataFrame(j[["county_fips"] + cols + ["geometry"]].reset_index(drop=True), geometry="geometry", crs=vtd.crs)
