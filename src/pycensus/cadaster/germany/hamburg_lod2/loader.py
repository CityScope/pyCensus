"""Hamburg 3D building model LoD2-DE (Landesbetrieb Geoinformation und Vermessung, open data, latest release), no API key.
One CityGML tile per km2 (783 tiles, ~6.7 GB unzipped), streamed with lxml: per building its ground surface (footprint), storeysAboveGround,
measuredHeight and ALKIS building function (31001_<code>). Objects of other ALKIS classes (51002 / 51003 / 51009: towers, silos, canopies and other
structures that are not buildings) are left out. Parsed once into a parquet (unified cadaster schema)."""
from __future__ import annotations

import logging
import zipfile
from concurrent.futures import ProcessPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd

from ... import cache_root, map_use, source_schema, standardize

logger = logging.getLogger(__name__)
SOURCE = "de_hamburg_lod2"
SEARCH = "https://suche.transparenz.hamburg.de/api/3/action/package_search?q=LoD2-DE%20Hamburg&rows=20"
NS = {"bldg": "http://www.opengis.net/citygml/building/1.0", "gml": "http://www.opengis.net/gml", "core": "http://www.opengis.net/citygml/1.0"}


def _latest_url() -> str:
    import re

    import requests

    urls = {r["url"] for p in requests.get(SEARCH, timeout=120).json()["result"]["results"] for r in p["resources"]
            if re.search(r"/LoD2-DE_HH_\d{4}-\d{2}-\d{2}\.zip$", r["url"]) and "archiv" not in r["url"]}
    return max(urls, key=lambda u: re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", u).group(1))


def _tile(args):
    """Buildings of one GML tile: [(id, function, storeys, height, [ring coords...])]."""
    zpath, name = args
    from lxml import etree

    out = []
    B, G = "{%s}" % NS["bldg"], "{%s}" % NS["gml"]
    with zipfile.ZipFile(zpath) as zf, zf.open(name) as fh:
        for _, el in etree.iterparse(fh, tag=B + "Building", huge_tree=True):
            bid = el.get(G + "id")
            fn = el.findtext(B + "function") or ""
            st = el.findtext(B + "storeysAboveGround"); h = el.findtext(B + "measuredHeight")
            rings = []
            for gs in el.iter(B + "GroundSurface"):
                for pl in gs.iter(G + "posList"):
                    v = np.array(pl.text.split(), float)
                    dim = int(pl.get("srsDimension") or 3)
                    rings.append(v.reshape(-1, dim)[:, :2])
            out.append((bid, fn, float(st) if st else np.nan, float(h) if h else np.nan, rings))
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
    return out


def _city(cache_dir=None, workers: int = 6) -> gpd.GeoDataFrame:
    d = cache_root(cache_dir) / SOURCE
    pq = d / "buildings.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    zd = d / "zips"
    zd.mkdir(parents=True, exist_ok=True)
    have = sorted(zd.glob("LoD2-DE_HH_*.zip"))
    if have:
        z = have[-1]
    else:
        import requests

        url = _latest_url()
        z = zd / url.rsplit("/", 1)[-1]
        with requests.get(url, stream=True, timeout=3600) as r:
            r.raise_for_status()
            with open(z.with_suffix(".part"), "wb") as fh:
                for b in r.iter_content(1 << 22):
                    fh.write(b)
        z.with_suffix(".part").replace(z)
    import shapely

    with zipfile.ZipFile(z) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".gml")]
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for part in ex.map(_tile, [(str(z), n) for n in names], chunksize=4):
            rows.extend(part)
    ids, fns, sts, hs, geoms = [], [], [], [], []
    for bid, fn, st, h, rings in rows:
        if not fn.startswith("31001_") or not rings:   # buildings only (not towers, silos, canopies...)
            continue
        polys = [shapely.Polygon(r) for r in rings if len(r) >= 4]
        g = shapely.make_valid(shapely.union_all(polys)) if len(polys) > 1 else (shapely.make_valid(polys[0]) if polys else None)
        if g is None or g.is_empty:
            continue
        ids.append(bid); fns.append(fn.split("_", 1)[1]); sts.append(st); hs.append(h); geoms.append(g)
    b = gpd.GeoDataFrame({"building_id": ids, "use_original": fns, "floors_above": sts, "height_m": hs}, geometry=geoms, crs=25832)
    b = b[b.geom_type.isin(["Polygon", "MultiPolygon"])].reset_index(drop=True)
    b["footprint_m2"] = b.geometry.area.to_numpy()   # UTM 32N: true area at Hamburg's latitude within ~0.04%
    b["floors_above"] = b["floors_above"].where(b["floors_above"] > 0)
    b["height_m"] = b["height_m"].where(b["height_m"] > 0)
    b["use_class"] = map_use(b["use_original"], source_schema(SOURCE)["use_map"], prefix_match=True)
    out = standardize(b, SOURCE, "DEU")
    out.to_parquet(pq)
    logger.info(f"{SOURCE}: {len(out):,} buildings from {len(names)} tiles of {z.name}, built area {out['built_area_m2'].sum() / 1e6:,.1f} km2")
    return out


def load(aoi: gpd.GeoDataFrame, cache_dir=None) -> gpd.GeoDataFrame:
    """Hamburg's LoD2 buildings inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    b = _city(cache_dir)
    a = aoi.to_crs(4326).total_bounds
    return b.cx[a[0]:a[2], a[1]:a[3]].reset_index(drop=True)
