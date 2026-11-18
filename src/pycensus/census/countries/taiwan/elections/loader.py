"""CEC (中央選舉委員會) election database loader: results per village (村里, native resolution) -> H3 res 8.

Source: https://db.cec.gov.tw/ElecTable/Election/ElectionList (keyless static JSON behind the Nuxt app, discovered from its JS bundle):
  list   https://db.cec.gov.tw/static/elections/list/ELC_{subject}.json                (themes: theme_id, session, vote_date, legislator type)
  data   https://db.cec.gov.tw/static/elections/data/{tickets|profiles}/ELC/{subject}/{legis}/{theme_id}/L/{prv}_{city}_00_000_0000.json
``L`` = village level; one file holds every village of a county/city (dict keyed by district). ``tickets`` = votes per candidate/party and village,
``profiles`` = valid/invalid/cast ballots and eligible voters (votable_population) per village. CEC ``prv+city+dept+li`` maps to MOI's 11-digit
village GEOID as ``prv(2)+city(3)+dept(3)+li[1:](3)`` (verified 456/456 for Taipei vs MOI RIS).

Subjects: P0 president (legis 00), L0 legislators (L4 = nationwide party-list vote used for ``load_legislative``), C1/C2 mayor of special
municipality / county-city (00), T1/T2 council of special municipality / county-city (T1 = regional constituencies; indigenous seats T2/T3 excluded).

Left/right: see ``schema/taiwan_elections_blocs.json`` (DPP & progressive small parties = left, KMT/PFP/NP = right, TPP/independents = other).
H3: village polygons (OSM Overpass via ``taiwan.geography.load_boundaries('village')``) -> res-8 cells, AREA-WEIGHTED (see ``pycensus.electoral``).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import json
from collections import namedtuple
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

from pycensus import electoral
from pycensus.census.countries.taiwan import constants, geography

ElectionResult = namedtuple("ElectionResult", ["census", "h3"])
BASE = "https://db.cec.gov.tw/static/elections/"
HEAD = {"User-Agent": "Mozilla/5.0 (pycensus research loader)"}
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "taiwan_elections_blocs.json"
SPECIAL_MUNI_PRV = {"63", "64", "65", "66", "67", "68"}
PARTY_SLUGS = {"中國國民黨": "kmt", "民主進步黨": "dpp", "台灣民眾黨": "tpp", "時代力量": "npp", "社會民主黨": "sdp", "台灣綠黨": "green",
               "親民黨": "pfp", "新黨": "np", "台灣基進": "tsp", "台灣團結聯盟": "tsu", "無黨籍及未經政黨推薦": "independent", "無黨團結聯盟": "nonpartisan_union"}
CAND_SLUGS = {"黃珊珊": "huang_shan_shan"}  # independents above the threshold get their own column; extend as needed


def _raw_dir(data_dir: Optional[str]) -> Path:
    d = get_data_dir("taiwan", data_dir) / "raw" / "cec_elections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_json(url: str, cache: Path):
    if cache.exists() and cache.stat().st_size > 2:
        return json.loads(cache.read_text(encoding="utf-8"))
    r = requests.get(url, headers=HEAD, timeout=120)
    r.raise_for_status()
    cache.write_text(r.text, encoding="utf-8")
    return r.json()


def _theme(subject: str, legis: str, year: int, data_dir) -> str:
    lst = _get_json(f"{BASE}list/ELC_{subject}.json", _raw_dir(data_dir) / f"list_{subject}.json")
    for t in lst[0]["theme_items"]:
        if t["vote_date"].startswith(str(year)) and t["legislator_type_id"] == legis and "重行" not in t["theme_name"]:
            return t["theme_id"]
    raise ValueError(f"No CEC theme for {subject}/{legis}/{year}")


def _village_rows(dt: str, subject: str, legis: str, theme: str, county: str, data_dir) -> pd.DataFrame:
    prv, city = county[:2], county[2:5]
    name = f"{prv}_{city}_00_000_0000"
    cache = _raw_dir(data_dir) / f"{dt}_{subject}_{legis}_{theme}_{name}.json"
    d = _get_json(f"{BASE}data/{dt}/ELC/{subject}/{legis}/{theme}/L/{name}.json", cache)
    df = pd.DataFrame([x for v in d.values() for x in v])
    df["GEOID"] = county + df["dept_code"] + df["li_code"].str[1:]
    return df


def _slug(row_party: str, party_code, cand: Optional[str]) -> str:
    if cand in CAND_SLUGS:
        return CAND_SLUGS[cand]
    return PARTY_SLUGS.get(row_party, f"p{party_code}")


def load_election(subject: str, legis: str, year: int, tag: str, counties: Iterable[str] = ("63000",), level: str = "village",
                  data_dir: Optional[str] = None, party_threshold: float = 0.03, with_h3: bool = True, candidate_party_column: bool = True) -> ElectionResult:
    """Generic loader. ``subject``/``legis`` as in the module docstring (for county-vs-municipality pairs C1/C2, T1/T2 the right one is chosen per county).

    Returns ``ElectionResult(census, h3)``: ``census`` keyed by ``GEOID`` (11-digit village; ``level='district'`` 8-digit, ``'county_city'`` 5-digit)
    with ``elec_<tag>_*`` columns; ``h3`` keyed by ``h3_cell`` (res 8) with the same shares plus ``cnt_*`` count columns.

    Args:
        subject: CEC election subject code.
        legis: CEC constituency code.
        year: Election year.
        tag: Column tag (``national_2024``...).
        counties: 5-digit county codes.
        level: ``"village"``, ``"district"`` or ``"county_city"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        party_threshold: Parties above this share get their own columns.
        with_h3: Also build the H3 frame.
        candidate_party_column: Use the candidate's party as the party.
    """
    blocs = electoral.load_blocs(BLOCS_PATH)
    pb, cb = blocs["parties"], blocs["candidates"].get(f"{tag}", {})
    rows, prof = [], []
    for county in counties:
        sj = subject
        if subject in ("C1", "T1", "C2", "T2"):
            base = subject[0]
            sj = f"{base}1" if county[:2] in SPECIAL_MUNI_PRV else f"{base}2"
        lg = legis
        theme = _theme(sj, lg, year, data_dir)
        t = _village_rows("tickets", sj, lg, theme, county, data_dir)
        t = t[t.get("is_vice", pd.Series(" ", index=t.index)) != "Y"].copy()
        if "cand_name" not in t:
            t["cand_name"] = None
        rows.append(t)
        prof.append(_village_rows("profiles", sj, lg, theme, county, data_dir))
    t, p = pd.concat(rows, ignore_index=True), pd.concat(prof, ignore_index=True)
    t["ticket_num"] = t["ticket_num"].astype(float)
    t["bloc"] = [cb.get(c, {}).get("bloc") or pb.get(pn, {}).get("bloc", "other") for c, pn in zip(t["cand_name"], t["party_name"])]
    # party columns: independents above threshold in the study area get their own column when listed in CAND_SLUGS, else party slug
    t["slug"] = [_slug(pn, pc, c if (pn == "無黨籍及未經政黨推薦") else None) for pn, pc, c in zip(t["party_name"], t["party_code"], t["cand_name"])]
    tot = t["ticket_num"].sum()
    sh = t.groupby("slug")["ticket_num"].sum() / tot
    keep = sorted(sh[sh >= party_threshold].index)
    g = t.pivot_table(index="GEOID", columns="bloc", values="ticket_num", aggfunc="sum", fill_value=0)
    for b in ("left", "right", "other"):
        if b not in g:
            g[b] = 0.0
    gp = t[t["slug"].isin(keep)].pivot_table(index="GEOID", columns="slug", values="ticket_num", aggfunc="sum", fill_value=0)
    gp.columns = [f"party_{c}" for c in gp.columns]
    pp = p.set_index("GEOID")[["valid_ticket", "vote_ticket", "votable_population"]].astype(float)
    pp.columns = ["valid", "ballots", "eligible"]
    cnt = pp.join(g[["left", "right", "other"]]).join(gp).fillna(0).reset_index()
    for k in keep:
        if f"party_{k}" not in cnt:
            cnt[f"party_{k}"] = 0.0
    chk = (cnt["left"] + cnt["right"] + cnt["other"] - cnt["valid"]).abs().max()
    assert chk < 1, f"bloc votes do not add to valid votes (max diff {chk})"
    h3df = None
    if with_h3:
        geoms = []
        for county in counties:
            geoms.append(geography.load_boundaries("village", county, data_dir=data_dir))
        import geopandas as gpd
        gdf = pd.concat(geoms, ignore_index=True)
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=4326).merge(cnt, on="GEOID", how="inner")
        cols = electoral.count_cols(cnt)
        hc = electoral.polygons_to_h3(gdf, cols)
        hc["h3_cell"] = hc["h3_cell"]
        h3df = electoral.finalize(hc, tag, "h3_cell", keep).merge(hc.rename(columns={c: f"cnt_{c}" for c in cols}), on="h3_cell")
    if level != "village":
        n = {"district": 8, "county_city": 5}[level]
        cnt["GEOID"] = cnt["GEOID"].str[:n]
        cnt = cnt.groupby("GEOID", as_index=False).sum(numeric_only=True)
    return ElectionResult(electoral.finalize(cnt, tag, "GEOID", keep), h3df)


def load_presidential(year: int = 2024, **kw) -> ElectionResult:
    """President/VP ticket vote (party of the presidential candidate). Columns ``elec_national_<year>_*``.

    Args:
        year: Election year.
        **kw: Passed to :func:`load_election`.

    Returns:
        The :class:`ElectionResult`.
    """
    return load_election("P0", "00", year, f"national_{year}", **kw)


def load_legislative(year: int = 2024, **kw) -> ElectionResult:
    """Legislative Yuan nationwide party-list vote (L4). Columns ``elec_national_<year>leg_*`` (suffix ``leg`` avoids clashing with the presidential).

    Args:
        year: Election year.
        **kw: Passed to :func:`load_election`.

    Returns:
        The :class:`ElectionResult`.
    """
    return load_election("L0", "L4", year, f"national_{year}leg", **kw)


def load_mayor(year: int = 2022, **kw) -> ElectionResult:
    """Mayor / county magistrate election. Columns ``elec_municipal_<year>_*`` (party = candidate's party; leading independents get own column).

    Args:
        year: Election year.
        **kw: Passed to :func:`load_election`.

    Returns:
        The :class:`ElectionResult`.
    """
    return load_election("C1", "00", year, f"municipal_{year}", **kw)


def load_council(year: int = 2022, **kw) -> ElectionResult:
    """City/county council (regional constituencies, candidate votes summed by party). Columns ``elec_municipal_<year>council_*``.

    Args:
        year: Election year.
        **kw: Passed to :func:`load_election`.

    Returns:
        The :class:`ElectionResult`.
    """
    return load_election("T1", "T1", year, f"municipal_{year}council", **kw)
