"""Euskadi Census 2021 (Censo de Poblacion y Viviendas 2021) source.

Importing this module registers the ``gdf.census2021`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Unlike US census data which has APIs, Euskadi's Eustat Census 2021 data
    must be downloaded as files from Eustat's website. This module provides
    tools to:
    1. Load and process the data into a common-schema GeoDataFrame
    2. Cache processed data for efficient repeated access
    3. Download data to the cache directory

Source:
    https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html
"""

from ...accessors import register_source_accessor
from .loader import download_census_data, load
from .schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "download_census_data", "SCHEMA"]
