"""Downloader / loader for the 2020 U.S. Religion Census: Religious Congregations & Membership Study (ASARB, 2023).

Source (keyless, free for studies and analysis, no redistribution -- cite Grammich, Dollhopf, Gautier, Houseal, Jones, Krindatch, Stanley and
Thumma 2023, ASARB): https://usreligioncensus.org/node/1639 -> ``2020_USRC_Summaries.xlsx`` (county totals) and ``2020_USRC_Group_Detail.xlsx``
(adherents of each of 372 religious bodies per county). The Census Bureau asks no religion question, so this is the nationwide county source.

``load_county_religion`` returns one row per county FIPS with the population (2020), congregations, adherents and the adherents of the main
traditions; shares are percent of the county population (``usrc_*_share``). Adherents are counted by the bodies themselves (a county's adherents
can exceed or fall below its residents).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

BASE = "https://www.usreligioncensus.org/sites/default/files/2023-06/"
SUMMARIES = "2020_USRC_Summaries.xlsx"
GROUP_DETAIL = "2020_USRC_Group_Detail.xlsx"
DEFAULT_DATA_DIR = str(get_data_dir("usa"))  # env/temp default, resolved at import

#: tradition -> test on (group code, group name)
TRADITIONS = {
    "catholic": lambda c, n: c == "081",
    "nondenominational": lambda c, n: c == "500",
    "southernBaptist": lambda c, n: c == "419",
    "lds": lambda c, n: c == "151",
    "muslim": lambda c, n: "Muslim" in n,
    "jewish": lambda c, n: "Judaism" in n or "Jewish" in n,
    "hindu": lambda c, n: "Hindu" in n,
    "buddhist": lambda c, n: "Buddhist" in n,
    "orthodoxChristian": lambda c, n: "Orthodox" in n and "Judaism" not in n,
}


def _download(name: str, data_dir: Optional[str]) -> Path:
    raw = get_data_dir("usa", data_dir) / "raw" / "us_religion_census"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / name
    if not path.exists() or path.stat().st_size == 0:
        r = requests.get(BASE + name, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def load_county_religion(data_dir: Optional[str] = None) -> pd.DataFrame:
    """County table: ``GEOID`` (5-digit FIPS) + ``usrc_*`` columns (counts, rates and shares in percent of the 2020 population).

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
    """
    import openpyxl

    wb = openpyxl.load_workbook(_download(SUMMARIES, data_dir), read_only=True, data_only=True)
    rows = [r for r in wb["2020 County Summary"].iter_rows(min_row=2, values_only=True) if r[0]]
    summ = pd.DataFrame([r[:8] for r in rows], columns=["GEOID", "state", "county", "pop", "congregations", "adherents", "cong_per100k", "adh_share"])
    summ["GEOID"] = summ["GEOID"].astype(str).str.zfill(5)
    for c in ("pop", "congregations", "adherents"):
        summ[c] = pd.to_numeric(summ[c], errors="coerce")

    wb2 = openpyxl.load_workbook(_download(GROUP_DETAIL, data_dir), read_only=True, data_only=True)
    g = pd.DataFrame([r[:7] for r in wb2["2020 Group by County"].iter_rows(min_row=2, values_only=True) if r[0]],
                     columns=["GEOID", "state", "county", "code", "name", "congregations", "adherents"])
    g["GEOID"] = g["GEOID"].astype(str).str.zfill(5)
    g["adherents"] = pd.to_numeric(g["adherents"], errors="coerce").fillna(0.0)
    g["code"] = g["code"].astype(str).str.zfill(3)
    g["name"] = g["name"].fillna("").astype(object).map(str)
    out = summ[["GEOID"]].copy()
    out["usrc_congregations"] = summ["congregations"].to_numpy()
    out["usrc_adherents"] = summ["adherents"].to_numpy()
    pop = summ["pop"].where(summ["pop"] > 0).to_numpy()
    out["usrc_congregations_per_100k_rate"] = summ["congregations"].to_numpy() / pop * 1e5
    out["usrc_adherents_share"] = summ["adherents"].to_numpy() / pop
    for key, test in TRADITIONS.items():
        mask = np.array([bool(test(str(c), str(n))) for c, n in zip(g["code"], g["name"])])
        s = g[mask].groupby("GEOID")["adherents"].sum()
        out[f"usrc_{key}Adherents"] = out["GEOID"].map(s).fillna(0.0).to_numpy()
        out[f"usrc_{key}_share"] = out[f"usrc_{key}Adherents"].to_numpy() / pop
    return out
