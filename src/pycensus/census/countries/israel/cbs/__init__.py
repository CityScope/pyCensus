"""Israel Census 2022 (Census of Population and Housing) source.

Importing this module registers the ``gdf.cbs`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Real, live, unauthenticated data from CBS's own hosted ArcGIS
    FeatureServer layers -- see :mod:`pycensus.israel.cbs.loader` and
    :mod:`pycensus.israel.constants` for the verified URLs and fields.

Source:
    https://services8.arcgis.com/JcXY3lLZni6BK4El/arcgis/rest/services/
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.israel.cbs.loader import load
from pycensus.census.countries.israel.cbs.schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
