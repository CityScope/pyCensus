"""INEGI Censo 2020 extended questionnaire: means of transport to work per municipality (see :mod:`.loader`)."""
from ....accessors import register_source_accessor
from .loader import SCHEMA, load, national, state_table

register_source_accessor(SCHEMA)

__all__ = ["load", "national", "state_table", "SCHEMA"]
