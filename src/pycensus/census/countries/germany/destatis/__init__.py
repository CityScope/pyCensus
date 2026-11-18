"""Germany Census 2022 source."""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.germany.destatis.loader import download_census_data, load
from pycensus.census.countries.germany.destatis.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "download_census_data", "SCHEMA"]
