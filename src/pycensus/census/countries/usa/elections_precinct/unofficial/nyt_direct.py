# -*- coding: utf-8 -*-
"""NYT 2024 precinct polygons WITH the NYT's own precinct votes -- UNOFFICIAL, validated at county level against MEDSL.

Used only for a state where the exact-count join of ``nyt_medsl`` fails (the two compilations split a precinct's votes differently, so precinct
counts do not agree) but the NYT precinct totals still reproduce MEDSL's independent county results: across the state the summed county deviation of
total votes is at most ``MAX_TOTAL_DEV`` and of Democratic votes at most ``MAX_DEM_DEV``. The precinct votes are then scaled county by county to the MEDSL
county totals (so every county keeps the MEDSL total). The geometry keeps the NYT resolution (precincts); the precinct split of votes inside a county is
the NYT's, not cross-validated.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pycensus.census.countries.usa.elections_precinct.nyt2024 import STATE_ABBR
from pycensus.census.countries.usa.elections_precinct.unofficial import medsl, nyt_medsl

MAX_TOTAL_DEV = 0.06
MAX_DEM_DEV = 0.07
ATTRIBUTION = ("Precinct polygons and votes: The New York Times 2024 presidential precinct map (nytimes/presidential-precinct-map-2024), county totals scaled to "
               "MEDSL Precinct-Level Returns 2024 (doi:10.7910/DVN/NYTPDU). Unofficial; county totals validated against MEDSL.")


def check(st: str, cache_dir=None):
    """NYT precinct votes against the MEDSL county totals of a state.

    Args:
        st: State abbreviation (lower case).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        ``(NYT polygons, comparison, total deviation, Democratic deviation)``.
    """
    g = nyt_medsl._nyt(st, cache_dir)
    m = medsl.load_president(st, cache_dir)
    g = g.copy()
    g["county_fips"] = g["GEOID"].astype(str).str[:5]
    cols = ["votes_dem", "votes_rep", "votes_total"]
    for c in cols:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    a, b = g.groupby("county_fips")[cols].sum(), m.groupby("county_fips")[cols].sum()
    j = a.join(b, lsuffix="_n", rsuffix="_m", how="outer").fillna(0)
    tot = abs(j.votes_total_n - j.votes_total_m).sum() / max(j.votes_total_m.sum(), 1)
    dem = abs(j.votes_dem_n - j.votes_dem_m).sum() / max(j.votes_dem_m.sum(), 1)
    return g, m, float(tot), float(dem)


MAX_FEC_DEV = 0.02
PARTIAL_OK = {"sd", "vt"}
_FEC = Path(__file__).resolve().parent / "verification" / "fec_2024_state_totals.json"


def check_fec(st: str, cache_dir=None):
    """NYT polygons+votes vs the FEC's official state totals: returns (frame, total deviation, Democratic deviation).

    Args:
        st: State abbreviation (lower case).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    g = nyt_medsl._nyt(st, cache_dir).copy()
    for c in ("votes_dem", "votes_rep", "votes_total"):
        g[c] = pd.to_numeric(g[c], errors="coerce")
    ref = json.loads(_FEC.read_text())["states"][st.lower()]
    return g, abs(g.votes_total.sum() - ref["total"]) / ref["total"], abs(g.votes_dem.sum() - ref["dem"]) / ref["dem"], ref


def _load_fec(st: str, cache_dir=None):
    """State where MEDSL's county totals are unusable (incomplete / doubled / FIPS mismatch) but the NYT precincts reproduce the official state
    totals within ``MAX_FEC_DEV``: the NYT votes are scaled by one statewide factor per column to the FEC totals; no county scaling."""
    g, tot, dem, ref = check_fec(st, cache_dir)
    if tot > MAX_FEC_DEV or dem > MAX_FEC_DEV:
        raise ValueError(f"{st}: NYT totals deviate from the FEC official state totals by {tot:.1%} (total) / {dem:.1%} (Democratic); not used")
    g = g[g["votes_total"].fillna(0) > 0].copy()
    for c, k in (("votes_dem", "dem"), ("votes_rep", "rep"), ("votes_total", "total")):
        g[c] = g[c] * (ref[k] / g[c].sum())
    g["county_fips"] = g["GEOID"].astype(str).str[:5]
    g["geometry"] = g.geometry.make_valid()
    return g[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)


def _load_partial(st: str, cache_dir=None):
    """State whose NYT file lacks whole counties or towns (SD, VT): counties whose NYT total reaches 97% of MEDSL's are scaled to the MEDSL county total,
    partly covered counties keep the NYT votes unscaled (no votes are invented for the missing precincts), counties with no NYT polygons are LEFT OUT
    (never filled with a county value)."""
    g, m, _, _ = check(st, cache_dir)
    cols = ["votes_dem", "votes_rep", "votes_total"]
    g = g[g["votes_total"].fillna(0) > 0].copy()
    g[cols] = g[cols].astype(float)
    want, have = m.groupby("county_fips")[cols].sum(), g.groupby("county_fips")[cols].sum()
    ratio = (have["votes_total"] / want["votes_total"]).reindex(have.index)
    full = g["county_fips"].map(ratio) >= 0.97
    for c in cols:
        f = g["county_fips"].map(want[c]) / g["county_fips"].map(have[c]).replace(0, np.nan)
        g.loc[full, c] = g.loc[full, c] * f[full].fillna(1.0)
    g["geometry"] = g.geometry.make_valid()
    return g[["county_fips"] + cols + ["geometry"]].reset_index(drop=True)


def _vt_towns(g, cache_dir=None):
    """Vermont: add the towns missing from the NYT file as Census 2020 voting districts (VT reports by town) carrying the MEDSL town votes, joined by
    town name; towns whose name has no single match stay out."""
    import re

    import geopandas as gpd

    from pycensus.census.countries.usa.voting_districts import load_vtd

    norm = lambda x: re.sub(r"[^a-z]", "", re.sub(r"\b(town|city|of)\b", "", str(x).lower()))
    m = medsl.load_president("vt", cache_dir)
    vtd = load_vtd("50", 2020).to_crs(g.crs)
    cover = g.geometry.union_all()
    vtd = vtd[vtd.geometry.representative_point().apply(lambda p: not cover.contains(p))].copy()
    vtd["k"] = vtd["NAME"].map(norm)
    m["k"] = m["precinct"].map(norm)
    mm = m.groupby("k")[["votes_dem", "votes_rep", "votes_total", "county_fips"]].agg({"votes_dem": "sum", "votes_rep": "sum", "votes_total": "sum", "county_fips": "first"})
    j = vtd.merge(mm.reset_index(), on="k", how="inner")
    j = j[~j["k"].duplicated(keep=False)]
    return gpd.GeoDataFrame(j[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]], geometry="geometry", crs=g.crs)


def load(state_fips: str, cache_dir=None):
    """NYT 2024 precinct polygons and votes when they agree with MEDSL (else with the FEC totals), scaled to the official
    totals.

    Args:
        state_fips: 2-digit state FIPS.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with votes.
    """
    st = STATE_ABBR[str(state_fips).zfill(2)].lower()
    try:
        g, m, tot, dem = check(st, cache_dir)
    except Exception:
        return _load_fec(st, cache_dir)
    if tot > MAX_TOTAL_DEV or dem > MAX_DEM_DEV:
        try:
            return _load_fec(st, cache_dir)
        except ValueError:
            if st in PARTIAL_OK:
                out = _load_partial(st, cache_dir)
                from pycensus.census.countries.usa.elections_precinct.unofficial import vest_residual
                out = vest_residual.fill(st, out, check(st, cache_dir)[1], cache_dir)
                return out
            raise
    want = m.groupby("county_fips")[["votes_dem", "votes_rep", "votes_total"]].sum()
    g = g[g["votes_total"].fillna(0) > 0].copy()
    have = g.groupby("county_fips")[["votes_dem", "votes_rep", "votes_total"]].transform("sum")
    for c in ("votes_dem", "votes_rep", "votes_total"):
        f = g["county_fips"].map(want[c]) / have[c].replace(0, np.nan)
        g[c] = g[c] * f.fillna(1.0)
    g["geometry"] = g.geometry.make_valid()
    out = g[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
    ref = json.loads(_FEC.read_text())["states"][st]
    if abs(out["votes_total"].sum() - ref["total"]) / ref["total"] > MAX_FEC_DEV:   # MEDSL's county totals themselves are off the official result (Alabama)
        return _load_fec(st, cache_dir)
    return out
