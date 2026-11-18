"""Álava / Araba foral cadaster INSPIRE Buildings: one province-wide zip (one GML per municipality), no API key."""
from __future__ import annotations

from pycensus.cadaster.countries.spain._inspire_bu import load_bbox, province

SOURCE = "es_araba"
URL = "https://geo.araba.eus/deskargak/INSPIRE/BU/GML/25830/BU_25830_GML.zip"


def load(aoi, cache_dir=None):
    """Araba / Álava cadaster buildings (INSPIRE) inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    return load_bbox(province(SOURCE, [URL], r"\.gml$", ["anyPoint"], cache_dir), aoi)
