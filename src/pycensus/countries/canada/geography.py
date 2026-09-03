"""Boundary fetching shared by every Canada census source.

Technical aspects:
    Boundaries come from Statistics Canada's real 2021 Census cartographic
    boundary files, published at
    https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm
    and verified live 2026-08-20 by actually downloading each zip and
    reading the shapefile inside it (not just checking the HTTP status):

    - Province/territory (``lpr_000b21a_e.zip``, 133,730,024 bytes,
      ``Content-Type: application/x-zip-compressed``): 13 rows, columns
      ``PRUID``/``DGUID``/``PRNAME``/... in EPSG:3347. ``PRUID`` values
      (10, 11, 12, ..., 62) matched exactly against
      :data:`pycensus.canada.constants.PROVINCE_CODES`.
    - Census subdivision / municipality (``lcsd000b21a_e.zip``,
      155,981,521 bytes): 5,161 rows, columns
      ``CSDUID``/``DGUID``/``CSDNAME``/``CSDTYPE``/``PRUID``/... in
      EPSG:3347. Toronto's row (``CSDUID == "3520005"``) has bounds
      ``[-79.639, 43.579, -79.115, 43.855]`` -- squarely inside the real
      city of Toronto's extent, and its ``CSDUID`` matches the DGUID
      (``2021A00053520005``) on Toronto's real population row in the
      Census Profile table (see :mod:`pycensus.canada.api`).

    Unlike Mexico's per-state Marco Geoestadistico bundle, StatCan
    publishes each level as a single *national* shapefile, so there is no
    per-region download to parallelize/skip -- the whole national zip is
    downloaded once (cached under ``<data_dir>/raw/statcan_boundaries/``,
    persistent across runs) and then filtered in memory per province.
    Because the download is already national and can't be made cheaper by
    narrowing first, :func:`provinces_in_aoi` does a real geometric
    intersects test against the actual province boundaries instead of a
    hand-set bounding-box heuristic (the pattern used by
    ``mexico.geography.states_in_aoi``, needed there specifically to avoid
    32 separate expensive per-state downloads).

    ``province``, ``municipality`` (census subdivision), and
    ``dissemination-area`` (DA -- StatCan's tract-equivalent, the finest
    unit with published Census Profile population data) are implemented.
    DA boundaries were verified live 2026-08-20 the same way as the other
    two levels: ``lda_000b21a_e.zip`` (197,042,003 bytes, GET returns 200
    / application/x-zip-compressed -- note this server 404s plain HEAD
    requests, so verification must use GET) contains a real shapefile,
    57,932 rows, columns ``DAUID``/``DGUID``/``LANDAREA``/``PRUID`` in
    EPSG:3347. Cross-check: DAs whose centroid falls within Toronto's CSD
    polygon (CSDUID ``3520005``) sum to a 2021 population of 2,788,296 --
    a 0.2% near-miss against the CSD-level total of 2,794,356, expected
    from the centroid-in-polygon method missing a handful of edge DAs
    rather than a data error (see :mod:`pycensus.canada.statcan.loader`
    for the DA-level population source, PID 98-10-0015).

    Dissemination block (DB) -- StatCan's actual finest geographic unit --
    was verified live 2026-08-22 and is now implemented too:
    ``ldb_000b21a_e.zip`` (317,391,964 bytes, GET-only like the DA file)
    contains a real shapefile, 498,547 rows, columns
    ``DBUID``/``DGUID``/``DBRPLAMX``/``DBRPLAMY``/``LANDAREA``/``PRUID``,
    EPSG:3347. Unlike the other three levels, DB attribute data (real
    per-block population and dwelling counts -- not merely a
    populated/unpopulated flag) does not come from a Full Table Download
    cube; it comes from a separate flat file, the 2021 Census *Geographic
    Attribute File* (catalogue 92-151-X, see
    :data:`pycensus.canada.constants.GEOGRAPHIC_ATTRIBUTE_FILE_URL` and
    :func:`pycensus.canada.api.fetch_block_totals`). Cross-check performed
    2026-08-22: summing the GAF's real block-level population for every
    one of Toronto's 3,743 real dissemination areas exactly reproduces PID
    98-10-0015's own published DA-level population (0 mismatches), and the
    grand total across all 13,322/13,323 matched Toronto blocks
    (2,794,356) exactly matches the City of Toronto's published CSD
    population -- see the module docstring of
    :mod:`pycensus.canada.statcan.loader` for the full writeup. ``nation``
    has no single-row national boundary file verified either (StatCan
    publishes the country outline as a byproduct of the province file,
    which could be derived with ``dissolve()``, but that hasn't been
    wired up).

Source:
    https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import pandas as pd
import requests

from ... import geometry_levels
from . import constants

# Levels with a real, verified boundary source wired up (see module docstring).
IMPLEMENTED_LEVELS = ("province", "municipality", "dissemination-area", "dissemination-block")

# StatCan shapefile column holding each level's id, mapped to the common "GEOID".
_ID_COLUMN = {
    "province": "PRUID",
    "municipality": "CSDUID",
    "dissemination-area": "DAUID",
    "dissemination-block": "DBUID",
}

# Basename (inside the zip) of the shapefile for each level.
_SHP_BASENAME = {
    "province": "lpr_000b21a_e",
    "municipality": "lcsd000b21a_e",
    "dissemination-area": "lda_000b21a_e",
    "dissemination-block": "ldb_000b21a_e",
}

# Levels whose national shapefile carries a PRUID column, needed to filter
# to one province (province rows are already PRUID-keyed; municipality,
# dissemination-area, and dissemination-block rows carry PRUID as an extra
# column -- verified live 2026-08-22 for dissemination-block: ldb_000b21a_e.shp
# columns are DBUID/DGUID/DBRPLAMX/DBRPLAMY/LANDAREA/PRUID).
_HAS_PRUID_COLUMN = ("municipality", "dissemination-area", "dissemination-block")


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "statcan_boundaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_boundary_zip(level: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) the national StatCan boundary zip for one level."""
    url = constants.BOUNDARY_URLS.get(level)
    if url is None:
        raise ValueError(f"No StatCan boundary URL known for level '{level}'")

    raw_dir = _raw_dir(data_dir)
    zip_path = raw_dir / f"{level}.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()
    tmp_path = zip_path.with_suffix(".zip.part")
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    tmp_path.rename(zip_path)
    return zip_path


def _extract_shapefile(level: str, data_dir: Optional[str] = None) -> Path:
    """Extract (once, cached on disk) the shapefile sibling files for one level."""
    basename = _SHP_BASENAME[level]
    extract_dir = _raw_dir(data_dir) / level
    shp_path = extract_dir / f"{basename}.shp"
    if shp_path.exists():
        return shp_path

    zip_path = _download_boundary_zip(level, data_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if Path(m).name.lower().startswith(basename.lower() + ".")]
        if not any(m.lower().endswith(".shp") for m in members):
            raise FileNotFoundError(
                f"No '{basename}.shp' found inside {zip_path} for level '{level}' -- "
                f"StatCan may have changed the boundary file layout"
            )
        for member in members:
            target = extract_dir / Path(member).name
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    return shp_path


def _load_national(level: str, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Load the full national boundary shapefile for one level, in EPSG:4326."""
    shp_path = _extract_shapefile(level, data_dir)
    gdf = gpd.read_file(shp_path)
    id_col = _ID_COLUMN[level]
    gdf = gdf.rename(columns={id_col: "GEOID"})
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    gdf = gdf.to_crs(4326)
    keep = ["GEOID", "geometry"] + (["PRUID"] if level in _HAS_PRUID_COLUMN else [])
    return gdf[keep]


def provinces_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2021, data_dir: Optional[str] = None) -> List[str]:
    """Return the PRUIDs of every province/territory that actually intersects ``aoi``.

    Unlike ``mexico.geography.states_in_aoi``'s bounding-box heuristic,
    this tests against the real national province boundary file (already
    a single, already-cached national download -- see module docstring),
    so the result is exact rather than approximate.
    """
    provinces = _load_national("province", data_dir)
    aoi_union = aoi.to_crs(4326).union_all()
    matches = provinces[provinces.intersects(aoi_union)]
    return matches["GEOID"].tolist()


def load_boundaries(
    level: str,
    province: Optional[str] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch real StatCan 2021 boundaries for one Canada geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.canada.constants.LEVEL_FALLBACK`. See
            :data:`IMPLEMENTED_LEVELS` and the module docstring for exactly
            which levels have a real, verified boundary source.
        province: Province code (PRUID), name, or postal abbreviation.
            Required -- narrows the national shapefile to one province's
            rows (a single row for ``level="province"``, every census
            subdivision in that province for ``level="municipality"``).
        year: Vintage year. Only 2021 is wired up.
        erase_water: Accepted for interface parity with ``usa.geography``
            but not implemented (StatCan's cartographic boundary files are
            already land-only polygons).
        data_dir: Base directory for the raw StatCan boundary zip cache.
            Defaults to :data:`pycensus.canada.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column (StatCan's ``PRUID`` or
        ``CSDUID``) and geometry, reprojected to EPSG:4326.

    Raises:
        ValueError: If ``province`` is not given, or ``level`` has no
            implemented boundary source yet.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="canada")

    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(
            f"Canada boundaries for level '{level}' are not implemented yet -- only "
            f"{IMPLEMENTED_LEVELS} are wired to a real StatCan source. See "
            f"pycensus.canada.geography module docstring."
        )

    if not province:
        raise ValueError("'province' is required: StatCan boundaries are filtered per province")

    pruid = constants.province_code(province)
    national = _load_national(level, data_dir)

    if level == "province":
        gdf = national[national["GEOID"] == pruid]
    else:
        gdf = national[national["PRUID"].astype(str) == pruid].drop(columns=["PRUID"])

    return gdf.reset_index(drop=True)


def load_boundaries_multi(
    level: str,
    provinces: Optional[Union[str, List[str]]] = None,
    year: int = 2021,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more provinces, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        provinces: Province code(s)/name(s)/abbreviation(s). If ``None``,
            uses every province/territory (13 -- cheap here since the
            underlying shapefile is a single national download already).
        year: Vintage year (see :func:`load_boundaries`).
        erase_water: Accepted for interface parity, not implemented.
        aoi: If given, the result is filtered to geometries intersecting it.
        data_dir: Base directory for the raw StatCan boundary zip cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if provinces is None:
        provinces = list(constants.PROVINCE_CODES.keys())
    elif isinstance(provinces, str):
        provinces = [provinces]

    pruids = [constants.province_code(p) for p in provinces]

    parts = [load_boundaries(level, p, year, erase_water, data_dir) for p in pruids]
    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


__all__ = [
    "IMPLEMENTED_LEVELS",
    "provinces_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
]
