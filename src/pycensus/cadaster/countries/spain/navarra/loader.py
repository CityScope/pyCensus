"""Navarra foral cadaster (Registro de la Riqueza Territorial) INSPIRE Buildings: one zip per municipality from the ATOM feed, no API key."""
from __future__ import annotations

from pycensus.cadaster.countries.spain._inspire_bu import feed_links, load_bbox, province

SOURCE = "es_navarra"
FEED = "https://filescartografia.navarra.es/2_CARTOGRAFIA_TEMATICA/2_7_CATASTRO/2_7_3_INSPIRE_ATOM/2_7_3_2_BU/Buildings_DatasetATOM_Navarra.xml"


def load(aoi, cache_dir=None):
    """Navarra cadaster buildings (INSPIRE) inside the bounding box of ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        The buildings.
    """
    from pycensus.cadaster import cache_root

    pq = cache_root(cache_dir) / SOURCE / "buildings.parquet"
    urls = [] if pq.is_file() else feed_links(FEED, r"BU_Navarra_\d+\.gml\.zip$")
    return load_bbox(province(SOURCE, urls, r"\.gml$", ["end", "beginning"], cache_dir), aoi)
