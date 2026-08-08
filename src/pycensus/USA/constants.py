"""Static US geography reference data shared by every US census source.

Technical aspects:
    Boundary files are fetched with `pygris <https://walker-data.com/pygris/>`_,
    which wraps the Census Bureau's TIGER/Line shapefiles. This module maps
    logical level names (``"tract"``, ``"blockgroup"``, ...) to the pygris
    function that fetches them, the geography hierarchy the Census API
    predicate string (``for=...&in=...``) needs to scope a request, whether
    water areas should be erased from the polygons, and the most recent
    vintage year available per level.

Source:
    https://www.census.gov/programs-surveys/geography.html
"""

from typing import Dict, List

import pygris

CENSUS_HIERARCHY: Dict[str, int] = {
    "state": 0,
    "county": 1,
    "tract": 2,
    "blockgroup": 3,
    "block": 4,
}
"""Ordering of the core spinal census geographies, coarsest first."""

GEOMETRY_FUNCS = {
    "nation": pygris.nation,
    "state": pygris.states,
    "county": pygris.counties,
    "tract": pygris.tracts,
    "blockgroup": pygris.block_groups,
    "block": pygris.blocks,
    "place": pygris.places,
    "puma": pygris.pumas,
    "core_based_statistical_area": pygris.core_based_statistical_areas,
    "congressional_district": pygris.congressional_districts,
    "school_district": pygris.school_districts,
    "county_subdivision": pygris.county_subdivisions,
}
"""Logical level name -> pygris function that fetches its boundaries."""

LEVEL_FALLBACK: Dict[str, str] = {
    "province": "county",
}
"""Standard levels (:data:`pycensus.geometry_levels.STANDARD_LEVELS`) the US has no
native geography for, mapped to the closest one it does have."""

GEO_HIERARCHIES: Dict[str, List[str]] = {
    "block": ["state", "county", "tract", "block"],
    "blockgroup": ["state", "county", "tract", "block group"],
    "tract": ["state", "county", "tract"],
    "county": ["state", "county"],
    "state": ["state"],
}
"""Level -> ordered geography chain used to build a Census API ``for``/``in`` predicate."""

ERASE_WATER: Dict[str, bool] = {
    "nation": False,
    "block": True,
    "blockgroup": True,
    "tract": True,
    "place": False,
    "county": False,
    "state": False,
    "puma": False,
    "core_based_statistical_area": False,
    "congressional_district": True,
    "school_district": True,
    "county_subdivision": False,
}
"""Level -> whether `pygris.utils.erase_water` should clip inland water bodies by default."""

LATEST_YEAR: Dict[str, int] = {
    "geography": 2023,
    "acs5": 2023,
    "acs1": 2024,
    "dhc": 2020,
    "lodes": 2021,
}
"""Most recent vintage year available per data kind, used when ``year="latest"``."""
