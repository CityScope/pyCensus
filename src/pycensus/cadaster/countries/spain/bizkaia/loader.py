"""Bizkaia foral cadaster INSPIRE Buildings: one zip per municipality from the ATOM feed, no API key."""
from __future__ import annotations

from pycensus.cadaster.countries.spain._inspire_bu import feed_links, load_bbox, province

SOURCE = "es_bizkaia"
FEED = "https://apli.bizkaia.eus/apps/Danok/INSPIRE/buildings.xml"


def load(aoi, cache_dir=None):
    """Bizkaia cadaster buildings (INSPIRE) inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    from pycensus.cadaster import cache_root

    pq = cache_root(cache_dir) / SOURCE / "buildings.parquet"
    urls = [] if pq.is_file() else feed_links(FEED, r"ES\.BFA\.BU\.\d+\.zip$")
    return load_bbox(province(SOURCE, urls, r"BU\.gml$", ["end", "beginning"], cache_dir), aoi)
