"""City of Toronto 3D Massing (open data, latest yearly shapefile): building footprints (massing parts) with lidar / site-plan heights, no API key.
No use or floor counts: built area = footprint x height / floor height (pycensus.cadaster.standardize). City of Toronto only; GBA fills the rest of
the metro area (pycensus.cadaster.load_buildings)."""
from __future__ import annotations

import logging
import re

import geopandas as gpd
import pandas as pd

from ... import cache_root, standardize, true_area_m2

logger = logging.getLogger(__name__)
SOURCE = "ca_toronto_massing"
PACKAGE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=3d-massing"


def _latest_url() -> tuple[str, str]:
    """(file name, url) of the newest yearly '3DMassingShapefile_<year>_WGS84.zip' resource."""
    import requests

    res = requests.get(PACKAGE, timeout=120).json()["result"]["resources"]
    shp = [(int(m.group(1)), r) for r in res if (m := re.match(r"3DMassingShapefile_(\d{4})_WGS84\.zip$", r["name"]))]
    year, r = max(shp, key=lambda t: t[0])
    return r["name"].lower(), r["url"]


def _city(cache_dir=None) -> gpd.GeoDataFrame:
    d = cache_root(cache_dir) / SOURCE
    pq = d / "buildings.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    zd = d / "zips"
    zd.mkdir(parents=True, exist_ok=True)
    have = sorted(zd.glob("3dmassingshapefile_*_wgs84.zip"))
    if have:
        z = have[-1]
    else:
        import requests

        name, url = _latest_url()
        z = zd / name
        with requests.get(url, stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(z.with_suffix(".part"), "wb") as fh:
                for b in r.iter_content(1 << 22):
                    fh.write(b)
        z.with_suffix(".part").replace(z)
    import pyogrio
    import zipfile

    with zipfile.ZipFile(z) as zf:
        shp = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
    b = pyogrio.read_dataframe(f"/vsizip/{z}/{shp}", columns=["AVG_HEIGHT", "MAX_HEIGHT", "MIN_HEIGHT", "HEIGHT_SRC", "BLDG_SRC"])
    b = b[b.geometry.notna() & ~b.geometry.is_empty].reset_index(drop=True)
    b["geometry"] = b.geometry.force_2d()
    b["footprint_m2"] = true_area_m2(b.geometry)
    # height of the part above its own base (MIN_HEIGHT > 0 for parts raised on others, e.g. a tower on a podium: only the part's own storeys)
    h = pd.to_numeric(b["AVG_HEIGHT"], errors="coerce") - pd.to_numeric(b["MIN_HEIGHT"], errors="coerce").fillna(0.0)
    b["height_m"] = h.where(h > 0)
    b["use_class"] = "unknown"
    b["use_original"] = b["BLDG_SRC"].astype(str)
    b["building_id"] = [f"{z.stem.split('_')[1]}_{i}" for i in range(len(b))]
    b = b.to_crs(4326)
    out = standardize(b, SOURCE, "CAN")
    out.to_parquet(pq)
    logger.info(f"{SOURCE}: {len(out):,} massing parts from {z.name}, built area {out['built_area_m2'].sum() / 1e6:,.1f} km2")
    return out


def load(aoi: gpd.GeoDataFrame, cache_dir=None) -> gpd.GeoDataFrame:
    """Toronto's 3D massing buildings inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    b = _city(cache_dir)
    a = aoi.to_crs(4326).total_bounds
    return b.cx[a[0]:a[2], a[1]:a[3]].reset_index(drop=True)
