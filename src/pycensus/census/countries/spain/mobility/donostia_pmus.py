"""Donostia / San Sebastian: trips by mode per neighbourhood (auzoa), from the neighbourhood sheets of the PMUS 2024-2029.

The city's sustainable mobility plan (PMUS San Sebastian 2024-2029, December 2023) tabulates, for each of its 15 surveyed neighbourhoods,
the weekday trips that start in it ("Origen <barrio>") by mode -- walking, bicycle, public transport ("colectivos"), car, motorcycle,
multimodal -- from the Basque mobility survey 2021 (EM CAPV) and its 2022 oversample of the city (Landarbaso and Oarain are left out by the
plan; Igeldo and Zubieta have no sheet). This is the finest published mode split of the city: the survey microdata are only released per
municipality. Trips are all purposes and by origin, so they include trips of non-residents leaving the neighbourhood (more so in the
centre) -- a travel-survey zoning, not a residence-based commute table.

The plan (PDF, 42 MB) and the city's neighbourhood polygons (``Auzoak.zip``, open data) are downloaded once into
``<cache>/spain/donostia_pmus/``; the sheets are read with ``pdftotext -layout`` (poppler).

    from pycensus.census.countries.spain.mobility import donostia_pmus
    donostia_pmus.table()      # DataFrame: one row per neighbourhood, trips by mode
    donostia_pmus.load()       # + neighbourhood geometry
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

PLAN_URL = "https://www.euskadi.eus/contenidos/informacion/eaes_649inet_pmus_dss/es_def/adjuntos/PMUS-SS-2024-2029.pdf"
AUZOAK_URL = "https://www.donostia.eus/ide/ADMINISTRAZIO_MUGAK-LIMITES_ADMINISTRATIVOS/shp/Auzoak.zip"
PAGES = (117, 165)   # the neighbourhood sheets
PREFIX = "donpmus_"
#: plan's row label -> column (trips starting in the neighbourhood, weekday)
MODES = {"andando": "walkTrips", "bicicleta": "bikeTrips", "colectivos": "publicTransportTrips", "automóvil": "carTrips",
         "moto": "motorcycleTrips", "multimodal": "multimodalTrips"}
#: plan's neighbourhood name -> the city's neighbourhood code (KodAuzo of Auzoak.zip)
CODES = {"Aiete": 1, "Altza": 2, "Amaraberri": 3, "Antiguo": 4, "Añorga": 5, "Ategorrieta-Ulia": 6, "Centro": 7, "Egia": 8, "Gros": 9,
         "Ibaeta": 10, "Intxaurrondo": 12, "Loiola": 13, "Martutene": 14, "Miracruz-Bidebieta": 15, "Miramon-Zorroaga": 16}


def _dir(cache_dir: Optional[str]) -> Path:
    from pycensus import cache as cache_store

    base = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    d = base / "spain" / "donostia_pmus"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get(url: str, path: Path, min_size: int) -> Path:
    if not path.is_file() or path.stat().st_size < min_size:
        import requests

        r = requests.get(url, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def parse_sheets(text: str) -> pd.DataFrame:
    """The "Origen <barrio>" tables of the plan's text: one row per neighbourhood, the Total column per mode.

    Args:
        text: ``pdftotext -layout`` text of the neighbourhood sheets.

    Returns:
        DataFrame with ``name`` and one trip count per mode (0 where the plan leaves the cell empty).
    """
    rows = []
    for m in re.finditer(r"\n\s*Origen (.+?)\n(.*?)\n\s*Destino ", text, re.S):
        name, body = m.group(1).strip(), m.group(2)
        r = {"name": name}
        for label, col in MODES.items():
            line = re.search(rf"^\s*{label}\s+(.*)$", body, re.M)
            nums = re.findall(r"(\d[\d.]*)\s+(\d+,\d)%", line.group(1)) if line else []
            r[col] = float(nums[-1][0].replace(".", "")) if nums else 0.0   # the last pair is the Total column
        rows.append(r)
    return pd.DataFrame(rows)


def table(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Trips by mode per neighbourhood (cached as parquet).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per neighbourhood: GEOID (KodAuzo), name, ``tripsTotal`` and the trips per mode, prefixed ``donpmus_``.

    Raises:
        RuntimeError: When the sheets cannot be read (a changed plan layout).
    """
    d = _dir(cache_dir)
    pq = d / "trips_auzoa.parquet"
    if pq.is_file():
        return pd.read_parquet(pq)
    pdf = _get(PLAN_URL, d / "PMUS-SS-2024-2029.pdf", 10_000_000)
    text = subprocess.run(["pdftotext", "-layout", "-f", str(PAGES[0]), "-l", str(PAGES[1]), str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    t = parse_sheets(text)
    if set(t["name"]) != set(CODES):
        raise RuntimeError(f"neighbourhood sheets read: {sorted(t['name'])}; expected {sorted(CODES)}")
    t.insert(0, "GEOID", t["name"].map(CODES).astype(str))
    t["tripsTotal"] = t[list(MODES.values())].sum(axis=1)
    t = t.rename(columns={c: PREFIX + c for c in [*MODES.values(), "tripsTotal"]})
    t.to_parquet(pq)
    return t


def load(aoi: Optional[gpd.GeoDataFrame] = None, cache_dir: Optional[str] = None, **_) -> gpd.GeoDataFrame:
    """Trips by mode with the neighbourhood polygons (the city's Auzoak layer, one polygon per code).

    Args:
        aoi: Area of interest (GeoDataFrame); ``None`` = the whole city.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame in EPSG:4326.
    """
    zp = _get(AUZOAK_URL, _dir(cache_dir) / "Auzoak.zip", 10_000)
    g = gpd.read_file(f"zip://{zp}").to_crs(4326)
    g = g.dissolve(by="KodAuzo", as_index=False)[["KodAuzo", "geometry"]]
    g["GEOID"] = g["KodAuzo"].astype(int).astype(str)
    res = gpd.GeoDataFrame(g[["GEOID", "geometry"]].merge(table(cache_dir), on="GEOID", how="inner"), geometry="geometry", crs=4326)
    if aoi is not None:
        res = res[res.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return res


__all__ = ["load", "table", "parse_sheets"]
