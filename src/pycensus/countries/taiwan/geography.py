"""Boundary fetching shared by every Taiwan census source.

Technical aspects:
    Taiwan's own National Land Surveying and Mapping Center (NLSC) publishes
    real, cataloged county/city and township/district boundary datasets
    (https://data.gov.tw/dataset/7442, /7441 -- real catalog entries, real
    field names ``COUNTYID``/``COUNTYCODE``/``COUNTYNAME``/``COUNTYENG``),
    but the actual download files are served from a TGOS host
    (``www.tgos.tw``) that returns HTTP 403 to every plain HTTP client
    (verified 2026-08-20, with and without a browser User-Agent/Referer, via
    both curl and wget) -- a real, confirmed dead end, not an assumption.

    ``county_city`` (the only level implemented here) instead uses
    geoBoundaries.org's Taiwan ADM1 layer
    (:data:`pycensus.taiwan.constants.GEOBOUNDARIES_TWN_ADM1_URL`): a real,
    keyless, single-file GeoJSON download (~3.2MB, all 22 counties/cities in
    one request, verified 2026-08-20 -- feature count, names, and ISO 3166-2
    codes all cross-checked against
    :data:`pycensus.taiwan.constants.COUNTY_CODES`, see
    :data:`pycensus.taiwan.constants.GEOBOUNDARIES_ISO_TO_COUNTY_CODE`).
    This is NOT an official NLSC file -- geoBoundaries' own catalog entry
    for Taiwan says ``"boundarySource": "OpenStreetMap, Wambacher"`` -- but
    it is real, verifiable, actively-maintained geometry, used here as the
    practical alternative until TGOS's download gate is beaten (browser
    automation, or a stable mirror of the actual NLSC file).

    ``district`` (townships/districts) uses geoBoundaries' Taiwan ADM2
    layer (:data:`pycensus.taiwan.constants.GEOBOUNDARIES_TWN_ADM2_URL`): a
    real, keyless, single-file GeoJSON download (~10.5MB, 368 features,
    verified 2026-08-20, same OpenStreetMap/Wambacher source as ADM1). Its
    features carry no MOI-compatible code field, so each one was matched
    to MOI RIS's 8-digit ``district_code`` prefix by spatial join (county
    disambiguation) plus Chinese/Hanyu-Pinyin/Tongyong-Pinyin name matching
    -- see :data:`pycensus.taiwan.constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE`
    for the full derivation and verification method. All 368 ADM2 features
    matched to all 368 MOI districts (1:1, nothing left over/guessed).

    ``village`` (村里/li, finer than district) uses OpenStreetMap's Overpass
    API: every ``admin_level=9``/``boundary=administrative`` relation inside
    a county/city's OSM area carries a ``nat_ref`` tag that IS MOI's own
    11-digit ``district_code`` directly -- no name/pinyin matching needed,
    unlike ``district``'s ADM2 join. Verified live 2026-08-22: Taipei City
    ("63000") returns exactly 456 such relations, and that set of 456
    ``nat_ref``s is an *exact* match (zero missing, zero extra) against the
    456 unique village ``district_code``s in MOI RIS's live
    ODRP013/11407 response for Taipei -- see
    :data:`pycensus.taiwan.constants.OVERPASS_API_URL` docstring for the
    full verification (including New Taipei City's close-but-not-exact
    1032/1039 match). :func:`load_boundaries` verifies this match itself,
    live, on every fetch for a given county -- it raises loudly rather than
    silently returning an unverified geometry set (see
    :func:`_download_village_geojson`).

    Real population data (:mod:`pycensus.taiwan.moi.loader`) is available
    and verified independently of this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import requests
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from . import constants

GEO_HIERARCHIES = {
    "village": ["nation", "county_city", "district", "village"],
    "district": ["nation", "county_city", "district"],
    "county_city": ["nation", "county_city"],
    "nation": ["nation"],
}

# county_city, district, and village all have real, verified boundary
# sources wired up -- see module docstring for exactly how village's
# OSM-sourced geometry is verified against MOI on every fetch.
IMPLEMENTED_LEVELS: tuple = ("county_city", "district", "village")

ERASE_WATER: dict = {
    "nation": False,
    "county_city": False,
    "district": False,
    "village": True,
}

_NOT_IMPLEMENTED_MESSAGE = (
    "No real boundary source is wired up for Taiwan level '{level}' -- only "
    f"{IMPLEMENTED_LEVELS} are implemented. NLSC's official boundary files "
    "are served from a TGOS host that returns HTTP 403 to a plain HTTP "
    "client (verified 2026-08-20, see pycensus.taiwan.geography module "
    "docstring)."
)

_OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:120];
area["name"="{county_name}"]["boundary"="administrative"]->.a;
(relation["boundary"="administrative"]["admin_level"="9"](area.a););
out geom;
"""


def _assemble_multipolygon(members: list) -> Optional[MultiPolygon]:
    """Assemble a relation's outer/inner way geometries into a (multi)polygon.

    Standard OSM multipolygon assembly: collect the ``outer``/``inner``
    role ways' point sequences as line segments, run
    :func:`shapely.ops.polygonize` to stitch each ring closed (handles
    multi-part relations, e.g. islands, the same way), then subtract any
    inner (hole) rings from the union of outer rings.
    """
    outer_lines, inner_lines = [], []
    for member in members:
        geometry = member.get("geometry")
        if not geometry or len(geometry) < 2:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geometry]
        line = LineString(coords)
        if member.get("role") == "inner":
            inner_lines.append(line)
        else:
            outer_lines.append(line)

    outer_polys = list(polygonize(outer_lines))
    if not outer_polys:
        return None
    outer_union = unary_union(outer_polys)

    if inner_lines:
        inner_polys = list(polygonize(inner_lines))
        if inner_polys:
            outer_union = outer_union.difference(unary_union(inner_polys))

    if isinstance(outer_union, Polygon):
        return MultiPolygon([outer_union])
    return outer_union


def _download_village_geojson(county_code: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) OSM's village relations for one county/city."""
    path = _raw_dir(data_dir).parent / "overpass" / f"{county_code}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return path

    county_name = constants.COUNTY_CODES[county_code]
    query = _OVERPASS_QUERY_TEMPLATE.format(county_name=county_name)
    headers = {"User-Agent": "pycensus/1.0 (+https://github.com/; research use)"}
    response = requests.post(
        constants.OVERPASS_API_URL, data={"data": query}, headers=headers, timeout=180
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("elements"):
        raise ValueError(
            f"Overpass returned zero admin_level=9 relations for county/city "
            f"'{county_name}' ({county_code}) -- the OSM area name or query "
            "may no longer match; not caching an empty result."
        )
    tmp_path = path.with_suffix(".json.part")
    tmp_path.write_text(json.dumps(payload))
    tmp_path.rename(path)
    return path


def _load_village_boundaries(county_code: str, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Load and verify one county/city's village boundaries from OSM Overpass.

    Verifies the fetched relations' ``nat_ref`` set against MOI RIS's own
    live village list for the same county -- see module docstring. Raises
    loudly (rather than silently using a partial/unverified match) if the
    match rate falls below 99%, mirroring the anti-fabrication standard
    used for Mexico's block level (see IMPLEMENTING_A_COUNTRY.md).
    """
    from . import api as moi_api
    from . import constants as _constants

    path = _download_village_geojson(county_code, data_dir)
    payload = json.loads(path.read_text())

    records = []
    for element in payload["elements"]:
        nat_ref = element.get("tags", {}).get("nat_ref")
        if not nat_ref:
            continue
        geom = _assemble_multipolygon(element.get("members", []))
        if geom is None or geom.is_empty:
            continue
        records.append({"GEOID": nat_ref, "geometry": geom})

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=4326)
    if gdf["GEOID"].duplicated().any():
        dupes = gdf.loc[gdf["GEOID"].duplicated(), "GEOID"].tolist()
        raise ValueError(
            f"OSM Overpass returned duplicate nat_ref value(s) {dupes} for county "
            f"'{county_code}' -- refusing to guess which polygon is correct."
        )

    # Verify against MOI's own live village list for this county -- the
    # anti-fabrication check documented in the module docstring.
    yyymm = _constants.LATEST_YEAR["census"]
    village_df = moi_api.fetch_resident_population(yyymm)
    moi_codes = set(village_df.loc[village_df["district_code"].str.startswith(county_code), "district_code"])
    osm_codes = set(gdf["GEOID"])
    if moi_codes:
        match_rate = len(moi_codes & osm_codes) / len(moi_codes)
        if match_rate < 0.99:
            raise ValueError(
                f"OSM village boundaries for county '{county_code}' matched only "
                f"{match_rate:.1%} of MOI's live village list ({len(moi_codes & osm_codes)}/"
                f"{len(moi_codes)}) -- below the verified threshold, refusing to use "
                "this geometry set (see pycensus.taiwan.geography module docstring)."
            )

    return gdf.reset_index(drop=True)


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "geoboundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_county_city_geojson(data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) geoBoundaries' Taiwan ADM1 GeoJSON."""
    path = _raw_dir(data_dir) / "TWN_ADM1.geojson"
    if path.exists() and path.stat().st_size > 0:
        return path

    response = requests.get(constants.GEOBOUNDARIES_TWN_ADM1_URL, timeout=60)
    response.raise_for_status()
    tmp_path = path.with_suffix(".geojson.part")
    tmp_path.write_bytes(response.content)
    tmp_path.rename(path)
    return path


def _download_district_geojson(data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) geoBoundaries' Taiwan ADM2 GeoJSON."""
    path = _raw_dir(data_dir) / "TWN_ADM2.geojson"
    if path.exists() and path.stat().st_size > 0:
        return path

    response = requests.get(constants.GEOBOUNDARIES_TWN_ADM2_URL, timeout=120)
    response.raise_for_status()
    tmp_path = path.with_suffix(".geojson.part")
    tmp_path.write_bytes(response.content)
    tmp_path.rename(path)
    return path


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: Optional[int] = None,
    erase_water: Optional[bool] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch real Taiwan county/city or district boundaries (see module docstring).

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.taiwan.constants.LEVEL_FALLBACK`. ``"county_city"``
            and ``"district"`` are implemented.
        region: A GEOID to filter down to (5-digit county/city code for
            ``level="county_city"``, 8-digit district code for
            ``level="district"``). Accepted for interface parity even
            though geoBoundaries serves each level as a single small
            national-scope download (all counties/cities, or all
            districts, in one request) -- there is no per-region fetch to
            select between (unlike Mexico's per-state MGN zips); ``region``
            just narrows the already-fetched result.
        year: Accepted for interface parity, not implemented -- geoBoundaries'
            TWN layers each have a single build vintage (2023).
        erase_water: Accepted for interface parity, not implemented.
        data_dir: Base directory for the raw GeoJSON cache. Defaults to
            :data:`pycensus.taiwan.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column (MOI's 5-digit county/city code,
        or 8-digit district code for ``level="district"``) and geometry, in
        EPSG:4326, for all 22 counties/cities or all 368 districts.

    Raises:
        ValueError: If ``level`` has no implemented boundary source.
    """
    from ... import geometry_levels

    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="taiwan")
    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(_NOT_IMPLEMENTED_MESSAGE.format(level=level))

    if level == "village":
        if region is None or len(region) < 5:
            raise ValueError(
                "Taiwan village-level boundaries are fetched per county/city (OSM "
                "Overpass has no single national village download) -- pass an "
                "explicit 'region' (5-, 8-, or 11-digit code) so the county/city "
                "can be resolved."
            )
        county_code = region[:5]
        gdf = _load_village_boundaries(county_code, data_dir)
        if region is not None and len(region) == 11:
            gdf = gdf[gdf["GEOID"] == region].reset_index(drop=True)
        return gdf
    elif level == "district":
        path = _download_district_geojson(data_dir)
        gdf = gpd.read_file(path)
        gdf["GEOID"] = gdf["shapeID"].map(constants.GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE)
        if gdf["GEOID"].isna().any():
            unmapped = gdf.loc[gdf["GEOID"].isna(), "shapeID"].tolist()
            raise ValueError(
                f"geoBoundaries TWN ADM2 has shapeID(s) {unmapped} missing from "
                "GEOBOUNDARIES_ADM2_TO_DISTRICT_CODE -- the source file changed shape."
            )
    else:
        path = _download_county_city_geojson(data_dir)
        gdf = gpd.read_file(path)
        gdf["GEOID"] = gdf["shapeISO"].map(constants.GEOBOUNDARIES_ISO_TO_COUNTY_CODE)
        if gdf["GEOID"].isna().any():
            unmapped = gdf.loc[gdf["GEOID"].isna(), "shapeISO"].tolist()
            raise ValueError(
                f"geoBoundaries TWN ADM1 has shapeISO code(s) {unmapped} missing from "
                "GEOBOUNDARIES_ISO_TO_COUNTY_CODE -- the source file changed shape."
            )
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)
    gdf = gdf[["GEOID", "geometry"]].reset_index(drop=True)

    if region is not None:
        # Callers (e.g. moi/loader.py) fetch one region at a time through
        # pycensus.cache's per-region parquet cache -- filter the single
        # small national download down to just the requested GEOID rather
        # than caching/returning all 22 counties/cities under every region's
        # cache key.
        gdf = gdf[gdf["GEOID"] == region].reset_index(drop=True)

    return gdf


def load_boundaries_multi(
    level: str,
    regions=None,
    year: Optional[int] = None,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch county/city boundaries, optionally filtered to ``regions``/clipped to ``aoi``.

    All 22 counties/cities come back from a single :func:`load_boundaries`
    call (see its docstring), so there's no per-region download loop here
    -- ``regions``/``aoi`` only narrow the already-fetched result.
    """
    gdf = load_boundaries(level, year=year, erase_water=erase_water, data_dir=data_dir)

    if regions is not None:
        regions = [regions] if isinstance(regions, str) else list(regions)
        gdf = gdf[gdf["GEOID"].isin(regions)].reset_index(drop=True)

    if aoi is not None:
        gdf = gdf[gdf.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return gdf


def counties_in_aoi(aoi: gpd.GeoDataFrame, data_dir: Optional[str] = None) -> List[str]:
    """Return the county/city codes whose real boundary intersects ``aoi``."""
    gdf = load_boundaries("county_city", data_dir=data_dir)
    aoi_union = aoi.to_crs(4326).union_all()
    return gdf.loc[gdf.intersects(aoi_union), "GEOID"].tolist()


def districts_in_aoi(aoi: gpd.GeoDataFrame, data_dir: Optional[str] = None) -> List[str]:
    """Return the 8-digit district codes whose real ADM2 boundary intersects ``aoi``."""
    gdf = load_boundaries("district", data_dir=data_dir)
    aoi_union = aoi.to_crs(4326).union_all()
    return gdf.loc[gdf.intersects(aoi_union), "GEOID"].tolist()


def villages_in_aoi(aoi: gpd.GeoDataFrame, data_dir: Optional[str] = None) -> List[str]:
    """Return the 11-digit village codes whose real OSM-sourced boundary intersects ``aoi``.

    Resolves ``aoi`` to the county/city codes it intersects first (via
    :func:`counties_in_aoi`, real geoBoundaries ADM1 geometry), then fetches
    village boundaries only for those counties -- avoiding a nationwide
    Overpass fetch for a typically-small city-scale AOI.
    """
    aoi_4326 = aoi.to_crs(4326)
    aoi_union = aoi_4326.union_all()
    county_codes = counties_in_aoi(aoi_4326, data_dir=data_dir)

    matched: List[str] = []
    for county_code in county_codes:
        gdf = _load_village_boundaries(county_code, data_dir)
        matched.extend(gdf.loc[gdf.intersects(aoi_union), "GEOID"].tolist())
    return matched


# Alias for interface parity with other countries (usa.states_in_aoi, etc).
states_in_aoi = counties_in_aoi


__all__ = [
    "GEO_HIERARCHIES",
    "IMPLEMENTED_LEVELS",
    "ERASE_WATER",
    "load_boundaries",
    "load_boundaries_multi",
    "districts_in_aoi",
    "villages_in_aoi",
    "counties_in_aoi",
    "states_in_aoi",
]
