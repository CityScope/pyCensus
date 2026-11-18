"""Spanish Catastro INSPIRE Buildings: per-municipality ATOM downloads (building + buildingpart GML), no API key.

    from pycensus.cadaster.countries.spain.catastro import load
    b = load(aoi, cache_dir)       # unified cadaster schema (pycensus.cadaster)

The municipality index (INE code, name, zip URL, GeoRSS bounding polygon) is read once from the 52 territorial-office feeds and cached;
the municipalities whose polygon touches the AOI are downloaded (zips kept under <cache>/cadaster/es_catastro/zips) and parsed.
"""
from __future__ import annotations

import json
import logging
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from pycensus.cadaster import cache_root, map_use, source_schema, standardize, true_area_m2

logger = logging.getLogger(__name__)
ROOT_FEED = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/ES.SDGC.BU.atom.xml"
SOURCE = "es_catastro"


def _get(url, retries=5, timeout=120):
    import requests

    for i in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def municipality_index(cache_dir=None, refresh: bool = False) -> pd.DataFrame:
    """code, name, url, geometry (shapely, EPSG:4326) of every municipality of the common-regime cadaster.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        refresh: Download the index again.

    Returns:
        DataFrame of municipalities.
    """
    d = cache_root(cache_dir) / SOURCE
    d.mkdir(parents=True, exist_ok=True)
    f = d / "municipality_index.json"
    if f.is_file() and not refresh:
        rows = json.loads(f.read_text())
    else:
        root = _get(ROOT_FEED).decode("latin-1")
        feeds = sorted(set(re.findall(r'href="([^"]*atom_\d+\.xml)"', root)))
        rows = []
        for fu in feeds:
            s = _get(fu.replace("http://", "https://")).decode("latin-1")
            for e in re.findall(r"<entry>(.*?)</entry>", s, flags=re.S):
                url = re.search(r'rel="enclosure" href="([^"]+\.zip)"', e)
                poly = re.search(r"<georss:polygon>([^<]+)</georss:polygon>", e)
                title = re.search(r"<title>\s*([^<]+?)\s*</title>", e)
                if not url or not poly:
                    continue
                v = [float(x) for x in poly.group(1).split()]
                rows.append({"code": re.search(r"/(\d{5})-", url.group(1)).group(1) if re.search(r"/(\d{5})-", url.group(1)) else "",
                             "name": title.group(1).replace(" buildings", "") if title else "", "url": url.group(1),
                             "polygon": list(zip(v[1::2], v[0::2]))})   # GeoRSS is lat lon
        f.write_text(json.dumps(rows))
    df = pd.DataFrame(rows)
    df["geometry"] = [shapely.Polygon(p) for p in df.polygon]
    return df.drop(columns="polygon")


def _download(url: str, d: Path) -> Path:
    z = d / Path(url).name
    if not z.is_file() or z.stat().st_size == 0:
        z.write_bytes(_get(url))
    return z


def _parse(z: Path) -> gpd.GeoDataFrame:
    """One municipality zip -> buildings in the unified schema."""
    import pyogrio

    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    bname = next((n for n in names if n.endswith(".building.gml")), None)
    pname = next((n for n in names if n.endswith(".buildingpart.gml")), None)
    if bname is None:
        return gpd.GeoDataFrame()
    b = pyogrio.read_dataframe(f"/vsizip/{z}/{bname}")
    if b.empty:
        return gpd.GeoDataFrame()
    b["footprint_m2"] = true_area_m2(b.geometry)
    if pname:
        p = pyogrio.read_dataframe(f"/vsizip/{z}/{pname}")
        if len(p):
            p["bid"] = p["gml_id"].astype(str).str.replace(r"_part\d+$", "", regex=True)
            p["a"] = true_area_m2(p.geometry)
            fa = pd.to_numeric(p["numberOfFloorsAboveGround"], errors="coerce").fillna(0)
            fb = pd.to_numeric(p.get("numberOfFloorsBelowGround"), errors="coerce").fillna(0) if "numberOfFloorsBelowGround" in p else 0 * fa
            g = pd.DataFrame({"bid": p["bid"], "a": p["a"], "fa": fa * p["a"], "fb": fb * p["a"]}).groupby("bid").sum()
            b = b.merge(g, left_on="gml_id", right_index=True, how="left")
            b["floors_above"] = b["fa"] / b["a"].where(b["a"] > 0)
            b["floors_below"] = b["fb"] / b["a"].where(b["a"] > 0)
            b["parts_built"] = b["fa"]
    off = pd.to_numeric(b.get("value"), errors="coerce") if "value" in b else np.nan
    gross = b.get("officialAreaReference", pd.Series("", index=b.index)).astype(str).str.contains("grossFloorArea", na=False)
    b["built_area_m2"] = np.where(gross & (off > 0), off, b.get("parts_built", np.nan))
    b["built_area_method"] = np.where(gross & (off > 0), "official", "floors_x_footprint")
    sch = source_schema(SOURCE)
    b["use_original"] = b.get("currentUse")
    b["use_class"] = map_use(b["use_original"], sch["use_map"])
    b["dwellings"] = pd.to_numeric(b.get("numberOfDwellings"), errors="coerce")
    b["units"] = pd.to_numeric(b.get("numberOfBuildingUnits"), errors="coerce")
    b["year_built"] = pd.to_datetime(b.get("beginning"), errors="coerce").dt.year
    b["building_id"] = b["gml_id"].astype(str)
    return standardize(b, SOURCE, "ESP")


def load(aoi: gpd.GeoDataFrame, cache_dir=None, workers: int = 8) -> gpd.GeoDataFrame:
    """Spanish common-regime cadaster buildings (INSPIRE) of every municipality touching ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        workers: Parallel downloads.

    Returns:
        The buildings.
    """
    idx = municipality_index(cache_dir)
    a = aoi.to_crs(4326).union_all()
    sel = idx[shapely.intersects(np.asarray(idx.geometry), a)]
    d = cache_root(cache_dir) / SOURCE / "zips"
    d.mkdir(parents=True, exist_ok=True)
    logger.info(f"es_catastro: {len(sel)} municipalities touch the AOI")
    def one(u):
        try:
            return _download(u, d)
        except Exception as exc:  # noqa: BLE001 -- one municipality missing leaves the others (its cells fall back to an equal split)
            logger.warning(f"es_catastro: {u} not downloaded ({type(exc).__name__}: {str(exc)[:120]})")
            return None

    with ThreadPoolExecutor(workers) as ex:
        zips = [z for z in ex.map(one, sel.url) if z is not None]

    def parse(z):
        try:
            return _parse(z)
        except Exception as exc:  # noqa: BLE001 -- a corrupt zip: dropped and logged, downloaded again next time
            logger.warning(f"es_catastro: {z.name} unreadable ({type(exc).__name__}: {str(exc)[:120]}); removed")
            z.unlink(missing_ok=True)
            return gpd.GeoDataFrame()

    parts = [g for g in map(parse, zips) if len(g)]
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326) if parts else standardize(gpd.GeoDataFrame(geometry=[], crs=4326), SOURCE, "ESP")


def prefetch(cache_dir=None, workers: int = 8, provinces=None) -> int:
    """Download every municipality zip (or those of `provinces`, INE 2-digit codes) without parsing. Returns the number of zips.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        workers: Parallel downloads.
        provinces: INE 2-digit province codes; ``None`` = all.
    """
    idx = municipality_index(cache_dir)
    if provinces:
        idx = idx[idx["code"].astype(str).str[:2].isin(set(provinces))] if "code" in idx.columns else idx
    d = cache_root(cache_dir) / SOURCE / "zips"
    d.mkdir(parents=True, exist_ok=True)
    ok = [0]

    def one(u):
        try:
            _download(u, d); ok[0] += 1
            if ok[0] % 250 == 0:
                logger.info(f"es_catastro prefetch: {ok[0]}/{len(idx)}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"es_catastro: {u} not downloaded ({type(exc).__name__}: {str(exc)[:120]})")

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, idx.url))
    return ok[0]
