"""Andorra: modes used by residents per parish, ENM 2050 citizen survey (CRES, July 2021) -- see :mod:`.loader`."""
from .loader import SOURCE_URL, load, parish_table

__all__ = ["load", "parish_table", "SOURCE_URL"]
