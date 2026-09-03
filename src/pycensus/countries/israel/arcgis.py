"""Thin, generic client for the public ArcGIS REST "FeatureServer/query" API.

Technical aspects:
    Every real Israel data source wired up in this package (CBS's own
    hosted ArcGIS Online services, and the Israel Planning Administration's
    iplan.gov.il ArcGIS Server) speaks the same Esri REST query protocol.
    This module implements just the subset needed here: paginated
    attribute+geometry queries, returned already reprojected to EPSG:4326
    (via the server-side ``outSR`` parameter, verified to work against both
    hosts), and conversion of Esri JSON geometry to Shapely.

    None of the endpoints used by this package require an API key or
    authentication token -- confirmed by live, unauthenticated queries
    against both hosts on 2026-08-19.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import MultiPolygon, Point, Polygon

_TIMEOUT = 60


def query_features(
    url: str,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = True,
    page_size: int = 1000,
) -> List[dict]:
    """Fetch every feature matching ``where`` from an ArcGIS FeatureServer layer.

    Handles pagination transparently via ``resultOffset``/``resultRecordCount``
    so callers never see ``exceededTransferLimit`` truncation.

    Args:
        url: Full FeatureServer layer URL (e.g. ``".../FeatureServer/0"``).
        where: SQL ``WHERE`` clause (default ``"1=1"``, i.e. everything).
        out_fields: Comma-separated field list, or ``"*"``.
        return_geometry: Whether to request geometry (reprojected to
            EPSG:4326 server-side via ``outSR``).
        page_size: Records requested per page.

    Returns:
        List of raw Esri JSON feature dicts (``{"attributes": {...},
        "geometry": {...}}``).

    Raises:
        requests.HTTPError: If any page request fails.
        RuntimeError: If the server returns an error payload.
    """
    base_params = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": str(return_geometry).lower(),
        "outSR": 4326,
        "f": "json",
    }

    features: List[dict] = []
    offset = 0
    paginate = True
    while True:
        params = dict(base_params)
        if paginate:
            params["resultOffset"] = offset
            params["resultRecordCount"] = page_size

        resp = requests.get(f"{url}/query", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            # Some ArcGIS Server (non-hosted-feature-service) endpoints don't
            # support resultOffset/resultRecordCount pagination at all --
            # fall back to a single unpaginated request in that case.
            if paginate and "pagination" in str(data["error"]).lower():
                paginate = False
                continue
            raise RuntimeError(f"ArcGIS query error for {url}: {data['error']}")

        page = data.get("features", [])
        features.extend(page)

        if not paginate or not data.get("exceededTransferLimit") or not page:
            break
        offset += len(page)

    return features


def _signed_area(ring: list) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _esri_geometry_to_shapely(geom: dict):
    if "rings" in geom:
        # Esri convention: clockwise ring = outer polygon boundary,
        # counter-clockwise ring = hole in the preceding outer ring.
        outers, holes = [], []
        for ring in geom["rings"]:
            (holes if _signed_area(ring) > 0 else outers).append(ring)

        polys = []
        for outer in outers:
            outer_poly = Polygon(outer)
            my_holes = [h for h in holes if outer_poly.contains(Point(h[0]))]
            polys.append(Polygon(outer, my_holes))

        if not polys:
            return None
        if len(polys) == 1:
            return polys[0]
        return MultiPolygon(polys)
    if "x" in geom and "y" in geom:
        return Point(geom["x"], geom["y"])
    raise ValueError(f"Unsupported Esri geometry shape: {list(geom)}")


def features_to_geodataframe(features: List[dict]) -> gpd.GeoDataFrame:
    """Convert raw Esri JSON features (from :func:`query_features`) to a GeoDataFrame.

    Args:
        features: Feature list as returned by :func:`query_features`.

    Returns:
        GeoDataFrame in EPSG:4326 with one column per attribute plus
        ``geometry``. Empty (zero-row, no geometry column) if ``features``
        is empty.
    """
    if not features:
        return gpd.GeoDataFrame()

    rows = [f["attributes"] for f in features]
    geoms = [_esri_geometry_to_shapely(f["geometry"]) for f in features] if "geometry" in features[0] else None

    df = pd.DataFrame(rows)
    if geoms is not None:
        return gpd.GeoDataFrame(df, geometry=geoms, crs=4326)
    return gpd.GeoDataFrame(df)


__all__ = ["query_features", "features_to_geodataframe"]
