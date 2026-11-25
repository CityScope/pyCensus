"""Taipei and New Taipei: public-transport share of residents' commuting / school trips per traffic zone, 2010.

Taipei DOT statistics report 102-03 (99年大臺北地區(雙北市)15歲以上居民通勤通學型態分析) tabulates the MOTC daily mode-use survey of 2010 (4,468
commuting / school trips of residents aged 15+) by the DOT's 13 traffic zones (表 4: 6 in Taipei City, 7 in New Taipei, each a group of districts):
附表 8-2 gives per zone the sample and the shares of public, non-motorised and private motorised transport (vehicle uses, the survey's 市占率).
It is the only published mode split below the city for New Taipei (the later MOTC surveys publish city totals; Taipei City has its own 2018
district survey, :mod:`taipei_mode_use`). The report is downloaded once into ``<cache>/taiwan/shuangbei_commute/`` and read with pdftotext.

    from pycensus.census.countries.taiwan import shuangbei_commute
    shuangbei_commute.table()     # 13 zones: shares, sample, member districts
    shuangbei_commute.load()      # + the zone polygons (districts dissolved)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

URL = ("https://www-ws.gov.taipei/Download.ashx?icon=.pdf&n=MTAyMDMtOTnlubTlpKfoh7rljJflnLDljYAo6ZuZ5YyX5biCKTE15q2y5Lul5LiK5bGF5rCR6YCa5Yuk6YCa5a245Z6L5oWL5YiG5p6QLnBkZg%3D%3D"
       "&u=LzAwMS9VcGxvYWQvMzkwL3JlbGZpbGUvNDMyNzMvODA5ODE5OS9hYmU3ZWU1NC1jZGE5LTRlODctOTcxYS1iYTJiODZkMzM2OWQucGRm")
YEAR = 2010
#: traffic zone (表 4) -> member districts (MOI district codes)
ZONES = {
    "士林北投": ["63000110", "63000120"], "內湖": ["63000100"], "南港": ["63000090"],
    "北市核心": ["63000030", "63000040", "63000050", "63000010", "63000020"], "大萬華": ["63000060", "63000070"], "文山": ["63000080"],
    "海山": ["65000030", "65000040", "65000010"], "土樹": ["65000090", "65000130", "65000070", "65000080"],
    "八里重新": ["65000230", "65000020", "65000150", "65000170", "65000160", "65000050", "65000140"],
    "北海岸": ["65000210", "65000220", "65000270", "65000100", "65000280"], "東北角": ["65000240", "65000260", "65000120", "65000250"],
    "汐止": ["65000110"], "大新店": ["65000190", "65000200", "65000290", "65000180", "65000060"],
}
COLS = ("transit_commute_share", "nonmotorised_commute_share", "private_motorised_commute_share")


def _text(cache_dir: Optional[str]) -> str:
    from pycensus import cache as cache_store

    d = Path(cache_dir or cache_store.default_cache_dir()) / "taiwan" / "shuangbei_commute"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "102-03_shuangbei_commute_2010.pdf"
    if not f.is_file() or f.stat().st_size < 100_000:
        import requests

        r = requests.get(URL, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        f.write_bytes(r.content)
    import unicodedata

    # NFKC: the PDF writes some characters as Kangxi radicals (⼠林北投 for 士林北投)
    return unicodedata.normalize("NFKC", subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True, check=True).stdout)


def parse(text: str) -> pd.DataFrame:
    """The zone rows of 附表 8-2 (the appendix table, last occurrence of its title).

    Args:
        text: ``pdftotext -layout`` text of the report.

    Returns:
        One row per zone: name, member districts, sample (trips), the three shares (0-1).

    Raises:
        RuntimeError: When a zone is not found.
    """
    lines = text.split("\n")
    start = max(i for i, ln in enumerate(lines) if "附表8-2" in re.sub(r"\s+", "", ln))
    rows = {}
    for ln in lines[start: start + 90]:
        s = ln.strip()
        for z in ZONES:
            if s.startswith(z) and z not in rows:
                v = re.findall(r"\d[\d,]*\.?\d*", s[len(z):])
                if len(v) >= 5:
                    rows[z] = {"zone": z, "districts": ",".join(ZONES[z]), "sample_trips": float(v[0].replace(",", "")),
                               **{c: float(x) / 100 for c, x in zip(COLS, v[2:5])}}
    miss = [z for z in ZONES if z not in rows]
    if miss:
        raise RuntimeError(f"traffic zones not read from 附表8-2: {miss}")
    t = pd.DataFrame(rows.values())
    t.insert(0, "GEOID", ["tz-" + str(i + 1) for i in range(len(t))])
    t["county"] = ["Taipei City" if ZONES[z][0].startswith("63") else "New Taipei City" for z in t["zone"]]
    t["year"] = YEAR
    return t


def table(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Per-zone shares (see the module docstring).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per traffic zone.
    """
    return parse(_text(cache_dir))


def load(cache_dir: Optional[str] = None, data_dir: Optional[str] = None, **_):
    """The 13 traffic zones with their shares; polygons = member districts dissolved.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        data_dir: Folder of the raw boundary downloads; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame (EPSG:4326).
    """
    import geopandas as gpd

    from pycensus.census.countries.taiwan import geography

    t = table(cache_dir)
    d = geography.load_boundaries("district", data_dir=data_dir).to_crs(4326).set_index("GEOID")
    geoms = [d.loc[[c for c in r.split(",") if c in d.index]].union_all() for r in t["districts"]]
    return gpd.GeoDataFrame(t, geometry=geoms, crs=4326)


__all__ = ["load", "table", "parse", "ZONES"]
