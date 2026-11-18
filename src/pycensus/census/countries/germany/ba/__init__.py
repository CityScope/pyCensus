"""BA (Bundesagentur fuer Arbeit) jobs-by-workplace source -- see loader.py."""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.germany.ba.loader import load, IMPLEMENTED_LEVELS
from pycensus.census.countries.germany.ba.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "IMPLEMENTED_LEVELS", "SCHEMA"]
