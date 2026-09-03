"""Low-level HTTP client for INE Chile's Division Politico Administrativa y Censal service.

Technical aspects:
    Chile's national statistics agency (INE, Instituto Nacional de
    Estadisticas, https://www.ine.gob.cl/) does not publish a documented
    REST API of its own for census tables (its "Geodatos Abiertos" page --
    https://www.ine.gob.cl/herramientas/portal-de-mapas/geodatos-abiertos
    -- points to bulk shapefile/geodatabase downloads, and REDATAM
    (http://redatam-ine.ine.cl/) is a browse-only web app, not an API).

    What *is* real, live, keyless, and verified (2026-08-20) is INE's own
    Census 2017 "Division Politico Administrativa y Censal" dataset,
    republished as a queryable Esri ArcGIS FeatureServer by Esri Chile
    under a CC BY-SA 4.0 license that explicitly names INE as the data
    source (ArcGIS item id `cae0235c672c4eed808e70c474f5f26b`, license
    text fetched and confirmed to require only attribution, no commercial
    restriction -- unlike the OCUC-republished "Comunas_de_Chile" dataset
    considered and rejected during research for carrying a non-commercial
    clause):

        https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
        Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer

    It has four layers, each with real Census 2017 attribute columns
    (T_POB/T_HOM/T_MUJ = total/male/female population, T_VIV = total
    dwellings) alongside the real DPA geometry and codes:

        0  Regiones   (REGION, NOM_REGION)
        1  Provincias (REGION, PROVINCIA, NOM_PROVIN)
        2  Comunas    (REGION, PROVINCIA, COMUNA, NOM_COMUNA)
        3  Distritos  (REGION, ..., COMUNA, COD_DISTRI, CODIGO_C17)

    Cross-checked against real, independently published figures: Region
    Metropolitana de Santiago T_POB=7,112,808; comuna Santiago
    T_POB=404,495; summing T_POB across all 16 regions gives exactly
    17,574,003 -- Chile's real published Census 2017 national total
    population. Comuna-level codes ("COMUNA": "13101" for Santiago,
    "8101" for Concepcion once zero-padded) match real published DIVIPOLA
    /CUT codes.

    Every query below fetches geometry *and* attributes in a single
    request (`f=geojson`, `outFields=*`), then caches the raw GeoJSON
    response on disk (independent of `pycensus.cache`'s parquet cache).
    `geography.py` reads geometry+GEOID from the cached file;
    `ine/loader.py` reads attribute columns from the very same cached
    file, so a boundary fetch and a data fetch for the same
    level/region never trigger two separate network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import requests

from . import constants

BASE_URL = (
    "https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/"
    "Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer"
)

# ArcGIS layer id, per DPA level.
LAYER_IDS = {
    "region": 0,
    "provincia": 1,
    "comuna": 2,
    "distrito": 3,
}

# Real field names (verified against the live service, see module
# docstring) holding each level's own code.
CODE_FIELDS = {
    "region": "REGION",
    "provincia": "PROVINCIA",
    "comuna": "COMUNA",
    "distrito": "CODIGO_C17",
}

# Zero-padded GEOID width per level, matching real published Chilean CUT/
# DIVIPOLA code lengths (region=2 digits, provincia=3, comuna=5,
# distrito=7 -- comuna's 5 digits plus the 2-digit intra-comuna district
# sequence).
GEOID_WIDTH = {
    "region": 2,
    "provincia": 3,
    "comuna": 5,
    "distrito": 7,
}


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "dpa_censal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def fetch_features(level: str, region: str, data_dir: Optional[str] = None) -> dict:
    """Fetch (once, cached on disk) every real DPA feature for one region's worth of ``level``.

    Args:
        level: One of ``"region"``, ``"provincia"``, ``"comuna"``,
            ``"distrito"``.
        region: Canonical 2-digit region code (see
            :func:`pycensus.chile.utils.region_code`) to scope the query
            to -- every layer carries a real ``REGION`` field, so this
            keeps each request small instead of pulling the whole country.
        data_dir: Base directory for the raw cache. Defaults to
            :data:`pycensus.chile.constants.DEFAULT_DATA_DIR`.

    Returns:
        The raw GeoJSON ``FeatureCollection`` dict as returned by the
        service (real geometry + real attributes, cached verbatim).

    Raises:
        ValueError: If ``level`` isn't one of the four real DPA layers.
    """
    if level not in LAYER_IDS:
        raise ValueError(f"Unknown Chile DPA level: '{level}' -- expected one of {sorted(LAYER_IDS)}")

    from . import utils

    region_2digit = utils.region_code(region)
    raw_dir = _raw_dir(data_dir)
    cache_path = raw_dir / level / f"{region_2digit}.geojson"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        with open(cache_path) as f:
            return json.load(f)

    region_api_value = utils.region_api_code(region)
    layer_id = LAYER_IDS[level]
    url = f"{BASE_URL}/{layer_id}/query"
    params = {
        "where": f"REGION='{region_api_value}'",
        "outFields": "*",
        "f": "geojson",
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "features" not in data:
        raise RuntimeError(
            f"Unexpected response from INE/Esri Chile DPA service for level={level!r} "
            f"region={region!r}: {data!r}"
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".geojson.part")
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    tmp_path.rename(cache_path)

    return data


def build_geoid(level: str, raw_code) -> str:
    """Zero-pad a raw DPA code (as returned by the API, e.g. "8" or "8101") to its real GEOID width."""
    width = GEOID_WIDTH[level]
    return str(raw_code).strip().zfill(width)


__all__ = ["BASE_URL", "LAYER_IDS", "CODE_FIELDS", "GEOID_WIDTH", "fetch_features", "build_geoid"]
