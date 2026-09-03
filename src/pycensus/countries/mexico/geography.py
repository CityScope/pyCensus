"""Boundary fetching shared by every Mexico census source.

Technical aspects:
    Boundaries come from INEGI's Marco Geoestadistico Nacional (MGN), a
    per-state shapefile bundle (see
    :data:`pycensus.mexico.constants.MARCO_GEOESTADISTICO_URLS`, verified
    2026-08-19). Real boundaries are implemented for ``state``,
    ``municipality``, ``ageb`` (urban AGEB only, ``{state}a.shp``), and
    ``block`` (urban manzana, ``{state}m.shp``) -- the levels INEGI's
    per-state MGN zip covers cleanly and that pair with a real
    attribute-side source (ITER for state/municipality, RESAGEBURB for
    AGEB/block, see :mod:`pycensus.mexico.api`).

    ``block`` pairing was live-verified end-to-end 2026-08-22 against
    Jalisco (state "14"): joining
    :func:`pycensus.mexico.api.fetch_block_totals`'s ``GEOID`` (16-digit
    ENTIDAD+MUN+LOC+AGEB+MZA) against the real ``14m.shp`` boundary's
    ``CVEGEO`` gives a 99.55% match rate restricted to
    ``AMBITO == "Urbana"`` boundary blocks (95,104 of 95,536 urban blocks
    matched) -- the only blocks RESAGEBURB, an urban-only source, can
    ever cover. The residual unmatched boundary blocks are almost
    entirely ``AMBITO == "Rural"`` (35,506 of 35,938 unmatched), exactly
    the documented RESAGEBURB urban-only gap, not a pairing bug. Summing
    ``POBTOT`` over every real block row for MUN "039" (Guadalajara)
    gives 1,385,621 -- identical to the already-verified AGEB-level
    total for the same municipality (see
    :func:`pycensus.mexico.api.fetch_ageb_totals`'s docstring),
    confirming the attribute side is correct independent of the boundary
    join; only ~0.8% of that population sum (162 of 13,791 blocks) falls
    on blocks that don't match the 2018-vintage MGN boundary, an
    expected small vintage/edge-case gap. Rural AGEB (``{state}ar.shp``)
    is not wired up -- RESAGEBURB only covers urban AGEBs.
    ``nation``/``locality`` are not implemented (no exact INEGI national
    boundary shapefile URL was verified, and locality boundaries are
    polygon *or* point depending on population per INEGI's own
    documentation, which needs handling this module doesn't attempt).

    Downloaded zips are cached under ``<data_dir>/raw/marco_geoestadistico/``
    (persistent across runs, independent of :mod:`pycensus.cache`'s
    parquet cache) and extracted once per state.

    Every boundary fetch here is stateless from :mod:`pycensus.cache`'s
    point of view - persistence of the final merged (geometry + attribute)
    result is handled entirely by :mod:`pycensus.cache`, one level higher
    in the call stack (in ``inegi/loader.py``), not by this module.

Source:
    https://www.inegi.org.mx/temas/mg/
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

# Geography hierarchy for census data queries: parent-child relationships.
GEO_HIERARCHIES = {
    "municipality": ["state", "municipality"],
    "ageb": ["state", "municipality", "ageb"],
    "block": ["state", "municipality", "ageb", "block"],
    "state": ["state"],
    "nation": ["nation"],
}

# Levels with a real, verified boundary source wired up (see module docstring).
IMPLEMENTED_LEVELS = ("state", "municipality", "ageb", "block")

ERASE_WATER: dict = {
    "nation": False,
    "state": False,
    "municipality": False,
    "locality": False,
    "ageb": True,
    "block": True,
}


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "marco_geoestadistico"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_state_mgn_zip(state_code: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) the Marco Geoestadistico zip for one state."""
    url = constants.MARCO_GEOESTADISTICO_URLS.get(state_code)
    if url is None:
        raise ValueError(f"No Marco Geoestadistico URL known for state '{state_code}'")

    raw_dir = _raw_dir(data_dir)
    zip_path = raw_dir / f"mg_{state_code}.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    response = requests.get(url, stream=True, timeout=180)
    response.raise_for_status()
    tmp_path = zip_path.with_suffix(".zip.part")
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    tmp_path.rename(zip_path)
    return zip_path


def _extract_shapefile(zip_path: Path, state_code: str, level: str, data_dir: Optional[str] = None) -> Path:
    """Extract just the shapefile sibling files for one level from the state MGN zip."""
    suffix = constants.MARCO_GEO_SHAPEFILE_SUFFIX.get(level)
    if suffix is None:
        raise ValueError(f"No Marco Geoestadistico shapefile suffix known for level '{level}'")

    basename = f"{state_code}{suffix}"
    extract_dir = _raw_dir(data_dir) / state_code
    shp_path = extract_dir / f"{basename}.shp"
    if shp_path.exists():
        return shp_path

    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = [
            m for m in zf.namelist()
            if Path(m).name.lower().startswith(basename.lower() + ".")
        ]
        if not shp_path.exists() and not any(m.lower().endswith(".shp") for m in members):
            raise FileNotFoundError(
                f"No '{basename}.shp' found inside {zip_path} for level '{level}'"
            )
        for member in members:
            target = extract_dir / Path(member).name
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    return shp_path


def states_in_aoi(aoi: gpd.GeoDataFrame, year: int = 2020) -> List[str]:
    """Return the INEGI codes of every state that plausibly intersects ``aoi``.

    Note:
        A precise version of this would test against a real national state
        boundary layer; no cheap verified one is wired up (only the
        heavier per-state Marco Geoestadistico zips, see module
        docstring), so this instead does a bounding-box test against
        :data:`pycensus.mexico.constants.STATE_BBOX` (each state's
        approximate rectangular extent, padded by
        :data:`pycensus.mexico.constants.STATE_BBOX_PADDING_DEG` to stay
        safely over-inclusive). This is deliberately coarse -- for an AOI
        near a state border it may include a neighboring state that isn't
        actually needed -- but it reliably narrows a whole-country, 32-state
        candidate list (and the ~150s/state MGN + ITER download that goes
        with each one) down to the handful of states an AOI like a single
        city actually touches, without ever risking a false negative that
        would silently drop real data.
    """
    aoi_union = aoi.to_crs(4326).union_all()
    minx, miny, maxx, maxy = aoi_union.bounds
    pad = constants.STATE_BBOX_PADDING_DEG

    matches = []
    for code, (bx0, by0, bx1, by1) in constants.STATE_BBOX.items():
        if minx <= bx1 + pad and maxx >= bx0 - pad and miny <= by1 + pad and maxy >= by0 - pad:
            matches.append(code)
    return matches


def load_boundaries(
    level: str,
    state: Optional[str] = None,
    year: int = 2020,
    erase_water: Optional[bool] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch real INEGI Marco Geoestadistico boundaries for one Mexico geography level.

    Args:
        level: Standard geometry level name, resolved through
            :data:`pycensus.mexico.constants.LEVEL_FALLBACK`. See
            :data:`IMPLEMENTED_LEVELS` and the module docstring for which
            levels have a real, verified boundary source.
        state: State code, name, or abbreviation. Required (Marco
            Geoestadistico is distributed per-state).
        year: Vintage year. Only 2020 data is wired up; other values are
            accepted but ignored (INEGI's per-state MGN zip used here is a
            2018-vintage boundary file, the geometry INEGI itself pairs
            with the 2020 census in its "descarga por entidad" catalog).
        erase_water: Accepted for interface parity with ``usa.geography``
            but not implemented (INEGI's MGN shapefiles are already
            land-only polygons).
        data_dir: Base directory for the raw Marco Geoestadistico zip
            cache. Defaults to :data:`pycensus.mexico.constants.DEFAULT_DATA_DIR`.

    Returns:
        GeoDataFrame with a ``GEOID`` column (INEGI's ``CVEGEO``) and
        geometry, reprojected to EPSG:4326.

    Raises:
        KeyError: If ``level`` does not resolve to a known geography level.
        ValueError: If ``state`` is not given, or ``level`` has no
            implemented boundary source yet.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK, country="mexico")

    if level not in IMPLEMENTED_LEVELS:
        raise ValueError(
            f"Mexico boundaries for level '{level}' are not implemented yet -- only "
            f"{IMPLEMENTED_LEVELS} are wired to a real INEGI source. See "
            f"pycensus.mexico.geography module docstring."
        )

    if not state:
        raise ValueError("'state' is required: Marco Geoestadistico boundaries are distributed per state")

    state_code = utils.state_code(state)
    zip_path = _download_state_mgn_zip(state_code, data_dir)
    shp_path = _extract_shapefile(zip_path, state_code, level, data_dir)

    gdf = gpd.read_file(shp_path)
    gdf = gdf.rename(columns={"CVEGEO": "GEOID"})
    gdf["GEOID"] = gdf["GEOID"].astype(str)
    gdf = gdf.to_crs(4326)

    return gdf[["GEOID", "geometry"]]


def load_boundaries_multi(
    level: str,
    states: Optional[Union[str, List[str]]] = None,
    year: int = 2020,
    erase_water: Optional[bool] = None,
    aoi: Optional[gpd.GeoDataFrame] = None,
    data_dir: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Fetch and concatenate boundaries across one or more states, optionally clipped to an AOI.

    Args:
        level: Standard geometry level name.
        states: State code(s), name(s), or abbreviation(s). If None, uses
            every state (32 downloads -- slow; prefer passing ``aoi`` or
            explicit ``states`` for anything short of a full-country run).
        year: Vintage year (see :func:`load_boundaries`).
        erase_water: Accepted for interface parity, not implemented.
        aoi: If given, the result is filtered to geometries intersecting it.
        data_dir: Base directory for the raw Marco Geoestadistico zip cache.

    Returns:
        GeoDataFrame with a ``GEOID`` column, geometry, in EPSG:4326.
    """
    if states is None:
        states = list(constants.STATE_CODES.keys())
    elif isinstance(states, str):
        states = [states]

    state_codes = [utils.state_code(s) for s in states]

    parts = [load_boundaries(level, sc, year, erase_water, data_dir) for sc in state_codes]

    result = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)

    if aoi is not None:
        result = result[result.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)

    return result


__all__ = [
    "GEO_HIERARCHIES",
    "ERASE_WATER",
    "IMPLEMENTED_LEVELS",
    "states_in_aoi",
    "load_boundaries",
    "load_boundaries_multi",
]
