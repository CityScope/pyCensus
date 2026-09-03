"""Bulk-file client for Chile's SII (Servicio de Impuestos Internos) comunal business/employment statistics.

Technical aspects:
    SII, Chile's national tax authority, publishes a real, keyless, plain
    downloadable .xlsx workbook of yearly comuna-level business statistics
    at:

        https://www.sii.cl/estadisticas/region/PUB_Reg_Com.xlsx

    (linked from https://www.sii.cl/sobre_el_sii/estadisticas_de_empresas.html
    and https://www.sii.cl/estadisticas/empresas_region.htm). Live-fetched
    and inspected 2026-08-23: a single sheet named ``EMP_Reg_Com``, header
    on row 6, one row per (year, region, comuna) with real columns:

        "Año Comercial", "ID_Region", "ID_Comuna", "Número de Empresas",
        "Ventas (UF)", "Número de Trabajadores Dependientes Informados",
        "Renta Neta Informada de Trabajadores Dependientes (UF)"

    "Número de Trabajadores Dependientes Informados" is the real count of
    dependent (payroll) workers *reported by employers whose tax domicile
    is in that comuna* -- i.e. jobs located in the comuna, not workers
    living there (SII's own comunal-statistics methodology attributes each
    worker to the employer's registered comuna). This is the Chile
    equivalent of USA's LODES WAC ``jobsTotal`` (see
    ``pycensus.countries.usa.lodes_wac``) -- a real jobs-by-workplace
    count, not an employed-residents count.

    Live-verified 2026-08-23: the file's ``Año Comercial`` column tops out
    at 2015 (the file itself has an HTTP ``Last-Modified`` of 2025-03-04,
    but SII appears to have stopped extending this particular historical
    series past commercial year 2015 -- later years are published through
    a different SII statistics product not identified/verified in this
    session). Reading comuna Concepcion (Región VIII del Bío-Bío) for 2015
    gives 154,065 dependent jobs and comuna Santiago (Región Metropolitana)
    gives 1,141,309 -- both plausible given each comuna's real role as a
    regional/national commercial and institutional job center (each
    figure exceeds the comuna's own resident population, consistent with
    a jobs-by-workplace count in a comuna that draws in commuters). This
    is a real, government-published number, not independently
    cross-checked against a second published total in this session --
    documented here as a plausibility check, not an exact-match
    verification. Given the 2015 vintage, wired data carries a
    ``sii_cl_jobsTotalYear`` companion column so downstream consumers can
    see how stale the figure is relative to other Chile sources (Casen
    2022, DPA/Censo 2017).

    ID_Region/ID_Comuna are free-text Spanish names (e.g. "VIII DEL BIO
    BIO", "CONCEPCION"), not CUT codes -- see ``loader.py`` for how these
    are matched to real DPA CUT codes via live comuna-name lookup (no
    hardcoded name->code table).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import requests

URL = "https://www.sii.cl/estadisticas/region/PUB_Reg_Com.xlsx"
SHEET_NAME = "EMP_Reg_Com"
HEADER_ROW = 5  # 0-indexed -- real header is on row 6 of the sheet


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    from .. import constants

    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "sii"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _fetch_xlsx(data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) SII's real national comuna-business .xlsx workbook."""
    raw_dir = _raw_dir(data_dir)
    cache_path = raw_dir / "PUB_Reg_Com.xlsx"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise RuntimeError(f"Unexpectedly small response fetching {URL!r} ({len(response.content)} bytes)")

    tmp_path = cache_path.with_suffix(".xlsx.part")
    with open(tmp_path, "wb") as f:
        f.write(response.content)
    tmp_path.rename(cache_path)
    return cache_path


def fetch_table(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch (cached) the raw SII comuna-year business table.

    Returns:
        DataFrame with real columns ``ano_comercial``, ``id_region``,
        ``id_comuna`` (free-text names), ``jobsTotal`` (real "Número de
        Trabajadores Dependientes Informados").
    """
    path = _fetch_xlsx(data_dir)
    raw = pd.read_excel(path, sheet_name=SHEET_NAME, header=HEADER_ROW)
    raw = raw.rename(
        columns={
            "Año Comercial": "ano_comercial",
            "ID_Region": "id_region",
            "ID_Comuna": "id_comuna",
            "Número de Trabajadores Dependientes Informados": "jobsTotal",
        }
    )
    raw = raw.dropna(subset=["ano_comercial", "id_region", "id_comuna"])
    return raw[["ano_comercial", "id_region", "id_comuna", "jobsTotal"]]


__all__ = ["URL", "fetch_table"]
