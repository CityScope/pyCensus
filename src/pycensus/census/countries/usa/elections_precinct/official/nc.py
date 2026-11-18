# -*- coding: utf-8 -*-
"""North Carolina -- 2024 general election, precinct level, from the State Board of Elections (dl.ncsbe.gov).

Results: ``ENRS/2024_11_05/results_pct_20241105.zip`` (official canvass, every contest by precinct; "non-real" precincts are the
county-wide absentee / provisional tabulations). Boundaries: ``PrecinctMaps/SBE_PRECINCTS_20240723.zip`` (the precinct file in force for
the election, EPSG:2264). Votes of non-real precincts are shared among the county's real precincts in proportion to their votes.
"""

from __future__ import annotations

import zipfile

import geopandas as gpd
import pandas as pd

from pycensus.elections_common import default_elections_cache, download

BASE = "https://s3.amazonaws.com/dl.ncsbe.gov"
RESULTS = BASE + "/ENRS/2024_11_05/results_pct_20241105.zip"
BOUNDS = BASE + "/PrecinctMaps/SBE_PRECINCTS_20240723.zip"
ATTRIBUTION = "North Carolina State Board of Elections: official 2024 general election precinct results and precinct boundaries (dl.ncsbe.gov)."
FIPS = "37"


def load(cache_dir=None) -> gpd.GeoDataFrame:
    """North Carolina official 2024 presidential results by precinct, joined to the official precinct polygons.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with ``votes_dem``, ``votes_rep``, ``votes_total``.
    """
    root = default_elections_cache(cache_dir) / "official_nc_2024"
    res_zip = download(RESULTS, root / "results_pct_20241105.zip")
    geo_zip = download(BOUNDS, root / "SBE_PRECINCTS_20240723.zip")
    with zipfile.ZipFile(res_zip) as z:
        r = pd.read_csv(z.open(z.namelist()[0]), sep="\t", dtype=str, encoding="latin-1")
    r.columns = [c.strip() for c in r.columns]
    r = r[r["Contest Name"] == "US PRESIDENT"].copy()
    r["v"] = pd.to_numeric(r["Total Votes"], errors="coerce").fillna(0.0)
    party = r["Choice Party"].str.strip()
    r["dem"] = r["v"].where(party == "DEM", 0.0)
    r["rep"] = r["v"].where(party == "REP", 0.0)
    t = r.groupby(["County", "Precinct", "Real Precinct"], as_index=False)[["dem", "rep", "v"]].sum()
    t["key"] = t["County"].str.strip().str.upper() + "|" + t["Precinct"].str.strip().str.upper()
    d = gpd.read_file(f"zip://{geo_zip}")
    d["key"] = d["county_nam"].str.strip().str.upper() + "|" + d["prec_id"].astype(str).str.strip().str.upper()
    d["county_fips"] = FIPS + (2 * d["county_id"].astype(int) - 1).astype(str).str.zfill(3)
    t["county"] = t["County"].str.strip().str.upper()
    # votes with no polygon (county-wide absentee / provisional tabulations, a few precincts missing from the map) are shared among the
    # county's mapped precincts in proportion to their votes, so every county total is preserved
    mapped = (t["Real Precinct"] == "Y") & t["key"].isin(set(d["key"]))
    real = t[mapped].copy()
    extra = t[~mapped].groupby("county")[["dem", "rep", "v"]].sum()
    share = real["v"] / real.groupby("county")["v"].transform("sum").replace(0, float("nan"))
    for c in ("dem", "rep", "v"):
        real[c] = real[c] + share.fillna(0.0) * real["county"].map(extra[c]).fillna(0.0)
    g = d.merge(real[["key", "dem", "rep", "v"]], on="key", how="inner").to_crs(4326)
    g = g.rename(columns={"dem": "votes_dem", "rep": "votes_rep", "v": "votes_total"})
    g["geometry"] = g.geometry.make_valid()
    return g[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
