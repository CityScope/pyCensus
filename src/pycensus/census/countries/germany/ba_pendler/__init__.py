"""BA (Bundesagentur fuer Arbeit) Pendlerstatistik (commuter statistics) source -- see loader.py."""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.germany.ba_pendler.loader import load, IMPLEMENTED_LEVELS
from pycensus.census.countries.germany.ba_pendler.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "IMPLEMENTED_LEVELS", "SCHEMA"]
