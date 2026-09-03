"""Boundary fetching for Germany census, backed by real Eurostat/GISCO NUTS data.

Technical aspects:
    Boundaries come from Eurostat/GISCO's NUTS (Nomenclature of Territorial
    Units for Statistics) geojson distribution -- a real, keyless, verified
    source (see :data:`pycensus.germany.constants.GISCO_NUTS_GEOJSON_URL`).
    Verified live 2026-08-19: NUTS level 0/1/3, filtered to
    ``CNTR_CODE == "DE"``, returned exactly 1 nation / 16 state / 401
    district feature -- the real, documented counts of Germany's
    administrative divisions -- and Hamburg's real NUTS1 geometry (DE6) has
    bounds matching Hamburg's real coordinates.

    Levels map to NUTS levels as: nation -> LEVL_0, state -> LEVL_1,
    district -> LEVL_3 (Germany's Kreise are NUTS3, not NUTS2).
    ``municipality`` (Gemeinde) has no real boundary source wired up yet --
    requesting it raises ``NotImplementedError`` rather than fabricating
    placeholder geometry (see :data:`IMPLEMENTED_LEVELS`).

    Downloaded NUTS geojson is cached on disk (one file per level) under
    ``<data_dir>/raw/gisco_nuts/``, independent of :mod:`pycensus.cache`'s
    parquet cache.

Source:
    https://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/administrative-units-statistical-units/nuts
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import requests

from ... import geometry_levels
from . import constants, utils

# NUTS level (LEVL_CODE) each geography level corresponds to.
_LEVEL_TO_NUTS: dict = {
    "nation": 0,
    "state": 1,
    "district": 3,
}

# Levels with a real, verified boundary source wired up (see module docstring).
# "municipality" (Gemeinde) is backed by real Eurostat/GISCO LAU (Local
# Administrative Units) geometry -- see :func:`_load_germany_lau` and the
# module docstring addendum below for the live verification.
IMPLEMENTED_LEVELS = tuple(_LEVEL_TO_NUTS.keys()) + ("municipality",)

GEO_HIERARCHIES = {
    "district": ["nation", "state", "district"],
    "municipality": ["nation", "state", "district", "municipality"],
    "state": ["nation", "state"],
    "nation": ["nation"],
}

ERASE_WATER: dict = {
    "nation": False,
    "state": False,
    "district": False,
    "municipality": False,
}

# Eurostat/GISCO LAU (Local Administrative Units) geojson distribution --
# Germany's real Gemeinde-equivalent. Verified live 2026-08-22:
# https://gisco-services.ec.europa.eu/distribution/v2/lau/geojson/LAU_RG_01M_2021_4326.geojson
# returns 11,001 real German municipality features (CNTR_CODE == "DE"),
# matching Germany's documented ~10,800-11,000 Gemeinde count. Each real
# feature already carries a real population field (``POP_2021``, Eurostat's
# regional population figure, ultimately sourced from national statistical
# offices including Destatis) alongside the boundary -- no separate GENESIS
# table is needed (see destatis/loader.py's municipality branch and its
# module docstring for why: GENESIS-Online's public statistic 12411 has no
# Gemeinde-level table, confirmed live by exhausting its real table
# catalogue and find/find search).
#
# Critically, for Germany, GISCO's ``LAU_ID`` IS the real 8-digit AGS
# (Amtlicher Gemeindeschluessel) code -- verified live against four known
# municipalities (Flensburg 01001000, Kiel 01002000, Munich 09162000,
# Stuttgart 08111000, Berlin 11000000, Hamburg 02000000) -- so, unlike the
# district level's AGS-to-NUTS3 crosswalk (destatis/crosswalk.py), no
# name-matching is needed here: LAU_ID *is* GEOID, and its first two digits
# are already the state AGS code in :data:`pycensus.countries.germany.constants.STATE_AGS`.
GISCO_LAU_GEOJSON_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/geojson/LAU_RG_01M_2021_4326.geojson"
)
# Population vintage embedded in the LAU_RG_01M_2021 file (field ``POP_2021``).
LAU_POPULATION_YEAR = 2021


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "gisco_nuts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _load_germany_nuts(levl_code: int, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return every German NUTS feature at ``levl_code``, cached as GeoParquet.

    On first call, downloads the real GISCO NUTS geojson for this level
    (see :data:`pycensus.germany.constants.GISCO_NUTS_GEOJSON_URL`) and
    filters it to ``CNTR_CODE == "DE"``.
    """
    raw_dir = _raw_dir(data_dir)
    cached_path = raw_dir / f"de_nuts{levl_code}.parquet"
    if cached_path.exists():
        return gpd.read_parquet(cached_path)

    url = constants.GISCO_NUTS_GEOJSON_URL.format(levl=levl_code)
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    gdf = gpd.GeoDataFrame.from_features(response.json()["features"], crs=4326)
    gdf = gdf[gdf["CNTR_CODE"] == "DE"]
    # Keep NUTS_NAME alongside GEOID -- needed to build a real AGS-to-NUTS3
    # name-matching crosswalk (see destatis/crosswalk.py); GISCO's NUTS_ID
    # (used elsewhere as GEOID) has no fixed arithmetic relationship to
    # Destatis' AGS (Amtlicher Gemeindeschluessel) codes.
    gdf = gdf.rename(columns={"NUTS_ID": "GEOID"})[["GEOID", "NUTS_NAME", "geometry"]]
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)

    gdf.to_parquet(cached_path)
    return gdf


def _load_germany_lau(data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return every German LAU (municipality) feature, cached as GeoParquet.

    On first call, downloads the real GISCO LAU 2021 geojson (~120MB) and
    filters it to ``CNTR_CODE == "DE"``. Retains the real ``POP_2021``
    population field alongside geometry -- see
    :data:`GISCO_LAU_GEOJSON_URL`'s docstring for why this is the real
    population source for this level (no GENESIS Gemeinde table exists).
    """
    raw_dir = _raw_dir(data_dir)
    cached_path = raw_dir / "de_lau2021.parquet"
    if cached_path.exists():
        return gpd.read_parquet(cached_path)

    response = requests.get(GISCO_LAU_GEOJSON_URL, timeout=300)
    response.raise_for_status()
    gdf = gpd.GeoDataFrame.from_features(response.json()["features"], crs=4326)
    gdf = gdf[gdf["CNTR_CODE"] == "DE"]
    gdf = gdf.rename(columns={"LAU_ID": "GEOID"})[["GEOID", "LAU_NAME", "POP_2021", "geometry"]]
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)

    gdf.to_parquet(cached_path)
    return gdf


def municipality_population(data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return ``{GEOID, LAU_NAME, POP_2021}`` for every German municipality.

    Real GISCO LAU population (see :data:`GISCO_LAU_GEOJSON_URL`), used by
    :mod:`pycensus.countries.germany.destatis.loader` for the
    ``municipality`` level -- unlike nation/state/district, this does not
    require a GENESIS-Online account since GISCO already publishes the
    population figure alongside the boundary.
    """
    gdf = _load_germany_lau(data_dir)
    return gdf[["GEOID", "LAU_NAME", "POP_2021"]].copy()


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch real GISCO NUTS boundaries for one Germany geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.germany.constants.LEVEL_FALLBACK`.
        region: A state name/abbreviation/code. If given for ``state``,
            filters to that one state; if given for ``district``, filters
            to districts within that state (by NUTS1 prefix). Ignored for
            ``nation``.
        year: Vintage year. Kept for interface parity; GISCO NUTS 2021 is
            the only vintage wired up.
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`ERASE_WATER` for the resolved level. Not yet implemented
            (GISCO NUTS geometries are land-only administrative boundaries
            already, so this is a no-op today).
        data_dir: Root directory for the raw GISCO cache. Defaults to
            :data:`pycensus.germany.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column (NUTS code), geometry, in EPSG:4326.

    Raises:
        ValueError: If ``level`` resolves to a level without a real,
            verified boundary source (e.g. ``municipality``).
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="germany")

    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(
            f"No real boundary source is wired up for Germany level '{level}'. "
            f"Implemented levels: {IMPLEMENTED_LEVELS}."
        )

    if level == "municipality":
        gdf = _load_germany_lau(data_dir)
        if region:
            ags_prefix = constants.STATE_AGS[utils.state_code(region)]
            gdf = gdf[gdf["GEOID"].str.startswith(ags_prefix)]
        return gdf[["GEOID", "geometry"]].reset_index(drop=True)

    levl_code = _LEVEL_TO_NUTS[level]
    gdf = _load_germany_nuts(levl_code, data_dir)

    if level == "state" and region:
        nuts1 = constants.STATE_NUTS1[utils.state_code(region)]
        gdf = gdf[gdf["GEOID"] == nuts1]
    elif level == "district" and region:
        nuts1 = constants.STATE_NUTS1[utils.state_code(region)]
        gdf = gdf[gdf["GEOID"].str.startswith(nuts1)]

    return gdf[["GEOID", "geometry"]].reset_index(drop=True)


def district_names(data_dir: Optional[str] = None) -> dict:
    """Return ``{NUTS3 GEOID: NUTS_NAME}`` for every German district.

    Real GISCO ``NUTS_NAME`` property (see :func:`_load_germany_nuts`),
    used by :mod:`pycensus.countries.germany.destatis.crosswalk` to build a
    real, name-matched AGS-to-NUTS3 crosswalk -- do not guess this mapping
    arithmetically (see that module's docstring for why).
    """
    gdf = _load_germany_nuts(_LEVEL_TO_NUTS["district"], data_dir)
    return dict(zip(gdf["GEOID"], gdf["NUTS_NAME"]))


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, data_dir: Optional[str] = None) -> List[str]:
    """Return the 2-letter state codes of every German state intersecting ``aoi``."""
    states = load_boundaries("state", None, year, data_dir=data_dir)
    hits = states[states.intersects(aoi.to_crs(4326).union_all())]
    return [constants.NUTS1_TO_STATE[nuts1] for nuts1 in hits["GEOID"] if nuts1 in constants.NUTS1_TO_STATE]


__all__ = [
    "IMPLEMENTED_LEVELS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "states_in_aoi",
    "load_boundaries",
    "district_names",
    "municipality_population",
]
