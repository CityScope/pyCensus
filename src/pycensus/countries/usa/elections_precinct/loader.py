# -*- coding: utf-8 -*-
"""US precinct-level election results for the study cities (Boston, San Francisco).

Elections (latest completed as of 2026-10; Nov 3 2026 not yet held):

=========== ============================== ==============================
scope       Boston (MA)                    San Francisco (CA)
=========== ============================== ==============================
national    2024 US President (precinct)   2024 US President (precinct)
state       2022 Governor (precinct)       2022 Governor (precinct)
municipal   2025-11-04 Mayor (precinct)    2024-11-05 Mayor (precinct,
                                           first-choice votes of the RCV)
=========== ============================== ==============================

Sources
-------
* MIT Election Data + Science Lab (MEDSL) precinct files on GitHub
  (``MEDSL/2024-elections-official`` individual_states/{st}24.zip and
  ``MEDSL/2022-elections-official`` individual_states/2022-{st}-local-precinct-general.zip).
  MEDSL has no redaction in MA; CA has a handful of ``*`` cells (small-count
  redaction) that are treated as 0.
* Boston mayor 2025: City of Boston official PDF "General Municipal Election -
  November 4, 2025, Mayor, votes cast by precinct"
  (boston.gov/sites/default/files/file/2025/11/2025-11-04-Mayor.pdf, parsed with
  ``pdftotext -layout``) and the registered-voter PDF (turnout).
  The general was effectively uncontested (Wu 93%, write-ins); the contested
  race was the 2025-09-09 preliminary (``municipal_stage="prelim"``).
* Geometry: Boston Precinct Boundaries (data.boston.gov, 275 precincts) and SF
  "Election Precincts - Current, Defined 2022" (DataSF d6x4-hefw, 514 precincts).
  MEDSL SF precinct ids ``1101``/``1101A`` (A = absentee) are merged to the 4-digit id.

Resampling: precinct -> H3 res 8 dasymetric with WorldPop 2025 100 m (see
:mod:`pycensus.elections_common`), then H3 -> census (TIGER 2020 tract / block
group) population weighted by the same pixels.
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

from ....elections_common import (
    PopulationGrid, build_counts, default_elections_cache, download, find_worldpop, finalize_all,
    h3_to_units, load_blocs, units_to_h3, write_schema,
)

logger = logging.getLogger(__name__)

BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
MEDSL24 = "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/individual_states/{st}24.zip"
MEDSL22 = "https://raw.githubusercontent.com/MEDSL/2022-elections-official/main/individual_states/2022-{st}-local-precinct-general.zip"
BOSTON_PREC = ("https://data.boston.gov/dataset/c37ac1db-da06-4347-a130-96134be12fe6/resource/"
               "59ad0d8e-bafc-4206-9556-291a83dd137d/download/boston_precinct_boundaries.geojson")
SF_PREC = "https://data.sfgov.org/resource/d6x4-hefw.geojson?$limit=5000"
BOS_MAYOR_GEN = "https://www.boston.gov/sites/default/files/file/2025/11/2025-11-04-Mayor.pdf"
BOS_TURNOUT_GEN = "https://www.boston.gov/sites/default/files/file/2025/11/2025-Unofficial-Ward-Precinct-Results-General-Municipal-Election.pdf"
BOS_MAYOR_PRELIM = "https://www.boston.gov/sites/default/files/file/2025/10/001-2025-09-09-25-Mayor-RECOUNT.pdf"

#: (city, scope) -> dict(year, key, office, ...)
ELECTIONS = {
    ("boston", "national"): dict(year=2024, key="national_2024", state="ma", office="US PRESIDENT", src="medsl24"),
    ("boston", "state"): dict(year=2022, key="state_2022_ma", state="ma", office="GOVERNOR", src="medsl22"),
    ("boston", "municipal"): dict(year=2025, key="municipal_2025_boston", src="boston_pdf"),
    ("san_francisco", "national"): dict(year=2024, key="national_2024", state="ca", office="US PRESIDENT", src="medsl24"),
    ("san_francisco", "state"): dict(year=2022, key="state_2022_ca", state="ca", office="GOVERNOR", src="medsl22"),
    ("san_francisco", "municipal"): dict(year=2024, key="municipal_2024_sf", state="ca", office="MAYOR", src="medsl24"),
}
CITY_STATE_FIPS = {"boston": "25", "san_francisco": "06"}
PARTISAN = {"US PRESIDENT", "GOVERNOR"}
DROP = {"UNDERVOTE", "OVERVOTE", "UNDER VOTES", "OVER VOTES", "OVERVOTES", "UNDERVOTES"}
BLANK = {"BLANK", "BLANKS", "BLANK VOTES"}


def _raw(cache_dir) -> Path:
    p = default_elections_cache(cache_dir) / "raw" / "usa"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_medsl(zpath: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        return pd.read_csv(z.open(name), low_memory=False, dtype={"precinct": str})


def _precinct_geometry(city: str, raw: Path) -> gpd.GeoDataFrame:
    if city == "boston":
        g = gpd.read_file(download(BOSTON_PREC, raw / "boston_prec.geojson"))
        g["unit"] = g["WDPCT"].astype(str)
    else:
        g = gpd.read_file(download(SF_PREC, raw / "sf_prec.geojson"))
        g["unit"] = g["prec_2022"].astype(str)
    return g[["unit", "geometry"]].to_crs(4326)


def _medsl_long(city: str, e: dict, raw: Path) -> tuple:
    st = e["state"]
    if e["src"] == "medsl24":
        d = _read_medsl(download(MEDSL24.format(st=st), raw / f"{st}24.zip"))
    else:
        d = _read_medsl(download(MEDSL22.format(st=st), raw / f"2022-{st}.zip"))
    if city == "boston":
        d = d[d["precinct"].str.upper().str.startswith("BOSTON_WARD")]
        m = d["precinct"].str.extract(r"(?i)ward(\d+)_precinct(\d+)")
        d["unit"] = m[0].astype(int).map("{:02d}".format) + m[1].astype(int).map("{:02d}".format)
    else:
        d = d[d["county_name"].str.upper() == "SAN FRANCISCO"]
        p = d["precinct"].astype(str)
        d["unit"] = np.where(p.str.startswith("06075"), p.str[5:9], p.str.replace(r"[A-Za-z]+$", "", regex=True))
    off = d[d["office"].str.upper() == e["office"]].copy()
    electors = ballots = None
    if e["office"] == "MAYOR" or e["src"] == "medsl24":
        for nm in ("TOTAL REGISTRATION", "TOTAL VOTES"):
            t = d[d["office"].str.upper() == nm]
            s = pd.to_numeric(t["votes"], errors="coerce").fillna(0).groupby(t["unit"]).sum()
            if len(s):
                if nm == "TOTAL REGISTRATION":
                    electors = s
                else:
                    ballots = s
    off["votes"] = pd.to_numeric(off["votes"], errors="coerce").fillna(0)
    cand = off["candidate"].astype(str).str.upper()
    off = off[~cand.isin(DROP)]
    cand = off["candidate"].astype(str).str.upper()
    blank = off[cand.isin(BLANK)].groupby("unit")["votes"].sum()
    off = off[~cand.isin(BLANK)]
    if e["office"] in PARTISAN:
        off["party"] = off["party_simplified"].fillna("OTHER").str.upper()
    else:
        off["party"] = off["candidate"].astype(str).str.upper()
    long = off.groupby(["unit", "party"], as_index=False)["votes"].sum()
    return long, blank, electors, ballots


def _pdftext(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def _boston_mayor_long(url: str, raw: Path, turnout_url: Optional[str]):
    txt = _pdftext(download(url, raw / Path(url).name))
    rows, blank, ballots = [], {}, {}
    ward, precs = None, None
    for ln in txt.splitlines():
        m = re.search(r"VOTES CAST BY PRECINCT.*WARD\s*:\s*(\d+)", ln)
        if m:
            ward, precs = int(m.group(1)), None
            continue
        if ward is None:
            continue
        if ln.strip().startswith("CANDIDATES") and precs is None:
            precs = re.findall(r"\d+", ln)
            continue
        if precs is None or not ln.strip():
            continue
        mm = re.match(r"^\s*([A-Z][A-Z .'()\-]*?)\s{2,}((?:\d+\s+)*\d+)\s*$", ln)
        if not mm:
            continue
        name, nums = mm.group(1).strip(), [int(x) for x in mm.group(2).split()]
        if len(nums) != len(precs) + 1:
            continue
        vals = nums[:-1]
        for p, v in zip(precs[:-1] if precs[-1] == "TOTAL" else precs, vals):
            u = f"{ward:02d}{int(p):02d}"
            if name == "BLANKS":
                blank[u] = v
            elif name == "BALLOTS CAST":
                ballots[u] = v
            elif name != "VOTES CAST":
                rows.append((u, name, v))
    long = pd.DataFrame(rows, columns=["unit", "party", "votes"])
    long["party"] = long["party"].str.replace(r"\s*\(WRITE-IN\)", " (WRITE-IN)", regex=True)
    blank = pd.Series(blank, name="blank")
    electors = None
    if turnout_url:
        t = _pdftext(download(turnout_url, raw / Path(turnout_url).name))
        reg = {}
        t = t.split("BOSTON - Total")[0]
        for m in re.finditer(r"WARD\s+(\d+),\s+PRECINCT\s+(\d+)\s+([\d,]+)\s+([\d,]+)", t):
            reg[f"{int(m.group(1)):02d}{int(m.group(2)):02d}"] = int(m.group(3).replace(",", ""))
        electors = pd.Series(reg)
    return long, blank, electors, pd.Series(ballots)


def _long_for(city: str, scope: str, raw: Path, municipal_stage: str):
    e = ELECTIONS[(city, scope)]
    if e["src"] == "boston_pdf":
        if municipal_stage == "prelim":
            return _boston_mayor_long(BOS_MAYOR_PRELIM, raw, None)
        return _boston_mayor_long(BOS_MAYOR_GEN, raw, BOS_TURNOUT_GEN)
    return _medsl_long(city, e, raw)


def _census(city: str, level: str, census_geometry, year: int = 2020) -> gpd.GeoDataFrame:
    if census_geometry is not None:
        return census_geometry
    from ..geography import load_boundaries

    return load_boundaries(level, CITY_STATE_FIPS[city], year)


def load_all(
    city: str,
    scope: str,
    census_levels=("tract", "blockgroup"),
    census_geometry: Optional[Dict[str, gpd.GeoDataFrame]] = None,
    worldpop_path: Optional[str] = None,
    cache_dir: Optional[str] = None,
    municipal_stage: str = "general",
) -> Dict[str, pd.DataFrame]:
    """All geographies for one election: ``{"precinct", "h3", "tract", "blockgroup"}``.

    ``census_geometry`` may map level -> GeoDataFrame(GEOID, geometry) to avoid TIGER downloads.

    Args:
        city: City key (``"boston"``...).
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        census_levels: Census levels built.
        census_geometry: ``{level: polygons}``.
        worldpop_path: Explicit WorldPop raster.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        municipal_stage: ``"general"`` or ``"prelim"`` (Boston municipal).
    """
    e = ELECTIONS[(city, scope)]
    year = e["year"]
    raw = _raw(cache_dir)
    cache = default_elections_cache(cache_dir) / "processed" / "usa"
    cache.mkdir(parents=True, exist_ok=True)
    tag = f"{city}_{scope}_{year}{'_prelim' if municipal_stage == 'prelim' and scope == 'municipal' and city == 'boston' else ''}"
    long, blank, electors, ballots = _long_for(city, scope, raw, municipal_stage)
    blocs = load_blocs(BLOCS_PATH, e["key"] if not (city == "boston" and scope == "municipal" and municipal_stage == "prelim") else "municipal_2025_boston_prelim")
    geom = _precinct_geometry(city, raw)
    unmatched = set(long["unit"]) - set(geom["unit"])
    if unmatched:
        v = long[long.unit.isin(unmatched)]["votes"].sum()
        logger.warning("%d precinct ids without geometry (%d votes dropped): %s", len(unmatched), v, sorted(unmatched)[:8])
    long = long[long.unit.isin(geom["unit"])]
    counts = build_counts(long, blocs, blank=blank, electors=electors, ballots=ballots)
    counts = counts[counts.index.isin(geom["unit"])]
    if "electors" in counts and (counts["electors"].fillna(0) == 0).all():
        counts = counts.drop(columns=["electors"])
    bounds = geom.total_bounds
    pad = 0.01
    grid = PopulationGrid(find_worldpop("usa", worldpop_path), (bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad))
    h3c = units_to_h3(geom.drop_duplicates("unit"), counts, grid)
    out_counts = {}
    for lvl in census_levels:
        cg = (census_geometry or {}).get(lvl)
        cg = _census(city, lvl, cg)
        out_counts[lvl] = h3_to_units(h3c, cg[["GEOID", "geometry"]], grid)
    # keep only census units that received votes
    res = {"precinct": counts, "h3": h3c, **out_counts}
    fin = {}
    from ....elections_common import kept_parties, finalize
    parties = kept_parties(counts)
    for k, v in res.items():
        f = finalize(v, scope, year, parties)
        f.index.name = {"precinct": "precinct", "h3": "h3_cell"}.get(k, "GEOID")
        fin[k] = f
    for k in out_counts:
        fin[k] = fin[k][fin[k].iloc[:, 0] > 0]
    return fin


def load(city: str, scope: str, level: str = "tract", **kw) -> pd.DataFrame:
    """One frame: ``level`` in ``tract``, ``blockgroup`` (index GEOID), ``h3`` (index h3_cell, res 8) or ``precinct``.

    Example: ``load("boston", "national", level="tract")``.

    Args:
        city: City key.
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        level: ``"tract"``, ``"blockgroup"``, ``"h3"`` or ``"precinct"``.
        **kw: Passed to :func:`load_all`.

    Returns:
        The frame of that level.
    """
    levels = (level,) if level in ("tract", "blockgroup") else ()
    return load_all(city, scope, census_levels=levels, **kw)[level]
