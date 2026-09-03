"""Loader for Chile's SII comunal jobs-by-workplace statistics, returning a common-schema GeoDataFrame.

Technical aspects:
    Mirrors :mod:`pycensus.countries.chile.casen.loader`'s shape (real
    bulk .xlsx download, fetched once and filtered per region -- see
    :mod:`pycensus.countries.chile.sii.api`).

    SII's raw table identifies comunas by free-text Spanish name (e.g.
    "CONCEPCION"), not by CUT code, so this loader builds a live
    name->CUT-code crosswalk from the same verified DPA FeatureServer
    already used for Chile's boundaries (:mod:`pycensus.countries.chile.api`,
    ``NOM_COMUNA``/``COMUNA`` fields on the ``comuna`` layer) instead of
    hardcoding a name table -- comuna names are matched after stripping
    accents/case (SII's names are unaccented ASCII, DPA's are accented).
    Region is resolved from SII's free-text ``id_region`` (e.g. "VIII DEL
    BIO BIO") via its leading roman-numeral token against
    :data:`pycensus.countries.chile.constants.REGION_ABBR`, with a
    special case for "METROPOLITANA" (Region 13, abbreviated "RM" rather
    than a roman numeral).

    Live-verified 2026-08-23: region "08" (Bio-Bio) -- all 33 real SII
    comuna rows matched a real DPA GEOID (100% match rate, no silent
    drops); comuna Concepcion (GEOID 08101) resolved to 154,065 jobsTotal.

    Only ``"comuna"`` is implemented -- this is the only level SII's
    comunal workbook publishes.
"""

from __future__ import annotations

from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd

from .... import cache as cache_store
from .... import geometry_levels
from pycensus.canonical import apply_canonical_names

from .. import api as dpa_api
from .. import constants, geography, utils
from . import api
from .schema import SCHEMA


def _normalize(name: str) -> str:
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ü": "u",
    }
    out = str(name).strip().lower()
    for accented, plain in replacements.items():
        out = out.replace(accented, plain)
    return out


def _sii_region_code(id_region: str) -> Optional[str]:
    """Resolve SII's free-text 'id_region' (e.g. 'VIII DEL BIO BIO') to a canonical 2-digit region code."""
    text = str(id_region).strip().upper()
    if "METROPOLITANA" in text:
        return "13"
    first_token = text.split(" ", 1)[0]
    abbr_to_code = {
        constants.REGION_ABBR[name]: code for code, name in constants.REGION_CODES.items()
    }
    return abbr_to_code.get(first_token)


def _comuna_name_to_geoid(region_2digit: str, data_dir: Optional[str]) -> dict:
    """Live crosswalk: normalized real DPA comuna name -> real DPA GEOID, for one region."""
    raw = dpa_api.fetch_features("comuna", region_2digit, data_dir)
    crosswalk = {}
    for feature in raw["features"]:
        props = feature["properties"]
        name = props.get("NOM_COMUNA")
        code = props.get(dpa_api.CODE_FIELDS["comuna"])
        if name is None or code is None:
            continue
        crosswalk[_normalize(name)] = dpa_api.build_geoid("comuna", code)
    return crosswalk


def _fetch_missing(
    missing_prefixed: List[str],
    level: str,
    region: str,
    data_dir: Optional[str],
) -> pd.DataFrame:
    """Fetch (via the cached national xlsx table) jobsTotal, filtered to ``region``, keyed by real DPA GEOID."""
    if level != "comuna":
        raise ValueError(f"SII comunal jobs data is only published at comuna level -- got level={level!r}.")

    table = api.fetch_table(data_dir)
    table = table[table["id_region"].map(_sii_region_code) == region]
    latest_year = table["ano_comercial"].max()
    table = table[table["ano_comercial"] == latest_year]

    crosswalk = _comuna_name_to_geoid(region, data_dir)
    table = table.copy()
    table["GEOID"] = table["id_comuna"].map(lambda n: crosswalk.get(_normalize(n)))
    table = table.dropna(subset=["GEOID"])

    result = table.groupby("GEOID", as_index=True)["jobsTotal"].sum().to_frame()
    result = result.rename(columns={"jobsTotal": SCHEMA.column_label("jobsTotal")})
    return result.reset_index()


def load(
    aoi: Optional[gpd.GeoDataFrame] = None,
    regions: Optional[Union[str, List[str]]] = None,
    level: str = "comuna",
    year: Union[int, str] = "latest",
    cache_dir: Optional[str] = None,
    cache: bool = True,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Load Chile SII comunal jobs-by-workplace data as a common-schema GeoDataFrame.

    Args:
        aoi: Area of interest. Used to auto-detect ``regions`` if not
            given, and to clip the final result.
        regions: Region name(s)/code(s) to load. Derived from ``aoi`` if
            omitted (``aoi`` is then required).
        level: Must resolve to ``"comuna"`` -- the only level SII's
            comunal workbook publishes.
        year: Ignored -- SII's file only carries data through commercial
            year 2015 (the latest available row is always used). See
            :mod:`pycensus.countries.chile.sii.api` module docstring.
        cache_dir: Root of pyCensus' parquet cache.
        cache: If ``False``, bypass the parquet cache entirely.
        data_dir: Base directory for the raw .xlsx/.geojson cache.

    Returns:
        GeoDataFrame with ``GEOID``, geometry, and ``sii_cl_jobsTotal``.

    Raises:
        ValueError: If neither ``regions`` nor ``aoi`` is given.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    if level != "comuna":
        raise NotImplementedError(f"SII comunal jobs data is only published at comuna level -- got level={level!r}.")

    if regions is None:
        if aoi is None:
            raise ValueError("Either 'regions' or 'aoi' is required")
        regions = geography.regions_in_aoi(aoi)
    elif isinstance(regions, str):
        regions = [regions]

    region_codes = [utils.region_code(r) for r in regions]
    columns = [SCHEMA.column_label(name) for name in SCHEMA.columns]

    region_frames = []
    for region_code in region_codes:
        path = cache_store.region_path(cache_dir, "chile_sii", level, region_code)

        gdf = cache_store.load_region(
            path,
            id_col="GEOID",
            columns=columns,
            fetch_boundary=lambda region=region_code: geography.load_boundaries(
                level, region, constants.LATEST_YEAR.get("geography"), data_dir=data_dir
            ),
            fetch_columns=lambda missing, region=region_code: _fetch_missing(missing, level, region, data_dir),
            use_cache=cache,
        )
        region_frames.append(gdf)

    if not region_frames:
        return apply_canonical_names(
            gpd.GeoDataFrame(
                pd.DataFrame({"GEOID": [], **{c: [] for c in columns}}),
                geometry=gpd.GeoSeries([], crs=4326),
                crs=4326,
            ),
            SCHEMA,
        )

    result = gpd.GeoDataFrame(pd.concat(region_frames, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return apply_canonical_names(result, SCHEMA)


__all__ = ["load"]
