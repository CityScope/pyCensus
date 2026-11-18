"""Spanish election results at census-section level (Congreso 2023, Municipales 2023, Parlamento Vasco 2024) + H3 res-8 versions.

Sources (verified live 2026-10-25):
  Ministerio del Interior, Infoelectoral "Area de descargas" (public JSON API used by the page itself; Basic-auth credentials are the public ones
  embedded in ``descargas.js``): ``https://infoelectoral.interior.gob.es/min/archivos/extraccion?tipoConvocatoria=<2|4>&idConvocatoria=<YYYYMM>``.
  Files ``02202307_MESA.zip`` (Congreso 23-07-2023) and ``04202305_MESA.zip`` (Municipales 28-05-2023): fixed-width ``03`` candidacies,
  ``09`` mesa totals, ``10`` mesa votes per candidacy. Native resolution = polling table (mesa), aggregated here to the census section
  (province(2)+municipality(3)+district(2)+section(3) = 10-digit GEOID). CERA (overseas, municipality 999) is dropped. Municipales mesa files
  only cover municipalities > 250 inhabitants (smaller ones are not in the mesa files and are not returned).
  Gobierno Vasco "Descarga de ficheros de resultados de elecciones": ``.../w_em_descargas/es_def/adjuntos/csv/Cas-csv.zip`` -> ``MesPv24_c.csv``
  (Parlamento Vasco 21-04-2024, per mesa; Araba/Gipuzkoa/Bizkaia only).
Geometry: INE census sections via ``spain.geography`` (``Secciones_2025`` OGC API; election sections that no longer exist in the 2025 sectioning
  keep their data in the section frame but are absent from H3 (reported in ``frame.attrs['unmatched_sections']``).
Parties: candidacies are merged by the *national accumulation head* (cols 227-232 of file 03) so coalitions that run under different codes per province
  are one party; Basque 2024 uses the party name. Bloc JSON: ``schema/elections_blocs.json``. Columns: see :mod:`pycensus.elections`.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import io
import json
import zipfile
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

from ....elections import build_frame, h3_weights, load_blocs, order_columns, to_h3
from .. import _http

API = "https://infoelectoral.interior.gob.es/min/"
AUTH = ("apiInfoelectoral", "apiInfoelectoralPro")
BASQUE_URL = "https://www.euskadi.eus/contenidos/informacion/w_em_descargas/es_def/adjuntos/csv/Cas-csv.zip"
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
ELECTIONS = {  # (scope, year) -> (tipo, YYYYMM)
    ("national", 2023): (2, "202307"), ("municipal", 2023): (4, "202305")}
PROVINCE_NAMES = {"Álava": "01", "Araba/Álava": "01", "Gipuzkoa": "20", "Bizkaia": "48"}


def norm(s: str) -> str:
    """Upper-case party name without dots or repeated spaces (the key of the blocs file).

    Args:
        s: Party name.

    Returns:
        The normalised name.
    """
    return " ".join(str(s).upper().replace(".", "").split())


def _raw(data_dir: Optional[str]) -> Path:
    d = get_data_dir("spain", data_dir) / "raw" / "elections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _interior_zip(tipo: int, conv: str, data_dir) -> Path:
    cached = _raw(data_dir) / f"{tipo:02d}{conv}_MESA.zip"   # `<tipo><convocatoria>_MESA.zip`: used first (the ministry's site may refuse automated requests)
    if cached.is_file() and cached.stat().st_size > 1_000_000:
        return cached
    r = requests.get(f"{API}archivos/extraccion", params={"tipoConvocatoria": tipo, "idConvocatoria": conv}, auth=AUTH, timeout=60,
                     headers=_http.BROWSER_HEADERS)
    r.raise_for_status()
    item = next(x for x in r.json()["data"] if x["nombreDoc"].endswith("_MESA.zip"))
    return _http.download(item["url"], _raw(data_dir) / item["nombreDoc"])


def _sections_interior(tipo: int, conv: str, data_dir, provinces):
    z = zipfile.ZipFile(_interior_zip(tipo, conv, data_dir))
    tt, ym = f"{tipo:02d}", conv[2:]
    name = lambda n: next(x for x in z.namelist() if x.upper() == f"{n}{tt}{ym}.DAT".upper())
    c = pd.read_fwf(io.BytesIO(z.read(name("03"))), colspecs=[(8, 14), (14, 64), (214, 220), (220, 226), (226, 232)], header=None, encoding="latin1",
                    dtype=str)
    c.columns = ["cand", "sig", "prov", "aut", "nat"]
    c["sig"] = c["sig"].str.strip()
    head = c.set_index("cand")["sig"]
    c["party"] = [norm(head.get(n, s)) for n, s in zip(c["nat"], c["sig"])]
    spec = [(9, 11), (11, 13), (13, 16), (16, 18), (18, 21), (22, 23)]
    cols = ["ccaa", "prov", "mun", "dis", "sec", "mesa"]
    t = pd.read_fwf(io.BytesIO(z.read(name("09"))), colspecs=spec + [(30, 37), (65, 72), (72, 79), (79, 86)], header=None, dtype=str)
    t.columns = cols + ["electors", "blank", "null", "cands"]
    v = pd.read_fwf(io.BytesIO(z.read(name("10"))), colspecs=spec + [(23, 29), (29, 36)], header=None, dtype=str)
    v.columns = cols + ["cand", "votes"]
    out = []
    for df in (t, v):
        df.drop(df.index[df["mun"] == "999"], inplace=True)
        if provinces is not None:
            df.drop(df.index[~df["prov"].isin(list(provinces))], inplace=True)
        df["GEOID"] = df["prov"] + df["mun"] + df["dis"] + df["sec"]
    for col in ("electors", "blank", "null", "cands"):
        t[col] = pd.to_numeric(t[col])
    t["cast"] = t["blank"] + t["null"] + t["cands"]
    totals = t.groupby("GEOID")[["blank", "cast", "electors"]].sum().reset_index()
    v["votes"] = pd.to_numeric(v["votes"])
    v = v.merge(c[["cand", "party"]], on="cand")
    votes = v.groupby(["GEOID", "party"])["votes"].sum().reset_index()
    return votes, totals


def _sections_basque(data_dir, provinces):
    p = _http.download(BASQUE_URL, _raw(data_dir) / "Cas-csv.zip")
    z = zipfile.ZipFile(p)
    raw = z.read("MesPv24_c.csv").decode("latin1")
    lines = raw.splitlines()
    parties_hdr = lines[0].split(";")
    df = pd.read_csv(io.StringIO("\n".join(lines[1:])), sep=";", dtype=str)
    for c in ("Cod Municipio", "Distrito", "Sección", "Mesa"):
        df[c] = df[c].str.strip().str.strip('"').str.strip()
    df["prov"] = df["TH"].map({"Álava": "01", "Gipuzkoa": "20", "Bizkaia": "48"})
    df = df[df["prov"].notna() & df["Sección"].notna()]
    if provinces is not None:
        df = df[df["prov"].isin(list(provinces))]
    df["GEOID"] = df["prov"] + df["Cod Municipio"].str.zfill(3) + df["Distrito"].str.zfill(2) + df["Sección"].str.zfill(3)
    num = lambda s: pd.to_numeric(s, errors="coerce").fillna(0)
    df["electors"], df["cast"], df["blank"] = num(df["Censo"]), num(df["Votos"]), num(df["Blancos"])
    totals = df.groupby("GEOID")[["blank", "cast", "electors"]].sum().reset_index()
    cols = list(df.columns)
    recs = []
    for i, name in enumerate(parties_hdr):
        if name and i >= 13 and parties_hdr[i - 1] != name:   # first column of each triple = absolute votes
            recs.append(pd.DataFrame({"GEOID": df["GEOID"], "party": norm(name), "votes": num(df[cols[i]])}))
    votes = pd.concat(recs).groupby(["GEOID", "party"])["votes"].sum().reset_index()
    return votes, totals


def _geom(provinces, data_dir):
    import geopandas as gpd
    from ..geography import _load_spain_sections_for_province
    return pd.concat([_load_spain_sections_for_province(p, data_dir) for p in provinces], ignore_index=True)


def load_election(scope: str, year: int, level: str = "section", provinces: Optional[Iterable[str]] = None, data_dir: Optional[str] = None,
                  min_share: float = 0.03) -> pd.DataFrame:
    """``scope`` national|municipal|state (state = Parlamento Vasco 2024 only); ``level`` 'section' (GEOID, 10 digit) or 'h3' (h3_cell, res 8).
    ``provinces``: 2-digit INE codes (None = all available; ``'h3'`` then needs all province geometries - slow, pass provinces).

    Args:
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        year: Election year.
        level: ``"section"`` or ``"h3"``.
        provinces: 2-digit province codes; ``None`` = all.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        min_share: Parties above this share get their own columns.

    Returns:
        The election frame.

    Raises:
        ValueError: For a state election other than the Basque 2024.
    """
    provs = list(provinces) if provinces is not None else None
    if scope == "state":
        if year != 2024:
            raise ValueError("state scope: only the Parlamento Vasco 2024 is implemented")
        votes, totals = _sections_basque(data_dir, provs)
    else:
        tipo, conv = ELECTIONS[(scope, year)]
        votes, totals = _sections_interior(tipo, conv, data_dir, provs)
    blocs = load_blocs(BLOCS_PATH)[f"{scope}_{year}"]
    # the bloc key set also keeps parties above min_share even if the area slice is small
    df = build_frame(votes, totals, blocs, scope, year, min_share)
    if level == "section":
        return order_columns(df)
    provs = provs or sorted(df["GEOID"].str[:2].unique())
    g = _geom(provs, data_dir)
    w = h3_weights(g, 8)
    out = to_h3(df, w, scope, year)
    out.attrs["unmatched_sections"] = sorted(set(df["GEOID"]) - set(g["GEOID"]))
    return out


def load_congreso_2023(level="section", provinces=None, data_dir=None):
    """Congreso election 2023 (see :func:`load_election`).

    Args:
        level: ``"section"`` or ``"h3"``.
        provinces: 2-digit province codes.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("national", 2023, level, provinces, data_dir)
def load_municipal_2023(level="section", provinces=None, data_dir=None):
    """Municipal elections 2023 (see :func:`load_election`).

    Args:
        level: ``"section"`` or ``"h3"``.
        provinces: 2-digit province codes.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("municipal", 2023, level, provinces, data_dir)
def load_parlamento_vasco_2024(level="section", provinces=("01", "20", "48"), data_dir=None):
    """Basque Parliament election 2024 (see :func:`load_election`).

    Args:
        level: ``"section"`` or ``"h3"``.
        provinces: 2-digit province codes.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("state", 2024, level, provinces, data_dir)
