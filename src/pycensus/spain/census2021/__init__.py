"""Spain Census 2021 (Censo de Población y Viviendas 2021) source.

Importing this module registers the ``gdf.census2021`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Unlike US census data which has APIs, Spain's INE Census 2021 data
    must be downloaded as files from INE's website. This module provides
    tools to:
    1. Download census aggregated tables to data/spain/
    2. Load and process the data into a common-schema GeoDataFrame
    3. Cache processed data for efficient repeated access

Source:
    https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780
"""

from ...accessors import register_source_accessor
from .loader import download_census_data, load
from .schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "download_census_data", "SCHEMA"]
