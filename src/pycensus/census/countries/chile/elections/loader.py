# -*- coding: utf-8 -*-
"""Gran Concepcion (11 comunas) election results.

Implemented
-----------
* ``national``: Presidential election, second round, 2025-12-14 (Servel *preliminary* results = 100% of mesas counted; official
  escrutinio differs by a few votes), one row per **mesa** with its voting place (``local de votacion``) and registered electors.
  Source: ``https://www.servel.cl/wp-content/uploads/2025/12/Datos_SegundaVotacion.zip`` (PRELIMINARES_PRESIDENTE_DE_LA_REPUBLICA_En_Chile.xlsx).
  total_votes = valid votes (Kast + Jara) + blank; null votes excluded; turnout = (valid + blank + null) / electors.

Geometry (important approximation)
----------------------------------
Servel publishes NO polygons or coordinates for mesas / locales de votacion. Locales are geocoded with OSM Nominatim (name + comuna;
retries with simplified names; cached in ``<cache>/elections/raw/chile/locales_geocoded.json``). The unit "polygon" of a geocoded local is
its Thiessen (Voronoi) cell clipped to its comuna; the votes of all mesas of that local go to that cell. Locales that cannot be
geocoded are pooled per comuna and spread over the comuna's cells proportionally to electors. Thus the H3/census values are a
*catchment approximation* (nearest-local), not true polling boundaries.

NOT implemented (not found as bulk open data)
---------------------------------------------
* ``state`` (Gobernador regional 2024, Biobio, 2024-10-27 / runoff 2024-11-24) and ``municipal`` (Alcalde 2024-10-27): Servel only serves
  them through the SPA elecciones.servel.cl / eleccionesgore.servel.cl (per-mesa pages and acta images) and the old *servel.cl*
  pages that held the files return 404; no CSV/XLSX bulk download was located.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Dict, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

from pycensus.elections_common import POOL, allocate_pools, build_counts, default_elections_cache, download, load_blocs, run_pipeline

logger = logging.getLogger(__name__)
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
URL = "https://www.servel.cl/wp-content/uploads/2025/12/Datos_SegundaVotacion.zip"
XLSX = "Datos_SegundaVotacion/PRELIMINARES_PRESIDENTE_DE_LA_REPUBLICA_En_Chile.xlsx"
ELECTIONS = {"national": dict(year=2025, key="national_2025", name="Presidential election, 2nd round (2025-12-14)")}
COMUNAS = ["CONCEPCION", "TALCAHUANO", "SAN PEDRO DE LA PAZ", "CHIGUAYANTE", "HUALPEN", "CORONEL", "LOTA", "PENCO", "TOME", "HUALQUI", "SANTA JUANA"]
UA = "pycensus-elections-research/1.0 (research use; low volume)"


def _un(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()


def _raw(cache_dir):
    p = default_elections_cache(cache_dir) / "raw" / "chile"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _table(raw: Path) -> pd.DataFrame:
    pq = raw / "seg2025_chile.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    z = download(URL, raw / "seg2025.zip")
    with zipfile.ZipFile(z) as zf:
        d = pd.read_excel(zf.open(XLSX), dtype=str)
    d.to_parquet(pq)
    return d


def _simplify(n: str) -> str:
    n = re.sub(r"\b(BASICA|TECNICO PROFESIONAL|POLIVALENTE|PARTICULAR|SUBVENCIONADO|COMPLEJO EDUCACIONAL|DE ADULTOS)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _geocode(locales: pd.DataFrame, raw: Path, online: bool = True) -> Dict[str, list]:
    import requests

    cache_f = raw / "locales_geocoded.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    for _, r in locales.iterrows():
        k = str(r["cod_local_votacion"])
        if k in cache or not online:
            continue
        hit = None
        for name in (r["local_votacion"], _simplify(_un(r["local_votacion"]))):
            q = f"{name}, {r['comuna'].title()}, Biobio, Chile"
            try:
                j = requests.get("https://nominatim.openstreetmap.org/search", params=dict(q=q, format="json", limit=1, countrycodes="cl"),
                                 headers={"User-Agent": UA}, timeout=15).json()
            except Exception as e:  # network hiccup: leave uncached, retry next call
                logger.warning("geocode failed %s: %s", q, e)
                hit = "ERR"
                break
            time.sleep(1.1)
            if j:
                hit = [float(j[0]["lon"]), float(j[0]["lat"])]
                break
        if hit != "ERR":
            cache[k] = hit
            cache_f.write_text(json.dumps(cache))
    return cache


def _voronoi_cells(pts: gpd.GeoDataFrame, comunas: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Thiessen cell of each geocoded local, clipped to its own comuna polygon (points outside their comuna are dropped)."""
    from shapely.geometry import MultiPoint
    from shapely.ops import voronoi_diagram

    out = []
    for com, grp in pts.groupby("comuna"):
        poly = comunas[comunas["comuna"] == com]
        if poly.empty:
            continue
        pm = poly.to_crs(32718).union_all()
        gm = grp.to_crs(32718)
        gm = gm[gm.within(pm.buffer(300))]
        if gm.empty:
            continue
        if len(gm) == 1:
            out.append(pd.DataFrame({"unit": gm["unit"].values, "geometry": [pm]}))
            continue
        vd = voronoi_diagram(MultiPoint(list(gm.geometry)), envelope=pm.buffer(5000))
        cells = gpd.GeoDataFrame(geometry=list(vd.geoms), crs=32718)
        j = gpd.sjoin(cells, gm[["unit", "geometry"]], predicate="contains")
        j["geometry"] = j.geometry.intersection(pm)
        out.append(j[["unit", "geometry"]])
    g = pd.concat(out)
    return gpd.GeoDataFrame(g, geometry="geometry", crs=32718).to_crs(4326)


def _national(raw, blocs, aoi, geocode=True):
    d = _table(raw)
    d["cu"] = d["comuna"].map(_un)
    d = d[d["cu"].isin(COMUNAS)].copy()
    d["votos"] = pd.to_numeric(d["votos_preliminares"], errors="coerce").fillna(0)
    locales = d.drop_duplicates("cod_local_votacion")[["cod_local_votacion", "local_votacion", "comuna", "cu"]]
    geo = _geocode(locales, raw, online=geocode)
    locales = locales.assign(ll=locales["cod_local_votacion"].astype(str).map(geo))
    ok = locales[locales["ll"].map(lambda v: isinstance(v, list))]
    pts = gpd.GeoDataFrame({"unit": ok["cod_local_votacion"].astype(str).values, "comuna": ok["cu"].values},
                           geometry=gpd.points_from_xy([v[0] for v in ok["ll"]], [v[1] for v in ok["ll"]]), crs=4326)
    if aoi is None or "municipality" not in aoi.columns:   # the study AOI has no comuna column: use the comuna polygons
        from pycensus.census.countries.chile.geography import load_boundaries

        aoi = load_boundaries("comuna", "08")
        names = {"08101": "CONCEPCION", "08102": "CORONEL", "08103": "CHIGUAYANTE", "08105": "HUALQUI", "08106": "LOTA", "08107": "PENCO",
                 "08108": "SAN PEDRO DE LA PAZ", "08109": "SANTA JUANA", "08110": "TALCAHUANO", "08111": "TOME", "08112": "HUALPEN"}   # INE comuna codes
        aoi = aoi.assign(municipality=aoi["GEOID"].astype(str).map(names)).dropna(subset=["municipality"])
    comunas = aoi.assign(comuna=aoi["municipality"].map(_un))
    cells = _voronoi_cells(pts, comunas)
    cu_of = dict(zip(pts["unit"], pts["comuna"]))
    covered = set(cu_of[u] for u in cells["unit"])
    extra = []
    for com in COMUNAS:  # comunas with no geocoded local: the whole comuna is one unit
        poly = comunas[comunas["comuna"] == com]
        if com not in covered and not poly.empty:
            extra.append(gpd.GeoDataFrame({"unit": [f"C:{com}"]}, geometry=[poly.to_crs(4326).union_all()], crs=4326))
            cu_of[f"C:{com}"] = com
    if extra:
        cells = pd.concat([cells] + extra, ignore_index=True)
    have = set(cells["unit"])
    d["unit"] = np.where(d["cod_local_votacion"].astype(str).isin(have), d["cod_local_votacion"].astype(str), POOL + d["cu"])
    # candidate rows
    nm = d["nombre_candidato"].astype(str)
    cand = d[~nm.str.startswith(("Total", "Votos Nulos", "Votos en Blanco"))]
    long = cand.groupby(["unit", "nombre_candidato"], as_index=False)["votos"].sum().rename(columns={"nombre_candidato": "party", "votos": "votes"})
    blank = d[nm == "Votos en Blanco"].groupby("unit")["votos"].sum().rename("blank")
    nulos = d[nm == "Votos Nulos"].groupby("unit")["votos"].sum()
    mesas = d.drop_duplicates("cod_mesa")
    electors = pd.to_numeric(mesas["electores"], errors="coerce").groupby(mesas["unit"]).sum()
    c = build_counts(long, blocs, blank=blank, electors=electors)
    c["ballots"] = c["total_votes"] + nulos.reindex(c.index).fillna(0)
    ug = pd.Series(cells["unit"].map(cu_of).to_numpy(), index=cells["unit"].to_numpy())
    w = c["electors"].fillna(0).where(~c.index.str.startswith(POOL), 0)
    allu = pd.Index(cells["unit"].unique())
    missing = allu.difference(c.index)
    if len(missing):
        c = pd.concat([c, pd.DataFrame(0.0, index=missing, columns=c.columns)])
    w = c["electors"].fillna(0).where(~c.index.str.startswith(POOL), 0)
    c = allocate_pools(c, ug, w, spread_electors=True)
    return cells, c


def _census(census_geometry, aoi):
    if census_geometry is None:
        from pycensus.census.countries.chile.ine import manzana

        mz = manzana.load(aoi=aoi)
        mz = mz[["GEOID", "geometry"]]
        zo = mz.assign(GEOID=mz["GEOID"].astype(str).str[:-3]).dissolve(by="GEOID", as_index=False)
        census_geometry = {"manzana": mz, "zona": zo}
    return census_geometry


def load_all(scope: str = "national", census_geometry: Optional[Dict[str, gpd.GeoDataFrame]] = None, aoi: Optional[gpd.GeoDataFrame] = None,
             worldpop_path: Optional[str] = None, cache_dir: Optional[str] = None, geocode: bool = True) -> Dict[str, pd.DataFrame]:
    """``{"local", "h3", "manzana", "zona"}`` frames. ``aoi``: GeoDataFrame with a ``municipality`` column (comuna polygons).

    Args:
        scope: Only ``"national"``.
        census_geometry: ``{level: polygons}``.
        aoi: Comuna polygons (``municipality`` column).
        worldpop_path: Explicit WorldPop raster.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        geocode: Geocode the polling places.

    Raises:
        NotImplementedError: For another scope.
    """
    if scope not in ELECTIONS:
        raise NotImplementedError("Only scope='national' is available for Chile (regional/municipal 2024: no bulk mesa-level download found).")
    e = ELECTIONS[scope]
    raw = _raw(cache_dir)
    blocs = load_blocs(BLOCS_PATH, e["key"])
    geom, counts = _national(raw, blocs, aoi, geocode)
    return run_pipeline(geom, counts, scope, e["year"], "chl", _census(census_geometry, aoi), worldpop_path, unit_label="local")


def load(scope: str = "national", level: str = "manzana", **kw) -> pd.DataFrame:
    """Example: ``load("national", level="manzana", aoi=gdf)``; levels ``manzana``, ``zona``, ``h3``, ``local``.

    Args:
        scope: Only ``"national"``.
        level: ``"manzana"``, ``"zona"``, ``"h3"`` or ``"local"``.
        **kw: Passed to :func:`load_all`.

    Returns:
        The frame of that level.
    """
    return load_all(scope, **kw)[level]
