"""2020 Decennial Census DHC (Demographic and Housing Characteristics) source.

Importing this module registers the ``gdf.dhc`` GeoDataFrame accessor (see
:mod:`pycensus.accessors`). Use :func:`load` to fetch data.
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
