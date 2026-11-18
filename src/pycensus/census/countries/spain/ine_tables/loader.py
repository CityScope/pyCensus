"""Municipality-level INE tables read from the keyless INE CSV bulk files (same route as ``spain.adrh``).

Technical aspects:
    ``https://www.ine.es/jaxiT3/files/t/es/csv_bd/<id>.csv?nocab=1`` (tab separated, Spanish number format: '.' thousands, ',' decimals).
    Verified 2026-10-25:
      * 39363  Viviendas turisticas (VTE, official INE experimental statistic from portal data, NOT Airbnb microdata): dwellings and places
        by municipality, semi-annual (2026M05, 2025M11, ...). 31 MB. Rows keyed 'NNNNN Name' in the 'Municipios' column.
      * 39366  Share of tourist dwellings over census dwellings, by municipality.
      * 69767  EMCR 'Saldos por municipio, ano, sexo y tipo de saldo' (net migration: total/exterior/interior), annual, 23 MB.
    Country-of-birth by section is not here: use censo2021 (``ID_LUGAR_NAC_EXT_N1``). INE table 75690 gives birth-country flows only by
    sub-municipal area for big cities (probed, not loaded).
    Native resolution is the municipality: the caller must broadcast to sections/H3 and tag the native level in popups.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

CSV_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bd/{id}.csv?nocab=1"


def _csv(table_id: int, data_dir: Optional[str]) -> Path:
    d = get_data_dir("spain", data_dir) / "raw" / "ine_tables"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{table_id}.csv"
    if not p.exists():
        r = requests.get(CSV_URL.format(id=table_id), timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def _read(table_id: int, data_dir: Optional[str], provinces: Optional[Iterable[str]], col: str = "Municipios") -> pd.DataFrame:
    df = pd.read_csv(_csv(table_id, data_dir), sep="\t", encoding="utf-8-sig", dtype=str)
    df = df[df[col].notna() & (df[col] != "")].copy()
    df["GEOID"] = df[col].str[:5]
    if provinces is not None:
        df = df[df["GEOID"].str[:2].isin({str(p).zfill(2) for p in provinces})]
    df["Total"] = _num(df["Total"])
    return df


def load_tourist_dwellings(provinces: Optional[Iterable[str]] = None, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Per municipality (GEOID, 5 digits): ``ine_tourist_dwellings_<period>``, ``ine_tourist_places_<period>`` (period like 2026M05) and
    ``ine_tourist_dwellings_share_<period>`` (% of census dwellings), plus ``..._latest`` columns. Municipalities with INE-suppressed values are NaN.

    Args:
        provinces: 2-digit province codes; ``None`` = all.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per municipality.
    """
    a = _read(39363, data_dir, provinces)
    a["kind"] = a["Viviendas y plazas"].str.lower().map(lambda x: "dwellings" if x.startswith("viviendas") else "places" if x.startswith("plazas") and "por" not in x else None)
    a = a[a["kind"].notna()]
    w = a.pivot_table(index="GEOID", columns=["kind", "Periodo"], values="Total", aggfunc="first")
    w.columns = [f"ine_tourist_{k}_{p}" for k, p in w.columns]
    b = _read(39366, data_dir, provinces)
    s = b.pivot_table(index="GEOID", columns="Periodo", values="Total", aggfunc="first")
    s.columns = [f"ine_tourist_dwellings_share_{p}" for p in s.columns]
    out = w.join(s, how="outer")
    for kind in ("dwellings", "places", "dwellings_share"):
        cols = sorted(c for c in out.columns if c.startswith(f"ine_tourist_{kind}_20"))
        if cols:
            out[f"ine_tourist_{kind}_latest"] = out[cols[-1]]
    return out.reset_index()


def load_migration_balance(provinces: Optional[Iterable[str]] = None, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Per municipality: ``ine_netmig_{total,exterior,interior}_<year>`` (both sexes), net migration saldo from EMCR (table 69767).

    Args:
        provinces: 2-digit province codes; ``None`` = all.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per municipality.
    """
    df = _read(69767, data_dir, provinces)
    df = df[df["Sexo"] == "Ambos sexos"]
    df["t"] = df["Tipo de saldo"].str.lower().str.replace("saldo ", "", regex=False).str.strip()
    w = df.pivot_table(index="GEOID", columns=["t", "Periodo"], values="Total", aggfunc="first")
    w.columns = [f"ine_netmig_{t}_{p}" for t, p in w.columns]
    return w.reset_index()
