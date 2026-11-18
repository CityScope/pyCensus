"""Andorra's Departament d'Estadistica: population by parish/year.

See :mod:`pycensus.andorra.estadisticaad.loader` for the real, verified
source and :mod:`pycensus.andorra.api` for the underlying ArcGIS endpoints.
"""

from pycensus.accessors import register_source_accessor
from pycensus.census.countries.andorra.estadisticaad.loader import load
from pycensus.census.countries.andorra.estadisticaad.schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
