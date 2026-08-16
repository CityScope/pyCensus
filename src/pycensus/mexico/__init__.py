"""Mexico census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Mexico source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage per
    data source (``census2020``), each with its own :class:`~pycensus.schema.ColumnSchema`,
    fetch client, and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - Census 2020 (Censo de Poblacion y Vivienda 2020): 
      https://www.inegi.org.mx/programas/ccpv/2020/
"""

from . import api, census2020, constants, geography, utils

__all__ = ["api", "census2020", "constants", "geography", "utils"]
