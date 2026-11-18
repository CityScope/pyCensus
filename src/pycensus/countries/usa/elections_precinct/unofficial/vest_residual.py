# -*- coding: utf-8 -*-
"""Gap filling for states whose NYT precinct file lacks counties or towns (South Dakota, Vermont) -- ESTIMATED sub-county votes, UNOFFICIAL.

The MEDSL county total minus what the NYT precincts already hold in that county (the *shortfall*) is spread over the VEST 2020 precinct polygons
(Harvard Dataverse doi:10.7910/DVN/K7760H) that the NYT polygons do not cover, in proportion to each precinct's 2020 presidential votes (Democratic
shortfall by 2020 Democratic votes, Republican by Republican, total by all). Every county therefore keeps its MEDSL county total, and the votes of
a precinct are an allocation, not a count: ``estimated`` is True on those rows.
"""

from __future__ import annotations

import glob
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd

from .....elections_common import default_elections_cache, download

DATAFILES = {"sd": 6082788, "vt": 14304794}
ATTRIBUTION_SUFFIX = ("Precincts missing from the NYT file: ESTIMATED by allocating the MEDSL county shortfall over VEST 2020 precinct polygons "
                       "(Voting and Election Science Team, doi:10.7910/DVN/K7760H) in proportion to their 2020 presidential votes.")


def _vest(st: str, cache_dir=None) -> gpd.GeoDataFrame:
    root = default_elections_cache(cache_dir) / "vest_2020" / st
    root.mkdir(parents=True, exist_ok=True)
    z = download(f"https://dataverse.harvard.edu/api/access/datafile/{DATAFILES[st]}?format=original", root / f"{st}_2020.zip", timeout=900)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(root)
    g = gpd.read_file(glob.glob(str(root / "*.shp"))[0]).to_crs(4326)
    cf = "COUNTYFP20" if "COUNTYFP20" in g.columns else "COUNTYFP"
    sf = "STATEFP20" if "STATEFP20" in g.columns else "STATEFP"
    g["county_fips"] = g[sf].astype(str).str.zfill(2) + g[cf].astype(str).str.zfill(3)
    pre = [c for c in g.columns if c.startswith("G20PRE")]
    g["w_dem"] = pd.to_numeric(g["G20PREDBID"], errors="coerce").fillna(0.0)
    g["w_rep"] = pd.to_numeric(g["G20PRERTRU"], errors="coerce").fillna(0.0)
    g["w_tot"] = g[pre].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
    return g[["county_fips", "w_dem", "w_rep", "w_tot", "geometry"]]


def fill(st: str, base: gpd.GeoDataFrame, medsl_votes: pd.DataFrame, cache_dir=None) -> gpd.GeoDataFrame:
    """`base` (NYT precincts with ``county_fips`` and the three vote columns, unscaled) plus estimated rows for the uncovered VEST polygons.

    Args:
        st: State abbreviation.
        base: NYT precincts with votes.
        medsl_votes: MEDSL votes per precinct.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    cols = ["votes_dem", "votes_rep", "votes_total"]
    want = medsl_votes.groupby("county_fips")[cols].sum()
    have = base.groupby("county_fips")[cols].sum().reindex(want.index).fillna(0.0)
    short = (want - have).clip(lower=0.0)
    v = _vest(st, cache_dir)
    cover = base.geometry.union_all()
    v = v[~v.geometry.representative_point().apply(cover.contains)].copy()
    out = []
    for cty, grp in v.groupby("county_fips"):
        if cty not in short.index:
            continue
        row = grp.copy()
        for c, w in (("votes_dem", "w_dem"), ("votes_rep", "w_rep"), ("votes_total", "w_tot")):
            tot = row[w].sum()
            row[c] = short.loc[cty, c] * (row[w] / tot if tot > 0 else 1.0 / len(row))
        out.append(row)
    if not out:
        return base
    est = pd.concat(out)[["county_fips"] + cols + ["geometry"]]
    est["estimated"] = True
    b = base[["county_fips"] + cols + ["geometry"]].copy()
    b["estimated"] = False
    return gpd.GeoDataFrame(pd.concat([b, est], ignore_index=True), geometry="geometry", crs=base.crs)
