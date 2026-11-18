# -*- coding: utf-8 -*-
"""California -- 2024 general election by registration-precinct (SRPREC), from the Statewide Database (UC Berkeley, the state's redistricting database).

Results: ``state_g24_sov_data_by_g24_srprec.csv`` = the counties' Statement of Vote tabulated to the 2024 general-election SRPRECs (``PRSDEM01``
Harris, ``PRSREP01`` Trump, all ``PRS*`` columns together = presidential total). Boundaries: ``srprec_state_g24_v01_shp.zip`` (the SRPREC polygons of that
election, built from the counties' own precinct maps). Rows with no polygon (county-wide absentee / provisional tabulations, a few precincts missing from the map)
are shared among the county's mapped precincts in proportion to their votes, so every county keeps its Statement-of-Vote total.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from pycensus.elections_common import default_elections_cache, download

BASE = "https://statewidedatabase.org/pub/data/G24/state/"
RESULTS = BASE + "state_g24_sov_data_by_g24_srprec.csv"
BOUNDS = BASE + "srprec_state_g24_v01_shp.zip"
ATTRIBUTION = ("California Statewide Database (UC Berkeley Law, the state's redistricting database): 2024 general election Statement of Vote by SRPREC "
               "(statewidedatabase.org/pub/data/G24/state/).")
FIPS = "06"


def load(cache_dir=None) -> gpd.GeoDataFrame:
    """California official 2024 presidential results by precinct, joined to the official precinct polygons.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with ``votes_dem``, ``votes_rep``, ``votes_total``.
    """
    root = default_elections_cache(cache_dir) / "official_ca_2024"
    r = pd.read_csv(download(RESULTS, root / "sov_srprec.csv"), dtype=str)
    prs = [c for c in r.columns if c.startswith("PRS")]
    for c in prs:
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0.0)
    r["votes_dem"], r["votes_rep"], r["votes_total"] = r["PRSDEM01"], r["PRSREP01"], r[prs].sum(axis=1)
    r["key"] = r["SRPREC_KEY"].astype(str).str.strip()
    r["county_fips"] = r["FIPS"].astype(str).str.zfill(5).where(r["FIPS"].astype(str).str.len() > 3, "06" + r["FIPS"].astype(str).str.zfill(3))
    shp = gpd.read_file(f"zip://{download(BOUNDS, root / 'srprec_g24.zip')}")
    shp["key"] = shp["SRPREC_KEY"].astype(str).str.strip()
    shp = shp.drop_duplicates("key")[["key", "geometry"]]
    mapped = r["key"].isin(set(shp["key"]))
    real = r[mapped].copy()
    extra = r[~mapped].groupby("county_fips")[["votes_dem", "votes_rep", "votes_total"]].sum()
    share = real["votes_total"] / real.groupby("county_fips")["votes_total"].transform("sum").replace(0, float("nan"))
    for c in ("votes_dem", "votes_rep", "votes_total"):
        real[c] = real[c] + share.fillna(0.0) * real["county_fips"].map(extra[c]).fillna(0.0)
    g = shp.merge(real[["key", "county_fips", "votes_dem", "votes_rep", "votes_total"]], on="key", how="inner").to_crs(4326)
    g["geometry"] = g.geometry.make_valid()
    return g[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
