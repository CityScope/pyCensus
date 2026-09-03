"""Canada census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Canada source
    directly (``api``, ``constants``, ``geography``, ``utils``), and one
    subpackage per data source (``statcan``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - Statistics Canada (StatCan) 2021 Census, Full Table Download (CSV):
      https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip
"""

from . import api, constants, geography, statcan, utils

__all__ = ["api", "constants", "geography", "statcan", "utils"]
