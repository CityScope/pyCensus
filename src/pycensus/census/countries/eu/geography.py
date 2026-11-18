"""EU-wide boundaries from Eurostat GISCO: NUTS 0-3 regions and LAU municipalities.

Technical aspects:
    One GeoPackage per vintage holds every country (NUTS: ~28 MB for all levels; LAU: ~64-78 MB). Each file is
    downloaded once into ``<data_dir>/raw/gisco_nuts`` or ``<data_dir>/raw/gisco_lau`` and read with a country filter,
    so a call for one country never parses the whole continent into memory twice. Output is EPSG:4326 with a
    ``GEOID`` column: the NUTS id (``ES300``) or the GISCO LAU id (``ES_28079``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

import geopandas as gpd

from pycensus.cache import get_data_dir

from pycensus.census.countries.eu import constants
from pycensus.census.countries.eu._http import download


def _raw(sub: str, data_dir: Optional[str]) -> Path:
    p = get_data_dir("eu", data_dir) / "raw" / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def _countries(countries: Union[None, str, Iterable[str]]):
    if countries is None:
        return None
    if isinstance(countries, str):
        countries = [countries]
    return [constants.to_eurostat(c) for c in countries]


def _where(col: str, codes) -> Optional[str]:
    return None if not codes else f"{col} IN ({', '.join(repr(c) for c in codes)})"


def nuts_file(year: int = 2024, data_dir: Optional[str] = None) -> Path:
    """Path of the cached GISCO NUTS GeoPackage of ``year`` (downloaded on first use).

    Args:
        year: NUTS vintage, one of :data:`constants.NUTS_YEARS`.
        data_dir: Root of the raw cache (default: the shared pycensus cache, ``data/eu``).

    Returns:
        Local path of the GeoPackage.
    """
    if year not in constants.NUTS_YEARS:
        raise ValueError(f"NUTS year {year} not wired; use one of {constants.NUTS_YEARS}")
    return download(constants.NUTS_GPKG_URL.format(year=year), _raw("gisco_nuts", data_dir))


def nuts(level: int, countries=None, year: int = 2024, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """NUTS regions of one level.

    Args:
        level: 0 (country), 1, 2 or 3.
        countries: Eurostat or ISO2 country code(s); ``None`` for every country in the file.
        year: NUTS vintage.
        data_dir: Root of the raw cache.

    Returns:
        GeoDataFrame with ``GEOID`` (NUTS id), ``country``, ``name``, ``nuts_level``, ``geometry`` (EPSG:4326).
    """
    if level not in (0, 1, 2, 3):
        raise ValueError("NUTS level must be 0, 1, 2 or 3")
    cc = _countries(countries)
    where = f"LEVL_CODE = {int(level)}" + (f" AND {_where('CNTR_CODE', cc)}" if cc else "")
    g = gpd.read_file(nuts_file(year, data_dir), where=where)
    g = g.rename(columns={"NUTS_ID": "GEOID", "CNTR_CODE": "country", "NAME_LATN": "name", "LEVL_CODE": "nuts_level"})
    return g[["GEOID", "country", "name", "nuts_level", "geometry"]].to_crs(4326).reset_index(drop=True)


def lau_file(year: int, data_dir: Optional[str] = None) -> Path:
    """Path of the cached GISCO LAU GeoPackage of ``year`` (downloaded on first use).

    Args:
        year: LAU vintage.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The GeoPackage path.

    Raises:
        ValueError: For a year not wired.
    """
    if year not in constants.LAU_YEARS:
        raise ValueError(f"LAU year {year} not wired; use one of {constants.LAU_YEARS}")
    return download(constants.LAU_GPKG_URL.format(year=year), _raw("gisco_lau", data_dir))


def lau(countries=None, year: int = 2023, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """LAU municipalities with their GISCO attributes.

    Args:
        countries: Eurostat or ISO2 country code(s); ``None`` for all.
        year: LAU vintage.
        data_dir: Root of the raw cache.

    Returns:
        GeoDataFrame with ``GEOID`` (GISCO id, e.g. ``ES_28079``), ``country``, ``lau_id``, ``name``, the vintage's
        ``POP_<year>`` / ``POP_DENS_<year>`` / ``AREA_KM2`` columns and ``geometry`` (EPSG:4326).
    """
    cc = _countries(countries)
    g = gpd.read_file(lau_file(year, data_dir), where=_where("CNTR_CODE", cc))
    g = g.rename(columns={"GISCO_ID": "GEOID", "CNTR_CODE": "country", "LAU_ID": "lau_id", "LAU_NAME": "name"})
    if "lau_id" not in g:   # LAU 2024 has no LAU_ID column: the national code is GISCO_ID after "<CC>_"
        g["lau_id"] = g["GEOID"].str.split("_", n=1).str[1]
    return g.to_crs(4326).reset_index(drop=True)


__all__ = ["nuts_file", "nuts", "lau_file", "lau"]
