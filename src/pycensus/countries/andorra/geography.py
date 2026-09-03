"""Boundary fetching shared by every Andorra census source.

Technical aspects:
    Real boundaries come from the Departament d'Estadistica's own hosted
    ArcGIS Server layer ``Parroquies_Pol_codi``
    (:data:`pycensus.andorra.api.PARISH_BOUNDARY_URL`), fetched live and
    verified 2026-08-20: querying it returns exactly 7 polygon features,
    whose ``Nom``/``Codi`` fields match Andorra's 7 real parishes and their
    ISO 3166-2:AD codes one-for-one (see
    :data:`pycensus.andorra.constants.PARISH_CODES`), and whose combined
    longitude/latitude bounds (1.409-1.787 E, 42.429-42.656 N, requested
    reprojected to EPSG:4326 via ``outSR=4326``) land exactly on Andorra's
    known geographic extent.

    Only ``parish`` boundaries are fetched directly. ``nation`` is built by
    dissolving all 7 parish polygons.

    No finer subdivision (``quart``/``veïnat`` -- see
    https://en.wikipedia.org/wiki/Parishes_of_Andorra) has a real, verified
    boundary source: the same ArcGIS Server only exposes country/parish/
    village-point layers (see :mod:`pycensus.andorra.api` module docstring
    for the full layer listing under ``Estadistica/Cartografia_base``).
    Requesting anything other than ``parish``/``nation`` raises
    ``NotImplementedError`` rather than fabricating placeholder geometry.
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from ... import geometry_levels
from . import api, constants

IMPLEMENTED_LEVELS = ("nation", "parish")

GEO_HIERARCHIES = {
    "parish": ["nation", "parish"],
    "nation": ["nation"],
}

ERASE_WATER: dict = {
    "nation": False,
    "parish": False,
}


def _load_parishes() -> gpd.GeoDataFrame:
    """Fetch (no caching beyond the process -- a single tiny 7-row request) real parish polygons."""
    gdf = api.fetch_parish_boundaries()
    if gdf.empty:
        return gpd.GeoDataFrame({"GEOID": []}, geometry=[], crs=4326)
    gdf = gdf.rename(columns={"Codi": "GEOID"})
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    return gdf[["GEOID", "geometry"]]


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2026,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch real boundaries for one Andorra geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.andorra.constants.LEVEL_FALLBACK`. Only
            :data:`IMPLEMENTED_LEVELS` (``nation``, ``parish``) are backed
            by a real source.
        region: A parish name or ISO 3166-2:AD code (see
            :func:`pycensus.andorra.constants.parish_code`). If ``None``,
            returns every geometry at this level.
        year: Accepted for interface parity; the source has no vintage
            dimension (current parish boundaries).
        erase_water: Accepted for interface parity, not implemented.

    Returns:
        GeoDataFrame with a ``GEOID`` column (ISO 3166-2:AD parish code, or
        ``"AD"`` for ``nation``) and geometry, in EPSG:4326.

    Raises:
        NotImplementedError: If ``level`` resolves to a level without a
            real, verified boundary source.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="andorra")

    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"No real boundary source is wired up for Andorra level '{level}'. "
            f"Implemented levels: {IMPLEMENTED_LEVELS}. estadistica.ad's own "
            f"ArcGIS Server (Estadistica/Cartografia_base) exposes only "
            f"nation/parish polygons and a village point layer ('Pobles') -- "
            f"no sub-parish ('quart'/'veinat') polygon layer was found in this "
            f"session. See pycensus.andorra.geography module docstring."
        )

    parishes = _load_parishes()

    if level == "parish":
        if region:
            code = constants.parish_code(region)
            return parishes[parishes["GEOID"] == code].reset_index(drop=True)
        return parishes.reset_index(drop=True)

    if level == "nation":
        if parishes.empty:
            return gpd.GeoDataFrame({"GEOID": []}, geometry=[], crs=4326)
        dissolved = parishes.dissolve()
        dissolved["GEOID"] = "AD"
        return dissolved[["GEOID", "geometry"]].reset_index(drop=True)

    raise AssertionError(f"unreachable: level '{level}' in IMPLEMENTED_LEVELS but not handled")


def load_boundaries_multi(
    level: str,
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2026,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region code(s). If ``None``, returns every region at this
            level (whole country -- both real levels here are a single
            cheap request regardless).
        year: Accepted for interface parity.
        erase_water: Accepted for interface parity, not implemented.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        result = load_boundaries(level, None, year, erase_water)
    else:
        if isinstance(regions, str):
            regions = [regions]
        parts = [load_boundaries(level, r, year, erase_water) for r in regions]
        result = (
            gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
            if parts
            else gpd.GeoDataFrame({"GEOID": []}, geometry=[], crs=4326)
        )

    if aoi is not None and not result.empty:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def parishes_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2026) -> List[str]:
    """Return the ISO 3166-2:AD codes of every parish intersecting ``aoi``.

    Andorra is tiny enough (7 parishes total, one 7-row request) that no
    bounding-box pre-filter is needed before fetching real geometry --
    unlike larger countries' ``states_in_aoi`` helpers.
    """
    parishes = load_boundaries("parish", None, year)
    if parishes.empty:
        return []
    hits = parishes[parishes.intersects(aoi.to_crs(4326).union_all())]
    return hits["GEOID"].tolist()


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2026) -> List[str]:
    """Alias of :func:`parishes_in_aoi`, kept for interface parity with other countries."""
    return parishes_in_aoi(aoi, year)


__all__ = [
    "IMPLEMENTED_LEVELS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "load_boundaries",
    "load_boundaries_multi",
    "parishes_in_aoi",
    "states_in_aoi",
]
