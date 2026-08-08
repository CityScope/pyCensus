"""LODES (LEHD Origin-Destination Employment Statistics): RAC and WAC job counts.

Importing this module registers two GeoDataFrame accessors, ``gdf.lodes_rac``
and ``gdf.lodes_wac`` (see :mod:`pycensus.accessors`). Use :func:`load_rac`
and :func:`load_wac` to fetch data.
"""

from ...accessors import register_source_accessor
from .loader import load_rac, load_wac
from .schema import RAC_SCHEMA, WAC_SCHEMA

register_source_accessor(RAC_SCHEMA)
register_source_accessor(WAC_SCHEMA)

__all__ = ["load_rac", "load_wac", "RAC_SCHEMA", "WAC_SCHEMA"]
