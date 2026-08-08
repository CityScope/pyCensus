"""United States census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every US source directly
    (``constants``, ``geography``, ``utils``), and one subpackage per data
    source (``acs``, ``dhc``, ``lodes``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - ACS 5-year estimates: https://www.census.gov/programs-surveys/acs
    - Decennial Census DHC: https://www.census.gov/programs-surveys/decennial-census
    - LODES (LEHD Origin-Destination Employment Statistics): https://lehd.ces.census.gov/data/
"""

from . import acs, constants, dhc, geography, lodes, utils

__all__ = ["acs", "dhc", "lodes", "constants", "geography", "utils"]
