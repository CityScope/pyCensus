"""API client for Spain INE (Instituto Nacional de Estadistica) population data.

Technical aspects:
    INE publishes its "Padron municipal" (municipal population register)
    through a real, public, keyless JSON API -- INEbase's "Tempus3" web
    service (documented at https://www.ine.es/dyngs/INEbase/es/operacion.htm
    and https://www.ine.es/dyngs/INEbase/es/dwtempusbaris.htm, and more
    directly at https://www.ine.es/wstempus_gen/INE_WSTempus_GenericaAI.pdf).

    Table 29005 ("Cifras oficiales del padron por municipio") returns,
    for every one of Spain's ~8,131 municipalities, three rows (Total /
    Hombres / Mujeres) each carrying that municipality's latest annual
    population figure and -- when queried with ``tip=AM`` -- a ``MetaData``
    block that includes the municipality's real 5-digit INE code (verified
    2026-08-19: ``GET
    https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/29005?nult=1&tip=AM``
    returns ``{"MetaData": [{"T3_Variable": "Municipios", "Codigo": "44001",
    "Nombre": "Ababuj", ...}], "Data": [{"Anyo": 2025, "Valor": 73.0}]}``
    -- and summing every municipality's "Total" value across the whole
    country gives 47,385,107, which matches INE table 2915's "Total
    Nacional" figure for 2021 exactly).

    No API key is required for this endpoint -- it is INE's own public read
    API, not a third-party service needing registration.

    Population *by census section* (see :func:`fetch_padron_secciones`
    below) comes from a different, real, keyless source -- per-province
    PC-Axis/CSV files, not the Tempus3 JSON API -- verified 2026-08-20.

Source:
    https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/29005
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

TEMPUS_BASE_URL = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA"

# Table 29005: "Cifras oficiales del padron por municipio" -- every Spanish
# municipality, latest year, broken down by sex (Total/Hombres/Mujeres).
PADRON_MUNICIPIOS_TABLE = "29005"

# Sex variable codes within table 29005's MetaData ("Sexo" -> "Codigo").
_SEX_CODE_TOTAL = "0"
_SEX_CODE_MALE = "1"
_SEX_CODE_FEMALE = "2"


def fetch_padron_municipios(raw_cache_path: Optional[Path] = None, timeout: int = 120) -> pd.DataFrame:
    """Download (or read from cache) INE's municipality-level population register.

    Args:
        raw_cache_path: If given and it already exists, read the raw JSON
            response from there instead of hitting the network; if given
            and it does not exist, the downloaded response is written there
            for next time.
        timeout: HTTP timeout in seconds.

    Returns:
        DataFrame with one row per municipality: ``GEOID`` (5-digit INE
        municipality code), ``TOTAL_POB``, ``POB_HOMBRES``, ``POB_MUJERES``,
        ``year``.

    Raises:
        requests.HTTPError: If the INE API request fails.
    """
    if raw_cache_path is not None and raw_cache_path.exists():
        payload = json.loads(raw_cache_path.read_text())
    else:
        url = f"{TEMPUS_BASE_URL}/{PADRON_MUNICIPIOS_TABLE}"
        response = requests.get(url, params={"nult": 1, "tip": "AM"}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if raw_cache_path is not None:
            raw_cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw_cache_path.write_text(json.dumps(payload))

    return _parse_padron_payload(payload)


def _parse_padron_payload(payload: list) -> pd.DataFrame:
    """Reshape INE Tempus's series-per-row JSON into one row per municipality."""
    rows: dict[str, dict] = {}
    for series in payload:
        meta = {m.get("T3_Variable"): m for m in series.get("MetaData", [])}
        mun_meta = meta.get("Municipios")
        sex_meta = meta.get("Sexo")
        data_points = series.get("Data") or []
        if mun_meta is None or sex_meta is None or not data_points:
            continue

        geoid = str(mun_meta.get("Codigo", "")).zfill(5)
        sex_code = str(sex_meta.get("Codigo", ""))
        # Latest (only, since nult=1) data point.
        point = data_points[-1]
        value = point.get("Valor")
        year = point.get("Anyo")

        row = rows.setdefault(geoid, {"GEOID": geoid, "year": year})
        if sex_code == _SEX_CODE_TOTAL:
            row["TOTAL_POB"] = value
        elif sex_code == _SEX_CODE_MALE:
            row["POB_HOMBRES"] = value
        elif sex_code == _SEX_CODE_FEMALE:
            row["POB_MUJERES"] = value

    return pd.DataFrame(rows.values())


# --- Population by census section ("Padron continuo por seccion censal") ---
#
# INE also publishes population broken down by census section, but *not*
# through the Tempus3 JSON API used above -- it is published as PC-Axis
# files, one per province, under the "Estadistica del Padron Continuo"
# operation's "Por secciones censales" results page:
# https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177012&menu=resultados&idp=1254734710990
#
# Verified live 2026-08-20: that page's "Por secciones censales" selector
# points at PC-Axis file directories under
# https://www.ine.es/dynt3/inebase/index.htm?type=pcaxis&path=/t20/e245/p07/a<YEAR>
# with 2022 the most recent year published (the 2023+ dropdown options do
# not exist -- INE has not continued this specific by-section product past
# 2022, even though its municipality-level Padron is more current). Each
# province has 6 tables (01-06); table 01 is "Poblacion por sexo, seccion
# y edad (grupos quinquenales)", which includes an "Edad = Total" row per
# section for each of "Ambos Sexos"/"Hombres"/"Mujeres". Downloaded (CSV,
# tab-separated) via:
#   GET https://www.ine.es/jaxi/files/_px/es/csv_bd/t20/e245/p07/a2022/l0/2001.csv_bd?nocab=1
# (province "20" = Gipuzkoa, table "01") -- returned a real tab-separated
# file, 36,036 data rows, with columns Sexo / Seccion / Edad / Total. Its
# 545 unique real section codes ("Seccion", e.g. "2000101001", format
# CPRO(2)+CMUN(3)+CDIS(2)+CSEC(3), matching the boundary service's
# ``CUSEC``) sum, for Sexo="Ambos Sexos" and Edad="Total", to exactly
# 724,418 -- which is also the file's own province-wide "TOTAL" row value,
# confirming this really is a complete, internally-consistent section
# breakdown, not a sample.
PADRON_SECCIONES_CSV_URL = (
    "https://www.ine.es/jaxi/files/_px/es/csv_bd/t20/e245/p07/a{year}/l0/{province}01.csv_bd"
)
PADRON_SECCIONES_LATEST_YEAR = 2022

_SECCIONES_SEX_TOTAL = "Ambos Sexos"
_SECCIONES_SEX_MALE = "Hombres"
_SECCIONES_SEX_FEMALE = "Mujeres"


def fetch_padron_secciones(
    province_code: str,
    year: int = PADRON_SECCIONES_LATEST_YEAR,
    raw_cache_path: Optional[Path] = None,
    timeout: int = 180,
) -> pd.DataFrame:
    """Download (or read from cache) INE's section-level population register for one province.

    Args:
        province_code: 2-digit INE province code (e.g. ``"20"`` for
            Gipuzkoa).
        year: Vintage year. 2022 is the latest year this specific
            by-section product was published (see module docstring); other
            years 2004-2022 also exist under the same URL pattern.
        raw_cache_path: If given and it already exists, read the raw CSV
            from there instead of hitting the network; if given and it
            does not exist, the downloaded response is written there for
            next time.
        timeout: HTTP timeout in seconds.

    Returns:
        DataFrame with one row per census section: ``GEOID`` (10-digit
        INE ``CUSEC``-format section code), ``TOTAL_POB``, ``POB_HOMBRES``,
        ``POB_MUJERES``.

    Raises:
        requests.HTTPError: If the INE download request fails.
    """
    if raw_cache_path is not None and raw_cache_path.exists():
        text = raw_cache_path.read_text(encoding="utf-8-sig")
    else:
        url = PADRON_SECCIONES_CSV_URL.format(year=year, province=province_code)
        response = requests.get(url, params={"nocab": 1}, timeout=timeout)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig")
        if raw_cache_path is not None:
            raw_cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw_cache_path.write_text(text, encoding="utf-8")

    return _parse_secciones_csv(text)


def _parse_secciones_csv(text: str) -> pd.DataFrame:
    """Reshape INE's per-province section CSV (Sexo/Seccion/Edad/Total rows) into one row per section."""
    from io import StringIO

    df = pd.read_csv(StringIO(text), sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[(df["Sección"] != "TOTAL") & (df["Edad (grupos quinquenales)"] == "Total")]
    df["Total"] = df["Total"].str.replace(".", "", regex=False).astype(float)

    pivot = df.pivot_table(index="Sección", columns="Sexo", values="Total", aggfunc="first")
    result = pd.DataFrame({"GEOID": pivot.index.astype(str).str.zfill(10)})
    result["TOTAL_POB"] = pivot.get(_SECCIONES_SEX_TOTAL).to_numpy() if _SECCIONES_SEX_TOTAL in pivot else None
    result["POB_HOMBRES"] = pivot.get(_SECCIONES_SEX_MALE).to_numpy() if _SECCIONES_SEX_MALE in pivot else None
    result["POB_MUJERES"] = pivot.get(_SECCIONES_SEX_FEMALE).to_numpy() if _SECCIONES_SEX_FEMALE in pivot else None
    return result.reset_index(drop=True)


__all__ = [
    "fetch_padron_municipios",
    "fetch_padron_secciones",
    "PADRON_MUNICIPIOS_TABLE",
    "PADRON_SECCIONES_CSV_URL",
    "PADRON_SECCIONES_LATEST_YEAR",
    "TEMPUS_BASE_URL",
]
