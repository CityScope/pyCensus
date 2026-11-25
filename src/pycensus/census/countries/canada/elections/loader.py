# -*- coding: utf-8 -*-
"""Election results for Toronto at the finest published unit, resampled to H3 res 8 and dissemination areas (DA 2021).

=========== =========================================== ============================== ======================
scope       election                                    native unit                    geometry
=========== =========================================== ============================== ======================
national    45th federal general election, 2025-04-28   polling division (~4,600 in    Elections Canada PD
                                                        the city, incl. mobile polls)  boundaries 2025 (SHP)
state       Ontario general election, 2025-02-27        polling division               Elections Ontario PD
                                                                                       shapefile 2025
municipal   Toronto general election, 2022-10-24, mayor voting subdivision (~1,460)    City of Toronto Open
                                                                                       Data subdivisions 2022
=========== =========================================== ============================== ======================

(The 2023-06-26 Toronto mayoral by-election and the 2026 Ontario by-elections are NOT used: only regular general elections.)

Sources
-------
* Federal: Elections Canada "45th General Election: Official Voting Results (raw data)" poll-by-poll CSV,
  ``https://www.elections.ca/res/rep/off/ovrGE45/62/data_donnees/pollresults_resultatsbureau{FED}.zip`` and boundary file
  ``https://www.elections.ca/res/cir/mapsCorner/vector/PollingDivisionBoundaries_2025_SHP.zip`` (92.8 MB).
* Ontario: Elections Ontario results portal API (``results.elections.on.ca/api/report-groups/48/report-outputs/1095/csv`` "Official
  Return from the Records", poll-by-poll; ``.../1096/csv`` candidates with party code) and the "Polling Division Shapefile - 2025
  General Election.zip" (``elections.on.ca/content/dam/NGW/sitecontent/2017/preo/shapefiles/``; **limited-use data licence** - check
  the licence on the download page before redistributing).
* Toronto: Open Data "Elections - Official Results" 2022 poll-by-poll XLSX zip, and "Elections Subdivisions" 2022 GeoJSON.
* Census geometry: StatCan 2021 DA (``dissemination-area``; www12.statcan.gc.ca is behind a Cloudflare challenge and is NOT bypassed:
  pass ``census_geometry`` or rely on pycensus.canada.geography's ArcGIS cache).

Votes without polygon (federal special ballots "S/R", Ontario advance polls ``ADVnnn``, Toronto subdivisions 97-99, polls
missing in the geometry) are pooled per riding/ward and spread over that district's polygons proportionally to registered electors.
total_votes = valid votes (federal/Ontario: candidates; Toronto: candidates incl. write-ins); turnout = (valid + rejected ballots)
/ electors for federal, absent for Ontario (advance polls have no electors) and Toronto (voter counts per subdivision only
partially cover pooled votes; reported as valid mayor votes / VOTER_COUNT, may exceed...: clipped to 1).
"""

from __future__ import annotations

import glob
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Dict, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

from pycensus.elections_common import (
    POOL, allocate_pools, build_counts, default_elections_cache, download, load_blocs, run_pipeline,
)

logger = logging.getLogger(__name__)

BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
EC = "https://www.elections.ca"
PD_FED = EC + "/res/cir/mapsCorner/vector/PollingDivisionBoundaries_2025_SHP.zip"
FED_RES = EC + "/res/rep/off/ovrGE45/62/data_donnees/pollresults_resultatsbureau{prov}.zip"
ON_API = "https://results.elections.on.ca/api/report-groups/48/report-outputs/{rid}/csv"
ON_PD = "https://www.elections.on.ca/content/dam/NGW/sitecontent/2017/preo/shapefiles/Polling%20Division%20Shapefile%20-%202025%20General%20Election.zip"
CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
TOR_WARDS = CKAN + "/dataset/5e7a8234-f805-43ac-820f-03d7c360b588/resource/737b29e0-8329-4260-b6af-21555ab24f28/download/city-wards-data-4326.geojson"
TOR_RES22 = CKAN + "/dataset/96d35404-44d9-49d8-95bb-fb1e5489240d/resource/3ad371de-7c51-45d3-9ea4-0b4efac5fc2b/download/2022-results.zip"
TOR_SUB22 = CKAN + "/dataset/1f5df7fa-8606-4085-b75e-6d658a227558/resource/38a9aa78-be8e-468c-9b80-262535c9bd84/download/voting-subdivisions-2022-4326.geojson"

ELECTIONS = {
    "national": dict(year=2025, key="national_2025", name="45th federal general election (2025-04-28)"),
    "state": dict(year=2025, key="state_2025_on", name="Ontario general election (2025-02-27)"),
    "municipal": dict(year=2022, key="municipal_2022_toronto", name="Toronto municipal election, mayor (2022-10-24)"),
}


def _raw(cache_dir) -> Path:
    p = default_elections_cache(cache_dir) / "raw" / "canada"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _city(raw: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(download(TOR_WARDS, raw / "tor_wards.geojson")).to_crs(4326)


def _pdkey(s: str) -> str:
    """'7' -> '7-0'; '7-1' -> '7-1'; '84A' -> '84-0' (letter sub-polls merge into the base division)."""
    m = re.match(r"\s*(\d+)(?:-(\d+))?", str(s))
    return f"{int(m.group(1))}-{int(m.group(2) or 0)}" if m else "S"


# ----------------------------------------------------------------------- federal
def _area(raw: Path, area):
    """The study area (a shapely geometry in EPSG:4326) or, by default, the City of Toronto."""
    if area is not None:
        return area
    city = _city(raw)
    return city.union_all() if hasattr(city, "union_all") else city.unary_union


def _federal(raw: Path, area=None):
    cu = _area(raw, area)
    shp_zip = download(PD_FED, raw / "pd2025_shp.zip")
    d = raw / "pd2025"
    if not d.exists():
        zipfile.ZipFile(shp_zip).extractall(d)
    shp = glob.glob(str(d / "**" / "*.shp"), recursive=True)[0]
    g = gpd.read_file(shp, where="FED_NUM>=35000 AND FED_NUM<36000").to_crs(4326)
    rep = g.copy()
    rep["geometry"] = rep.representative_point()
    keep = g[rep.within(cu).to_numpy()]
    feds = sorted(keep["FED_NUM"].unique())
    keep = g[g["FED_NUM"].isin(feds)].copy()  # whole ridings: advance/special votes are pooled per riding
    keep["unit"] = keep["FED_NUM"].astype(str) + "_" + keep["PD_NUM_SFX"].astype(str)
    # study-area units = polygons whose representative point lies in the city; others only act as pool recipients? no: drop
    inside = rep.loc[keep.index].within(cu).to_numpy()
    keep["inside"] = inside
    z = download(FED_RES.format(prov="35"), raw / "fed45_on_res.zip")
    rows = []
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            m = re.search(r"(\d{5})\.csv$", n)
            if m and int(m.group(1)) in feds:
                rows.append(pd.read_csv(zf.open(n), dtype=str, encoding="utf-8-sig"))
    d = pd.concat(rows)
    d.columns = [c.split("/")[0] for c in d.columns]
    d["votes"] = d["Candidate Vote Count"].astype(float)
    d["fed"] = d["Electoral District Number"].astype(str)
    d["key"] = d["fed"] + "_" + d["Polling Division Number"].map(_pdkey)
    d["matched"] = d["key"].isin(set(keep["unit"]))
    d["unit"] = np.where(d["matched"], d["key"], POOL + d["fed"])
    d["party"] = d["Political Affiliation Name_English"]
    per_poll = d.drop_duplicates(["fed", "Polling Division Number"]).copy()
    per_poll["unit"] = np.where(per_poll["key"].isin(set(keep["unit"])), per_poll["key"], POOL + per_poll["fed"])
    per_poll["el"] = pd.to_numeric(per_poll["Electors for poll"], errors="coerce").fillna(0)
    per_poll["rej"] = pd.to_numeric(per_poll["Rejected Ballots for poll"], errors="coerce").fillna(0)
    electors = per_poll.groupby("unit")["el"].sum()
    rejected = per_poll.groupby("unit")["rej"].sum()
    long = d.groupby(["unit", "party"], as_index=False)["votes"].sum()
    return keep, long, electors, rejected, "fed"


def _federal_counts(raw, blocs, area=None):
    keep, long, electors, rejected, _ = _federal(raw, area)
    c = build_counts(long, blocs, electors=electors, rejected=rejected)
    ug = pd.Series(keep["FED_NUM"].astype(str).to_numpy(), index=keep["unit"].to_numpy())
    c = allocate_pools(c, ug, c["electors"].where(~c.index.str.startswith(POOL), 0).fillna(0))
    geom = keep.loc[keep["inside"], ["unit", "geometry"]]
    return geom, c


# ---------------------------------------------------------------------- Ontario
def _ontario_counts(raw, blocs, area=None):
    cu = _area(raw, area)
    z = download(ON_PD, raw / "on_pd2025.zip")
    d = raw / "on_pd2025"
    if not d.exists():
        zipfile.ZipFile(z).extractall(d)
    g = gpd.read_file(glob.glob(str(d / "*.shp"))[0]).to_crs(4326)
    rep = g.copy()
    rep["geometry"] = rep.representative_point()
    eds = sorted(g.loc[rep.within(cu).to_numpy(), "ED_ID"].unique())
    g = g[g["ED_ID"].isin(eds)].copy()
    g["unit"] = g["ED_ID"].astype(int).astype(str).str.zfill(3) + "_" + g["PD_LABEL"].astype(str).str.zfill(3)
    g["inside"] = rep.loc[g.index].within(cu).to_numpy()
    res = pd.read_csv(download(ON_API.format(rid=1095), raw / "on2025_return.csv"), dtype=str, encoding="utf-8-sig")
    res = res[res["EventNameEnglish"].str.contains("2025 Provincial General")].copy()
    cand = pd.read_csv(download(ON_API.format(rid=1096), raw / "on2025_cands.csv"), dtype=str, encoding="utf-8-sig")
    cand = cand[cand["EventNameEnglish"].str.contains("2025 Provincial General")]
    res["ed"] = res["ElectoralDistrictNameEnglish"].str[:3]
    res = res[res["ed"].isin(set(g["unit"].str[:3]))]
    cand["ed"] = cand["ElectoralDistrictNumber"].astype(str).str.zfill(3)
    def _nk(n):  # "SNOW, MARK" and "MARK SNOW" -> same key
        return " ".join(sorted(re.sub(r"[^A-Z ]", " ", str(n).upper()).split()))

    pc = {(e_, _nk(n)): c_ for e_, n, c_ in zip(cand["ed"], cand["NameOfCandidates"], cand["PoliticalInterestCode"])}
    res["party"] = [pc.get((e_, _nk(n)), "IND") for e_, n in zip(res["ed"], res["NameOfCandidates"])]
    miss = sum(1 for e_, n in zip(res["ed"], res["NameOfCandidates"]) if (e_, _nk(n)) not in pc)
    if miss:
        logger.warning("%d result rows with candidate not matched to a party code (-> IND)", miss)
    res["votes"] = pd.to_numeric(res["AcceptedBallotCount"], errors="coerce").fillna(0)
    std = (res["PollCategory"] == "Standard") & (res["ed"] + "_" + res["PollNumber"].astype(str).str.zfill(3)).isin(set(g["unit"]))
    res["unit"] = np.where(std, res["ed"] + "_" + res["PollNumber"].astype(str).str.zfill(3), POOL + res["ed"])
    polls = res.drop_duplicates(["ed", "PollCategory", "PollNumber"]).copy()
    polls["unit"] = np.where(polls["PollCategory"].eq("Standard") & (polls["ed"] + "_" + polls["PollNumber"].astype(str).str.zfill(3)).isin(set(g["unit"])),
                             polls["ed"] + "_" + polls["PollNumber"].astype(str).str.zfill(3), POOL + polls["ed"])
    polls["el"] = pd.to_numeric(polls["NamesOnListOfElectors"], errors="coerce").fillna(0)
    electors = polls[~polls.unit.str.startswith(POOL)].groupby("unit")["el"].sum()
    long = res.groupby(["unit", "party"], as_index=False)["votes"].sum()
    c = build_counts(long, blocs, electors=electors)
    ug = pd.Series(g["ED_ID"].astype(int).astype(str).str.zfill(3).to_numpy(), index=g["unit"].to_numpy())
    c = allocate_pools(c, ug, c["electors"].fillna(0))
    c = c.drop(columns=["electors"], errors="ignore")  # advance polls have no elector counts -> turnout not defined
    return g.loc[g["inside"], ["unit", "geometry"]], c


# ---------------------------------------------------------------------- Toronto
def _toronto_counts(raw, blocs):
    z = download(TOR_RES22, raw / "tor2022.zip")
    xls = pd.read_excel(zipfile.ZipFile(z).open("2022_Toronto_Poll_By_Poll_Mayor.xlsx"), sheet_name=None, header=None)
    g = gpd.read_file(download(TOR_SUB22, raw / "tor_subdiv2022.geojson")).to_crs(4326)
    g["unit"] = g["AREA_LONG_CODE"].astype(str).str.zfill(5)
    have = set(g["unit"])
    rows = []
    for sh, x in xls.items():
        ward = int(re.search(r"\d+", sh).group())
        hdr = x.iloc[1].tolist()
        subs = hdr[1:-1]
        for r in range(3, len(x)):
            name = str(x.iloc[r, 0])
            if "Totals" in name:
                break
            for j, s in enumerate(subs, start=1):
                v = x.iloc[r, j]
                if pd.notna(v):
                    u = f"{ward:02d}{int(float(s)):03d}"
                    rows.append((u if u in have else POOL + f"{ward:02d}", name, float(v)))
    long = pd.DataFrame(rows, columns=["unit", "party", "votes"]).groupby(["unit", "party"], as_index=False)["votes"].sum()
    electors = g.groupby("unit")["VOTER_COUNT"].sum().astype(float)
    c = build_counts(long, blocs, electors=electors)
    c["ballots"] = c["total_votes"]
    ug = pd.Series(g["unit"].str[:2].to_numpy(), index=g["unit"].to_numpy())
    c = allocate_pools(c, ug, electors)
    return g[["unit", "geometry"]], c


def _census(census_geometry, levels):
    if census_geometry is None:
        from pycensus.census.countries.canada.geography import load_boundaries

        da = load_boundaries("dissemination-area", "35")
        census_geometry = {"da": da}
    out = {}
    for k, v in census_geometry.items():
        v = v.copy()
        if "GEOID" not in v.columns and "DAUID" in v.columns:
            v = v.rename(columns={"DAUID": "GEOID"})
        out[k] = v[["GEOID", "geometry"]]
    return out


def load_all(scope: str, census_geometry: Optional[Dict[str, gpd.GeoDataFrame]] = None, worldpop_path: Optional[str] = None,
             cache_dir: Optional[str] = None, area=None) -> Dict[str, pd.DataFrame]:
    """``{"poll", "h3", "da"}`` frames for scope in national/state/municipal.

    ``census_geometry``: ``{"da": GeoDataFrame(GEOID|DAUID, geometry)}`` (2021 dissemination areas around Toronto).

    Args:
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        census_geometry: ``{"da": dissemination areas}``.
        worldpop_path: Explicit WorldPop raster.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        area: Study area (shapely geometry, EPSG:4326 -- e.g. the union of the census geometry): the federal and Ontario elections take
            every polling division whose representative point lies in it (all of the province publishes them); ``None`` = the City of
            Toronto. The municipal election is the City of Toronto's in any case.
    """
    e = ELECTIONS[scope]
    raw = _raw(cache_dir)
    blocs = load_blocs(BLOCS_PATH, e["key"])
    if scope == "municipal":
        geom, counts = _toronto_counts(raw, blocs)
    else:
        geom, counts = {"national": _federal_counts, "state": _ontario_counts}[scope](raw, blocs, area)
    return run_pipeline(geom, counts, scope, e["year"], "can", _census(census_geometry, None), worldpop_path, unit_label="poll")


def load(scope: str, level: str = "da", **kw) -> pd.DataFrame:
    """One frame: level ``da`` (index GEOID = DAUID), ``h3`` (index h3_cell, res 8) or ``poll``.

    Example: ``load("national", level="da")``.

    Args:
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        level: ``"da"``, ``"h3"`` or ``"poll"``.
        **kw: Passed to :func:`load_all`.

    Returns:
        The frame of that level.
    """
    return load_all(scope, **kw)[level]
