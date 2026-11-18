"""USACE National Structure Inventory: per-county GeoJSON from the public API (no key), cached per county, unified cadaster schema.

Points, not footprints: built_area_m2 is the reported total floor area (sqft), footprint_m2 the reported footprint. NSI also estimates the
night / day population of each structure (population_night / population_day)."""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd

from ... import cache_root, map_use, source_schema, standardize

logger = logging.getLogger(__name__)
API = "https://nsi.sec.usace.army.mil/nsiapi/structures?fips={fips}"
SOURCE = "us_nsi"
SQFT = 0.09290304


def county(fips: str, cache_dir=None) -> gpd.GeoDataFrame:
    """National Structure Inventory buildings of one county (NSI API, no key), cached.

    Args:
        fips: 5-digit county FIPS code.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The structures.
    """
    import requests

    d = cache_root(cache_dir) / SOURCE
    d.mkdir(parents=True, exist_ok=True)
    pq = d / f"{fips}.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    for i in range(6):
        try:
            r = requests.get(API.format(fips=fips), timeout=600)
            r.raise_for_status()
            fc = r.json()
            break
        except Exception:  # noqa: BLE001
            if i == 5:
                raise
            time.sleep(2 ** i)
    feats = fc.get("features", [])
    if not feats:
        out = standardize(gpd.GeoDataFrame(geometry=[], crs=4326), SOURCE, "USA")
        out.to_parquet(pq)
        return out
    p = pd.DataFrame([f["properties"] for f in feats])
    out = _unified(gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["x"], p["y"]), crs=4326))
    out.to_parquet(pq)
    return out


STATE_ZIP = "https://nsi.sec.usace.army.mil/downloads/nsi_2022/nsi_2022_{fips}.gpkg.zip"


def state(state_fips: str, cache_dir=None) -> gpd.GeoDataFrame:
    """A whole state from NSI's bulk GeoPackage (one zip per state, no key): much faster than the per-county API for large areas.
    The bulk file has no footprint / height / housing-unit fields (they stay null).

    Args:
        state_fips: 2-digit state FIPS code.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The structures.
    """
    import requests
    import pyogrio

    d = cache_root(cache_dir) / SOURCE
    d.mkdir(parents=True, exist_ok=True)
    pq = d / f"state_{state_fips}.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    z = d / f"nsi_2022_{state_fips}.gpkg.zip"
    if not z.is_file():
        part = z.with_suffix(".part")
        for attempt in range(10):   # resumable: a dropped connection continues where it stopped
            have = part.stat().st_size if part.is_file() else 0
            try:
                with requests.get(STATE_ZIP.format(fips=state_fips), stream=True, timeout=900, headers={"Range": f"bytes={have}-"} if have else {}) as r:
                    if r.status_code == 416:
                        break
                    r.raise_for_status()
                    with open(part, "ab" if have and r.status_code == 206 else "wb") as fh:
                        for blk in r.iter_content(1 << 22):
                            fh.write(blk)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"NSI {state_fips}: download interrupted ({type(exc).__name__}), resuming")
                time.sleep(min(60, 5 * (attempt + 1)))
        else:
            raise RuntimeError(f"NSI {state_fips}: download failed")
        import zipfile as _zf
        _zf.ZipFile(part).testzip()   # a truncated file fails here instead of being cached
        part.replace(z)
    import zipfile
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".gpkg"))
    g = pyogrio.read_dataframe(f"/vsizip/{z}/{name}")
    out = _unified(g.to_crs(4326))
    out.to_parquet(pq)
    return out


def _unified(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    num = lambda c: pd.to_numeric(g.get(c), errors="coerce") if c in g else pd.Series(np.nan, index=g.index)  # noqa: E731
    g["building_id"] = g["bid"].astype(str) if "bid" in g else g["fd_id"].astype(str)
    g["footprint_m2"] = num("ftprntsqft") * SQFT
    g["floors_above"] = num("num_story")
    g["height_m"] = num("bldheight")   # metres (a 2-storey house is ~5.7)
    g["built_area_m2"] = num("sqft") * SQFT
    g["built_area_method"] = np.where(g["built_area_m2"] > 0, "reported_floor_area", None)
    g["use_original"] = g.get("occtype")
    g["use_class"] = map_use(g["use_original"], source_schema(SOURCE)["use_map"], prefix_match=True)
    g["dwellings"] = num("resunits")
    g["population_night"] = num("pop2amu65").fillna(0) + num("pop2amo65").fillna(0)
    g["population_day"] = num("pop2pmu65").fillna(0) + num("pop2pmo65").fillna(0)
    g["year_built"] = num("med_yr_blt")
    return standardize(g, SOURCE, "USA")


def load(aoi: gpd.GeoDataFrame, cache_dir=None, workers: int = 4) -> gpd.GeoDataFrame:
    """Every county intersecting the AOI (TIGER counties from pycensus.countries.usa.geography).

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        workers: Parallel county downloads.

    Returns:
        The structures (unified schema).
    """
    from ....countries.usa.geography import load_boundaries

    a = aoi.to_crs(4326)
    states = sorted({s for s in _states_for(a)})
    fips = []
    for st in states:
        c = load_boundaries("county", st, 2023).to_crs(4326)
        fips += c[c.intersects(a.union_all())]["GEOID"].astype(str).tolist()
    with ThreadPoolExecutor(workers) as ex:
        parts = [p for p in ex.map(lambda f: county(f, cache_dir), fips) if len(p)]
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326) if parts else standardize(gpd.GeoDataFrame(geometry=[], crs=4326), SOURCE, "USA")


def _states_for(aoi):
    from ....countries.usa.geography import load_boundaries

    s = load_boundaries("state", None, 2023).to_crs(4326)
    return s[s.intersects(aoi.union_all())]["GEOID"].astype(str).tolist()
