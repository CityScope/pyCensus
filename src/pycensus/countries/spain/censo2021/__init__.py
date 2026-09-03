"""Spain Censo de Poblacion y Viviendas 2021 (SDC21) source.

See :mod:`pycensus.countries.spain.censo2021.api` and ``loader.py`` module
docstrings for the real, live-verified source details and exactly which
fields are implemented.
"""

from __future__ import annotations

from .loader import load
from .schema import SCHEMA

__all__ = ["load", "SCHEMA"]
