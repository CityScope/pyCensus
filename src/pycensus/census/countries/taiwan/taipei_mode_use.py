"""Taipei City: residents' use of transport modes per district (行政區), Taipei Department of Transportation's survey of daily mode use
(107年臺北市居民日常使用運具狀況調查, October 2018, telephone survey of 1,867 residents aged 15+; report published on data.taipei).

The finest published geography of any Taipei mode-use survey: the city's 12 districts. Two tables per district are read from the report:

* commute trips (表 5-4-2-2, 通勤學旅次使用運具類別次數占比): shares of the vehicles used on yesterday's (weekday) commuting / school trips --
  green modes, public transport, non-motorised, private motorised -- the outcome closest to a commute mode split;
* all trips (表Ⅱ, 昨天(平日)外出各交通工具市占率): shares of every vehicle used on yesterday's trips: MRT, city bus, taxi, walking,
  private motorcycle, private car, ...;
* the sample per district (表 4-2: residents surveyed, and those who went out the day before).

Shares count every vehicle used on a trip (a trip by bus and MRT counts twice), as the survey defines its 市占率. The report (PDF) is
downloaded once into ``<cache>/taiwan/taipei_mode_use/`` and read with ``pdftotext -layout``; a changed layout fails loudly.

    from pycensus.census.countries.taiwan import taipei_mode_use
    taipei_mode_use.table()    # DataFrame: one row per district
    taipei_mode_use.load()     # + district polygons (pycensus taiwan.geography "district")
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

URL = ("https://data.taipei/api/getDatasetInfo/downloadResource?id=86c4e5f9-211e-41e1-91f1-84a65a99eca3"
       "&rid=95621ebf-b3d6-4389-87c8-7a97767b63f6")
YEAR = 2018
#: district name -> GEOID of the district boundaries (MOI code)
DISTRICTS = {"松山區": "63000010", "信義區": "63000020", "大安區": "63000030", "中山區": "63000040", "中正區": "63000050", "大同區": "63000060",
             "萬華區": "63000070", "文山區": "63000080", "南港區": "63000090", "內湖區": "63000100", "士林區": "63000110", "北投區": "63000120"}
#: rows of the all-trips table (表Ⅱ) kept, as column names (per cent of vehicle uses)
TRIP_ROWS = {"綠運輸": "green_trip_share", "公共運具": "transit_trip_share", "捷運": "mrt_trip_share", "市區公車": "bus_trip_share",
             "計程車": "taxi_trip_share", "非機動運具": "nonmotorised_trip_share", "步行": "walk_trip_share", "私人機動運具": "private_motorised_trip_share",
             "私人機車": "motorcycle_trip_share", "自用小客車": "car_trip_share"}
COMMUTE_COLS = ("green_commute_share", "transit_commute_share", "nonmotorised_commute_share", "private_motorised_commute_share")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _text(cache_dir: Optional[str]) -> str:
    from pycensus import cache as cache_store

    d = Path(cache_dir or cache_store.default_cache_dir()) / "taiwan" / "taipei_mode_use"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "107_taipei_daily_mode_use.pdf"
    if not f.is_file() or f.stat().st_size < 1_000_000:
        import requests

        r = requests.get(URL, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        f.write_bytes(r.content)
    return subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True, check=True).stdout


def _section(text: str, title: str, n_lines: int) -> list:
    """The lines after the table title (the second occurrence: the first is the table of contents)."""
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if title in _squash(ln)]
    if len(hits) < 2:
        raise RuntimeError(f"table {title!r} not found in the Taipei mode-use report")
    return lines[hits[1] + 1: hits[1] + 1 + n_lines]


def parse(text: str) -> pd.DataFrame:
    """Commute shares, all-trip shares and samples per district from the report text.

    Args:
        text: ``pdftotext -layout`` text of the report.

    Returns:
        One row per district (12), shares as fractions.

    Raises:
        RuntimeError: When a table or district is missing.
    """
    rows = {n: {"name": n} for n in DISTRICTS}
    for ln in _section(text, "表5-4-2-2通勤學旅次使用運具類別次數占比", 30):   # district rows: name + 4 shares
        s = _squash(ln)
        for n in DISTRICTS:
            if s.startswith(n):
                v = [float(x) for x in re.findall(r"\d+\.\d", ln)]
                rows[n].update({c: x / 100 for c, x in zip(COMMUTE_COLS, v[:4])})
    head = None
    for ln in _section(text, "表Ⅱ昨天(平日)外出各交通工具市占率", 40):   # districts are columns, in the header's order
        s = _squash(ln)
        v = [float(x) for x in re.findall(r"\d+\.\d", ln)]
        for label, col in TRIP_ROWS.items():
            if s.startswith(label) and len(v) == 13:   # Taipei total + 12 districts
                head = head or ["松山區", "信義區", "大安區", "中山區", "中正區", "大同區", "萬華區", "文山區", "南港區", "內湖區", "士林區", "北投區"]
                for n, x in zip(head, v[1:]):
                    rows[n].setdefault(col, x / 100)
    for ln in _section(text, "表4-2各行政區樣本數及抽樣誤差", 40):
        s = _squash(ln)
        for n in DISTRICTS:
            if s.startswith(n):
                v = re.findall(r"(\d[\d,]*)\s+±", ln)
                rows[n].update({"sample_residents": float(v[0].replace(",", "")), "sample_out_yesterday": float(v[1].replace(",", ""))})
    t = pd.DataFrame(rows.values())
    need = [*COMMUTE_COLS, *TRIP_ROWS.values(), "sample_residents", "sample_out_yesterday"]
    miss = [c for c in need if c not in t or t[c].isna().any()]
    if miss:
        raise RuntimeError(f"Taipei mode-use report: not read for every district: {miss}")
    t.insert(0, "GEOID", t["name"].map(DISTRICTS))
    t["year"] = YEAR
    return t


def table(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Per-district shares (see the module docstring).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per district.
    """
    return parse(_text(cache_dir))


def load(cache_dir: Optional[str] = None, data_dir: Optional[str] = None, **_):
    """The 12 districts with their shares and polygons.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        data_dir: Folder of the raw boundary downloads; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame (EPSG:4326).
    """
    import geopandas as gpd

    from pycensus.census.countries.taiwan import geography

    g = geography.load_boundaries("district", data_dir=data_dir).to_crs(4326)
    return gpd.GeoDataFrame(g[["GEOID", "geometry"]].merge(table(cache_dir), on="GEOID", how="inner"), geometry="geometry", crs=4326)


__all__ = ["load", "table", "parse"]
