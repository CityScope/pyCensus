"""WorldPop gridded population source.

Importing this module registers the ``gdf.worldpop`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`download_worldpop_population` to
fetch the raw raster and :func:`get_country_region` to resolve a country
(and optional subdivision) code from a lat/lon.
"""

from ....accessors import register_source_accessor
from .loader import GLOBAL_SCHEMA_FEATURES, download_worldpop_layer, download_worldpop_population, get_country_region
from .h3 import worldpop_raster_to_h3
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = [
    "download_worldpop_population",
    "download_worldpop_layer",
    "GLOBAL_SCHEMA_FEATURES",
    "get_country_region",
    "worldpop_raster_to_h3",
    "SCHEMA",
]
