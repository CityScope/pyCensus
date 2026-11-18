"""INEGI Censo 2020 extended questionnaire: means of transport to work per municipality (see :mod:`.loader`)."""
from pycensus.accessors import register_source_accessor
from pycensus.census.countries.mexico.inegi_movilidad.loader import SCHEMA, load, national, state_table

register_source_accessor(SCHEMA)

__all__ = ["load", "national", "state_table", "SCHEMA"]
