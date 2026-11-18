# -*- coding: utf-8 -*-
"""Guadalajara metro (10 AMG municipalities) election results.

Implemented
-----------
* ``national``: 2024 federal election, President (2024-06-02), INE Cómputos Distritales, one row per casilla acta
  (finest unit; aggregated to electoral *sección*, the smallest published polygon).
  Source: ``https://computos2024.ine.mx/<archivoCorte>.zip`` (name from ``/assets/JSON/PRESIDENTE/NACIONAL/Presidente_NACIONAL_AVANCE.json``,
  e.g. ``20240608_2030_COMPUTOS.zip`` -> ``..._PRES.zip`` -> ``PRES_2024.csv``, '|' separated).
  Geometry: INE SECCION shapefile (``https://pautas.ine.mx/transparencia/mapas/cob_2025/SECCION.zip``, 2025 cut of the marco geoelectoral).
* Coalition columns (e.g. PVEM_PT_MORENA) are summed to the candidate they support: Sheinbaum (MORENA, PT, PVEM), Gálvez (PAN, PRI, PRD),
  Máynez (MC). total_votes = candidate votes + unregistered-candidate write-ins (null votes excluded); turnout = TOTAL_VOTOS_CALCULADOS
  (incl. null) / LISTA_NOMINAL.

NOT implemented (blocked / not published)
-----------------------------------------
* ``state`` (Jalisco Governor 2024) and ``municipal`` (Guadalajara/AMG ayuntamientos 2024): the IEPC Jalisco publishes only PDF
  district actas (https://www2.iepcjalisco.org.mx/proceso-electoral-2024/resultados-gubernatura/); no casilla-level open data was
  found; the PREP host ``prep2024.iepcjalisco.mx`` no longer resolves; ``iepcjalisco.org.mx`` serves an incomplete TLS chain (not bypassed).
"""

from __future__ import annotations

import glob
import io
import logging
import zipfile
from pathlib import Path
from typing import Dict, Optional

import geopandas as gpd
import pandas as pd

from pycensus.elections_common import build_counts, default_elections_cache, download, load_blocs, run_pipeline

logger = logging.getLogger(__name__)
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
COMP = "https://computos2024.ine.mx/20240608_2030_COMPUTOS.zip"
SECC = "https://pautas.ine.mx/transparencia/mapas/cob_2025/SECCION.zip"
ELECTIONS = {"national": dict(year=2024, key="national_2024", name="Federal election 2024, President")}
CAND = {
    "Claudia Sheinbaum Pardo": ["PVEM", "PT", "MORENA", "PVEM_PT_MORENA", "PVEM_PT", "PVEM_MORENA", "PT_MORENA"],
    "Bertha Xochitl Galvez Ruiz": ["PAN", "PRI", "PRD", "PAN_PRI_PRD", "PAN_PRI", "PAN_PRD", "PRI_PRD"],
    "Jorge Alvarez Maynez": ["MC"],
    "Candidato no registrado": ["CANDIDATO/A NO REGISTRADO/A"],
}


def _raw(cache_dir):
    p = default_elections_cache(cache_dir) / "raw" / "mexico"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _casillas(raw: Path) -> pd.DataFrame:
    z = download(COMP, raw / "comp24.zip")
    with zipfile.ZipFile(z) as outer:
        inner = zipfile.ZipFile(io.BytesIO(outer.read("20240608_2030_COMPUTOS_PRES.zip")))
        txt = inner.read("PRES_2024.csv").decode("latin1")
    lines = txt.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith("CLAVE_CASILLA"))
    d = pd.read_csv(io.StringIO("\n".join(lines[i:])), sep="|", dtype=str)
    return d


def _clean(s):
    return s.str.replace('="', "", regex=False).str.replace('"', "", regex=False).str.strip()


def _sections(raw: Path, aoi: Optional[gpd.GeoDataFrame]):
    zp = download(SECC, raw / "seccion2025.zip")
    d = raw / "seccion2025"
    if not d.exists():
        zipfile.ZipFile(zp).extractall(d)
    shp = glob.glob(str(d / "**" / "*.shp"), recursive=True)[0]
    g = gpd.read_file(shp, where="entidad=14").to_crs(4326)
    g["unit"] = "14" + g["seccion"].astype(int).astype(str).str.zfill(4)
    if aoi is not None:
        rep = g.copy()
        rep["geometry"] = rep.representative_point()
        u = aoi.to_crs(4326).union_all()
        g = g[rep.within(u).to_numpy()]
    return g[["unit", "geometry"]]


def _national(raw, blocs, aoi):
    d = _casillas(raw)
    g = _sections(raw, aoi)
    d["unit"] = _clean(d["ID_ENTIDAD"]).str.zfill(2) + _clean(d["SECCION"]).str.zfill(4)
    d = d[d["unit"].isin(set(g["unit"]))]
    num = lambda c: pd.to_numeric(d[c], errors="coerce").fillna(0)
    rows = []
    for cand, cols in CAND.items():
        v = sum(num(c) for c in cols)
        rows.append(pd.DataFrame({"unit": d["unit"], "party": cand, "votes": v}))
    long = pd.concat(rows).groupby(["unit", "party"], as_index=False)["votes"].sum()
    electors = num("LISTA_NOMINAL").groupby(d["unit"]).sum()
    ballots = num("TOTAL_VOTOS_CALCULADOS").groupby(d["unit"]).sum()
    return g, build_counts(long, blocs, electors=electors, ballots=ballots)


def _census(census_geometry):
    if census_geometry is None:
        from pycensus.census.countries.mexico.geography import load_boundaries

        census_geometry = {"ageb": load_boundaries("ageb", "14"), "manzana": load_boundaries("block", "14")}
    return census_geometry


def load_all(scope: str = "national", census_geometry: Optional[Dict[str, gpd.GeoDataFrame]] = None, aoi: Optional[gpd.GeoDataFrame] = None,
             worldpop_path: Optional[str] = None, cache_dir: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """``{"seccion", "h3", "ageb", "manzana"}`` frames. ``aoi``: GeoDataFrame of the study area (e.g. Guadalajara AOI) to select sections.

    ``census_geometry``: ``{"ageb": gdf, "manzana": gdf}`` with GEOID + geometry (INEGI MGN 2020, Jalisco).

    Args:
        scope: Only ``"national"``.
        census_geometry: ``{"ageb", "manzana": polygons}``.
        aoi: Study area.
        worldpop_path: Explicit WorldPop raster.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Raises:
        NotImplementedError: For another scope.
    """
    if scope not in ELECTIONS:
        raise NotImplementedError("Only scope='national' is available for Mexico (state/municipal Jalisco 2024: no casilla-level open data).")
    e = ELECTIONS[scope]
    raw = _raw(cache_dir)
    blocs = load_blocs(BLOCS_PATH, e["key"])
    geom, counts = _national(raw, blocs, aoi)
    return run_pipeline(geom, counts, scope, e["year"], "mex", _census(census_geometry), worldpop_path, unit_label="seccion")


def load(scope: str = "national", level: str = "ageb", **kw) -> pd.DataFrame:
    """Example: ``load("national", level="ageb", aoi=gdf)``; levels ``ageb``, ``manzana``, ``h3``, ``seccion``.

    Args:
        scope: Only ``"national"``.
        level: ``"ageb"``, ``"manzana"``, ``"h3"`` or ``"seccion"``.
        **kw: Passed to :func:`load_all`.

    Returns:
        The frame of that level.
    """
    return load_all(scope, **kw)[level]
