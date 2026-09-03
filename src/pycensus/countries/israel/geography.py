"""Boundary fetching shared by every Israel census source.

Technical aspects:
    Real boundaries, no fabrication. Two live, unauthenticated ArcGIS
    endpoints are used (verified 2026-08-19/2026-08-20, see
    :mod:`pycensus.israel.constants` for exact URLs and field
    cross-checks):

    - CBS's own hosted ArcGIS Online layer (``STAT_AREAS_2022_URL``) for
      statistical-area polygons.
    - The Israel Planning Administration's (iplan.gov.il) ArcGIS Server
      layer (``IPLAN_JURISDICTION_URL``) for municipal jurisdiction
      (locality) polygons, which ``district``/``nation`` are built by
      dissolving.

    ``IMPLEMENTED_LEVELS`` is only ``nation``/``district``/``locality``/
    ``statistical_area`` -- ``subdistrict``/``street``/``block`` have no
    verified real boundary source and raise ``ValueError`` rather than
    fabricate placeholder polygons (the old module's
    ``np.random.seed(hash(region))`` fabrication is gone).

    West Bank exclusion: both real sources were queried live for a known
    West Bank settlement (Ariel) and returned zero features from either --
    neither ever exposes West Bank geometry/attributes. ``Machoz`` values
    in :data:`pycensus.israel.constants.EXCLUDED_MACHOZ` are still
    filtered out defensively.

    Open caveat (not resolved): the iplan ``Machoz`` field's "Northern"
    (``צפון``) district, as Israel administers it, includes the Golan
    Heights -- also not internationally recognized as sovereign Israeli
    territory, same category as the West Bank. No verified
    locality-level Golan/non-Golan classification was found to filter it
    out, so ``level="district"`` region ``"1"``/``"Northern"`` and
    ``level="nation"`` currently include Golan Heights polygon area.
    ``locality``/``statistical_area`` results for any specific non-Golan
    locality (e.g. Beersheba) are unaffected.

    Every boundary fetch here is stateless - persistence is handled
    entirely by :mod:`pycensus.cache`, one level higher in the call stack
    (in each source's ``loader.py``), not by this module.

Source:
    https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/gvulot_retzef/MapServer/1
    https://services8.arcgis.com/JcXY3lLZni6BK4El/arcgis/rest/services/statistical_areas_2022/FeatureServer/0
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from ... import geometry_levels
from . import arcgis, constants, utils

# Levels with a real, verified boundary source wired up (see module docstring).
IMPLEMENTED_LEVELS = ("nation", "district", "locality", "statistical_area")

# Geography hierarchy for census data queries.
GEO_HIERARCHIES = {
    "statistical_area": ["nation", "district", "locality", "statistical_area"],
    "locality": ["nation", "district", "locality"],
    "district": ["nation", "district"],
    "nation": ["nation"],
}

# Whether to erase water by default for each level.
ERASE_WATER: dict = {
    "nation": False,
    "district": False,
    "locality": False,
    "statistical_area": True,
}


def _fetch_localities(where: str) -> gpd.GeoDataFrame:
    """Real jurisdiction-polygon query against IPLAN_JURISDICTION_URL.

    Returns a GeoDataFrame with ``CR_LAMAS``, ``Muni_Eng``, ``Machoz`` and
    geometry -- West-Bank-flagged ``Machoz`` values already filtered out
    (see :data:`pycensus.israel.constants.EXCLUDED_MACHOZ`).
    """
    features = arcgis.query_features(
        constants.IPLAN_JURISDICTION_URL,
        where=where,
        out_fields="CR_LAMAS,Muni_Eng,Machoz",
        return_geometry=True,
    )
    features = [
        f for f in features if f["attributes"].get("Machoz") not in constants.EXCLUDED_MACHOZ
    ]
    gdf = arcgis.features_to_geodataframe(features)
    if gdf.empty or "geometry" not in gdf.columns:
        gdf = gpd.GeoDataFrame({"CR_LAMAS": [], "Muni_Eng": [], "Machoz": []}, geometry=[], crs=4326)
    return gdf


def _empty_boundaries() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"GEOID": []}, geometry=gpd.GeoSeries([], crs=4326), crs=4326)


def _load_locality_boundaries(region: Optional[str]) -> gpd.GeoDataFrame:
    if region is not None:
        code = utils.locality_code(region)
        where = f"CR_LAMAS = '{code}'"
    else:
        where = "1=1"

    gdf = _fetch_localities(where)
    if gdf.empty:
        return _empty_boundaries()

    gdf["GEOID"] = gdf["CR_LAMAS"].astype(str)
    return gdf[["GEOID", "geometry"]]


def _load_statistical_area_boundaries(region: Optional[str]) -> gpd.GeoDataFrame:
    if region is not None:
        code = utils.locality_code(region)
        where = f"SEMEL_YISHUV = {int(code)}"
    else:
        where = "1=1"

    features = arcgis.query_features(
        constants.STAT_AREAS_2022_URL,
        where=where,
        out_fields="YISHUV_STAT_2022,SEMEL_YISHUV",
        return_geometry=True,
    )
    gdf = arcgis.features_to_geodataframe(features)
    if gdf.empty or "geometry" not in gdf.columns:
        return _empty_boundaries()

    gdf["GEOID"] = gdf["YISHUV_STAT_2022"].astype(str)
    return gdf[["GEOID", "geometry"]]


def _load_district_boundaries(region: Optional[str]) -> gpd.GeoDataFrame:
    if region is not None:
        dist_code = utils.district_code(region)
        machoz_names = [
            heb for heb, code in constants.MACHOZ_TO_DISTRICT_CODE.items() if code == dist_code
        ]
        if not machoz_names:
            return _empty_boundaries()
        gdf = _fetch_localities(f"Machoz = '{machoz_names[0]}'")
        if gdf.empty:
            return _empty_boundaries()
        return gpd.GeoDataFrame(
            {"GEOID": [dist_code]}, geometry=[gdf.union_all()], crs=4326
        )

    # All districts: one query per real Machoz value (avoids the
    # unchunked whole-country query the iplan MapServer 500s on).
    codes, geoms = [], []
    for heb, code in constants.MACHOZ_TO_DISTRICT_CODE.items():
        gdf = _fetch_localities(f"Machoz = '{heb}'")
        if gdf.empty:
            continue
        codes.append(code)
        geoms.append(gdf.union_all())

    if not codes:
        return _empty_boundaries()
    return gpd.GeoDataFrame({"GEOID": codes}, geometry=geoms, crs=4326)


def _load_nation_boundaries() -> gpd.GeoDataFrame:
    gdf = _fetch_localities("1=1")
    if gdf.empty:
        return _empty_boundaries()
    return gpd.GeoDataFrame({"GEOID": ["ISR"]}, geometry=[gdf.union_all()], crs=4326)


def _districts_by_bbox(aoi: gpd.GeoDataFrame) -> List[str]:
    """Cheap bounding-box pre-filter: which district codes' hand-set bbox overlaps ``aoi``'s bbox.

    Avoids ever issuing an unchunked whole-country query against the
    iplan jurisdiction MapServer, which 500s/times out on ~1,300+
    localities at once (see constants.DISTRICT_BBOX's docstring).
    """
    minx, miny, maxx, maxy = aoi.to_crs(4326).total_bounds
    hits = []
    for code, (dminx, dminy, dmaxx, dmaxy) in constants.DISTRICT_BBOX.items():
        if minx <= dmaxx and maxx >= dminx and miny <= dmaxy and maxy >= dminy:
            hits.append(code)
    return hits


def districts_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2022) -> List[str]:
    """Return the CBS codes of every district intersecting ``aoi``.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2022, only vintage available).

    Returns:
        List of one-digit district codes.
    """
    codes = []
    for dist_code in _districts_by_bbox(aoi):
        machoz_names = [
            heb for heb, c in constants.MACHOZ_TO_DISTRICT_CODE.items() if c == dist_code
        ]
        if not machoz_names:
            continue
        gdf = _fetch_localities(f"Machoz = '{machoz_names[0]}'")
        if not gdf.empty and gdf.intersects(aoi.to_crs(4326).union_all()).any():
            codes.append(dist_code)
    return sorted(codes)


def localities_in_aoi(aoi: gpd.GeoDataFrame) -> List[str]:
    """Return the ``CR_LAMAS`` codes of every locality intersecting ``aoi``.

    Chunks the real jurisdiction-layer query per-district (using a cheap
    bbox pre-filter, :func:`_districts_by_bbox`) rather than issuing one
    unchunked whole-country query, which the iplan MapServer 500s/times
    out on (see module docstring).

    Args:
        aoi: Area of interest, any CRS.

    Returns:
        List of locality codes (``GEOID``s) intersecting ``aoi``.
    """
    aoi_geom = aoi.to_crs(4326).union_all()
    codes: List[str] = []
    for dist_code in _districts_by_bbox(aoi):
        machoz_names = [
            heb for heb, c in constants.MACHOZ_TO_DISTRICT_CODE.items() if c == dist_code
        ]
        if not machoz_names:
            continue
        gdf = _fetch_localities(f"Machoz = '{machoz_names[0]}'")
        if gdf.empty:
            continue
        hit = gdf[gdf.intersects(aoi_geom)]
        codes.extend(str(c).strip() for c in hit["CR_LAMAS"] if str(c).strip())
    return codes


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2022,
    erase_water: Optional[bool] = None,
) -> gpd.GeoDataFrame:
    """Fetch real boundaries for one Israel geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.israel.constants.LEVEL_FALLBACK`.
        region: Region code (district code, locality code/name, etc).
            If None, returns all geometries at this level for the entire
            country/level (may be slow -- see module docstring on
            pagination).
        year: Vintage year (default 2022, only vintage available).
        erase_water: Unused (kept for interface parity) -- no verified
            inland-water-erasure source is wired up here.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        ValueError: If ``level`` doesn't resolve to something in
            :data:`IMPLEMENTED_LEVELS`.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="israel")

    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(
            f"No real, verified boundary source for Israel level '{level}' -- only "
            f"{IMPLEMENTED_LEVELS} are implemented (see pycensus.israel.geography module "
            f"docstring for what was checked and not found)."
        )

    if level == "locality":
        return _load_locality_boundaries(region)
    if level == "statistical_area":
        return _load_statistical_area_boundaries(region)
    if level == "district":
        return _load_district_boundaries(region)
    return _load_nation_boundaries()


def load_boundaries_multi(
    level: str,
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2022,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region code(s). If None, returns every region at this level.
        year: Vintage year (default 2022).
        erase_water: Unused, kept for interface parity.
        aoi: If given, the result is filtered to geometries intersecting it.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        return load_boundaries(level, None, year, erase_water)
    if isinstance(regions, str):
        regions = [regions]

    parts = []
    for region in regions:
        gdf = load_boundaries(level, region, year, erase_water)
        if not gdf.empty:
            parts.append(gdf)

    if not parts:
        raise ValueError(f"No boundaries could be loaded for any of the requested regions: {regions}")

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2022) -> List[str]:
    """Return the CBS codes of every district intersecting ``aoi``.

    Kept for naming parity with other pyCensus countries -- Israel's
    equivalent of "states" is districts.

    Args:
        aoi: Area of interest, any CRS.
        year: Geographic data vintage year (default 2022).

    Returns:
        List of one-digit district codes.
    """
    return districts_in_aoi(aoi, year)


__all__ = [
    "IMPLEMENTED_LEVELS",
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "districts_in_aoi",
    "localities_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
