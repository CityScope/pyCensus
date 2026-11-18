"""2020 Decennial Census DHC (Demographic and Housing Characteristics) source.

Importing this module registers the ``gdf.dhc`` GeoDataFrame accessor (see
:mod:`pycensus.accessors`). Use :func:`load` to fetch data.
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.usa.dhc.loader import load
from pycensus.census.countries.usa.dhc.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
