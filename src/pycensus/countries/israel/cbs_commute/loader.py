"""Israel Census 2022: main means of transport to work, per sub-quarter (tat-rova) of the large cities and per locality elsewhere.

The CBS publishes the census public-use microdata file (PUF) but no mode-to-work table below the locality; the weighted PUF
tabulation per sub-quarter, with its polygons, is published as GeoJSON inside
https://mulysan.github.io/html/transport_mode_israel.html (one feature per city / quarter / sub-quarter, 2008 and 2022 censuses).
This loader downloads that page once (13.5 MB) into ``<cache>/israel/cbs_commute/``, takes the 2022 collection and keeps, for every
locality, its finest level (sub-quarter, else quarter, else the locality), so the units tile the country without overlap.
Counts = weighted workers (``n22``) x the published percentage.

    from pycensus.countries.israel import cbs_commute
    gdf = cbs_commute.load(aoi=aoi)          # GEOID, level, locality code, name, geometry, commuter counts
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from pycensus.canonical import apply_canonical_names

from .schema import FEATURES, SCHEMA, SOURCE_URL

_ORDER = {"sub_borough": 0, "borough": 1, "city": 2}


def _dir(cache_dir: Optional[str]) -> Path:
    from .... import cache as cache_store

    base = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    d = base / "israel" / "cbs_commute"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _collections(html: str):
    dec = json.JSONDecoder()
    for m in re.finditer(r'\{"type": "FeatureCollection"', html):
        try:
            yield dec.raw_decode(html, m.start())[0]
        except ValueError:
            continue


def national(cache_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Every unit of the country (finest level per locality), cached as parquet.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame of every unit.
    """
    d = _dir(cache_dir)
    pq = d / "commute_area_2022.parquet"
    if pq.is_file():
        return gpd.read_parquet(pq)
    page = d / "transport_mode_israel.html"
    if not page.is_file() or page.stat().st_size < 1_000_000:
        import requests

        r = requests.get(SOURCE_URL, timeout=300)
        r.raise_for_status()
        page.write_bytes(r.content)
    html = page.read_text(encoding="utf-8", errors="ignore")
    fc = next(c for c in _collections(html) if c["features"] and "n22" in c["features"][0]["properties"]
              and not any(k.startswith("p08") for k in c["features"][0]["properties"]))
    g = gpd.GeoDataFrame.from_features(fc["features"], crs=4326)
    g = g[pd.to_numeric(g["n22"], errors="coerce").fillna(0) > 0].copy()
    g["_o"] = g["level"].map(_ORDER).fillna(3)
    finest = g.groupby("sn")["_o"].transform("min")
    g = g[g["_o"] == finest].copy()
    n = pd.to_numeric(g["n22"], errors="coerce").fillna(0.0)
    out = pd.DataFrame({"GEOID": [f"{int(s)}" if lv == "city" else f"{int(s)}_{a}" for s, lv, a in zip(g["sn"], g["level"], g["area"])],
                        "commute_level": g["level"].to_numpy(), "locality_code": g["sn"].astype(int).astype(str).to_numpy(),
                        "name": [f"{c} {a}" if a else str(c) for c, a in zip(g["city"], g["area"].fillna(""))]})
    for name, f in FEATURES.items():
        if name == "commuteTotal":
            v = n
        else:
            v = sum(pd.to_numeric(g[c], errors="coerce").fillna(0.0) for c in f["codes"]) / 100.0 * n
        out[SCHEMA.column_label(name)] = v.to_numpy()
    res = gpd.GeoDataFrame(out, geometry=g.geometry.make_valid().to_numpy(), crs=4326)
    res = res.drop_duplicates("GEOID").reset_index(drop=True)
    res.to_parquet(pq)
    return res


def load(aoi: Optional[gpd.GeoDataFrame] = None, level: str = "commute_area", cache_dir: Optional[str] = None, **_) -> gpd.GeoDataFrame:
    """Commute modes of the 2022 census by statistical sub-quarter / locality, inside ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        level: Only ``"commute_area"``.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame with global column names.

    Raises:
        NotImplementedError: For another level.
    """
    if level != "commute_area":
        raise NotImplementedError(f"the census mode-to-work tabulation exists only per sub-quarter / locality ('commute_area'), not {level!r}")
    g = national(cache_dir)
    if aoi is not None:
        g = g[g.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return apply_canonical_names(g, SCHEMA)


__all__ = ["load", "national"]
