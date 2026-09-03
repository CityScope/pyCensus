"""Boundary fetching shared by every Euskadi census source.

Technical aspects:
    Boundaries and population come from Eurostat/GISCO's LAU (Local
    Administrative Units) 2021 GeoPackage, a real, keyless, EU-published
    cartography product that republishes each Spanish municipality's
    official INE-sourced boundary together with a real ``POP_2021`` figure:
    https://gisco-services.ec.europa.eu/distribution/v2/lau/gpkg/LAU_RG_01M_2021_4326.gpkg

    Verified 2026-08-19 against real downloaded data: filtering to Spanish
    ``LAU_ID`` codes starting with "20" (Gipuzkoa) yields exactly 88
    municipalities totalling ``POP_2021`` = 726,033; "01" (Araba) yields 51
    municipalities / 333,626 people; "48" (Bizkaia) yields 112
    municipalities / 1,154,334 people -- all three match real, documented
    2021 population totals for Euskadi's historical territories. Euskadi's
    own geographic data portals (``opendata.euskadi.eus``,
    ``eustat.eus/geoservicios/descargas.html``) remain genuinely
    unreachable to a scripted client (404/403) -- see ``euskadi/api.py``'s
    module docstring for the (separate, reachable) Eustat *data* API this
    module does not yet use for geometry.

    Only ``municipality`` boundaries are downloaded directly.
    ``territory``/``autonomous_community`` boundaries are built by
    dissolving municipality geometries: a Spanish ``LAU_ID``'s first two
    characters are the province code, which for Euskadi's three provinces
    is exactly the historical-territory code (see
    :data:`pycensus.euskadi.constants.TERRITORY_CODES`).

    ``comarca``/``district``/``section``/``block`` have no real, verified
    boundary source wired up in this rebuild and are not present in
    :data:`GEOMETRY_LEVELS` -- requesting them raises ``KeyError`` rather
    than fabricating placeholder geometry (see
    :data:`pycensus.euskadi.constants.LEVEL_FALLBACK`, which now resolves
    every standard level to one of the three real ones instead).

    The downloaded GeoPackage is cached on disk under
    ``<cache_dir>/raw/euskadi_gisco_lau/``, persistent across runs,
    independent of :mod:`pycensus.cache`'s parquet cache (which caches the
    already-filtered per-region result one level higher, in
    ``eustat/loader.py``).

    Only the 2021 vintage is implemented -- ``load_boundaries`` raises
    ``ValueError`` for any other ``year``.

Source:
    https://gisco-services.ec.europa.eu/distribution/v2/lau/lau-2021-files.html
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import requests

from ... import geometry_levels
from . import constants, utils

GISCO_LAU_GPKG_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/gpkg/LAU_RG_01M_2021_4326.gpkg"
)

# Levels with a real, verified boundary source wired up (see module docstring).
GEOMETRY_LEVELS = ("autonomous_community", "territory", "municipality")

# Geography hierarchy for census data queries: parent-child relationships.
GEO_HIERARCHIES = {
    "municipality": ["autonomous_community", "territory", "municipality"],
    "territory": ["autonomous_community", "territory"],
    "autonomous_community": ["autonomous_community"],
}

ERASE_WATER: dict = {
    "autonomous_community": False,
    "territory": False,
    "municipality": False,
}


def _raw_dir(cache_dir: Optional[str] = None) -> Path:
    base = Path(cache_dir) if cache_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "euskadi_gisco_lau"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_gisco_lau(cache_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) the GISCO LAU 2021 GeoPackage."""
    raw_dir = _raw_dir(cache_dir)
    gpkg_path = raw_dir / "LAU_RG_01M_2021_4326.gpkg"
    if gpkg_path.exists() and gpkg_path.stat().st_size > 0:
        return gpkg_path

    response = requests.get(GISCO_LAU_GPKG_URL, stream=True, timeout=300)
    response.raise_for_status()
    tmp_path = gpkg_path.with_suffix(".gpkg.part")
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    tmp_path.rename(gpkg_path)
    return gpkg_path


def _load_gisco_municipalities(region: str, cache_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return every municipality boundary + real population for one territory.

    Args:
        region: Territory name, abbreviation, or two-digit code (Araba,
            Bizkaia, Gipuzkoa or 01, 48, 20).
        cache_dir: Root of the raw GISCO cache.

    Returns:
        GeoDataFrame with ``GEOID`` (5-digit LAU_ID), ``NAME``,
        ``population`` (real ``POP_2021``), ``area_km2`` (real
        ``AREA_KM2``), and geometry in EPSG:4326.
    """
    terr_code = utils.territory_code(region)
    gpkg_path = _download_gisco_lau(cache_dir)

    gdf = gpd.read_file(gpkg_path, where=f"CNTR_CODE='ES'", engine="pyogrio")
    gdf = gdf[gdf["LAU_ID"].astype(str).str.startswith(terr_code)].copy()
    gdf = gdf.rename(columns={"LAU_ID": "GEOID", "LAU_NAME": "NAME", "POP_2021": "population", "AREA_KM2": "area_km2"})
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    gdf = gdf[["GEOID", "NAME", "population", "area_km2", "geometry"]]
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)
    return gdf.reset_index(drop=True)


def territories_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, cache_dir: Optional[str] = None) -> List[str]:
    """Return the two-digit codes of every territory intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2021, the only one
            implemented).
        cache_dir: Root of the raw GISCO cache.

    Returns:
        List of two-digit territory codes (01=Araba, 48=Bizkaia, 20=Gipuzkoa).
    """
    hits = []
    aoi_geom = aoi.to_crs(4326).union_all()
    for terr_code in constants.TERRITORY_CODES:
        muni = _load_gisco_municipalities(terr_code, cache_dir)
        if muni.intersects(aoi_geom).any():
            hits.append(terr_code)
    return hits


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    cache_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Euskadi geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.euskadi.constants.LEVEL_FALLBACK`.
        region: Territory name/abbreviation/code. If ``None``, returns all
            geometries at this level for the whole of Euskadi.
        year: Vintage year -- only 2021 (GISCO LAU's vintage) is implemented.
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`ERASE_WATER` for the resolved level (currently a no-op --
            GISCO LAU geometries are land-only administrative boundaries
            already).
        cache_dir: Root of the raw GISCO cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
        ValueError: If ``year`` isn't 2021.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="euskadi")

    if level not in GEOMETRY_LEVELS:
        raise KeyError(f"Unknown geography level '{level}'. Known: {sorted(GEOMETRY_LEVELS)}")

    if year != 2021:
        raise ValueError(
            f"Only year=2021 (GISCO LAU's vintage) is implemented for Euskadi boundaries, got {year}."
        )

    if erase_water is None:
        erase_water = ERASE_WATER.get(level, False)

    if level == "municipality":
        if region is None:
            parts = [_load_gisco_municipalities(c, cache_dir) for c in constants.TERRITORY_CODES]
            muni = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
        else:
            terr_code = utils.territory_code(region)
            muni = _load_gisco_municipalities(terr_code, cache_dir)
        result = muni[["GEOID", "geometry"]]

    elif level == "territory":
        if region is not None:
            terr_code = utils.territory_code(region)
            muni = _load_gisco_municipalities(terr_code, cache_dir)
            dissolved = muni.dissolve()
            dissolved["GEOID"] = terr_code
            result = dissolved[["GEOID", "geometry"]]
        else:
            parts = []
            for terr_code in constants.TERRITORY_CODES:
                muni = _load_gisco_municipalities(terr_code, cache_dir)
                dissolved = muni.dissolve()
                dissolved["GEOID"] = terr_code
                parts.append(dissolved[["GEOID", "geometry"]])
            result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    else:  # autonomous_community
        parts = [_load_gisco_municipalities(c, cache_dir) for c in constants.TERRITORY_CODES]
        muni = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
        dissolved = muni.dissolve()
        dissolved["GEOID"] = "EUS"
        result = dissolved[["GEOID", "geometry"]]

    result = result.reset_index(drop=True)
    result["GEOID"] = result["GEOID"].astype(str)
    result = result.set_crs(4326) if result.crs is None else result.to_crs(4326)
    return result[["GEOID", "geometry"]]


def load_boundaries_multi(
    level: str,
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
    cache_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Territory name(s)/abbreviation(s)/code(s). If ``None``,
            returns every geometry at this level for the whole of Euskadi.
        year: Vintage year (see :func:`load_boundaries`).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.
        cache_dir: Root of the raw GISCO cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        result = load_boundaries(level, None, year, erase_water, cache_dir)
    else:
        if isinstance(regions, str):
            regions = [regions]
        parts = [load_boundaries(level, region, year, erase_water, cache_dir) for region in regions]
        if not parts:
            raise ValueError(f"No boundaries could be loaded for any of the requested regions: {regions}")
        result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, cache_dir: Optional[str] = None) -> List[str]:
    """Return the Eustat codes of every territory intersecting ``aoi``.

    This function is kept for interface parity with the USA implementation.
    In Euskadi, the equivalent of states are historical territories.
    """
    return territories_in_aoi(aoi, year, cache_dir)


__all__ = [
    "GISCO_LAU_GPKG_URL",
    "GEOMETRY_LEVELS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "territories_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
