"""Loader for the Eurostat Census 2021 population grid (1 km x 1 km, EU-wide).

Technical aspects:
    Source: ``https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip`` (566 MB, final
    version based on data received 22/01/2025, published 2026-06-19; checked live 2026-11-17). The zip holds the same
    table as CSV, GeoPackage, GeoTIFF and a 76 MB Parquet; this loader extracts only the Parquet.

    Coverage: the EU-27 plus Switzerland, Liechtenstein and Norway; 4,595,932 cells (populated and unpopulated) plus one
    ``<CC>_unallocated`` row per country that could not place part of its population on the grid (FR, IT, FI, BG,
    EL, SE, DK, NO, BE, LV, LU, SI...).

    Columns (EU regulation 1799/2018): ``T`` total population, ``M``/``F`` sex, ``Y_LT15``/``Y_1564``/``Y_GE65`` age,
    ``EMP`` employed persons, ``NAT``/``EU_OTH``/``OTH`` place of birth, ``SAME``/``CHG_IN``/``CHG_OUT`` residence one
    year before, ``LAND_SURFACE`` (km2), ``POPULATED``, ``CNTR_ID`` (countries reporting the cell, e.g. ``AT-CH-LI``
    for border cells). ``-8888`` = confidential, ``-9999`` = not available: both are read as missing (NaN), never as 0.

    Verification (2026-11-17), sum of ``T`` over the cells of one country: Spain 47.371 M (INE Census 2021: 47.385 M),
    Italy 58.985 M + 0.096 M unallocated (ISTAT Census 2021: 59.03 M). Germany sums 81.6 M (official 83.2 M): German
    cells carry disclosure control (rounding / suppression of sparse cells), as in the Zensus grids. By-category
    columns need not add up to ``T`` for the same reason (documented in the file's read.me).

    Geometry: ``GRD_ID`` = ``CRS3035RES1000mN<northing>E<easting>``, the south-west corner of the cell in
    ETRS89-LAEA (EPSG:3035). Cells are built as 1 km squares there and returned in EPSG:4326.

    Resolution class: ``high`` -- every cell is at most 1 km2, so no unit with more than 5,000 residents exceeds
    1 km2 (:mod:`pycensus.resolution`).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from pycensus.cache import get_data_dir

from pycensus.census.countries.eu import constants
from pycensus.census.countries.eu._http import download

GRID_ZIP_URL = "https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip"
PARQUET_MEMBER = "Eurostat_Census-GRID_2021_V3/ESTAT_Census_2021_V3.parquet"
GRID_CRS = 3035
CELL_M = 1000
RESOLUTION = "high"
MISSING = (-8888, -9999)

#: Eurostat code -> feature name (the schema's ``feature_name``; codes are kept as ``original_name``).
COLUMNS = {"T": "population", "M": "malePopulation", "F": "femalePopulation", "Y_LT15": "under15Population",
           "Y_1564": "population15to64", "Y_GE65": "over65Population", "EMP": "employedResidents",
           "NAT": "nativeBornPopulation", "EU_OTH": "bornOtherEUPopulation", "OTH": "bornOutsideEUPopulation",
           "SAME": "sameResidenceLastYear", "CHG_IN": "movedWithinCountryLastYear", "CHG_OUT": "movedFromAbroadLastYear",
           "LAND_SURFACE": "landAreaKm2"}


def _raw_dir(data_dir: Optional[str]) -> Path:
    p = get_data_dir("eu", data_dir) / "raw" / "census_grid"
    p.mkdir(parents=True, exist_ok=True)
    return p


def table_path(data_dir: Optional[str] = None) -> Path:
    """Local path of the grid Parquet (downloads the zip and extracts the Parquet on first use).

    Args:
        data_dir: Root of the raw cache (default: the shared pycensus cache, ``data/eu``).

    Returns:
        Path of ``ESTAT_Census_2021_V3.parquet``.
    """
    raw = _raw_dir(data_dir)
    out = raw / Path(PARQUET_MEMBER).name
    if not out.exists():
        z = download(GRID_ZIP_URL, raw)
        with zipfile.ZipFile(z) as zf, zf.open(PARQUET_MEMBER) as src, open(out.with_suffix(".part"), "wb") as dst:
            while chunk := src.read(1 << 24):
                dst.write(chunk)
        out.with_suffix(".part").rename(out)
    return out


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Rename to feature names, turn the missing codes into NaN, add ``foreignBornPopulation``."""
    out = pd.DataFrame({"GEOID": df["GRD_ID"].astype(str), "countries": df["CNTR_ID"].astype(str)})
    for code, name in COLUMNS.items():
        v = df[code].astype("float64")
        out[name] = v.where(~v.isin(MISSING)).astype("float32")
    out["foreignBornPopulation"] = (out["bornOtherEUPopulation"] + out["bornOutsideEUPopulation"]).astype("float32")
    out["populated"] = df["POPULATED"].astype("int8")
    return out


def _corner(geoid: pd.Series):
    """(easting, northing) of the south-west corner from ``CRS3035RES1000mN<n>E<e>``."""
    p = geoid.str.extract(r"N(\d+)E(\d+)")
    return p[1].astype("float64").to_numpy(), p[0].astype("float64").to_numpy()


def load(aoi=None, countries: Union[None, str, Iterable[str]] = None, populated_only: bool = True,
         data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """1 km grid cells of the Census 2021 grid.

    Args:
        aoi: GeoDataFrame / GeoSeries of the area of interest; cells intersecting it are returned.
        countries: Eurostat or ISO2 code(s): only cells reported by these countries (border cells reported by several
            countries are kept for each of them).
        populated_only: drop cells with no population (``T == 0`` and ``POPULATED == 0``).
        data_dir: Root of the raw cache.

    Returns:
        GeoDataFrame with ``GEOID`` (``GRD_ID``), ``countries`` (``CNTR_ID``), the :data:`COLUMNS` features,
        ``foreignBornPopulation``, ``populated`` and ``geometry`` (1 km square, EPSG:4326). The unallocated rows are not
        included: see :func:`unallocated`.
    """
    df = pd.read_parquet(table_path(data_dir))
    df = df[df["GRD_ID"].str.startswith("CRS3035")]
    if populated_only:
        df = df[(df["T"] > 0) | (df["POPULATED"] == 1)]
    if countries is not None:
        cc = [constants.to_eurostat(c) for c in ([countries] if isinstance(countries, str) else countries)]
        parts = df["CNTR_ID"].astype(str).str.split("-")
        df = df[parts.apply(lambda s: any(c in s for c in cc))]
    e, n = _corner(df["GRD_ID"])
    if aoi is not None:
        a = aoi.to_crs(GRID_CRS)
        x0, y0, x1, y1 = a.total_bounds
        keep = (e + CELL_M > x0) & (e < x1) & (n + CELL_M > y0) & (n < y1)
        df, e, n = df[keep], e[keep], n[keep]
    out = _clean(df.reset_index(drop=True))
    g = gpd.GeoDataFrame(out, geometry=[box(x, y, x + CELL_M, y + CELL_M) for x, y in zip(e, n)], crs=GRID_CRS)
    if aoi is not None:
        g = g[g.intersects(a.union_all())]
    return g.to_crs(4326).reset_index(drop=True)


def unallocated(data_dir: Optional[str] = None) -> pd.DataFrame:
    """Population each country could not place on the grid (one row per country, ``GEOID`` ``<CC>_unallocated``).

    Args:
        data_dir: Root of the raw cache.

    Returns:
        DataFrame with ``GEOID``, ``country`` and the feature columns (no geometry).
    """
    df = pd.read_parquet(table_path(data_dir))
    df = df[df["GRD_ID"].str.endswith("_unallocated")].reset_index(drop=True)
    out = _clean(df)
    out.insert(1, "country", out["GEOID"].str[:2])
    return out


__all__ = ["GRID_ZIP_URL", "GRID_CRS", "CELL_M", "RESOLUTION", "COLUMNS", "table_path", "load", "unallocated"]
