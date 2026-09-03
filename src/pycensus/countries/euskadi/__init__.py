"""Euskadi (Basque Country) census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Euskadi source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage per
    data source (``eustat``), each with its own :class:`~pycensus.schema.ColumnSchema`,
    fetch client, and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - Eustat (real, GISCO/LAU-backed municipality/territory population):
      https://www.eustat.eus/
"""

from . import api, constants, eustat, geography, utils

__all__ = ["api", "constants", "eustat", "geography", "utils"]
