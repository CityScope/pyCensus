"""Israel Census 2022 main means of transport to work per sub-quarter / locality (see :mod:`.loader`)."""
from ....accessors import register_source_accessor
from .loader import load, national
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "national", "SCHEMA"]
