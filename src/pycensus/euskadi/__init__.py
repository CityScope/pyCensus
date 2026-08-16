"""Euskadi (Basque Country) census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Euskadi source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage per
    data source (``census2021``), each with its own :class:`~pycensus.schema.ColumnSchema`,
    fetch client, and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - Census 2021 (Censo de Poblacion y Viviendas 2021): 
      https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html
"""

from . import api, census2021, constants, geography, utils

__all__ = ["api", "census2021", "constants", "geography", "utils"]
