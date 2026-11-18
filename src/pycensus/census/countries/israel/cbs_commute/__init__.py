"""Israel Census 2022 main means of transport to work per sub-quarter / locality (see :mod:`.loader`)."""
from pycensus.accessors import register_source_accessor
from pycensus.census.countries.israel.cbs_commute.loader import load, national
from pycensus.census.countries.israel.cbs_commute.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "national", "SCHEMA"]
