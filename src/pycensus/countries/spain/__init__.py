"""Spain census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Spain source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage per
    data source (``ine``), each with its own :class:`~pycensus.schema.ColumnSchema`,
    fetch client, and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - INE Padron (real, live Tempus3 API + GISCO/LAU boundaries):
      https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780
"""

from . import api, constants, geography, ine, utils

__all__ = ["api", "constants", "geography", "ine", "utils"]
