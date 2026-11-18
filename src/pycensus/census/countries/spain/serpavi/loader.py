"""SERPAVI rent per m2 by census section / district / municipality / province (2011-2024).

Technical aspects:
    Source: MIVAU bulk workbook (tax data, Modelo 100 + Catastro), one sheet per level ('Secciones censales', 'Distritos', 'Municipios',
    'Provincias', 'CCAA'); columns are ``<MEASURE>_<GROUP>_<YY>``. The server answered 403 to plain curl but serves the CDN file
    (verified 2026-10-25, 71 MB) to browser-like headers (``_http.BROWSER_HEADERS``). Sections follow the INE 2021 census section code
    (``CUSEC``, 10 digits), so GEOID matches ``spain.ine``/``censo2021``.

    Measures kept (monthly EUR/m2, rent per property, area, count): group VC = collective housing (flats; used for the headline value),
    VU = single-family/rural. Output columns: ``serpavi_rent_m2_{median,p25,p75}_{vc,vu}_{YYYY}``, ``serpavi_rent_total_median_{vc,vu}_{YYYY}``,
    ``serpavi_area_m2_median_{vc,vu}_{YYYY}``, ``serpavi_n_{vc,vu}_{YYYY}``, plus ``serpavi_rent_m2_latest`` (VC median, else VU median, latest
    year with data). Sections with too few observations are suppressed by the Ministry (NaN). Basque Country and Navarre (foral tax
    regimes) are NaN/partial in early years; check coverage per year in ``coverage``; use Eustat/Gobierno de Navarra sources to fill.
    The parsed sheet is cached as parquet next to the xlsx so the 71 MB workbook is read only once.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from pycensus.census.countries.spain import _http

SERPAVI_XLSX_URL = ("https://cdn.mivau.gob.es/portal-web-mivau/vivienda/serpavi/"
                    "2026-03_09_bd_SERPAVI_2011-2024%20-%20DEFINITIVO%20WEB_v2.xlsx")
SHEETS = {"section": ("Secciones censales", "CUSEC"), "district": ("Distritos", "CUDIS"),
          "municipality": ("Municipios", "CUMUN"), "province": ("Provincias", "CPRO")}
_MEASURE = {"BI_ALVHEPCO": "n", "ALQM2_LV_M": "rent_m2_median", "ALQM2_LV_25": "rent_m2_p25", "ALQM2_LV_75": "rent_m2_p75",
            "ALQTBID12_M": "rent_total_median", "ALQTBID12_25": "rent_total_p25", "ALQTBID12_75": "rent_total_p75",
            "SLVM2_M": "area_m2_median", "SLVM2_25": "area_m2_p25", "SLVM2_75": "area_m2_p75"}
_COL = re.compile(r"^(BI_ALVHEPCO|ALQM2_LV_M|ALQM2_LV_25|ALQM2_LV_75|ALQTBID12_M|ALQTBID12_25|ALQTBID12_75|SLVM2_M|SLVM2_25|SLVM2_75)_(?:T)?(VC|VU)_(\d\d)$")
_COL_N = re.compile(r"^BI_ALVHEPCO_T(VC|VU)_(\d\d)$")


def _dir(data_dir: Optional[str]) -> Path:
    d = get_data_dir("spain", data_dir) / "raw" / "serpavi"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rename(col: str) -> Optional[str]:
    m = _COL_N.match(col)
    if m:
        return f"serpavi_n_{m.group(1).lower()}_{2000 + int(m.group(2))}"
    m = _COL.match(col)
    if m:
        return f"serpavi_{_MEASURE[m.group(1)]}_{m.group(2).lower()}_{2000 + int(m.group(3))}"
    return None


def _sheet(level: str, data_dir: Optional[str], force: bool = False) -> pd.DataFrame:
    sheet, key = SHEETS[level]
    d = _dir(data_dir)
    pq = d / f"serpavi_{level}.parquet"
    if pq.exists() and not force:
        return pd.read_parquet(pq)
    xlsx = _http.download(SERPAVI_XLSX_URL, d / "serpavi.xlsx", force=force)
    raw = pd.read_excel(xlsx, sheet_name=sheet, dtype={"CPRO": str, "CUMUN": str, "CUSEC": str, "CUDIS": str})
    ren = {c: _rename(c) for c in raw.columns if _rename(c)}
    keep = [c for c in ("CPRO", "CUMUN", "NMUN", "LITMUN", "NPRO", "LITPRO", key) if c in raw.columns]
    out = raw[list(dict.fromkeys(keep))].join(raw[list(ren)].rename(columns=ren))
    out = out.rename(columns={key: "GEOID"})
    for c in ("GEOID", "CPRO", "CUMUN"):
        if c in out:
            w = {"GEOID": {"section": 10, "district": 7, "municipality": 5, "province": 2}[level], "CPRO": 2, "CUMUN": 5}[c]
            out[c] = out[c].astype(str).str.zfill(w)
    out.to_parquet(pq)
    return out


def municipality_crosswalk(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Province name + municipality name -> 5-digit INE code (from the SERPAVI 'Municipios' sheet), used to join name-only sources.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        ``CPRO``, ``NPRO``, ``CUMUN``, ``NMUN``.
    """
    m = _sheet("municipality", data_dir)
    return m[["CPRO", "NPRO", "GEOID", "NMUN"]].rename(columns={"GEOID": "CUMUN"})


def load_attributes(provinces: Optional[Iterable[str]] = None, level: str = "section", data_dir: Optional[str] = None,
                    years: Optional[Iterable[int]] = None) -> pd.DataFrame:
    """Return SERPAVI columns for ``level`` ('section'|'district'|'municipality'|'province'), optionally restricted to 2-digit ``provinces``
    and ``years``. Adds ``serpavi_rent_m2_latest`` and ``serpavi_rent_m2_latest_year``.

    Args:
        provinces: 2-digit province codes.
        level: ``"section"``, ``"district"``, ``"municipality"`` or ``"province"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        years: Years kept; ``None`` = all.

    Returns:
        One row per unit.
    """
    df = _sheet(level, data_dir)
    if provinces is not None:
        ps = {str(p).zfill(2) for p in provinces}
        df = df[df["GEOID"].str[:2].isin(ps)] if level != "province" else df[df["GEOID"].isin(ps)]
    df = df.copy()
    ys = sorted({int(c[-4:]) for c in df.columns if c.startswith("serpavi_rent_m2_median_vc_")})
    if years is not None:
        ys_keep = set(years)
        df = df[[c for c in df.columns if not c.startswith("serpavi_") or int(c[-4:]) in ys_keep]]
    latest = pd.Series(float("nan"), index=df.index)
    latest_y = pd.Series(pd.NA, index=df.index, dtype="Int64")
    for y in sorted(ys, reverse=True):  # newest year wins, VC before VU
        for g in ("vc", "vu"):
            c = f"serpavi_rent_m2_median_{g}_{y}"
            if c in df:
                m = latest.isna() & df[c].notna()
                latest[m] = df.loc[m, c]
                latest_y[m] = y
    df["serpavi_rent_m2_latest"] = latest
    df["serpavi_rent_m2_latest_year"] = latest_y
    return df.reset_index(drop=True)


def coverage(df: pd.DataFrame, year: int = 2024) -> pd.Series:
    """Share of rows with a VC median rent per m2 for ``year``, by 2-digit province.

    Args:
        df: Output of :func:`load_attributes`.
        year: Year checked.

    Returns:
        Share by province.
    """
    c = f"serpavi_rent_m2_median_vc_{year}"
    return df.groupby(df["GEOID"].str[:2])[c].apply(lambda s: s.notna().mean())
