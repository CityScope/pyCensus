# -*- coding: utf-8 -*-
"""Delaware -- 2024 general election by ELECTION DISTRICT, from the Department of Elections and the state's own election-district map.

Results: the official "2024 General Election Report" (``elections.delaware.gov/reports/GE2024.html``, by-election-district section, every
contest). Boundaries: FirstMap ``DE_Political_Boundaries`` layer 0 "Election Districts" (State of Delaware, Department of Elections; updated
Nov 2023, so it holds the districts used on 2024-11-05). Key: ``RDED`` ("01-01" = representative district 01, election district 01).
The report lists six districts with no polygon (02-27, 31-16, 41-16 with 922 votes in all; 02-28, 31-17, 41-17 are empty): their votes are
shared among the mapped election districts of the same representative district in proportion to their votes, so every representative
district keeps its total (the statewide total is exact).
"""

from __future__ import annotations

import re

import geopandas as gpd
import pandas as pd

from .....elections_common import default_elections_cache, download

REPORT = "https://elections.delaware.gov/reports/GE2024.html"
BOUNDS = ("https://enterprise.firstmap.delaware.gov/arcgis/rest/services/Boundaries/DE_Political_Boundaries/FeatureServer/0/query"
          "?where=1%3D1&outFields=*&f=geojson&outSR=4326&resultRecordCount=2000")
ATTRIBUTION = ("Delaware Department of Elections: official 2024 General Election Report by election district (elections.delaware.gov) and "
               "State of Delaware FirstMap election-district boundaries (DE_Political_Boundaries, Department of Elections).")
FIPS = "10"
OFFICE = "President and Vice President"


def _report_rows(html: str, contest: str) -> pd.DataFrame:
    i, j = html.find('id="byelectiondist"'), html.find('id="bycounty"')
    sec = html[i:j]
    start = sec.find(f'<h3 class="contest-title {contest}')
    nxt = sec.find('<h3 class="contest-title', start + 50)
    block = sec[start: nxt if nxt > 0 else len(sec)]
    rows = []
    for m in re.finditer(r"Election District (\d\d-\d\d) </h4><table.*?</table>", block, re.S):
        for r in re.finditer(r'data-label="Party">([^<]*)</td>.*?data-label="Total Votes">([\d,]+)', m.group(0), re.S):
            rows.append((m.group(1), r.group(1).strip(), float(r.group(2).replace(",", ""))))
    return pd.DataFrame(rows, columns=["rded", "party", "v"])


def load(cache_dir=None) -> gpd.GeoDataFrame:
    """Delaware official 2024 presidential results by precinct, joined to the official precinct polygons.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with ``votes_dem``, ``votes_rep``, ``votes_total``.
    """
    root = default_elections_cache(cache_dir) / "official_de_2024"
    html = download(REPORT, root / "GE2024.html").read_text(encoding="utf-8", errors="ignore")
    r = _report_rows(html, "PresidentandVicePresident")
    t = r.pivot_table(index="rded", columns="party", values="v", aggfunc="sum").fillna(0.0)
    t = pd.DataFrame({"votes_dem": t.get("Democratic Party", 0.0), "votes_rep": t.get("Republican Party", 0.0), "votes_total": t.sum(axis=1)})
    poly = gpd.read_file(download(BOUNDS, root / "election_districts.geojson"))
    poly = poly[["RDED", "DISTRICT", "geometry"]].rename(columns={"RDED": "rded"})
    poly["geometry"] = poly.geometry.make_valid()
    t["rd"] = t.index.str[:2]
    mapped = t.index.isin(poly["rded"])
    extra = t[~mapped].groupby("rd")[["votes_dem", "votes_rep", "votes_total"]].sum()
    real = t[mapped].copy()
    share = real["votes_total"] / real.groupby("rd")["votes_total"].transform("sum").replace(0, float("nan"))
    for c in ("votes_dem", "votes_rep", "votes_total"):
        real[c] = real[c] + share.fillna(0.0) * real["rd"].map(extra[c]).fillna(0.0)
    g = poly.merge(real.drop(columns="rd"), left_on="rded", right_index=True, how="inner")
    # county of each election district: the Census county holding its representative point (counties come from the 2020 voting districts' GEOID)
    from ...voting_districts import load_vtd
    v = load_vtd(FIPS, 2020)[["GEOID", "geometry"]]
    pts = gpd.GeoDataFrame(geometry=g.geometry.representative_point(), crs=g.crs)
    j = gpd.sjoin_nearest(pts.to_crs(5070), v.to_crs(5070), how="left")
    j = j[~j.index.duplicated(keep="first")]
    g["county_fips"] = j["GEOID"].astype(str).str[:5].to_numpy()
    return g[["county_fips", "rded", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
