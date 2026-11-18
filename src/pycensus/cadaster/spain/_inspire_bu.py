"""Shared reader for the foral cadasters' INSPIRE Buildings downloads (Álava, Bizkaia, Navarra): zips of GML files listed in an ATOM feed,
downloaded once, parsed into one province-wide parquet in the unified cadaster schema."""
from __future__ import annotations

import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import cache_root, standardize, true_area_m2

logger = logging.getLogger(__name__)


def feed_links(feed_url: str, pattern: str) -> List[str]:
    """Download links of an ATOM feed matching `pattern` (regex on the href).

    Args:
        feed_url: ATOM feed URL.
        pattern: Regex the link must match.

    Returns:
        Sorted unique links.
    """
    import requests

    r = requests.get(feed_url, timeout=120)
    r.raise_for_status()
    return sorted(set(h for h in re.findall(r'href="([^"]+)"', r.text) if re.search(pattern, h)))


def _download(url: str, dest: Path) -> Path:
    import requests

    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    import time

    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(6):   # the foral servers reset connections under load: retry with a growing pause
        try:
            with requests.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(part, "wb") as fh:
                    for b in r.iter_content(1 << 22):
                        fh.write(b)
            part.replace(dest)
            return dest
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == 5:
                raise
            logger.info(f"download {url.rsplit('/', 1)[-1]} retry {attempt + 1} ({type(exc).__name__})")
            time.sleep(5 * (attempt + 1))


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)


def _year(df, cols):
    for c in cols:
        if c in df.columns:
            y = pd.to_datetime(df[c], errors="coerce", utc=True).dt.year.astype(float)
            if y.notna().any():
                return y.where((y > 1000) & (y < 2100))
    return pd.Series(np.nan, index=df.index)


def parse_gml(path: str, year_cols) -> gpd.GeoDataFrame:
    """Buildings of one INSPIRE Building GML file (id, footprint, floors, dwellings, year built, use).

    Args:
        path: GML file.
        year_cols: GML fields holding the construction year, in order of preference.

    Returns:
        GeoDataFrame of buildings.
    """
    import pyogrio

    b = pyogrio.read_dataframe(path, layer="Building")
    if b.empty:
        return b
    b = b[b.geometry.notna() & ~b.geometry.is_empty].copy()
    b["geometry"] = b.geometry.make_valid()
    out = gpd.GeoDataFrame({"building_id": (b["localId"] if "localId" in b.columns else b["gml_id"]).astype(str)}, geometry=b.geometry.values, crs=b.crs)
    out["footprint_m2"] = true_area_m2(out.geometry)
    out["height_m"] = _num(b, "value").where(lambda x: x > 0).to_numpy()
    out["floors_above"] = _num(b, "numberOfFloorsAboveGround").where(lambda x: x > 0).to_numpy()   # 0 = unknown (Navarra): height / 3 instead
    out["floors_below"] = _num(b, "numberOfFloorsBelowGround").to_numpy()
    out["dwellings"] = _num(b, "numberOfDwellings").to_numpy()
    out["units"] = _num(b, "numberOfBuildingUnits").to_numpy()
    out["year_built"] = _year(b, year_cols).to_numpy()
    out["use_class"] = np.where(out["dwellings"] > 0, "residential", "unknown")
    return out.to_crs(4326)


def province(source: str, urls: List[str], members_pattern: str, year_cols, cache_dir=None, workers: int = 3) -> gpd.GeoDataFrame:
    """Every zip of `urls` downloaded into the cache, every GML member matching `members_pattern` parsed; one parquet per source.

    Args:
        source: Source name (cache sub-folder).
        urls: Zip URLs.
        members_pattern: Regex of the GML members to read.
        year_cols: GML fields holding the construction year.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        workers: Parallel downloads.

    Returns:
        All the buildings of the province.
    """
    d = cache_root(cache_dir) / source
    d.mkdir(parents=True, exist_ok=True)
    pq = d / "buildings.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    zd = d / "zips"
    zd.mkdir(exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        zips = list(ex.map(lambda u: _download(u, zd / u.rsplit("/", 1)[-1]), urls))
    parts = []
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                members = [n for n in zf.namelist() if re.search(members_pattern, n)]
            for m in members:
                parts.append(parse_gml(f"/vsizip/{z}/{m}", year_cols))
        except Exception as exc:  # noqa: BLE001 -- a corrupt zip is deleted (downloaded again next time) and skipped
            logger.warning(f"{source}: {z.name} not parsed ({type(exc).__name__}: {str(exc)[:150]}) -- deleted")
            z.unlink(missing_ok=True)
    parts = [p for p in parts if len(p)]
    b = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326) if parts else gpd.GeoDataFrame(geometry=[], crs=4326)
    out = standardize(b, source, "ESP")
    out.to_parquet(pq)
    logger.info(f"{source}: {len(out):,} buildings from {len(zips)} zips, built area {out['built_area_m2'].sum() / 1e6:,.1f} km2")
    return out


def load_bbox(b: gpd.GeoDataFrame, aoi: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The buildings inside the bounding box of ``aoi``.

    Args:
        b: Buildings.
        aoi: Area of interest (GeoDataFrame).

    Returns:
        The selected buildings.
    """
    a = aoi.to_crs(4326).total_bounds
    return b.cx[a[0]:a[2], a[1]:a[3]].reset_index(drop=True)
