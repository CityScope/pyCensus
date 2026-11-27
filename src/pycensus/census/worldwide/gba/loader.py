"""GlobalBuildingAtlas (GBA): worldwide building footprints with heights (LoD1).

Zhu et al. (2025), "GlobalBuildingAtlas", Earth Syst. Sci. Data 17, 6647 (https://essd.copernicus.org/articles/17/6647/2025/,
https://github.com/zhu-xlab/GlobalBuildingAtlas). The data come in 5 x 5 degree tiles named `e030_n35_e035_n30` (west, north, east,
south edges) under a continent folder, in three parts (all EPSG:3857):

    GBA.ODbLPolygon  <continent>/<tile>.geojson           footprints from ODbL sources (OSM, Microsoft)       ODbL
    GBA.LoD1         Polygon/<continent>/<tile>.geojson   the other footprints (Google, GBA's own)            CC BY-NC 4.0
    GBA.LoD1         LoD1/<continent>/<tile>.json         {source+id+region: {height, var}} for every footprint  CC BY-NC 4.0

(the height rasters, GBA.Height on mediaTUM, are not needed: every footprint already carries its LoD1 height). Mixing the parts has
license implications -- see the dataset's README.

    from pycensus.census.worldwide.gba import load_buildings
    b = load_buildings(aoi, cache_dir)     # GeoDataFrame EPSG:4326: source, id, region, height (m), height_var, footprint_m2

Downloads go to `<cache_dir>/gba/...` (kept, resumable); the buildings of an AOI are cached as parquet under `<cache_dir>/gba/_aoi/`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
HF = "https://huggingface.co/"
CONTINENTS = ("africa", "asiaeast", "asiawest", "europe", "northamerica", "oceania", "southamerica")
TILE_DEG = 5


def _gba_dir(cache_dir) -> Path:
    from pycensus.cache import default_cache_dir

    d = Path(cache_dir or default_cache_dir()) / "gba"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tile_name(lon: float, lat: float) -> str:
    """Name of the 5-degree tile containing (lon, lat), e.g. (34.8, 31.25) -> 'e030_n35_e035_n30'.

    Args:
        lon: Longitude.
        lat: Latitude.

    Returns:
        The tile name.
    """
    w = math.floor(lon / TILE_DEG) * TILE_DEG
    n = math.floor(lat / TILE_DEG) * TILE_DEG + TILE_DEG
    f = lambda v, pos, neg, width: f"{pos if v >= 0 else neg}{abs(v):0{width}d}"  # noqa: E731
    return f"{f(w, 'e', 'w', 3)}_{f(n, 'n', 's', 2)}_{f(w + TILE_DEG, 'e', 'w', 3)}_{f(n - TILE_DEG, 'n', 's', 2)}"


def tiles_for_bbox(west: float, south: float, east: float, north: float) -> List[str]:
    """Every tile a WGS84 bounding box touches.

    Args:
        west: West bound.
        south: South bound.
        east: East bound.
        north: North bound.

    Returns:
        Tile names.
    """
    eps = 1e-9
    lons = np.arange(math.floor(west / TILE_DEG) * TILE_DEG, east + eps, TILE_DEG)
    lats = np.arange(math.floor(south / TILE_DEG) * TILE_DEG, north + eps, TILE_DEG)
    return sorted({tile_name(min(lo + 0.5, east), min(la + 0.5, north)) for lo in lons for la in lats})


def _get(url: str, retries: int = 5, **kw):
    import requests

    for i in range(retries):
        try:
            r = requests.get(url, timeout=kw.pop("timeout", 300), **kw)
            r.raise_for_status()
            return r
        except Exception:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def tile_index(cache_dir=None) -> dict:
    """{tile: continent} for every tile GBA publishes (from the HuggingFace folder listings of GBA.LoD1 `Polygon/<continent>`; cached).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    f = _gba_dir(cache_dir) / "tile_index.json"
    if f.is_file():
        return json.loads(f.read_text())
    idx = {}
    for c in CONTINENTS:
        for item in _get(f"{HF}api/datasets/zhu-xlab/GBA.LoD1/tree/main/Polygon/{c}").json():
            name = Path(item["path"]).stem
            if item["path"].endswith(".geojson"):
                idx[name] = c
    f.write_text(json.dumps(idx, indent=0))
    return idx


def _download(url: str, dest: Path, chunk: int = 1 << 22) -> Path:
    """Resumable download (`<dest>.part`, HTTP range), renamed when complete."""
    import requests

    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(8):
        have = part.stat().st_size if part.is_file() else 0
        try:
            with requests.get(url, stream=True, timeout=300, headers={"Range": f"bytes={have}-"} if have else {}) as r:
                if r.status_code == 416:   # already complete
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with open(part, mode) as fh:
                    for b in r.iter_content(chunk):
                        fh.write(b)
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"GBA download {dest.name} interrupted ({exc}); retrying")
            time.sleep(min(60, 2 ** attempt))
    part.replace(dest)
    return dest


def tile_paths(tile: str, continent: str, cache_dir=None) -> Tuple[Path, Path, Path]:
    """Local paths of a tile's (ODbL polygons, other polygons, heights) files.

    Args:
        tile: Tile name.
        continent: GBA continent folder.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    d = _gba_dir(cache_dir)
    return (d / "ODbLPolygon" / continent / f"{tile}.geojson", d / "Polygon" / continent / f"{tile}.geojson",
            d / "LoD1" / continent / f"{tile}.json")


def download_tiles(tiles: Iterable[str], cache_dir=None) -> List[Tuple[str, str]]:
    """Download the three parts of each tile (skipping files already there). Returns [(tile, continent)] for the tiles GBA has.

    Args:
        tiles: Tile names.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    from concurrent.futures import ThreadPoolExecutor

    idx = tile_index(cache_dir)
    out, jobs = [], []
    for t in tiles:
        c = idx.get(t)
        if c is None:
            logger.info(f"GBA has no tile {t} (ocean / no buildings)")
            continue
        odbl, poly, lod1 = tile_paths(t, c, cache_dir)
        jobs += [(f"{HF}datasets/zhu-xlab/GBA.ODbLPolygon/resolve/main/{c}/{t}.geojson", odbl),
                 (f"{HF}datasets/zhu-xlab/GBA.LoD1/resolve/main/Polygon/{c}/{t}.geojson", poly),
                 (f"{HF}datasets/zhu-xlab/GBA.LoD1/resolve/main/LoD1/{c}/{t}.json", lod1)]
        out.append((t, c))
    with ThreadPoolExecutor(3) as ex:   # the files are large and come from one server: three at a time, not one after another, never a burst
        list(ex.map(lambda j: _download(*j), jobs))
    return out


_HEIGHT_RE = re.compile(rb'"((?:[^"\\]|\\.)*)"\s*:\s*\{([^{}]*)\}')
_NUM_RE = re.compile(rb'"(height|var)"\s*:\s*(null|-?[0-9.]+(?:[eE][-+]?[0-9]+)?)')


def read_heights(json_path: Path, keys: set, chunk: int = 1 << 26) -> dict:
    """{key: (height, var)} for `keys` from a GBA LoD1 height file (a single JSON object, read in chunks -- the files are ~1 GB).

    Args:
        json_path: LoD1 height file.
        keys: Building keys wanted.
        chunk: Read size in bytes.
    """
    want = {k.encode() for k in keys}
    out = {}
    tail = b""
    with open(json_path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            buf = tail + block
            last = 0
            for m in _HEIGHT_RE.finditer(buf):
                last = m.end()
                k = m.group(1)
                if k in want:
                    vals = {a.decode(): (None if b == b"null" else float(b)) for a, b in _NUM_RE.findall(m.group(2))}
                    out[k.decode()] = (vals.get("height"), vals.get("var"))
            tail = buf[last:] if block else b""
            if not block:
                break
            if len(tail) > chunk:   # no complete entry in a whole chunk: not this format
                raise ValueError(f"{json_path}: unexpected LoD1 height file layout")
    return out


def _true_area_m2(geom_3857: gpd.GeoSeries) -> np.ndarray:
    """Footprint area in m2 from EPSG:3857 polygons (Mercator inflates areas by 1/cos^2(lat))."""
    y = geom_3857.centroid.y.to_numpy()
    lat = np.degrees(2 * np.arctan(np.exp(y / 6378137.0)) - np.pi / 2)
    return geom_3857.area.to_numpy() * np.cos(np.radians(lat)) ** 2


def load_buildings(aoi: gpd.GeoDataFrame, cache_dir=None, clip: bool = True, refresh: bool = False) -> gpd.GeoDataFrame:
    """Every GBA footprint of `aoi` with its LoD1 height.

    Returns a GeoDataFrame (EPSG:4326): `source` (osm / ms / google / ...), `id`, `region`, `height` (m; NaN where GBA has none),
    `height_var`, `footprint_m2` (true area). `clip`: keep the footprints whose centroid lies inside the AOI polygon (else its bbox).

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        clip: Keep only footprints inside the AOI polygon.
        refresh: Ignore the cached file.
    """
    aoi4326 = aoi.to_crs(4326)
    w, s, e, n = aoi4326.total_bounds
    key = hashlib.sha1(np.round(aoi4326.total_bounds, 6).tobytes() + (aoi4326.union_all().wkb if clip else b"")).hexdigest()[:12]
    cache = _gba_dir(cache_dir) / "_aoi" / f"buildings_{key}.parquet"
    if cache.is_file() and not refresh:
        return gpd.read_parquet(cache)
    import pyogrio

    bbox3857 = gpd.GeoSeries.from_xy([w, e], [s, n], crs=4326).to_crs(3857).total_bounds
    parts = []
    for tile, cont in download_tiles(tiles_for_bbox(w, s, e, n), cache_dir):
        odbl, poly, lod1 = tile_paths(tile, cont, cache_dir)
        frames = [pyogrio.read_dataframe(f, bbox=tuple(bbox3857)) for f in (odbl, poly) if f.is_file()]
        g = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else None
        if g is None:
            continue
        g = gpd.GeoDataFrame(g, geometry="geometry", crs=3857)
        g["_key"] = g["source"].astype(str) + g["id"].astype(str) + g["region"].astype(str)
        hv = read_heights(lod1, set(g["_key"])) if lod1.is_file() else {}
        g["height"] = g["_key"].map(lambda k: hv.get(k, (None, None))[0]).astype(float)
        g["height_var"] = g["_key"].map(lambda k: hv.get(k, (None, None))[1]).astype(float)
        logger.info(f"GBA {tile}: {len(g):,} footprints in the AOI box, {g['height'].notna().mean():.1%} with a height")
        parts.append(g.drop(columns="_key"))
    if not parts:
        out = gpd.GeoDataFrame({c: [] for c in ("source", "id", "region", "height", "height_var", "footprint_m2")}, geometry=[], crs=4326)
    else:
        g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=3857)
        g = g.drop_duplicates(subset=["source", "id", "region"])   # a footprint on a tile edge is in both tiles
        g["footprint_m2"] = _true_area_m2(g.geometry)
        out = g.to_crs(4326)
        if clip:
            c = out.geometry.centroid
            import shapely

            out = out[shapely.contains_xy(aoi4326.union_all(), c.x.to_numpy(), c.y.to_numpy())].reset_index(drop=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out
