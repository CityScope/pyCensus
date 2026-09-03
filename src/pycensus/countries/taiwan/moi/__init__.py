"""Taiwan MOI RIS (內政部戶政司) resident population source.

Importing this module registers the ``gdf.moi`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    MOI's household-registration statistics (dataset ODRP013) provide real,
    keyless, verified population/male/female counts down to village
    granularity -- see :mod:`pycensus.taiwan.api` and
    :mod:`pycensus.taiwan.moi.loader` module docstrings. Boundary geometry
    is not implemented for any level (see
    :mod:`pycensus.taiwan.geography`), so :func:`load` currently raises
    ``NotImplementedError`` once it reaches geometry assembly.

Source:
    https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/{yyymm}
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
