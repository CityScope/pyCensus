"""INE Chile Censo 2017 source (via the Esri Chile DPA FeatureServer).

Importing this module registers the ``gdf.ine`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Source:
    https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
    Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer
    (real Censo 2017 data republished by Esri Chile, attributed to INE --
    see :mod:`pycensus.chile.api` module docstring for verification notes).
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.chile.ine.loader import load
from pycensus.census.countries.chile.ine.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
