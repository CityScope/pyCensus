"""LODES RAC (Residence Area Characteristics): job counts by residence block.

Importing this module registers the ``gdf.lodes_rac`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load_rac` to fetch data.
"""

from ....accessors import register_source_accessor
from .loader import load_rac
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load_rac", "SCHEMA"]
