"""Boundary fetching shared by every Spain census source.

Technical aspects:
    Boundaries come from Eurostat/GISCO's LAU (Local Administrative Units)
    dataset, verified 2026-08-19:
    https://gisco-services.ec.europa.eu/distribution/v2/lau/download/ref-lau-2021-01m.geojson.zip
    (~106 MB zip containing every EU/EFTA/candidate country's municipalities
    at 1:1,000,000 resolution; contains 8,131 Spanish features whose
    ``LAU_ID`` is exactly INE's 5-digit municipality code -- verified by
    cross-checking ``LAU_ID == "44001"`` (Ababuj, Teruel) against INE's own
    Tempus API (:mod:`pycensus.spain.ine.loader`), and by summing every
    Spanish feature's ``POP_2021`` to get 47,385,107 -- matching INE table
    2915's "Total Nacional" 2021 figure exactly).

    Only ``municipality`` boundaries are downloaded directly.
    ``province``/``autonomous_community``/``nation`` boundaries are built by
    dissolving municipality geometries using the code prefixes/mapping in
    :mod:`pycensus.spain.constants` (INE municipality codes are
    ``{2-digit province code}{3-digit municipality code}``, so the first two
    characters of ``LAU_ID`` are the province code).

    ``section`` (seccion censal) boundaries come from a real, verified
    source found in this rebuild: INE's own OGC API Features service,
    documented at
    https://www.ine.es/geoserver/ogc/features/v1/collections?f=text/html
    and https://www.ine.es/geoserver/www/guias/OGC_API_Feature_Seccionado.pdf
    -- verified 2026-08-20 with a live request:
    ``GET https://www.ine.es/geoserver/ogc/features/v1/collections/WMS_INE_SECCIONES_G01:Secciones_2025/items?filter=CPRO='20' AND TIPO='SECCIONADO'&filter-lang=cql-text&f=json&limit=2000``
    returned 544 real MultiPolygon features for Gipuzkoa (province code
    "20"), each carrying a real ``CUSEC`` 10-digit code (``CPRO`` 2 +
    ``CMUN`` 3 + ``CDIS`` 2 + ``CSEC`` 3, e.g. ``"2000101001"``) matching
    the format INE's own population-by-section files use for their
    ``Sección`` column. The collection also contains ``TIPO='DISTRITO'``
    aggregate rows (``CSEC='000'``) that are *not* real sections -- these
    are filtered out via the ``TIPO='SECCIONADO'`` CQL clause. The
    response's ``crs`` member is ``urn:ogc:def:crs:EPSG::4326``, confirmed
    live.

    ``district``/``block`` (distrito/manzana) are still not implemented --
    INE's cartography service exposes ``district`` only as the
    ``TIPO='DISTRITO'`` aggregate rows within the same section collection
    (usable, but not yet wired up here), and no stable direct-download URL
    for block-level (``manzana``) cartography was verified in this
    session. Requesting those levels raises ``NotImplementedError`` rather
    than fabricating placeholder geometry (see :data:`IMPLEMENTED_LEVELS`).

    Downloaded/derived files are cached under
    ``<data_dir>/raw/gisco_lau/`` (municipality+) and
    ``<data_dir>/raw/ine_secciones/`` (section, one parquet per province),
    both persistent across runs, independent of :mod:`pycensus.cache`'s
    parquet cache.

Source:
    https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units/local-administrative-units
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import requests

from ... import geometry_levels
from . import constants, utils

LAU_ZIP_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/download/"
    "ref-lau-2021-01m.geojson.zip"
)
LAU_MEMBER_NAME = "LAU_RG_01M_2021_4326.geojson"

# INE's OGC API Features service, census-section ("Secciones censales")
# collection -- verified live 2026-08-20 (see module docstring).
INE_SECCIONES_COLLECTION_URL = (
    "https://www.ine.es/geoserver/ogc/features/v1/collections/"
    "WMS_INE_SECCIONES_G01:Secciones_2025/items"
)

# Geography hierarchy for census data queries: parent-child relationships.
GEO_HIERARCHIES = {
    "municipality": ["nation", "autonomous_community", "province", "municipality"],
    "province": ["nation", "autonomous_community", "province"],
    "autonomous_community": ["nation", "autonomous_community"],
    "nation": ["nation"],
    "section": ["nation", "autonomous_community", "province", "section"],
}

# Levels with a real, verified boundary source wired up (see module docstring).
IMPLEMENTED_LEVELS = ("nation", "autonomous_community", "province", "municipality", "section")

ERASE_WATER: dict = {
    "nation": False,
    "autonomous_community": False,
    "province": False,
    "municipality": False,
    "district": True,
    "section": True,
    "block": True,
}


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "gisco_lau"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_lau_zip(data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) the GISCO LAU boundary zip."""
    raw_dir = _raw_dir(data_dir)
    zip_path = raw_dir / "ref-lau-2021-01m.geojson.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    response = requests.get(LAU_ZIP_URL, stream=True, timeout=300)
    response.raise_for_status()
    tmp_path = zip_path.with_suffix(".zip.part")
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    tmp_path.rename(zip_path)
    return zip_path


def _load_spain_municipalities(data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return every Spanish municipality boundary, cached as a small GeoParquet.

    On first call, downloads the (whole-Europe, ~106 MB) GISCO LAU zip,
    extracts just the EPSG:4326 GeoJSON member, filters it to Spain
    (``CNTR_CODE == "ES"``, 8,131 features) and writes that filtered
    result out as GeoParquet so every subsequent call is fast and doesn't
    need the zip again.
    """
    raw_dir = _raw_dir(data_dir)
    cached_path = raw_dir / "es_municipalities.parquet"
    if cached_path.exists():
        return gpd.read_parquet(cached_path)

    zip_path = _download_lau_zip(data_dir)
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(LAU_MEMBER_NAME) as src:
            tmp_geojson = raw_dir / LAU_MEMBER_NAME
            with open(tmp_geojson, "wb") as dst:
                dst.write(src.read())

    gdf = gpd.read_file(tmp_geojson, where="CNTR_CODE='ES'", engine="pyogrio")
    gdf = gdf.rename(columns={"LAU_ID": "GEOID"})[["GEOID", "LAU_NAME", "POP_2021", "geometry"]]
    gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)

    gdf.to_parquet(cached_path)
    # The uncompressed whole-Europe GeoJSON (~126 MB) is no longer needed
    # once the Spain-only GeoParquet is cached; keep the zip (cheap re-derive).
    tmp_geojson.unlink(missing_ok=True)
    return gdf


def _sections_raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "ine_secciones"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _load_spain_sections_for_province(province_code: str, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Return every real census-section boundary for one province, cached as GeoParquet.

    On first call, fetches INE's OGC API Features "Secciones_2025"
    collection filtered (server-side, via CQL) to
    ``CPRO='<province_code>' AND TIPO='SECCIONADO'`` -- ``TIPO='DISTRITO'``
    rows are district-level aggregates (``CSEC='000'``), not real
    sections, and are excluded. See the module docstring for the live
    verification (544 real sections for Gipuzkoa, province "20").
    """
    raw_dir = _sections_raw_dir(data_dir)
    cached_path = raw_dir / f"sections_{province_code}.parquet"
    if cached_path.exists():
        return gpd.read_parquet(cached_path)

    params = {
        "filter": f"CPRO='{province_code}' AND TIPO='SECCIONADO'",
        "filter-lang": "cql-text",
        "f": "json",
        "limit": 5000,
    }
    response = requests.get(INE_SECCIONES_COLLECTION_URL, params=params, timeout=180)
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", [])
    if not features:
        raise ValueError(
            f"INE's census-section feature service returned no 'SECCIONADO' features for "
            f"CPRO='{province_code}'. Response numberMatched={payload.get('numberMatched')}."
        )

    gdf = gpd.GeoDataFrame.from_features(features, crs=4326)
    gdf = gdf.rename(columns={"CUSEC": "GEOID"})[
        ["GEOID", "CPRO", "CMUN", "CUMUN", "CDIS", "CSEC", "NMUN", "geometry"]
    ]
    gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(10)

    gdf.to_parquet(cached_path)
    return gdf


def _province_codes_in_region(region: str) -> List[str]:
    """Resolve ``region`` (AC code or province code) to a list of province codes.

    Mirrors :func:`_municipality_codes_in_region`'s AC-before-province
    resolution order (a bare 2-digit string is genuinely ambiguous between
    an autonomous-community code and a province code).
    """
    try:
        ac_code = utils.autonomous_community_code(region)
        return list(constants.AUTONOMOUS_COMMUNITY_PROVINCES.get(ac_code, []))
    except ValueError:
        pass
    return [utils.province_code(region)]


def _province_code_for_municipality(geoid: str) -> str:
    """First two digits of a 5-digit INE municipality code == its province code."""
    return geoid[:2]


def load_boundaries(
    level: str,
    region: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch boundaries for one Spain geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.spain.constants.LEVEL_FALLBACK`.
        region: Region code -- an autonomous community code, province code,
            or municipality code, matching ``level``. If ``None``, returns
            every geometry at this level for the entire country. Required
            for ``level="section"`` (see below).
        year: Vintage year. GISCO LAU 2021 is the only vintage wired up
            for municipality+; INE's "Secciones_2025" collection is the
            only vintage wired up for sections. Kept as a parameter for
            interface parity with other countries.
        erase_water: Whether to clip inland water bodies. Defaults to
            :data:`ERASE_WATER` for the resolved level. Not yet implemented
            (GISCO LAU / INE section geometries are land-only administrative
            boundaries already, so this is a no-op today).
        data_dir: Root directory for the raw GISCO/INE cache. Defaults to
            :data:`pycensus.spain.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
        ValueError: If ``level`` resolves to ``"section"`` without a
            ``region`` (fetching every one of Spain's ~36,000 census
            sections in one call is not supported).
        NotImplementedError: If ``level`` resolves to a level without a
            real, verified boundary source (``district``/``block``).
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="spain")

    if level not in IMPLEMENTED_LEVELS:
        raise NotImplementedError(
            f"No real boundary source is wired up for Spain level '{level}'. "
            f"Implemented levels: {IMPLEMENTED_LEVELS}. INE's OGC API Features 'Secciones' "
            f"collection also exposes 'district' as TIPO='DISTRITO' aggregate rows and could "
            f"be wired up the same way as 'section' (see pycensus.spain.geography module "
            f"docstring); no stable direct-download URL for block ('manzana') cartography "
            f"was verified in this rebuild."
        )

    if level == "section":
        if region is None:
            raise ValueError(
                "Spain 'section' boundaries must be requested with an explicit 'region' "
                "(autonomous community or province code) -- fetching every one of Spain's "
                "~36,000 census sections in one call is not supported."
            )
        province_codes = _province_codes_in_region(region)
        parts = [_load_spain_sections_for_province(p, data_dir) for p in province_codes]
        result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
        return result[["GEOID", "geometry"]].reset_index(drop=True)

    muns = _load_spain_municipalities(data_dir)

    if level == "municipality":
        result = muns[["GEOID", "geometry"]]
        if region:
            region_codes = _municipality_codes_in_region(region, muns)
            result = result[result["GEOID"].isin(region_codes)]
        return result.reset_index(drop=True)

    if level == "province":
        prov_series = muns["GEOID"].str[:2]
        if region:
            prov_code = utils.province_code(region)
            sel = muns[prov_series == prov_code]
            dissolved = sel.dissolve()
            dissolved["GEOID"] = prov_code
        else:
            # Drop the original per-municipality GEOID before dissolving --
            # dissolve()'s default aggfunc="first" would otherwise carry it
            # through, and reset_index().rename() would then produce two
            # columns both named "GEOID" (the surviving municipality code
            # and the renamed province-group key), silently breaking any
            # code that reads `gdf["GEOID"]` expecting a Series.
            grouped = muns[["geometry"]].assign(_prov=prov_series)
            dissolved = grouped.dissolve(by="_prov").reset_index().rename(columns={"_prov": "GEOID"})
        return dissolved[["GEOID", "geometry"]].reset_index(drop=True)

    if level == "autonomous_community":
        prov_series = muns["GEOID"].str[:2]
        muns_ac = muns.assign(_prov=prov_series)
        if region:
            ac_code = utils.autonomous_community_code(region)
            prov_codes = constants.AUTONOMOUS_COMMUNITY_PROVINCES.get(ac_code, [])
            sel = muns_ac[muns_ac["_prov"].isin(prov_codes)]
            dissolved = sel.dissolve()
            dissolved["GEOID"] = ac_code
        else:
            prov_to_ac = {
                p: ac for ac, provs in constants.AUTONOMOUS_COMMUNITY_PROVINCES.items() for p in provs
            }
            muns_ac["_ac"] = muns_ac["_prov"].map(prov_to_ac)
            muns_ac = muns_ac.dropna(subset=["_ac"])
            # See the "province" branch above for why the original
            # per-municipality GEOID must be dropped before dissolving.
            dissolved = (
                muns_ac[["geometry", "_ac"]]
                .dissolve(by="_ac")
                .reset_index()
                .rename(columns={"_ac": "GEOID"})
            )
        return dissolved[["GEOID", "geometry"]].reset_index(drop=True)

    if level == "nation":
        dissolved = muns.dissolve()
        dissolved["GEOID"] = "ES"
        return dissolved[["GEOID", "geometry"]].reset_index(drop=True)

    raise KeyError(f"Unknown geography level '{level}'. Known: {sorted(IMPLEMENTED_LEVELS)}")


def _municipality_codes_in_region(region: str, muns: gpd.GeoDataFrame) -> List[str]:
    """Resolve ``region`` (AC code, province code, or municipality code) to municipality GEOIDs.

    AC codes ("01".."19") and province codes ("01".."52") share the same
    2-digit numeric space for their low values (e.g. "15" is Navarra as an
    AC code but La Coruña as a province code), so a bare 2-digit string is
    genuinely ambiguous. This must try autonomous-community resolution
    first, matching :func:`pycensus.spain.ine.loader.load`'s
    ``region_codes`` resolution order -- those two functions previously
    disagreed (this one tried province first), so a valid AC code like
    "15"/"16" coming from :func:`states_in_aoi` silently resolved to the
    wrong province's municipalities instead of raising or matching, with no
    error (verified live: this caused ``loader.load(aoi=<Gipuzkoa AOI>,
    level="municipality")`` to return 0 rows because AC code "16" (País
    Vasco) got resolved as province code "16" (Cuenca), nowhere near the
    AOI).
    """
    if isinstance(region, str) and len(region) == 5 and region.isdigit():
        return [region]
    try:
        ac_code = utils.autonomous_community_code(region)
        prov_codes = set(constants.AUTONOMOUS_COMMUNITY_PROVINCES.get(ac_code, []))
        return muns.loc[muns["GEOID"].str[:2].isin(prov_codes), "GEOID"].tolist()
    except ValueError:
        pass
    prov_code = utils.province_code(region)
    return muns.loc[muns["GEOID"].str[:2] == prov_code, "GEOID"].tolist()


def load_boundaries_multi(
    level: str,
    regions: Optional[Union[str, List[str]]] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more regions, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        regions: Region code(s). If ``None``, returns every geometry at
            this level for the entire country.
        year: Vintage year (see :func:`load_boundaries`).
        erase_water: Whether to clip inland water bodies.
        aoi: If given, the result is filtered to geometries intersecting it.
        data_dir: Root directory for the raw GISCO cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if regions is None:
        return load_boundaries(level, None, year, erase_water, data_dir)
    if isinstance(regions, str):
        regions = [regions]

    parts = []
    for region in regions:
        gdf = load_boundaries(level, region, year, erase_water, data_dir)
        parts.append(gdf)

    if not parts:
        raise ValueError(f"No boundaries could be loaded for any of the requested regions: {regions}")

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


def autonomous_communities_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, data_dir: Optional[str] = None) -> List[str]:
    """Return the INE codes of every autonomous community intersecting ``aoi``."""
    acs = load_boundaries("autonomous_community", None, year, data_dir=data_dir)
    hits = acs[acs.intersects(aoi.to_crs(4326).union_all())]
    return hits["GEOID"].tolist()


def provinces_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, data_dir: Optional[str] = None) -> List[str]:
    """Return the INE codes of every province intersecting ``aoi``."""
    provs = load_boundaries("province", None, year, data_dir=data_dir)
    hits = provs[provs.intersects(aoi.to_crs(4326).union_all())]
    return hits["GEOID"].tolist()


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, data_dir: Optional[str] = None) -> List[str]:
    """Alias for :func:`autonomous_communities_in_aoi` (interface parity with ``usa``)."""
    return autonomous_communities_in_aoi(aoi, year, data_dir)


__all__ = [
    "LAU_ZIP_URL",
    "INE_SECCIONES_COLLECTION_URL",
    "GEO_HIERARCHIES",
    "IMPLEMENTED_LEVELS",
    "ERASE_WATER",
    "autonomous_communities_in_aoi",
    "provinces_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
    "states_in_aoi",
]
