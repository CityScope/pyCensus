"""Loader for Euskadi municipal population, returning a common-schema GeoDataFrame.

Technical aspects:
    Similar to usa.acs.loader, mexico.inegi.loader, and spain.eustat.loader,
    this module provides a load() function that:
    1. Resolves the requested geographic level
    2. Determines which territories to load (from AOI or explicit list)
    3. Uses the cache system to load only missing columns
    4. Fetches boundaries and attribute data as needed
    5. Returns a GeoDataFrame with GEOID, geometry, and eustat_prefixed columns

    Unlike ``usa``'s Census Bureau API, neither of Euskadi's own real data
    portals (``opendata.euskadi.eus``, ``eustat.eus``) is reachable over a
    plain scripted HTTP request -- both returned 403/404 to real ``curl``
    checks made during this rebuild (see ``euskadi/geography.py``'s
    docstring for the exact checks). This loader therefore sources both
    geometry and its one real attribute column (population, via
    ``euskadi.eustat.schema.SCHEMA``) from Eurostat/GISCO's LAU 2021
    GeoPackage, which republishes real INE-sourced Spanish municipal
    boundaries and population -- verified against Gipuzkoa's, Araba's, and
    Bizkaia's well-documented real populations (see schema.json).

    No API key is required for this source.

Source:
    Eurostat/GISCO LAU 2021: https://gisco-services.ec.europa.eu/distribution/v2/lau/lau-2021-files.html
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from .. import constants, geography, utils
from .schema import SCHEMA
from pycensus.canonical import apply_canonical_names

# GISCO LAU's own columns, already produced by geography._load_gisco_municipalities.
_RAW_COLUMN_MAP = {
    "population": "population",
    "areaKm2": "area_km2",
    # populationDensity isn't carried by geography.py's municipality frame
    # (only GEOID/NAME/population/area_km2/geometry) -- computed below from
    # the two real fields above instead of a fourth network round trip.
}


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    region: str,
    year: int,
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch and compute just the logical columns in ``missing_prefixed``.

    Args:
        missing_prefixed: Prefixed column names that need to be fetched.
        level: Geographic level (territory, municipality, autonomous_community).
        region: Territory code (01/48/20).
        year: Vintage year (2021 only, see geography.load_boundaries).
        cache_dir: Cache directory for storing raw data files.

    Returns:
        DataFrame with GEOID column plus the requested columns.
    """
    if level == "municipality":
        muni = geography._load_gisco_municipalities(region, cache_dir)
        base = muni[["GEOID", "population", "area_km2"]].copy()
    else:
        # territory / autonomous_community: aggregate real municipality data.
        codes = [region] if level == "territory" else list(constants.TERRITORY_CODES)
        parts = [geography._load_gisco_municipalities(c, cache_dir) for c in codes]
        muni = pd.concat(parts, ignore_index=True)
        geoid = region if level == "territory" else "EUS"
        base = pd.DataFrame(
            {"GEOID": [geoid], "population": [muni["population"].sum()], "area_km2": [muni["area_km2"].sum()]}
        )

    base["populationDensity"] = base["population"] / base["area_km2"].replace(0, pd.NA)

    result = pd.DataFrame({"GEOID": base["GEOID"]})
    for prefixed_name in missing_prefixed:
        col_name = SCHEMA.strip_prefix(prefixed_name)
        result[prefixed_name] = base[col_name] if col_name in base.columns else pd.Series(dtype="float64")
    return result


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "municipality",
    year: Union[int, str] = "latest",
    api_key: Optional[str] = None,
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Euskadi municipal population data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not given,
            and to clip the final result.
        regions: Territory name(s)/abbreviation(s)/code(s) to load (Araba,
            Bizkaia, Gipuzkoa or 01, 48, 20). Derived from ``aoi`` if
            omitted (``aoi`` is then required).
        level: Standard geometry level name. Real levels implemented here
            are ``autonomous_community``, ``territory``, and
            ``municipality`` -- everything finer falls back to
            ``municipality`` via :data:`pycensus.euskadi.constants.LEVEL_FALLBACK`
            (see that module's docstring for why).
        year: Vintage year, or ``"latest"`` (only 2021, GISCO LAU's vintage,
            is implemented).
        api_key: Unused -- no API key is required for this source.
        cache_dir: Root of pyCensus' parquet cache.
        cache: If ``False``, bypass the cache entirely.
        data_dir: Unused (kept for interface compatibility).

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and one ``eustat_``-prefixed
        column per logical column in :data:`pycensus.euskadi.eustat.schema.SCHEMA`.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="euskadi")
    year = constants.LATEST_YEAR.get("census", 2021) if year == "latest" else int(year)

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.territories_in_aoi(aoi, year, cache_dir)
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = [utils.territory_code(r) for r in regions]
    if level == "autonomous_community":
        # Euskadi-wide totals don't depend on which territories were asked
        # for -- collapse to one fetch/cache entry instead of duplicating
        # the same "EUS" row once per requested region.
        region_codes = region_codes[:1]

    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "euskadi", level, region_code)

        def fetch_boundary(region=region_code):
            return geography.load_boundaries(level, region, year, cache_dir=cache_dir)

        def fetch_columns(missing, region=region_code):
            return _fetch_missing(missing, level, region, year, cache_dir)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=fetch_boundary,
            fetch_columns=fetch_columns,
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}), geometry="geometry", crs=4326
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
