"""CONEVAL "Grado de Rezago Social e indicadores, segun AGEB urbana de Mexico, 2020" (built from INEGI's Censo 2020, no income component).

Source: ``https://www.coneval.org.mx/Medicion/Documents/GRS_AGEB_2020/GRS_AGEB_urbana_2020.zip`` (one xlsx, ~61,400 urban AGEBs, key ``Clave de la AGEB`` = 13-digit
INEGI CVEGEO). The five grades Muy bajo ... Muy alto become ``deprivationIndex`` 1..5. It is a deprivation index, NOT an income-poverty rate (CONEVAL publishes
income poverty only for states and municipalities).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from pycensus.cache import get_data_dir

URL = "https://www.coneval.org.mx/Medicion/Documents/GRS_AGEB_2020/GRS_AGEB_urbana_2020.zip"
GRADES = {"muy bajo": 1, "bajo": 2, "medio": 3, "alto": 4, "muy alto": 5}
ATTRIBUTION = "CONEVAL, Grado de Rezago Social por AGEB urbana 2020 (Censo de Poblacion y Vivienda 2020, INEGI)."


def deprivation_by_ageb(data_dir: Optional[str] = None) -> pd.Series:
    """`Series(deprivationIndex 1..5)` indexed by the 13-digit AGEB CVEGEO.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
    """
    raw = get_data_dir("mexico", data_dir) / "raw" / "coneval"
    raw.mkdir(parents=True, exist_ok=True)
    cache = raw / "grs_ageb_2020.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["deprivationIndex"]
    xlsx = raw / "GRS_AGEB_urbana_2020.xlsx"
    if not xlsx.exists():
        r = requests.get(URL, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            xlsx.write_bytes(zf.read("GRS_AGEB_urbana_2020.xlsx"))
    x = pd.read_excel(xlsx, header=None, skiprows=6, dtype=str)
    key, grade = x.iloc[:, 7].str.strip(), x.iloc[:, 27].str.strip().str.lower()
    s = pd.Series(grade.map(GRADES).to_numpy(), index=key.to_numpy(), name="deprivationIndex").dropna()
    s = s[~s.index.duplicated()]
    s.to_frame().to_parquet(cache)
    return s
