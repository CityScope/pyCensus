"""Valor tasado medio de vivienda libre (EUR/m2), municipalities above 25,000 inhabitants, quarterly (Boletin Online, table 4).

Technical aspects:
    ``https://apps.fomento.gob.es/BoletinOnline2/sedal/35103500.XLS`` (verified 2026-10-25, 4 MB, one sheet per quarter 'T1A2005'..'T2A2026').
    Rows carry province and municipality NAMES only (no INE code): the join to 5-digit codes uses the SERPAVI 'Municipios' sheet
    (province+municipality names, accent/case/article-insensitive); unmatched rows keep GEOID NaN and are reported in ``attrs['unmatched']``.
    Needs ``xlrd`` (legacy .xls). Native resolution: municipality (about 480 municipalities), so only for coarse H3 levels / popups.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import re
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

from .. import _http
from ..serpavi import municipality_crosswalk

URL = "https://apps.fomento.gob.es/BoletinOnline2/sedal/35103500.XLS"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)|/.*$", "", s)
    s = re.sub(r"\b(el|la|los|las|l|les|els|a|o|as|os|de|del|d)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def load_attributes(data_dir: Optional[str] = None, quarters: Optional[list] = None) -> pd.DataFrame:
    """Return GEOID (5-digit), province/municipality names and ``valor_tasado_{new,old,total}_<QnYYYY>`` (EUR/m2) and
    ``valor_tasado_n_<QnYYYY>`` (appraisals) for the given sheet names (default: the latest sheet and the one 4 and 40 quarters earlier).

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        quarters: Sheet names (``QnYYYY``); ``None`` = the defaults.

    Returns:
        One row per municipality.
    """
    d = get_data_dir("spain", data_dir) / "raw" / "valor_tasado"
    xls = _http.download(URL, d / "35103500.XLS")
    book = pd.read_excel(xls, sheet_name=None, header=None)
    names = [n.strip() for n in book]
    if quarters is None:
        quarters = [names[-1], names[-5], names[-41]]
    xw = municipality_crosswalk(data_dir)
    xw["k"] = xw["NPRO"].map(_norm) + "|" + xw["NMUN"].map(_norm)
    xw = xw.drop_duplicates("k").set_index("k")["CUMUN"]
    nm = xw.reset_index().assign(n=lambda d: d["k"].str.split("|").str[1])
    by_name = nm[~nm["n"].duplicated(keep=False)].set_index("n")["CUMUN"]
    out = None
    for q in quarters:
        raw = book[[n for n in book if n.strip() == q][0]]
        body = raw.iloc[17:, 1:10]
        body.columns = ["prov", "mun", "new", "old", "total", "_", "n_new", "n_old", "n_total"]
        body["prov"] = body["prov"].ffill()
        body = body[body["mun"].notna() & body["total"].notna()]
        body = body[~body["prov"].astype(str).str.contains("Fuente|Nota|\\(", regex=True)]
        body["k"] = body["prov"].map(_norm) + "|" + body["mun"].map(_norm)
        body["GEOID"] = body["k"].map(xw)
        miss = body["GEOID"].isna()  # province name wrapped/misspelt in the sheet: fall back to a nationally unique municipality name
        body.loc[miss, "GEOID"] = body.loc[miss, "mun"].map(_norm).map(by_name)
        body = body.rename(columns={c: f"valor_tasado_{c}_{q}" for c in ("new", "old", "total", "n_total")})
        body = body[["GEOID", "prov", "mun"] + [c for c in body.columns if c.startswith("valor_tasado_")]]
        for c in body.columns[3:]:
            body[c] = pd.to_numeric(body[c], errors="coerce")
        out = body if out is None else out.merge(body.drop(columns=["prov"]), on=["GEOID", "mun"], how="outer")
    out.attrs["unmatched"] = int(out["GEOID"].isna().sum())
    return out
