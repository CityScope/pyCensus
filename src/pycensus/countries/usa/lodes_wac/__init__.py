"""LODES WAC (Workplace Area Characteristics): job counts by workplace block.

Importing this module registers the ``gdf.lodes_wac`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load_wac` to fetch data.
"""

from ....accessors import register_source_accessor
from .loader import load_wac
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load_wac", "SCHEMA"]
