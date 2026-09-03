"""Statistics Canada (StatCan) 2021 Census source.

Importing this module registers the ``gdf.statcan`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    StatCan has no per-region queryable API used here -- data is fetched
    via the Full Table Download (bulk CSV) route
    (:mod:`pycensus.canada.api`), the same shape as
    :mod:`pycensus.mexico.inegi`'s ITER downloader.

Source:
    https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
