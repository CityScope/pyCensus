"""LODES RAC (Residence Area Characteristics): job counts by residence block.

Importing this module registers the ``gdf.lodes_rac`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load_rac` to fetch data.
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.usa.lodes_rac.loader import load_rac
from pycensus.census.countries.usa.lodes_rac.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load_rac", "SCHEMA"]
