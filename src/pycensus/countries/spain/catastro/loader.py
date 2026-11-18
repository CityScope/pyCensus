"""Catastro buildings aggregated to census sections: building counts, dwellings, floor area and construction-year statistics.

Technical aspects (verified 2026-10-25):
    * STATE Catastro (Direccion General del Catastro), every province EXCEPT 01 Araba, 20 Gipuzkoa, 31 Navarra, 48 Bizkaia (foral cadastres):
      ATOM index ``https://www.catastro.hacienda.gob.es/INSPIRE/Buildings/ES.SDGC.BU.atom.xml`` -> one feed per territorial office
      (``http://www.catastro.hacienda.gob.es/INSPIRE/buildings/<PP>/ES.SDGC.bu.atom_<PP>.xml``) -> one zip per municipality
      (``.../Buildings/<PP>/<MMMMM>-<NAME>/A.ES.SDGC.BU.<MMMMM>.zip``, e.g. Abejar: 0.17 MB; contains ``*.building.gml``, ``*.buildingpart.gml``,
      ``*.otherconstruction.gml``). Updated twice a year, free reuse with attribution (D.G. del Catastro). INSPIRE BU model, EPSG:25830/25829/25828/32628.
      Per building: ``dateOfConstruction/beginning`` (year), ``currentUse`` (1_residential, 2_agriculture, 3_industrial, 4_1_office, 4_2_retail,
      4_3_publicServices), ``numberOfDwellings``, ``numberOfBuildingUnits``, ``value`` (gross floor area m2, ``officialAreaReference`` grossFloorArea).
    * ARABA: ``https://geo.araba.eus/atom/BU/Buildings.atom`` -> ONE zip (EPSG:4258, 11.5 MB) with a GML per municipality (INSPIRE BU, CC BY 4.0;
      Vitoria alone has 24,281 buildings). Year in ``dateOfConstruction/anyPoint``, ``numberOfDwellings``, ``numberOfBuildingUnits``, floors; ``value`` is the
      building HEIGHT in m (not a floor area), no use.
    * NAVARRA: ``https://filescartografia.navarra.es/2_CARTOGRAFIA_TEMATICA/2_7_CATASTRO/2_7_3_INSPIRE_ATOM/2_7_3_2_BU/Buildings_ServiceATOM_Navarra.xml``
      -> one GML zip per municipality (``.../files/BU_Navarra_<n>.gml.zip``, ~0.02 MB for a village; CC BY 4.0, SITNA): ``beginning`` year (1900 is the
      default), dwellings, units, floors, ``value`` = height (m).
    * BIZKAIA: ``https://apli.bizkaia.eus/apps/Danok/INSPIRE/buildings.xml`` (listed in ``atom.xml``) -> one zip per municipality
      (``ES.BFA.BU.<NNN>.zip``, e.g. Amorebieta 0.49 MB; EPSG:4258): construction year in ``dateOfConstruction/end`` (spread 1900-2020, plausible),
      floors and building units; no dwellings, use or floor area.
    * GIPUZKOA: Diputacion Foral B5M open dataset ``https://b5m.gipuzkoa.eus/datasets/GFA_DSET_BU_SHP.zip`` (25 MB, 159,815 polygons, EPSG:25830,
      updated 2026-10): ONLY footprint, average/maximum height, construction date (41 % of buildings) and type (building / other covered structure);
      NO use, dwellings or gross floor area (those columns are NaN there). Open licence, attribution "Gipuzkoako Foru Aldundia".
    * BIZKAIA: ATOM/WFS INSPIRE buildings exist (``https://www.bizkaia.eus/es/inspirebizkaia``) but no download endpoint was verified; not implemented.
Method: each building's centroid is assigned to the census section polygon that contains it (centroids outside every section are dropped).
Raw downloads are cached under ``<data_dir>/raw/catastro/`` (never in git).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from .. import _http

STATE_INDEX = "https://www.catastro.hacienda.gob.es/INSPIRE/Buildings/ES.SDGC.BU.atom.xml"
ARABA_ZIP = "https://geo.araba.eus/deskargak/INSPIRE/BU/GML/4258/BU_4258_GML.zip"
NAVARRA_FEED = "https://filescartografia.navarra.es/2_CARTOGRAFIA_TEMATICA/2_7_CATASTRO/2_7_3_INSPIRE_ATOM/2_7_3_2_BU/Buildings_ServiceATOM_Navarra.xml"
BIZKAIA_FEED = "https://apli.bizkaia.eus/apps/Danok/INSPIRE/buildings.xml"
STATE_PROVINCE_FEED = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{pp}/ES.SDGC.bu.atom_{pp}.xml"
GIPUZKOA_ZIP = "https://b5m.gipuzkoa.eus/datasets/GFA_DSET_BU_SHP.zip"
MIN_YEAR, MAX_YEAR = 1000, 2100

#: pycensus feature names -> (type, unit, definition)
FEATURES = {
    "catastro_buildings": ("count", "buildings", "Buildings (cadastral building footprints, annexes included) whose centroid lies in the section."),
    "catastro_dwellings": ("count", "dwellings", "Dwellings registered in the cadastre (sum of numberOfDwellings). State Catastro, NaN in Gipuzkoa."),
    "catastro_building_units": ("count", "units", "Building units (dwellings, shops, offices, garages...) registered in the cadastre. NaN in Gipuzkoa."),
    "catastro_floor_area_m2_total": ("count", "m2", "Total gross floor area of the buildings (m2, cadastral 'value'). NaN in Gipuzkoa (no floor area published)."),
    "catastro_footprint_m2_total": ("count", "m2", "Total building footprint area (m2) of the buildings of the section."),
    "catastro_year_built_median": ("median", "year", "Median year of construction of the buildings with a known year (1900 is often a catch-all for older buildings)."),
    "catastro_share_built_before_1960": ("share", "fraction", "Fraction of the buildings with a known construction year built before 1960."),
    "catastro_share_built_since_2000": ("share", "fraction", "Fraction of the buildings with a known construction year built in 2000 or later."),
    "catastro_share_built_before_1945": ("share", "fraction", "Fraction of the buildings with a known construction year built before 1945."),
    "catastro_share_built_1945_1969": ("share", "fraction", "Fraction of the buildings with a known construction year built 1945-1969."),
    "catastro_share_built_1970_1999": ("share", "fraction", "Fraction of the buildings with a known construction year built 1970-1999."),
    "catastro_residential_share": ("share", "fraction", "Fraction of the buildings whose current use is residential. NaN in Gipuzkoa (no use published)."),
    "catastro_dwellings_per_building": ("mean", "dwellings", "Mean number of dwellings per residential building. NaN in Gipuzkoa."),
    "catastro_height_mean_m": ("mean", "m", "Mean building height (m): Gipuzkoa (B5M average height), Araba and Navarra (cadastral height); NaN elsewhere."),
    "catastro_floors_mean": ("mean", "floors", "Mean number of floors above ground (Araba, Bizkaia, Navarra and the state Catastro where populated)."),
}
NO_FOLLOW = ("01", "20", "31", "48")


def source_of_province(province: str) -> str:
    """``state`` | ``araba`` | ``navarra`` | ``gipuzkoa`` | ``bizkaia`` (bizkaia: not implemented).

    Args:
        province: 2-digit province code.

    Returns:
        The cadaster source.
    """
    return {"01": "araba", "20": "gipuzkoa", "31": "navarra", "48": "bizkaia"}.get(str(province).zfill(2), "state")


def _cache(data_dir) -> Path:
    return get_data_dir("spain", data_dir) / "raw" / "catastro"


def _get(url: str) -> str:
    r = requests.get(url, headers=_http.BROWSER_HEADERS, timeout=120)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="replace")


def _municipality_zips(province: str) -> list:
    """Zip URLs of a province's municipalities from its ATOM feed (state, Navarra, Bizkaia)."""
    if province == "31":
        return sorted(set(re.findall(r'href="([^"]*BU_Navarra_\d+\.gml\.zip)"', _get(NAVARRA_FEED))))
    if province == "48":
        return sorted(set(re.findall(r'href="([^"]*ES\.BFA\.BU\.\d+\.zip)"', _get(BIZKAIA_FEED))))
    return sorted(set(re.findall(r'href="([^"]*/A\.ES\.SDGC\.BU\.\d{5}\.zip)"', _get(STATE_PROVINCE_FEED.format(pp=province)))))


def _col(g: gpd.GeoDataFrame, name: str, numeric: bool = True) -> pd.Series:
    if name not in g.columns:
        return pd.Series(np.nan if numeric else None, index=g.index, dtype=float if numeric else object)
    return pd.to_numeric(g[name], errors="coerce") if numeric else g[name]


def _year(g: gpd.GeoDataFrame) -> pd.Series:
    """Construction year: first non-null of ``beginning`` (state, Navarra), ``end`` (Bizkaia: dateOfConstruction end), ``anyPoint`` (Araba)."""
    out = pd.Series(np.nan, index=g.index, dtype=float)
    for name in ("beginning", "end", "anyPoint"):
        if name in g.columns:
            y = pd.to_numeric(g[name].astype(str).str[:4], errors="coerce")
            out = out.fillna(y)
    return out


def _frame_from_gdf(g: gpd.GeoDataFrame) -> pd.DataFrame:
    """Normalise one INSPIRE BU layer (state / Araba / Navarra / Bizkaia attribute variants) to the columns used by ``aggregate``."""
    if g.empty:
        return pd.DataFrame()
    if g.crs is None:
        g = g.set_crs(4258)
    metric = g.to_crs(g.estimate_utm_crs()) if g.crs.is_geographic else g
    c = gpd.GeoSeries(metric.geometry.centroid, crs=metric.crs).to_crs(4326)
    uom = g["value_uom"].astype(str) if "value_uom" in g.columns else pd.Series("", index=g.index)
    value = _col(g, "value")
    height = value.where(uom == "m")
    if "heightAboveGround" in g.columns:
        height = height.fillna(_col(g, "heightAboveGround"))
    dwellings = _col(g, "numberOfDwellings")
    use = _col(g, "currentUse", numeric=False)
    if use.isna().all() and dwellings.notna().any():   # no use published (Araba, Navarra): residential = has dwellings
        use = pd.Series(np.where(dwellings > 0, "1_residential", "other"), index=g.index)
    return pd.DataFrame({
        "lon": c.x.to_numpy(), "lat": c.y.to_numpy(), "year": _year(g).to_numpy(float), "use": use.astype(object).where(use.notna(), None).to_numpy(),
        "dwellings": dwellings.to_numpy(float), "units": _col(g, "numberOfBuildingUnits").to_numpy(float),
        "floor_area": value.where(uom == "m2").to_numpy(float), "footprint": metric.geometry.area.to_numpy(float),
        "height": height.to_numpy(float), "floors": _col(g, "numberOfFloorsAboveGround").to_numpy(float),
    })


def _read_inspire_gml(zip_path: Path) -> pd.DataFrame:
    """Buildings of an INSPIRE BU zip (every ``*.gml`` that is not a building part / other construction) as a normalised frame."""
    frames = []
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".gml") and "part" not in n.lower() and "otherconstruction" not in n.lower()]
        for i, n in enumerate(names):
            tmp = zip_path.with_suffix(f".{i}.building.gml")
            tmp.write_bytes(z.read(n))
            try:
                frames.append(_frame_from_gdf(gpd.read_file(tmp)))
            finally:
                tmp.unlink(missing_ok=True)
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _read_gipuzkoa(zip_path: Path) -> pd.DataFrame:
    g = gpd.read_file(f"zip://{zip_path}")
    g = g[g["TYPE_EN"].astype(str).str.lower().str.startswith("edificio")]   # drop "Otra estructura cubierta"
    c = gpd.GeoSeries(g.geometry.centroid, crs=g.crs).to_crs(4326)
    return pd.DataFrame({
        "lon": c.x.to_numpy(), "lat": c.y.to_numpy(), "year": pd.to_numeric(g["DATE_CONST"].astype(str).str[:4], errors="coerce").to_numpy(float),
        "use": None, "dwellings": np.nan, "units": np.nan, "floor_area": np.nan, "footprint": g.geometry.area.to_numpy(float),
        "height": pd.to_numeric(g["AVERAGE_HE"], errors="coerce").to_numpy(float), "floors": np.nan,
    })


def _download_buildings(province: str, data_dir, workers: int = 4) -> pd.DataFrame:
    d = _cache(data_dir)
    src = source_of_province(province)
    if src == "gipuzkoa":
        return _read_gipuzkoa(_http.download(GIPUZKOA_ZIP, d / "gipuzkoa" / "GFA_DSET_BU_SHP.zip"))
    if src == "araba":
        return _read_inspire_gml(_http.download(ARABA_ZIP, d / "araba" / "BU_4258_GML.zip"))
    urls = _municipality_zips(province)   # the cadastre's municipality codes are NOT INE codes (Abejar: 42002 vs INE 42001): whole province, spatial join

    def one(url):
        dest = d / province / url.rsplit("/", 1)[-1]
        for attempt in range(3):
            try:
                return _read_inspire_gml(_http.download(url, dest))
            except Exception:  # noqa: BLE001
                dest.unlink(missing_ok=True)
                time.sleep(2 * (attempt + 1))
        return pd.DataFrame()

    with ThreadPoolExecutor(workers) as ex:
        frames = list(ex.map(one, urls))
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate(buildings: pd.DataFrame, sections: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate a building frame (``lon``/``lat`` centroid + attributes) to the ``GEOID`` polygons of ``sections`` (any CRS).

    Args:
        buildings: Buildings with ``lon`` / ``lat``.
        sections: Census sections (``GEOID`` + polygons).

    Returns:
        One row per section.
    """
    sec = sections[["GEOID", "geometry"]].to_crs(4326)
    cols = list(FEATURES)
    if buildings.empty:
        return pd.DataFrame({"GEOID": sec["GEOID"].astype(str).to_numpy(), **{c: np.nan for c in cols}})
    pts = gpd.GeoDataFrame(buildings, geometry=gpd.points_from_xy(buildings["lon"], buildings["lat"]), crs=4326)
    j = gpd.sjoin(pts, sec, how="inner", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    j["year"] = j["year"].where((j["year"] >= MIN_YEAR) & (j["year"] <= MAX_YEAR))
    j["res"] = (j["use"] == "1_residential").astype(float).where(j["use"].notna() & (j["use"] != "None"))
    g = j.groupby("GEOID")
    known = j[j["year"].notna()].groupby("GEOID")["year"]
    res = j[j["res"] == 1].groupby("GEOID")
    out = pd.DataFrame({
        "catastro_buildings": g.size().astype(float),
        "catastro_dwellings": g["dwellings"].sum(min_count=1),
        "catastro_building_units": g["units"].sum(min_count=1),
        "catastro_floor_area_m2_total": g["floor_area"].sum(min_count=1),
        "catastro_footprint_m2_total": g["footprint"].sum(min_count=1),
        "catastro_year_built_median": known.median(),
        "catastro_share_built_before_1960": known.apply(lambda s: float((s < 1960).mean())),
        "catastro_share_built_since_2000": known.apply(lambda s: float((s >= 2000).mean())),
        "catastro_share_built_before_1945": known.apply(lambda s: float((s < 1945).mean())),
        "catastro_share_built_1945_1969": known.apply(lambda s: float(((s >= 1945) & (s < 1970)).mean())),
        "catastro_share_built_1970_1999": known.apply(lambda s: float(((s >= 1970) & (s < 2000)).mean())),
        "catastro_residential_share": g["res"].mean(),
        "catastro_dwellings_per_building": res["dwellings"].mean(),
        "catastro_height_mean_m": g["height"].mean(),
        "catastro_floors_mean": g["floors"].mean(),
    })
    out = out.reindex(sec["GEOID"].astype(str).unique())
    out["catastro_buildings"] = out["catastro_buildings"].fillna(0.0)   # a section with no building centroid has zero buildings
    out.index.name = "GEOID"
    return out.reset_index()[["GEOID", *cols]]


def load_attributes(province: str, sections: gpd.GeoDataFrame, data_dir: Optional[str] = None) -> pd.DataFrame:
    """``GEOID`` + the ``catastro_*`` columns of ``FEATURES`` for the census ``sections`` (columns ``GEOID`` + polygons) of ONE province.

    Downloads (and caches) every municipality of the province for the state feeds: the cadastre's municipality codes are its own
    (not INE's), so the join to sections is purely spatial.

    Args:
        province: 2-digit province code.
        sections: Census sections of that province.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per section.
    """
    province = str(province).zfill(2)
    return aggregate(_download_buildings(province, data_dir), sections)
