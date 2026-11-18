"""Gipuzkoa INSPIRE Buildings (b5m): one province-wide zip, parsed once into a parquet (unified cadaster schema), no API key."""
from __future__ import annotations

import logging
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd

from ... import cache_root, standardize, true_area_m2

logger = logging.getLogger(__name__)
URL = "https://b5m.gipuzkoa.eus/inspire/download/GML/ES.GFA.BU.zip"
SOURCE = "es_gipuzkoa"


def _province(cache_dir=None) -> gpd.GeoDataFrame:
    d = cache_root(cache_dir) / SOURCE
    d.mkdir(parents=True, exist_ok=True)
    pq = d / "buildings.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    z = d / "ES.GFA.BU.zip"
    if not z.is_file():
        import requests

        with requests.get(URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(z.with_suffix(".part"), "wb") as fh:
                for b in r.iter_content(1 << 22):
                    fh.write(b)
        z.with_suffix(".part").replace(z)
    import pyogrio

    with zipfile.ZipFile(z) as zf:
        gml = next(n for n in zf.namelist() if n.endswith("BU.gml"))
    b = pyogrio.read_dataframe(f"/vsizip/{z}/{gml}", columns=["gml_id", "value", "numberOfDwellings", "numberOfFloorsAboveGround", "numberOfFloorsBelowGround"])
    b["footprint_m2"] = true_area_m2(b.geometry)
    b["height_m"] = pd.to_numeric(b["value"], errors="coerce").where(lambda x: x > 0)
    b["floors_above"] = pd.to_numeric(b["numberOfFloorsAboveGround"], errors="coerce")
    b["floors_below"] = pd.to_numeric(b["numberOfFloorsBelowGround"], errors="coerce")
    b["dwellings"] = pd.to_numeric(b["numberOfDwellings"], errors="coerce")
    b["use_class"] = np.where(b["dwellings"] > 0, "residential", "unknown")
    b["building_id"] = b["gml_id"].astype(str)
    out = standardize(b, SOURCE, "ESP")
    out.to_parquet(pq)
    return out


def load(aoi: gpd.GeoDataFrame, cache_dir=None) -> gpd.GeoDataFrame:
    """Gipuzkoa cadaster buildings inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    b = _province(cache_dir)
    a = aoi.to_crs(4326).total_bounds
    return b.cx[a[0]:a[2], a[1]:a[3]].reset_index(drop=True)
