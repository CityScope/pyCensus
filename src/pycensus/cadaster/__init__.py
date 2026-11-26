"""Cadaster / building sources: one row per building with its built floor area, in one unified schema.

Layout: ``pycensus/cadaster/<country>/<source>/`` with a ``loader.py`` (download + ``load(aoi, cache_dir)``) and a ``schema.json`` (how the
source's own fields map onto the global schema ``pycensus/cadaster/global_schema.json``, and its use codes onto the unified
``use_class``). The worldwide fallback is GlobalBuildingAtlas (``cadaster/worldwide/gba``, footprints + heights everywhere).

    from pycensus import cadaster
    b = cadaster.load_buildings("ESP", aoi, cache_dir)        # every source covering the AOI, GBA where no cadaster has buildings
    b = cadaster.load("es_catastro", aoi, cache_dir)          # one source

None of the sources needs an API key.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
from pathlib import Path
from typing import Iterable, List, Optional

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
GLOBAL_SCHEMA = json.loads((Path(__file__).resolve().parent / "global_schema.json").read_text())
COLUMNS = [f["name"] for f in GLOBAL_SCHEMA["fields"]]
USE_CLASSES = next(f["values"] for f in GLOBAL_SCHEMA["fields"] if f["name"] == "use_class")
#: per use class: can its buildings hold residents / jobs (`global_schema.json`, "use_classes")
USE_CLASS_RULES = {k: v for k, v in GLOBAL_SCHEMA["use_classes"].items() if not k.startswith("_")}
assert set(USE_CLASS_RULES) == set(USE_CLASSES), "use_classes of global_schema.json must list exactly the values of the use_class field"
FLOOR_HEIGHT_M = float(GLOBAL_SCHEMA["floor_height_m"])

#: source key -> module (relative to pycensus.cadaster)
SOURCES = {
    "es_catastro": "countries.spain.catastro",
    "es_gipuzkoa": "countries.spain.gipuzkoa",
    "es_araba": "countries.spain.araba",
    "es_bizkaia": "countries.spain.bizkaia",
    "es_navarra": "countries.spain.navarra",
    "us_nsi": "countries.usa.nsi",
    "ca_toronto_massing": "countries.canada.toronto_massing",
    "de_hamburg_lod2": "countries.germany.hamburg_lod2",
    "gba": "worldwide.gba",
}
#: the cadaster sources of each country, best first (GBA fills what none of them covers)
BY_COUNTRY = {"ESP": ["es_gipuzkoa", "es_araba", "es_bizkaia", "es_navarra", "es_catastro"], "USA": ["us_nsi"], "CAN": ["ca_toronto_massing"], "DEU": ["de_hamburg_lod2"]}


def source_schema(source: str) -> dict:
    """The schema JSON of one cadaster source.

    Args:
        source: Source name (a key of ``SOURCES``).

    Returns:
        The schema as a dict.
    """
    return json.loads((Path(__file__).resolve().parent / SOURCES[source].replace(".", "/") / "schema.json").read_text())


def cache_root(cache_dir) -> Path:
    """The cadaster cache folder (created): ``<cache_dir or the pycensus cache>/cadaster``.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The folder.
    """
    from pycensus.cache import default_cache_dir

    d = Path(cache_dir or default_cache_dir()) / "cadaster"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _valid(aoi: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """EPSG:4326 copy with valid geometries (a self-touching boundary breaks the unions below)."""
    a = aoi.to_crs(4326).copy()
    a["geometry"] = a.geometry.make_valid()
    return a


def aoi_key(aoi: gpd.GeoDataFrame) -> str:
    """Short hash of an area's geometry, used to name its cached files.

    Args:
        aoi: Area of interest (GeoDataFrame).

    Returns:
        12-character key.
    """
    a = _valid(aoi)
    return hashlib.sha1(a.union_all().wkb).hexdigest()[:12]


def true_area_m2(geoms: gpd.GeoSeries) -> np.ndarray:
    """Polygon areas in m2 from any CRS (local equal-area projection).

    Args:
        geoms: Polygons in any CRS.

    Returns:
        Areas in m2.
    """
    g = geoms.to_crs(4326)
    if g.empty:
        return np.zeros(0)
    x0, y0, x1, y1 = g.total_bounds   # centre of the projection: the bounds' centre (a union of every footprint is slow and fails on invalid ones)
    laea = f"+proj=laea +lat_0={(y0 + y1) / 2} +lon_0={(x0 + x1) / 2} +datum=WGS84 +units=m"
    return g.to_crs(laea).area.to_numpy()


def map_use(codes: Iterable, use_map: dict, prefix_match: bool = False) -> np.ndarray:
    """Source use codes -> unified use_class (unknown when unmapped). With `prefix_match`, the longest mapped prefix of each code wins.

    Args:
        codes: Source use codes.
        use_map: ``{source code: use_class}``.
        prefix_match: Match code prefixes.

    Returns:
        Array of use classes.
    """
    keys = sorted(use_map, key=len, reverse=True)
    out = []
    for c in codes:
        s = "" if c is None or (isinstance(c, float) and np.isnan(c)) else str(c)
        if prefix_match:
            out.append(next((use_map[k] for k in keys if s.startswith(k)), "unknown"))
        else:
            out.append(use_map.get(s, "unknown"))
    return np.asarray(out, dtype=object)


def standardize(df: gpd.GeoDataFrame, source: str, country: str) -> gpd.GeoDataFrame:
    """Every global column present (null where unknown), in schema order, EPSG:4326; built_area_m2 filled from floors x footprint or
    height x footprint when the source gave no floor area.

    Args:
        df: Buildings of one source.
        source: Source name.
        country: Country code.

    Returns:
        The buildings in the unified schema.
    """
    df = df.copy()
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    df["source"], df["country"] = source, country
    ba = pd.to_numeric(df["built_area_m2"], errors="coerce")
    fp = pd.to_numeric(df["footprint_m2"], errors="coerce")
    fl = pd.to_numeric(df["floors_above"], errors="coerce")
    h = pd.to_numeric(df["height_m"], errors="coerce")
    meth = df["built_area_method"].astype(object).where(ba.notna() & (ba > 0), None)
    a = ba.where(ba > 0)
    use_fl = a.isna() & (fl > 0) & (fp > 0)
    a = a.where(~use_fl, fp * fl); meth = meth.where(~use_fl, "floors_x_footprint")
    use_h = a.isna() & (h > 0) & (fp > 0)
    a = a.where(~use_h, fp * np.maximum(h / FLOOR_HEIGHT_M, 1.0)); meth = meth.where(~use_h, "height_x_footprint")
    use_fp = a.isna() & (fp > 0)
    a = a.where(~use_fp, fp); meth = meth.where(~use_fp, "footprint_only")
    df["built_area_m2"], df["built_area_method"] = a, meth
    df["use_class"] = df["use_class"].where(df["use_class"].isin(USE_CLASSES), "unknown")
    out = gpd.GeoDataFrame(df[COLUMNS + ["geometry"]], geometry="geometry", crs=df.crs).to_crs(4326)
    return out.reset_index(drop=True)


def load(source: str, aoi: gpd.GeoDataFrame, cache_dir=None, refresh: bool = False) -> gpd.GeoDataFrame:
    """One source's buildings inside `aoi` (centroid inside), unified schema, cached as parquet per AOI.

    Args:
        source: Source name (a key of ``SOURCES``).
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        refresh: Ignore the cached file.

    Returns:
        The buildings (unified schema).
    """
    aoi = _valid(aoi)
    f = cache_root(cache_dir) / "_aoi" / f"{source}_{aoi_key(aoi)}.parquet"
    if f.is_file() and not refresh:
        return gpd.read_parquet(f)
    mod = importlib.import_module(f"{__name__}.{SOURCES[source]}.loader")
    b = mod.load(aoi, cache_dir=cache_dir)
    if len(b):
        import shapely

        c = b.geometry.representative_point() if b.geom_type.iloc[0] != "Point" else b.geometry
        b = b[shapely.contains_xy(aoi.to_crs(4326).union_all(), c.x.to_numpy(), c.y.to_numpy())].reset_index(drop=True)
    f.parent.mkdir(parents=True, exist_ok=True)
    b.to_parquet(f)
    logger.info(f"cadaster {source}: {len(b):,} buildings in the AOI, built area {pd.to_numeric(b['built_area_m2']).sum() / 1e6:,.2f} km2")
    return b


def load_buildings(country: str, aoi: gpd.GeoDataFrame, cache_dir=None, sources: Optional[List[str]] = None, gba_fill: bool = True,
                   fill_resolution: int = 8) -> gpd.GeoDataFrame:
    """Every cadaster source of `country` covering the AOI (best first: a building of a later source is dropped where an earlier one already
    has buildings in the same res-`fill_resolution` H3 cell), then GBA in the cells no cadaster covers. Unified schema.

    Args:
        country: Country code (keys of ``BY_COUNTRY``).
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        sources: Sources in priority order; ``None`` = the country's list.
        gba_fill: Fill cells no cadaster covers with GBA buildings.
        fill_resolution: H3 resolution of the coverage test.

    Returns:
        The buildings (unified schema).
    """
    import h3ronpy.vector as hv

    parts, covered = [], np.zeros(0, np.uint64)
    names = list(sources if sources is not None else BY_COUNTRY.get(country, [])) + (["gba"] if gba_fill else [])
    for s in names:
        try:
            b = load(s, aoi, cache_dir)
        except Exception as exc:  # noqa: BLE001 -- one source failing leaves the others (and GBA) in place
            logger.warning(f"cadaster {s} not loaded: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        if b.empty:
            continue
        c = b.geometry.representative_point() if b.geom_type.iloc[0] != "Point" else b.geometry
        cells = np.asarray(hv.coordinates_to_cells(c.y.to_numpy(), c.x.to_numpy(), fill_resolution)).astype(np.uint64)
        new = ~np.isin(cells, covered)
        if (~new).any():
            logger.info(f"cadaster {s}: {int((~new).sum()):,} buildings in cells an earlier source covers -- dropped")
        parts.append(b[new]); covered = np.union1d(covered, np.unique(cells[new]))
    if not parts:
        return standardize(gpd.GeoDataFrame(geometry=[], crs=4326), "none", country)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
