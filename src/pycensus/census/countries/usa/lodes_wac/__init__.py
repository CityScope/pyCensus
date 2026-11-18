"""LODES WAC (Workplace Area Characteristics): job counts by workplace block.

Importing this module registers the ``gdf.lodes_wac`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load_wac` to fetch data.
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.usa.lodes_wac.loader import load_wac
from pycensus.census.countries.usa.lodes_wac.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load_wac", "SCHEMA"]
