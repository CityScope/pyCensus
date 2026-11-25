"""Basque Country (CAPV): weekday trips by mode per comarca of origin, Estudio de la Movilidad de la CAPV 2021 (Basque Government household
survey, November-December 2021, population aged 7+).

The study publishes origin-destination matrices between its zones -- the 20 comarcas, with the three capitals (Vitoria-Gasteiz, Bilbao,
Donostia / San Sebastian) as zones of their own -- for all trips (Tabla 120) and per mode (Tablas 123-141, absolute values). The row total of
a matrix is the trips that start in the zone; this module reads those row totals. The microdata are released only on request and only per
municipality above 10,000 inhabitants, so these are the finest published mode splits outside Donostia's neighbourhood sheets
(:mod:`donostia_pmus`). Trips are all purposes, by origin (residents' and visitors' trips that start in the zone).

Geometry: the Basque Government's comarca polygons (``COMARCAS_5000_ETRS89``); a capital is its municipality polygon (``MUNICIPIOS_5000``)
and is cut out of its comarca. The report (PDF) and the polygons are downloaded once into ``<cache>/spain/em_capv/``.

    from pycensus.census.countries.spain.mobility import em_capv
    em_capv.table()      # DataFrame: one row per zone, trips by mode
    em_capv.load()       # + zone polygons (EPSG:4326)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

REPORT_URL = "https://www.euskadi.eus/contenidos/documentacion/em2021/es_def/adjuntos/Informe_encuesta+telefonia-CAST.pdf"
COMARCAS_URL = "https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/COMARCAS_5000_ETRS89.zip"
MUNICIPIOS_URL = "https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/MUNICIPIOS_5000_ETRS89.zip"
PREFIX = "emcapv_"
#: matrix (absolute values) -> column of trips starting in the zone
TABLES = {120: "tripsTotal", 123: "carTrips", 126: "publicTransportTrips", 129: "walkTrips", 132: "bikeTrips", 135: "multimodalTrips",
          138: "motorcycleTrips", 141: "otherTrips"}
#: row label in the report -> (zone code, comarca of the polygon layer (province, comarca code) or the capital's Eustat municipality code)
ZONES = {
    "Añana": ("01-01", ("01", "01")), "Llanada Alavesa": ("01-02", ("01", "02")), "Vitoria - Gasteiz": ("01-CAP", "01059"),
    "Montaña Alavesa": ("01-03", ("01", "03")), "Rioja Alavesa": ("01-04", ("01", "04")), "Estribaciones del Gorbea": ("01-05", ("01", "05")),
    "Cantábrica Alavesa": ("01-06", ("01", "06")),
    "Arratia-Nervión": ("48-01", ("48", "01")), "Gran Bilbao": ("48-02", ("48", "02")), "Bilbao": ("48-CAP", "48020"),
    "Duranguesado": ("48-03", ("48", "03")), "Encartaciones": ("48-04", ("48", "04")), "Gernika-Bermeo": ("48-05", ("48", "05")),
    "Markina-Ondarroa": ("48-06", ("48", "06")), "Plentzia-Mungia": ("48-07", ("48", "07")),
    "Bajo Bidasoa": ("20-01", ("20", "01")), "Bajo Deba": ("20-02", ("20", "02")), "Alto Deba": ("20-03", ("20", "03")),
    "Donostialdea": ("20-04", ("20", "04")), "Donostia / San Sebastián": ("20-CAP", "20069"),
    "Goierri": ("20-05", ("20", "05")), "Tolosaldea": ("20-06", ("20", "06")), "Urola Costa": ("20-07", ("20", "07")),
}
#: rows the report prints without a label (the label sits in the wrapped header): the row right after this one
UNLABELLED_AFTER = {"Rioja Alavesa": "Estribaciones del Gorbea", "Donostialdea": "Donostia / San Sebastián", "Externo nacional": "Externo internacional"}
STOP = ("CAPV",)


def _dir(cache_dir: Optional[str]) -> Path:
    from pycensus import cache as cache_store

    d = Path(cache_dir or cache_store.default_cache_dir()) / "spain" / "em_capv"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get(url: str, path: Path, min_size: int) -> Path:
    if not path.is_file() or path.stat().st_size < min_size:
        import requests

        r = requests.get(url, timeout=600, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def _row_totals(lines: list, start: int) -> dict:
    """Row label -> last number of the row (the row total), from a matrix's title line to its CAPV row."""
    out, prev = {}, None
    for ln in lines[start + 1: start + 200]:
        nums = re.findall(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})*)(?![\d,])", ln)
        if not nums:
            continue
        label = re.split(r"\s{2,}", ln.strip())[0]
        if re.fullmatch(r"[\d.]+", label):            # a row printed without its label
            label = UNLABELLED_AFTER.get(prev)
            if label is None:
                continue
        if label.startswith(STOP):
            break
        out[label] = float(nums[-1].replace(".", ""))
        prev = label
    return out


def parse(text: str) -> pd.DataFrame:
    """Trips starting in each zone, per mode, from the report text.

    Args:
        text: ``pdftotext -layout`` text of the report.

    Returns:
        One row per zone: ``zone`` (label), ``GEOID`` (zone code), trips per mode (0 where the matrix has no row: no trips sampled).

    Raises:
        RuntimeError: When a matrix or a zone of the all-trips matrix is missing.
    """
    lines = text.split("\n")
    cols = {}
    for t, col in TABLES.items():
        hits = [i for i, ln in enumerate(lines) if re.search(rf"Tabla {t}\. Matriz origen-destino", ln)]
        if len(hits) < 2:
            raise RuntimeError(f"Tabla {t} not found in the EM CAPV 2021 report")
        cols[col] = _row_totals(lines, hits[1])
    miss = [z for z in ZONES if z not in cols["tripsTotal"]]
    if miss:
        raise RuntimeError(f"EM CAPV 2021: zones missing from the all-trips matrix: {miss}")
    rows = [{"zone": z, "GEOID": ZONES[z][0], **{c: cols[c].get(z, 0.0) for c in TABLES.values()}} for z in ZONES]
    return pd.DataFrame(rows)


def table(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Trips by mode per zone (cached as parquet), columns prefixed ``emcapv_``.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per zone.
    """
    d = _dir(cache_dir)
    pq = d / "trips_zone_2021.parquet"
    if pq.is_file():
        return pd.read_parquet(pq)
    pdf = _get(REPORT_URL, d / "Informe_encuesta_telefonia_2021.pdf", 1_000_000)
    t = parse(subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout)
    t = t.rename(columns={c: PREFIX + c for c in TABLES.values()})
    t.to_parquet(pq)
    return t


def load(aoi=None, cache_dir: Optional[str] = None, **_):
    """Trips by mode with the zone polygons: comarcas, the capitals cut out of theirs.

    Args:
        aoi: Area of interest (GeoDataFrame); ``None`` = the whole CAPV.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame (EPSG:4326).
    """
    import geopandas as gpd

    d = _dir(cache_dir)
    com = gpd.read_file(f"zip://{_get(COMARCAS_URL, d / 'COMARCAS_5000_ETRS89.zip', 100_000)}")
    mun = gpd.read_file(f"zip://{_get(MUNICIPIOS_URL, d / 'MUNICIPIOS_5000_ETRS89.zip', 100_000)}")
    caps = {}
    for z, (code, ref) in ZONES.items():
        if isinstance(ref, str):
            hit = mun[mun["EUSTAT"].astype(str) == ref]
            if hit.empty:
                raise RuntimeError(f"capital {ref!r} not found in the municipality polygons")
            caps[code] = hit.union_all()
    geoms = {}
    for z, (code, ref) in ZONES.items():
        if isinstance(ref, str):
            geoms[code] = caps[code]
            continue
        g = com[(com["COM_PROV"] == ref[0]) & (com["COM_COM"] == ref[1])].union_all()
        for cap in caps.values():
            g = g.difference(cap)
        geoms[code] = g
    zones = gpd.GeoDataFrame({"GEOID": list(geoms)}, geometry=list(geoms.values()), crs=com.crs).to_crs(4326)
    res = gpd.GeoDataFrame(zones.merge(table(cache_dir), on="GEOID"), geometry="geometry", crs=4326)
    if aoi is not None:
        res = res[res.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return res


__all__ = ["load", "table", "parse"]
