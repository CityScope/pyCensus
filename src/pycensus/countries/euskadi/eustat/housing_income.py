"""Basque housing-market and income tables (EMAL rent, Eustat section income / dwellings / sale price). All return DataFrames keyed by ``GEOID``.

GEOIDs follow ``spain.adrh.eustat_sections``: 10-digit INE section = province(2)+municipality(3)+district(2)+section(3); 5-digit = INE municipality.
Raw downloads are cached under ``<data_dir>/raw/eustat_housing`` (default ``data/euskadi``; keep outside git).

Sources (verified live 2026-10):
  EMAL (rental-deposit statistic, Gobierno Vasco, CC BY): opendata.euskadi.eus/contenidos/estadistica/122417_emal_tablas_estad/opendata/
      EMAL.-Barrios-Municipios.-2016-2025_es.xlsx (municipalities >5,000 inh. T2.x annual; Donostia zones/districts/barrios T8.x) and
      EMAL-2016-2025_es.xlsx (province / municipality-size class T2.x).
  Eustat income by section 2019 (CC BY): eustat.eus/elementos/xls0017461_c.csv (Gipuzkoa), xls0017445_c.csv (Araba), xls0017462_c.csv (Bizkaia).
  Eustat dwellings by district and section, Gipuzkoa 01/01/2024: xls0018855_c.csv (includes tenure: owned / rented / other, %).
  Eustat sale price per m2 (Registradores) by province: xls0019433_c.csv.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import io
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

EMAL_BASE = "https://opendata.euskadi.eus/contenidos/estadistica/122417_emal_tablas_estad/opendata/"
EMAL_MUNI_FILE = "EMAL.-Barrios-Municipios.-2016-2025_es.xlsx"
EMAL_SIZE_FILE = "EMAL-2016-2025_es.xlsx"
EUSTAT = "https://www.eustat.eus/elementos/"
INCOME_FILES = {"20": "xls0017461_c.csv", "01": "xls0017445_c.csv", "48": "xls0017462_c.csv"}
DWELLINGS_FILES = {"20": "xls0018855_c.csv"}
PRICE_FILE = "xls0019433_c.csv"
PROVINCE_NAMES = {"Araba/Álava": "01", "Álava": "01", "Gipuzkoa": "20", "Bizkaia": "48"}


def _get(url: str, data_dir: Optional[str]) -> Path:
    d = get_data_dir("euskadi", data_dir) / "raw" / "eustat_housing"
    d.mkdir(parents=True, exist_ok=True)
    p = d / url.rsplit("/", 1)[-1]
    if not p.exists() or p.stat().st_size < 500:
        r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


def _num(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return float("nan")


def _sheet(path: Path, name: str):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [list(r) for r in wb[name].iter_rows(values_only=True)]


def _year_cols(rows):
    """Header row with year labels -> {col_index: year} (annual columns only; skips 'vigentes a fecha' columns)."""
    for r in rows[:5]:
        cols = {i: int(str(v)) for i, v in enumerate(r) if re.fullmatch(r"20\d\d", str(v or "").strip())}
        if cols:
            return cols
    raise ValueError("no year header")


def load_emal_municipal(year: int = 2025, data_dir: Optional[str] = None, provinces=("01", "20", "48")) -> pd.DataFrame:
    """EMAL by municipality (>5,000 inhabitants), contracts started in ``year`` (2016-2025). GEOID = 5-digit INE municipality.

    emalRentM2 (EUR/m2 built/month, average), emalRentMonthly (EUR/month), emalDeposits (number of rental deposits).

    Args:
        year: Contract start year (2016-2025).
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        provinces: 2-digit province codes.

    Returns:
        One row per municipality.
    """
    p = _get(EMAL_BASE + EMAL_MUNI_FILE, data_dir)
    out = None
    for sheet, col in (("T2.1", "emalDeposits"), ("T2.2", "emalRentMonthly"), ("T2.3", "emalRentM2")):
        rows = _sheet(p, sheet)
        yc = _year_cols(rows)
        idx = next(i for i, y in yc.items() if y == year)
        recs = {str(r[0]).strip(): _num(r[idx]) for r in rows if r[0] and re.fullmatch(r"\d{5}", str(r[0]).strip()) and str(r[0]).strip()[:2] in provinces}
        s = pd.Series(recs, name=col)
        out = s.to_frame() if out is None else out.join(s, how="outer")
    out.index.name = "GEOID"
    return out.reset_index()


def load_emal_donostia(year: int = 2025, data_dir: Optional[str] = None) -> pd.DataFrame:
    """EMAL rent per m2 (EUR/m2/month) inside Donostia/San Sebastian: OFIN zones, districts and barrios (sub-municipal; not census-section keyed).

    Columns: level ('zone'|'district'|'barrio'), code, name, emalRentM2, emalRentMonthly, emalDeposits. Municipal GEOID 20069.

    Args:
        year: Contract start year.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per zone, district and barrio.
    """
    p = _get(EMAL_BASE + EMAL_MUNI_FILE, data_dir)
    res = None
    for sheet, col in (("T8.1", "emalDeposits"), ("T8.2", "emalRentMonthly"), ("T8.3", "emalRentM2")):
        rows = _sheet(p, sheet)
        idx = next(i for i, y in _year_cols(rows).items() if y == year)
        lvl, recs = None, []
        for r in rows[4:]:
            if r[0] in ("Zonificación OFIN",): lvl = "zone"
            elif r[0] == "Distrito": lvl = "district"
            elif r[0] == "Barrio": lvl = "barrio"
            elif r[0] and lvl: break
            if lvl and (r[2] is not None):
                code = str(r[1]) if lvl == "barrio" else str(r[2])
                recs.append((lvl, code, str(r[2]) if lvl == "barrio" else str(r[2]), _num(r[idx])))
        d = pd.DataFrame(recs, columns=["level", "code", "name", col]).drop_duplicates(["level", "code"])
        res = d if res is None else res.merge(d[["level", "code", col]], on=["level", "code"], how="outer")
    return res


def load_emal_size_context(year: int = 2025, data_dir: Optional[str] = None) -> pd.DataFrame:
    """EMAL rent per m2 by territory and municipality-size class (context columns): rows 'Euskadi', provinces, size classes.

    Args:
        year: Contract start year.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per territory or size class.
    """
    p = _get(EMAL_BASE + EMAL_SIZE_FILE, data_dir)
    rows = _sheet(p, "T2.3")
    idx = next(i for i, y in _year_cols(rows).items() if y == year)
    recs = []
    for r in rows[4:]:
        if r[0] and str(r[0]).startswith(("Datos", "(*)")): break
        label = r[1] or r[0]
        if label and isinstance(r[idx], (int, float)):
            recs.append((str(label), r[idx]))
    return pd.DataFrame(recs, columns=["area", "emalRentM2"]).assign(year=year)


def load_income_sections(provinces=("20",), data_dir: Optional[str] = None) -> pd.DataFrame:
    """Eustat mean personal income (EUR, population 18+) 2019 by census section (``section 00`` rows = municipality totals are dropped).

    Columns: GEOID (10-digit), incomeTotal, incomeWork, incomeMovableCapital, incomeRealEstateCapital, incomeActivity, incomeTransfers, incomeDisposable.

    Args:
        provinces: 2-digit province codes.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per census section.
    """
    names = ["incomeTotal", "incomeWork", "incomeMovableCapital", "incomeRealEstateCapital", "incomeActivity", "incomeTransfers", "incomeDisposable"]
    frames = []
    for prov in provinces:
        p = _get(EUSTAT + INCOME_FILES[prov], data_dir)
        raw = pd.read_csv(p, sep=";", header=None, dtype=str, encoding="utf-8-sig", skip_blank_lines=False, names=list(range(80)))
        hdr = raw.index[raw[0] == "Código"][0]
        d = raw.iloc[hdr + 1:, :11].copy()
        d.columns = ["cod", "muni", "dist", "sec"] + names
        d["cod"] = d["cod"].ffill()
        d["dist"] = d["dist"].ffill()
        d = d[d["sec"].notna() & d["dist"].notna()]
        # municipality code only appears on first row of each municipality
        d["dist"] = d["dist"].str.zfill(2)
        d = d[d["sec"] != "00"]
        d["GEOID"] = prov + d["cod"].str.zfill(3) + d["dist"] + d["sec"].str.zfill(3)
        for c in names:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d.loc[d["incomeTotal"] <= 0, names] = float("nan")  # suppressed sections
        frames.append(d[["GEOID"] + names].dropna(subset=["incomeTotal"]))
    return pd.concat(frames, ignore_index=True)


def load_dwellings_sections(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Eustat dwellings by census section of Gipuzkoa (01/01/2024), incl. tenure shares (% of main family dwellings).

    Columns: GEOID, dwellingsTotal, dwellingsFamily, dwellingsMain, dwellingsOther, dwellingAvgAge, dwellingAvgUsefulArea, dwellingsOwnedPct, dwellingsRentedPct, dwellingsOtherTenurePct.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per census section.
    """
    p = _get(EUSTAT + DWELLINGS_FILES["20"], data_dir)
    raw = pd.read_csv(p, sep=";", header=None, dtype=str, encoding="utf-8-sig", skip_blank_lines=False, names=list(range(80)))
    d = raw[raw[2].fillna("").str.fullmatch(r"\d{10}")].copy()
    cols = {2: "GEOID", 3: "dwellingsTotal", 4: "dwellingsFamily", 5: "dwellingsMain", 6: "dwellingsOther", 10: "avgResidents", 11: "dwellingAvgAge",
            12: "dwellingAvgUsefulArea", 15: "dwellingsOwnedPct", 16: "dwellingsRentedPct", 17: "dwellingsOtherTenurePct"}
    d = d[list(cols)].rename(columns=cols)
    for c in d.columns[1:]:
        d[c] = d[c].map(_num)
    return d.reset_index(drop=True)


def load_sale_price_province(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Eustat mean sale price per m2 built of free housing (EUR/m2), by province and quarter (Registradores). Context column (province-wide).

    Columns: year, quarter, province (GEOID 2-digit or 'EUS'), type ('total'|'new'|'used'), salePriceM2.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per province, quarter and type.
    """
    p = _get(EUSTAT + PRICE_FILE, data_dir)
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    heads = [(g, t) for g, t in zip(["EUS"] * 3 + ["01"] * 3 + ["48"] * 3 + ["20"] * 3, ["total", "new", "used"] * 4)]
    recs, year = [], None
    for ln in lines[4:]:
        c = [x.strip('"') for x in ln.split(";")]
        if re.fullmatch(r"20\d\d", c[0]): year = int(c[0]); continue
        if c[0] in ("I", "II", "III", "IV") and len(c) >= 13:
            for (g, t), v in zip(heads, c[1:13]):
                v = v.replace(".", "").replace(",", ".")
                recs.append((year, c[0], g, t, float(v) if v not in ("", "-") else float("nan")))
    return pd.DataFrame(recs, columns=["year", "quarter", "province", "type", "salePriceM2"])
