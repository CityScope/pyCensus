"""Loader for Eurostat GISCO LAU (municipality) boundaries with their population, EU-wide.

Technical aspects:
    GISCO publishes one LAU file per year (``https://gisco-services.ec.europa.eu/distribution/v2/lau/``) with the
    columns ``GISCO_ID, CNTR_CODE, LAU_ID, LAU_NAME, POP_<year>, POP_DENS_<year>, AREA_KM2, YEAR``. Not every country
    reports every year: checked 2026-11-17, LAU 2024 has 0 population for all 8,132 Spanish and 34,946 French LAUs,
    while LAU 2023 has them. :func:`load` therefore picks, **per country**, the latest vintage in which at least 95 % of
    the country's LAUs have population, using the small CSV of each vintage, and then reads only that country's
    geometry from the vintage's GeoPackage.

    The area is computed from the boundary in ETRS89-LAEA rather than read from GISCO's ``AREA_KM2``, which is wrong
    in LAU 2023 for Spain (Barcelona 16,843 km2 instead of 99 km2; 97 % of Spanish LAUs off by more than 10 %).

    Countries without population in any wired vintage (Iceland, Serbia, Albania in 2021-2024) raise an error rather
    than return zeros.

    Resolution class: ``low`` (municipal units, :mod:`pycensus.resolution`): usable for boundaries and as a fallback,
    never for regressions or the census tab.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Union

import geopandas as gpd
import pandas as pd

from pycensus.cache import get_data_dir

from .. import constants, geography
from .._http import download

RESOLUTION = "low"
MIN_REPORTED_SHARE = 0.95


def _attrs(year: int, data_dir: Optional[str]) -> pd.DataFrame:
    raw = get_data_dir("eu", data_dir) / "raw" / "gisco_lau"
    return pd.read_csv(download(constants.LAU_CSV_URL.format(year=year), Path(raw)), dtype={"LAU_ID": str})


def vintage_by_country(data_dir: Optional[str] = None) -> Dict[str, int]:
    """For every country, the latest LAU vintage in which it reported population.

    Args:
        data_dir: Root of the raw cache.

    Returns:
        ``{eurostat country code: year}``; countries that never reported are absent.
    """
    out: Dict[str, int] = {}
    for year in sorted(constants.LAU_YEARS, reverse=True):
        a = _attrs(year, data_dir)
        share = (a[f"POP_{year}"] > 0).groupby(a["CNTR_CODE"]).mean()
        for c, s in share.items():
            if c not in out and s >= MIN_REPORTED_SHARE:
                out[c] = year
    return out


def load(countries: Union[str, Iterable[str]], year: Optional[int] = None, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """LAU municipalities of ``countries`` with population and area.

    Args:
        countries: Eurostat or ISO2 code(s).
        year: a fixed LAU vintage; ``None`` = the latest vintage with population, chosen per country.
        data_dir: Root of the raw cache.

    Returns:
        GeoDataFrame with ``GEOID`` (GISCO id), ``country``, ``lau_id``, ``name``, ``population``, ``landAreaKm2``,
        ``year`` (vintage used) and ``geometry`` (EPSG:4326).

    Raises:
        ValueError: if a country has no population in the requested (or any wired) vintage.
    """
    cc = [constants.to_eurostat(c) for c in ([countries] if isinstance(countries, str) else countries)]
    years = {c: year for c in cc} if year else vintage_by_country(data_dir)
    missing = [c for c in cc if c not in years]
    if missing:
        raise ValueError(f"no LAU vintage {constants.LAU_YEARS} has population for {missing}")
    parts = []
    for y in sorted({years[c] for c in cc}):
        group = [c for c in cc if years[c] == y]
        g = geography.lau(group, y, data_dir)
        if (g[f"POP_{y}"] <= 0).all():
            raise ValueError(f"LAU {y} has no population for {group}")
        # area from the geometry (ETRS89-LAEA, equal area): GISCO's AREA_KM2 is wrong in LAU 2023 for Spain (Barcelona
        # 16,843 km2 instead of 99; 97 % of Spanish LAUs off by more than 10 %, checked 2026-11-17)
        g = g.rename(columns={f"POP_{y}": "population"})
        g["landAreaKm2"] = g.to_crs(3035).geometry.area / 1e6
        g["year"] = y
        parts.append(g[["GEOID", "country", "lau_id", "name", "population", "landAreaKm2", "year", "geometry"]])
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326)


__all__ = ["RESOLUTION", "vintage_by_country", "load"]
