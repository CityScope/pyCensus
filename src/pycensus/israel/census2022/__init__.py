"""Israel Census 2022 (Census of Population and Housing) source.

Importing this module registers the ``gdf.census2022`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Technical aspects:
    Unlike US census data which has APIs, Israel's CBS Census 2022 data
    must be downloaded as files from CBS's website. This module provides
    tools to:
    1. Load and process the data into a common-schema GeoDataFrame
    2. Cache processed data for efficient repeated access
    3. Download data to the cache directory

Source:
    https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
"""

from ...accessors import register_source_accessor
from .loader import download_census_data, load
from .schema import SCHEMA

# Register the accessor
register_source_accessor(SCHEMA)

__all__ = ["load", "download_census_data", "SCHEMA"]
