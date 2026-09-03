"""Israel census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Israel source directly
    (``api``, ``arcgis``, ``constants``, ``geography``, ``utils``), and one
    subpackage per data source (``cbs``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - CBS Census 2022 (Central Bureau of Statistics, via CBS's own hosted
      ArcGIS layers): population/housing at locality and statistical-area
      granularity.
"""

from . import api, arcgis, cbs, constants, geography, utils

__all__ = ["api", "arcgis", "cbs", "constants", "geography", "utils"]
