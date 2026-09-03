"""Euskadi municipal population source (real data via Eurostat/GISCO LAU).

Importing this module registers the ``gdf.eustat`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Named ``eustat`` for continuity with the column-naming convention
    (``eustat_population``, etc.), but see ``api.py`` and ``geography.py``
    for why the actual data comes from Eurostat/GISCO's LAU dataset rather
    than eustat.eus directly (that portal 403s a scripted client).

Source:
    https://gisco-services.ec.europa.eu/distribution/v2/lau/lau-2021-files.html
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
