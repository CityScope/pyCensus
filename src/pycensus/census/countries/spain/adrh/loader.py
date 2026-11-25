"""Loader for INE's Atlas de Distribución de Renta de los Hogares (ADRH, operation 353): per census section / district / municipality
income (mean net/gross per person and household, per consumption unit), income sources, Gini and P80/P20, relative-poverty shares and
demographic indicators (mean age, <18 and 65+ shares, household size, single-person households, nationality).

Technical aspects:
    INE publishes one table per province and indicator family (CSV bulk files at
    ``https://www.ine.es/jaxiT3/files/t/es/csv_bd/<table id>.csv?nocab=1``). The table ids of a province are found by reading the first
    data row of each table of operation 353 (``servicios.ine.es/wstempus`` lists them) and cached in ``<data_dir>/raw/adrh/tables.json``.
    Values are thousands of euros with a decimal point (``20.935`` = 20,935 EUR) -> multiplied by 1000. The latest period of each table is used.

    ``load_attributes`` returns a plain DataFrame (``GEOID`` = 10-digit section code or 5-digit municipality code) with global-schema
    names bare (``meanHouseholdIncome``, ``under18Population``, ``over65Population``, ``households``, ``povertyPopulation``) and the other
    indicators prefixed ``ine_``; geometry comes from the caller (``pycensus.census.countries.spain.ine``).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import json
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

OPERATION = 353
TABLES_URL = f"https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/{OPERATION}"
CSV_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bd/{id}.csv?nocab=1"

FAMILIES = {
    "income": "Indicadores de renta media y mediana",
    "sources": "Distribución por fuente de ingresos",
    "gini": "Índice de Gini y Distribución de la renta P80/P20",
    "relative": "Porcentaje de población con ingresos por unidad de consumo por debajo/encima de determinados umbrales relativos por sexo",
    "demo": "Indicadores demográficos",
}

INCOME = {
    "Renta neta media por persona": "ine_incomeNetPersonMean",
    "Renta neta media por hogar": "meanHouseholdIncome",
    "Media de la renta por unidad de consumo": "ine_incomePerConsumptionUnitMean",
    "Mediana de la renta por unidad de consumo": "ine_incomePerConsumptionUnitMedian",
    "Renta bruta media por persona": "ine_incomeGrossPersonMean",
    "Renta bruta media por hogar": "ine_incomeGrossHouseholdMean",
}
SOURCES = {
    "Fuente de ingreso: salario": "ine_incomeSourceSalaryShare",
    "Fuente de ingreso: pensiones": "ine_incomeSourcePensionsShare",
    "Fuente de ingreso: prestaciones por desempleo": "ine_incomeSourceUnemploymentBenefitsShare",
    "Fuente de ingreso: otras prestaciones": "ine_incomeSourceOtherBenefitsShare",
    "Fuente de ingreso: otros ingresos": "ine_incomeSourceOtherShare",
}
GINI = {"Índice de Gini": "ine_giniIndex", "Distribución de la renta P80/P20": "ine_incomeP80P20Ratio"}
RELATIVE = {
    "Población con ingresos por unidad de consumo por debajo 40% de la mediana": "ine_belowHalfMedianShare40",
    "Población con ingresos por unidad de consumo por debajo 50% de la mediana": "ine_belowMedianShare50",
    "Población con ingresos por unidad de consumo por debajo 60% de la mediana": "ine_belowMedianShare60",
    "Población con ingresos por unidad de consumo por encima 140% de la mediana": "ine_aboveMedianShare140",
    "Población con ingresos por unidad de consumo por encima 160% de la mediana": "ine_aboveMedianShare160",
    "Población con ingresos por unidad de consumo por encima 200% de la mediana": "ine_aboveMedianShare200",
}
DEMO = {
    "Edad media de la población": "ine_ageMean", "Porcentaje de población menor de 18 años": "_under18Share",
    "Porcentaje de población de 65 y más años": "_over65Share", "Tamaño medio del hogar": "ine_householdSizeMean",
    "Porcentaje de hogares unipersonales": "ine_singlePersonHouseholdsShare", "Población": "_population",
    "Porcentaje de población española": "_spanishShare",
}
_INCOME_COLUMNS = {"meanHouseholdIncome", "ine_incomeNetPersonMean", "ine_incomePerConsumptionUnitMean", "ine_incomePerConsumptionUnitMedian",
                   "ine_incomeGrossPersonMean", "ine_incomeGrossHouseholdMean"}


def _raw(data_dir: Optional[str]) -> Path:
    d = get_data_dir("spain", data_dir) / "raw" / "adrh"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _first_municipality(table_id: int) -> str:
    r = requests.get(CSV_URL.format(id=table_id), stream=True, timeout=120)
    buf = b""
    for chunk in r.iter_content(4096):
        buf += chunk
        if buf.count(b"\n") > 2:
            break
    r.close()
    return buf.decode("utf-8-sig", errors="ignore").split("\n")[1].split("\t")[0][:2]


def _table_id(family: str, province: str, raw: Path) -> int:
    cache = raw / "tables.json"
    known = json.loads(cache.read_text()) if cache.exists() else {}
    key = f"{family}:{province}"
    if key in known:
        return known[key]
    tables = requests.get(TABLES_URL, timeout=120).json()
    for t in tables:
        if t["Nombre"] != FAMILIES[family]:
            continue
        if _first_municipality(t["Id"]) == province:
            known[key] = t["Id"]
            cache.write_text(json.dumps(known))
            return t["Id"]
    raise LookupError(f"No ADRH table '{FAMILIES[family]}' for province {province}")


def _read(family: str, province: str, raw: Path) -> pd.DataFrame:
    tid = _table_id(family, province, raw)
    path = raw / f"{tid}.csv"
    if not path.exists():
        r = requests.get(CSV_URL.format(id=tid), timeout=600)
        r.raise_for_status()
        path.write_bytes(r.content)
    df = pd.read_csv(path, sep="\t", encoding="utf-8-sig", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df.rename(columns={"Period": "Periodo"})


def _indicator_column(df: pd.DataFrame, wanted: str) -> str:
    """The table's indicator column: INE words its header differently per province table ('...renta media' vs '...media y mediana')."""
    if wanted in df.columns:
        return wanted
    others = [c for c in df.columns if c not in ("Municipios", "Distritos", "Secciones", "Periodo", "Total", "Sexo")]
    return others[0]


def _latest_wide(df: pd.DataFrame, indicator_col: str, mapping: dict, level: str, extra_filter: Optional[dict] = None) -> pd.DataFrame:
    indicator_col = _indicator_column(df, indicator_col)
    if extra_filter:
        for col, val in extra_filter.items():
            df = df[df[col] == val]
    df = df[df["Periodo"] == df["Periodo"].max()]
    if level == "section":
        df = df[df["Secciones"].notna()]
        df = df.assign(GEOID=df["Secciones"].str.split().str[0])
    elif level == "district":
        df = df[df["Distritos"].notna() & df["Secciones"].isna()]
        df = df.assign(GEOID=df["Distritos"].str.split().str[0])
    else:
        df = df[df["Distritos"].isna() & df["Secciones"].isna() & df["Municipios"].notna()]
        df = df.assign(GEOID=df["Municipios"].str.split().str[0])
    df = df[df[indicator_col].isin(mapping)]
    total = df["Total"].str.replace(",", ".", regex=False)
    is_count = df[indicator_col] == "Población"
    total = total.where(~is_count, df["Total"].str.replace(",", "", regex=False).str.replace(".", "", regex=False))   # counts: thousands separator
    df = df.assign(value=pd.to_numeric(total, errors="coerce"), name=df[indicator_col].map(mapping))
    return df.pivot_table(index="GEOID", columns="name", values="value", aggfunc="first").reset_index()


def load_attributes(provinces: Iterable[str], level: str = "section", data_dir: Optional[str] = None) -> pd.DataFrame:
    """ADRH indicators of ``level`` ('section' / 'district' / 'municipality') for the 2-digit ``provinces``.

    Args:
        provinces: 2-digit province codes.
        level: ``"section"``, ``"district"`` or ``"municipality"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per unit (``GEOID``).
    """
    raw = _raw(data_dir)
    frames = []
    for province in provinces:
        parts = []
        for family, mapping, indicator in (
            ("income", INCOME, "Indicadores de renta media y mediana"), ("sources", SOURCES, "Distribución por fuente de ingresos"),
            ("gini", GINI, "Índice de Gini y Distribución de la renta P80/P20"), ("demo", DEMO, "Indicadores demográficos"),
        ):
            parts.append(_latest_wide(_read(family, province, raw), indicator, mapping, level))
        parts.append(_latest_wide(_read("relative", province, raw), "Distribución de la renta por unidad de consumo", RELATIVE, level, {"Sexo": "Total"}))
        merged = parts[0]
        for p in parts[1:]:
            merged = merged.merge(p, on="GEOID", how="outer")
        for c in _INCOME_COLUMNS & set(merged.columns):
            merged[c] = merged[c] * 1000.0   # thousands of EUR -> EUR
        pop = merged.get("_population")
        if pop is not None:
            if "_under18Share" in merged:
                merged["under18Population"] = pop * merged["_under18Share"] / 100.0
            if "_over65Share" in merged:
                merged["over65Population"] = pop * merged["_over65Share"] / 100.0
            if "_spanishShare" in merged:
                merged["ine_foreignNationalPopulation"] = pop * (100.0 - merged["_spanishShare"]) / 100.0
            if "ine_householdSizeMean" in merged:
                merged["households"] = pop / merged["ine_householdSizeMean"].where(merged["ine_householdSizeMean"] > 0)
            if "ine_belowMedianShare60" in merged:
                merged["povertyPopulation"] = pop * merged["ine_belowMedianShare60"] / 100.0
        merged = merged[merged["GEOID"].astype(str).str[:2] == str(province).zfill(2)]   # INE's file for Álava (01) holds the whole country
        frames.append(merged.drop(columns=[c for c in merged.columns if c.startswith("_")]))
    if not frames:
        return pd.DataFrame({"GEOID": []})
    # one row per unit: a unit twice (two provinces' files) doubled every count of the census join (Gipuzkoa 2026-11-20: 1.45 M residents for 0.72 M)
    return pd.concat(frames, ignore_index=True).drop_duplicates("GEOID")
