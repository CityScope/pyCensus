"""BA (Bundesagentur fuer Arbeit) Pendlerstatistik (commuter statistics) source -- see loader.py."""

from ....accessors import register_source_accessor
from .loader import load, IMPLEMENTED_LEVELS
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "IMPLEMENTED_LEVELS", "SCHEMA"]
