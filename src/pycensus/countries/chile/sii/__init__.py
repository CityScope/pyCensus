"""Chile SII comunal jobs-by-workplace source (bulk .xlsx download, Servicio de Impuestos Internos).

Importing this module registers the ``gdf.sii_cl`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Source:
    https://www.sii.cl/estadisticas/region/PUB_Reg_Com.xlsx
    (real comuna-level dependent-worker counts, i.e. jobs located in the
    comuna -- see :mod:`pycensus.countries.chile.sii.api` module docstring
    for verification notes and the 2015-vintage caveat).
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
