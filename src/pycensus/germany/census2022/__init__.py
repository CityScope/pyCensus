"""Germany Census 2022 source."""

from ...accessors import register_source_accessor
from .loader import download_census_data, load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "download_census_data", "SCHEMA"]
