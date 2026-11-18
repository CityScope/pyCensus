"""INE Chile Censo 2024, block-level (manzana-entidad) counts: the finest census geography of Chile.

Source: INE's Censo 2024 cartography (``Cartografia_censo2024_R<region>.zip``, GeoPackage; public Google Cloud bucket ``bktdescargascenso2024``),
whose layers ``Manzanas_CPV24`` (urban blocks) and ``Entidades_CPV24`` (rural entities) carry the 189 aggregated variables of the
"Base manzana-entidad" (persons, households, dwellings; dictionary: ``diccionario_variables_glosas_censo2024.xlsx``). The zip is downloaded once into
``<data_dir>/raw/censo2024/``. Replaces the Censo 2017 "Microdatos Manzana" source (no education, labour, commute or tenure variables).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests

URL = "https://storage.googleapis.com/bktdescargascenso2024/Cartografia/GPKG/Cartografia_censo2024_R{region}.zip"   # INE Censo 2024: block polygons with the 189 aggregated variables
LAYERS = ("Manzanas_CPV24", "Entidades_CPV24")   # urban blocks + rural entities

#: gpkg field -> feature name (global-schema names stay bare in the loader output, the rest get the ``ine_cl_`` prefix).
FIELDS = {
    "n_per": "population", "n_hombres": "malePopulation", "n_mujeres": "femalePopulation",
    "n_edad_0_5": "population0to5", "n_edad_6_13": "population6to13", "n_edad_14_17": "population14to17", "n_edad_18_24": "population18to24",
    "n_edad_25_44": "population25to44", "n_edad_45_59": "population45to59", "n_edad_60_mas": "population60plus",
    "n_inmigrantes": "foreignBornPopulation", "n_pueblos_orig": "minorityEthnicityPopulation",
    "n_religion": "religiousPopulation", "n_discapacidad": "disabledPopulation",
    "n_ocupado": "employedResidents", "n_desocupado": "unemployedResidents", "n_cise_rec_independientes": "selfEmployedResidents",
    "n_transporte_auto": "carCommuters", "n_transporte_publico": "publicTransportCommuters", "n_transporte_camina": "walkCommuters",
    "n_transporte_bicicleta": "bikeCommuters", "n_transporte_motocicleta": "motorcycleCommuters",
    "n_vp": "dwellings", "n_hog": "households", "n_hog_unipersonales": "singlePersonHouseholds",
    "n_tipo_viv_casa": "dwellingsHouse", "n_tipo_viv_depto": "dwellingsApartment", "n_tipo_viv_pieza": "dwellingsTenement", "n_tipo_viv_mediagua": "dwellingsMediagua",
    "n_tipo_viv_movil": "dwellingsMobile", "n_tipo_viv_indigena": "dwellingsIndigenous", "n_tipo_viv_otro": "dwellingsOtherType",
    "prom_escolaridad18": "meanSchoolingYears",
}
#: sums of several fields: feature name -> fields
SUMS = {
    "under18Population": ["n_edad_0_5", "n_edad_6_13", "n_edad_14_17"],
    "educationPrimaryOrLessPopulation": ["n_cine_nunca_curso_primera_infancia", "n_cine_primaria"],
    "educationSecondaryPopulation": ["n_cine_secundaria"],
    "educationUniversityPopulation": ["n_cine_terciaria_maestria_doctorado"],
    "laborForce": ["n_ocupado", "n_desocupado"],
    "ownerHouseholds": ["n_tenencia_propia_pagada", "n_tenencia_propia_pagandose"],
    "renterHouseholds": ["n_tenencia_arrendada_contrato", "n_tenencia_arrendada_sin_contrato"],
    "motorizedCommuters": ["n_transporte_auto", "n_transporte_publico", "n_transporte_motocicleta"],
}


def _raw_dir(data_dir: Optional[str]) -> Path:
    d = get_data_dir("chile", data_dir) / "raw" / "censo2024"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _gpkg(data_dir: Optional[str], region: str = "08") -> Path:
    raw = _raw_dir(data_dir)
    gp = raw / f"Cartografia_censo2024_R{region}.gpkg"
    if gp.exists():
        return gp
    zpath = raw / f"carto_R{region}.zip"
    if not zpath.exists():
        r = requests.get(URL.format(region=region), timeout=900, stream=True)
        r.raise_for_status()
        with open(zpath, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(raw)
    found = list(raw.rglob(gp.name))
    return found[0] if found else gp


def load(aoi: Optional[gpd.GeoDataFrame] = None, data_dir: Optional[str] = None, region: str = "08", **_ignored) -> gpd.GeoDataFrame:
    """Blocks (manzanas) and rural entities intersecting ``aoi`` with the count fields in `FIELDS`/`SUMS` (GEOID = MANZENT code), EPSG:4326.

    Args:
        aoi: Area of interest (GeoDataFrame).
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        region: 2-digit region code.
        **_ignored: Ignored.

    Returns:
        GeoDataFrame (EPSG:4326).
    """
    from pycensus.canonical import global_feature_names

    glob = global_feature_names()
    gp = _gpkg(data_dir, region)
    parts = []
    for layer in LAYERS:
        g = gpd.read_file(gp, layer=layer)
        if aoi is not None:
            a = aoi.to_crs(g.crs)
            g = g[g.intersects(a.union_all())]
        parts.append(g)
    g = pd.concat(parts, ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=parts[0].crs)
    out = pd.DataFrame({"GEOID": g["MANZENT"].astype(str).values})
    num = lambda f: pd.to_numeric(g[f], errors="coerce").to_numpy()
    for field, name in FIELDS.items():
        out[name if name in glob else f"ine_cl_{name}"] = num(field)
    for name, fields in SUMS.items():
        out[name if name in glob else f"ine_cl_{name}"] = sum(pd.Series(num(f)).fillna(0) for f in fields).to_numpy()
    out["adultPopulation" if "adultPopulation" in glob else "ine_cl_adultPopulation"] = out[[c for c in out.columns if c.endswith("population18to24") or c.endswith("population25to44") or c.endswith("population45to59") or c.endswith("population60plus")]].sum(axis=1)
    res = gpd.GeoDataFrame(out, geometry=g.geometry.values, crs=g.crs).to_crs(4326)
    if aoi is not None:
        res = res[res.intersects(aoi.to_crs(4326).union_all())]
    return res.reset_index(drop=True)
