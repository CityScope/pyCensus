"""Boundary fetching shared by every Chile census source.

Technical aspects:
    Boundaries (and, in the same response, real Census 2017 attribute
    columns) come from the verified ArcGIS FeatureServer described in
    :mod:`pycensus.chile.api`'s module docstring. Real boundaries are
    implemented for all four of that service's layers: ``region``,
    ``provincia``, ``comuna``, ``distrito`` -- every one of them was
    fetched live, inspected, and cross-checked (see api.py docstring for
    the real population totals confirmed).

    ``nation`` and ``block`` are not implemented: no single verified
    national-outline feature/endpoint was found on this service (each
    query is scoped to one level's polygons, not a national union), and
    Chile's DPA service has no unit finer than distrito censal (no manzana
    /block layer). Requesting either raises ``NotImplementedError`` here.

    Re-investigated 2026-08-22 (see task history): a candidate manzana
    (city-block) source exists --
    ``https://services9.arcgis.com/kKJR3Qt68ohAWuet/arcgis/rest/services/
    Manzanas_censo_2017/FeatureServer/0`` (Observatorio de Ciudades UC,
    "Distribucion de la Poblacion por Manzana en Chile segun Censo 2017").
    Live-querying it explained *part* of the original ~3% comuna-total
    discrepancy that got manzana rejected: it returns duplicate features
    per ``MANZENT_I`` (e.g. Providencia returns 643 features for only 622
    distinct manzana ids, Santiago 1334 for 1290) -- a real double-counting
    bug in the source, not a bug in pyCensus's own aggregation. Deduping by
    ``MANZENT_I`` (keep first) closes most of the gap for dense urban
    comunas: Providencia 146,467 raw -> 141,986 deduped vs. real 142,079
    (-0.07%); Santiago 415,611 raw -> 402,847 deduped vs. real 404,495
    (-0.41%). But deduped totals for Gran Concepcion's own comunas (the
    live study area) still miss by more than that even though most of
    them are >85% urban: Concepcion -2.70%, Talcahuano -1.42%, Penco
    -2.08%, Coronel -5.09%, Tome -10.45%, Hualqui -14.34% (T_POB from the
    verified DPA comuna layer used as ground truth). Smaller/more rural
    Region Metropolitana comunas fare far worse post-dedup (Alhue -58%,
    San Pedro -100% -- effectively no manzana coverage at all). So beyond
    the fixable duplicate-id bug, this manzana layer has real, unexplained
    coverage gaps that don't correlate cleanly with rural population share
    -- consistent with genuinely incomplete/stale manzana polygons, not
    just a fixable overlap bug. Net match rate is nowhere near the >99%
    bar Mexico's block level cleared, including for Gran Concepcion's own
    comunas, so manzana/block stays rejected and unimplemented here. Do
    not re-wire it without re-verifying against fresh live totals across
    many comunas again.

    Re-investigated again 2026-08-22 (second pass, chasing two leads: INE's
    own geoportal, and SII/MINVU independent cadastral geodata):

    Lead 1 (INE's own official publication, not the OCUC mirror): INE
    itself does not run a live, publicly-fetchable ArcGIS/WFS endpoint from
    this environment -- ``geografia.ine.cl`` (found via web search, e.g.
    ``.../server/rest/services/Censo2017/Limites_INE_C2017/MapServer``)
    reset the TLS connection on every attempt (curl and WebFetch alike), so
    it could not be verified live. However, a second, genuinely distinct
    republication of INE's real manzana microdata *was* found and
    verified: Esri Chile's own "Microdatos Censo 2017" FeatureServer
    (ArcGIS item ``3d6337a57d5b433594512d0724e725fa``, tagged ``INE``
    directly, hosted on the same ``r7t1P5pnkoOLRdhr`` org as the
    already-implemented comuna/distrito service) --
    ``https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
    Microdatos_Censo_2017/FeatureServer/0`` (layer 0, "Microdatos Manzana -
    Urbano"). This is a different publisher/org from the rejected OCUC
    (Observatorio de Ciudades UC) source, has no duplicate-feature bug (one
    row per ``MANZENT``), and yet summing its real ``TOTAL_PERS`` column
    for Gran Concepcion's own comunas -- live-queried, cross-checked
    against the same verified DPA comuna ``T_POB_U`` used above --
    reproduces the *exact same* coverage gaps as the rejected OCUC dataset:
    Concepcion -2.70%, Talcahuano -1.42%, Coronel -5.09%, Tome -10.45%,
    Hualqui -14.34%, Penco -2.08%. Identical percentages from an
    independent republisher confirm these gaps are inherent to INE's
    underlying manzana microdata table itself (missing/incomplete manzana
    records in the real Census 2017 database), not an artifact of one
    mirror's processing. Manzana stays rejected on stronger evidence now:
    two independent publishers of the same INE source data both show it.
    No separate, independently-populated "zona censal" (intermediate)
    layer was found anywhere -- every zona-labeled dataset located (e.g.
    OCUC's "Zonas Censales de la Region Metropolitana 2017") only carries
    geometry with population derived by summing the same manzana table, so
    it would inherit the identical gaps and was not separately verified.

    Lead 2 (SII/MINVU independent cadastral geodata): not pursued past a
    light search -- Lead 1 already reached a firm, well-evidenced answer,
    and SII/MINVU parcel data would need a real methodology for joining
    non-census cadastral geometry to census population attributes (out of
    scope for a single follow-up pass). MINVU does publish regional viewer
    services (e.g. ``Visor_Pro_Informacion_MINVU_y_Base``, SEREMI/SERVIU
    Biobio orgs) but these were not opened -- flagged here as a genuine
    unexplored longer shot, not a checked-and-rejected one, for a future
    pass.

Source:
    https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
    Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer
"""

from __future__ import annotations

from typing import List, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from ... import geometry_levels
from . import api, constants, utils

# Levels with a real, verified boundary source wired up (see module docstring).
IMPLEMENTED_LEVELS = ("region", "provincia", "comuna", "distrito")


def regions_in_aoi(aoi: gpd.GeoDataFrame) -> List[str]:
    """Return the canonical 2-digit region codes that plausibly intersect ``aoi``.

    Note:
        No cheap national region-index endpoint was found to test against
        precisely (only the per-level ArcGIS queries in
        :mod:`pycensus.chile.api`), so -- same pattern as
        ``mexico.geography.states_in_aoi`` -- this does a bounding-box test
        against :data:`pycensus.chile.constants.REGION_BBOX`, padded by
        :data:`pycensus.chile.constants.REGION_BBOX_PADDING_DEG` to stay
        safely over-inclusive.
    """
    aoi_union = aoi.to_crs(4326).union_all()
    minx, miny, maxx, maxy = aoi_union.bounds
    pad = constants.REGION_BBOX_PADDING_DEG

    matches = []
    for code, (bx0, by0, bx1, by1) in constants.REGION_BBOX.items():
        if minx <= bx1 + pad and maxx >= bx0 - pad and miny <= by1 + pad and maxy >= by0 - pad:
            matches.append(code)
    return matches


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2017,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch real DPA boundaries for one Chile geography level, scoped to one region.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.chile.constants.LEVEL_FALLBACK`. Only
            ``"region"``, ``"provincia"``, ``"comuna"``, ``"distrito"`` are
            implemented (see :data:`IMPLEMENTED_LEVELS`).
        region: Region name or code. Required -- the ArcGIS service is
            queried per-region to keep each request small (see
            :mod:`pycensus.chile.api` module docstring).
        year: Vintage year. Only 2017 (the Census 2017 DPA vintage this
            service publishes) is wired up; other values are accepted but
            ignored.
        data_dir: Base directory for the raw GeoJSON cache. Defaults to
            :data:`pycensus.chile.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column and geometry, reprojected to
        EPSG:4326.

    Raises:
        ValueError: If ``region`` is not given, or ``level`` resolves to a
            level with no implemented boundary source.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="chile")

    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"Chile boundaries for level '{level}' are not implemented yet -- only "
            f"{IMPLEMENTED_LEVELS} are wired to the verified INE/Esri Chile DPA service. "
            f"See pycensus.chile.geography module docstring for why 'nation'/'block' "
            f"are excluded."
        )

    if not region:
        raise ValueError("'region' is required: the DPA service is queried per region")

    raw = api.fetch_features(level, region, data_dir)
    code_field = api.CODE_FIELDS[level]

    geoids = []
    geoms = []
    for feature in raw["features"]:
        props = feature["properties"]
        geoids.append(api.build_geoid(level, props[code_field]))
        geoms.append(shape(feature["geometry"]))

    gdf = gpd.GeoDataFrame({"GEOID": geoids}, geometry=geoms, crs=4326)
    return gdf


def load_boundaries_multi(
    level: str,
    regions: Optional[List[str]] = None,
    year: int = 2017,
    aoi: Optional[gpd.GeoDataFrame] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region name(s)/code(s). If ``None``, uses every region (16
            downloads).
        year: Vintage year (see :func:`load_boundaries`).
        aoi: If given, the result is filtered to geometries intersecting it.
        data_dir: Base directory for the raw GeoJSON cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        regions = list(constants.REGION_NAMES.keys())
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = [utils.region_code(r) for r in regions]
    parts = [load_boundaries(level, rc, year, data_dir) for rc in region_codes]

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


__all__ = [
    "IMPLEMENTED_LEVELS",
    "regions_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
]
