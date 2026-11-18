# -*- coding: utf-8 -*-
"""Hawaii -- 2024 general election by precinct, from the Office of Elections and the Hawaii Statewide GIS Program.

Results: the official "Statewide Precinct Report" (``files.hawaii.gov/elections/files/results/2024/General/precinct.pdf``), one page per
reporting unit: ``MAIL dd-dd`` and ``IN-PERSON dd-dd`` for each of the 247 voting precincts, plus the presidential-only (``PRES``) and overseas
(``OS I`` / ``OS II``) units that have no polygon. The text is read with ``pdftotext -raw`` (poppler). Boundaries: ``Election Precincts - 2024``
(geodata.hawaii.gov AdminBnd layer 13, Office of Elections data, May 2024; key ``dp``). The mail and in-person votes of a precinct are added; the
votes of the special units are shared among all precincts in proportion to their votes, so the statewide total is exact.
"""

from __future__ import annotations

import re
import subprocess

import geopandas as gpd
import pandas as pd

from pycensus.elections_common import default_elections_cache, download

PDF = "https://files.hawaii.gov/elections/files/results/2024/General/precinct.pdf"
BOUNDS = ("https://geodata.hawaii.gov/arcgis/rest/services/AdminBnd/MapServer/13/query?where=1%3D1&outFields=*&f=geojson&outSR=4326&resultRecordCount=1000")
ATTRIBUTION = ("Hawaii Office of Elections: 2024 General Election Statewide Precinct Report (elections.hawaii.gov) and Hawaii Statewide GIS Program "
               "Election Precincts - 2024 (geodata.hawaii.gov).")
FIPS = "15"
COUNTY = {"HAWAII": "15001", "OAHU": "15003", "HONOLULU": "15003", "KALAWAO": "15005", "KAUAI": "15007", "MAUI": "15009"}
_HEAD = re.compile(r"^((?:MAIL|IN-PERSON) (?:\d{2}-\d{2}[A-Z]?|PRES|OS I{1,2}))$")


def _parse(text: str) -> pd.DataFrame:
    lines = text.split("\n")
    rows, cur = [], None
    for i, l in enumerate(lines):
        m = _HEAD.match(l.strip())
        if m and i + 1 < len(lines) and lines[i + 1].strip().startswith("November 5, 2024"):
            cur = {"unit": m.group(1), "lines": []}
            rows.append(cur)
        elif cur is not None:
            cur["lines"].append(l)
    out = []
    for b in rows:
        ls = b["lines"]
        try:
            a = ls.index("President and Vice President")
            z = next(j for j in range(a, len(ls)) if ls[j].startswith("U.S. Senator"))
        except (ValueError, StopIteration):
            continue
        party = None
        for l in ls[a + 1: z]:
            m = re.match(r"^\(([A-Z]+)\)", l)
            if m:
                party = m.group(1)
                continue
            m = re.match(r"^([\d,]+) [\d.]+%$", l.strip())
            if m and party:
                out.append((b["unit"], party, int(m.group(1).replace(",", ""))))
                party = None
    return pd.DataFrame(out, columns=["unit", "party", "v"])


def load(cache_dir=None) -> gpd.GeoDataFrame:
    """Hawaii official 2024 presidential results by precinct, joined to the official precinct polygons.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        Precinct polygons with ``votes_dem``, ``votes_rep``, ``votes_total``.
    """
    root = default_elections_cache(cache_dir) / "official_hi_2024"
    pdf = download(PDF, root / "precinct.pdf")
    text = subprocess.run(["pdftotext", "-raw", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    d = _parse(text)
    d["id"] = d["unit"].str.replace(r"^(MAIL|IN-PERSON) ", "", regex=True)
    t = d.pivot_table(index="id", columns="party", values="v", aggfunc="sum").fillna(0.0)
    t = pd.DataFrame({"votes_dem": t.get("D", 0.0), "votes_rep": t.get("R", 0.0), "votes_total": t.sum(axis=1)})
    poly = gpd.read_file(download(BOUNDS, root / "precincts.geojson"))[["dp", "county", "geometry"]].rename(columns={"dp": "id"})
    poly = poly.dissolve(by="id", aggfunc="first").reset_index()   # a precinct split in several polygons must receive its votes once
    special = t[~t.index.isin(poly["id"])]
    real = t[t.index.isin(poly["id"])].copy()
    share = real["votes_total"] / real["votes_total"].sum()
    for c in ("votes_dem", "votes_rep", "votes_total"):
        real[c] = real[c] + share * special[c].sum()
    g = poly.merge(real, left_on="id", right_index=True, how="inner")
    g["county_fips"] = g["county"].str.upper().map(COUNTY)
    g["geometry"] = g.geometry.make_valid()
    return g[["county_fips", "votes_dem", "votes_rep", "votes_total", "geometry"]].reset_index(drop=True)
