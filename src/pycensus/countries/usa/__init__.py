"""United States census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every US source directly
    (``constants``, ``geography``, ``utils``), and one subpackage per data
    source (``acs1``, ``acs3``, ``acs5``, ``dhc``, ``lodes_rac``, ``lodes_wac``),
    each with its own :class:`~pycensus.schema.ColumnSchema`, fetch client,
    and loader that returns a GeoDataFrame ready for
    :meth:`geohierarchy.GeoHierarchy.add_level`.

    LODES Origin-Destination (LODES-OD) is intentionally not implemented as
    a source yet.

Sources:
    - ACS 1-year estimates: https://www.census.gov/programs-surveys/acs
    - ACS 3-year estimates (historical, through 2013): https://www.census.gov/programs-surveys/acs
    - ACS 5-year estimates: https://www.census.gov/programs-surveys/acs
    - Decennial Census DHC: https://www.census.gov/programs-surveys/decennial-census
    - LODES RAC (Residence Area Characteristics): https://lehd.ces.census.gov/data/
    - LODES WAC (Workplace Area Characteristics): https://lehd.ces.census.gov/data/
"""

from . import acs1, acs3, acs5, constants, dhc, geography, lodes_rac, lodes_wac, utils

__all__ = [
    "acs1",
    "acs3",
    "acs5",
    "dhc",
    "lodes_rac",
    "lodes_wac",
    "constants",
    "geography",
    "utils",
]
