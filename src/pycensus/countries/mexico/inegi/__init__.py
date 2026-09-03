"""Mexico Census 2020 (Censo de Poblacion y Vivienda 2020) source.

Importing this module registers the ``gdf.inegi`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Unlike US census data which has APIs, Mexico's INEGI Census 2020 data
    must be downloaded as files from INEGI's website. This module provides
    tools to:
    1. Download census microdata and aggregated tables to data/mexico/
    2. Load and process the data into a common-schema GeoDataFrame
    3. Cache processed data for efficient repeated access

Source:
    https://www.inegi.org.mx/programas/ccpv/2020/
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
