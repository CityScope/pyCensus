"""pyCensus: common-schema census loaders ready to drop into a geohierarchy.GeoHierarchy.

Every source across every country shares two conventions:
    - **Common wording**: logical column names (``population``, ``households``,
      ``gdp``, ...) are shared across sources and countries wherever the
      underlying concept matches, so e.g. ``population`` means the same
      thing whether it came from LODES or the ACS.
    - **Accessors**: importing a source module registers a GeoDataFrame
      accessor named after it (``gdf.lodes_rac``, ``gdf.acs``, ...).
      Indexing the accessor with a logical column name returns a
      :class:`~pycensus.accessors.ColumnView`, which adds
      ``.density`` (value / geometry area in m2, or length in m for lines)
      and ``.relative`` (value / that column's registered total, per
      :class:`~pycensus.schema.ColumnSchema`) on top of the raw values.

Each source's loader returns a plain GeoDataFrame with a ``GEOID`` id
column and prefixed attribute columns -- pass it straight to
:meth:`geohierarchy.GeoHierarchy.add_level` (using the source's
``SCHEMA.aggregations()`` for the ``agg`` argument) to build a hierarchy,
or use it standalone.

Currently implemented:
    - United States (:mod:`pycensus.USA`): ACS 5-year estimates, 2020
      Decennial Census DHC, and LODES RAC/WAC job counts.
    - Mexico (:mod:`pycensus.mexico`): INEGI Census 2020 disaggregated data
      including population, gender, ethnicity, religion, income, employment,
      housing, car ownership, and commuting mode.
    - Spain (:mod:`pycensus.spain`): INE Census 2021 disaggregated data
      including population, nationality, education, income, employment,
      housing, car ownership, commuting mode, disability, and more.
    - Worldwide (:mod:`pycensus.worldwide`): WorldPop gridded population
      rasters.
"""

from . import USA, cache, geometry_levels, mexico, spain, worldwide
from .accessors import ColumnView
from .api_keys import resolve_api_key
from .schema import ColumnDef, ColumnSchema

__all__ = [
    "USA",
    "mexico",
    "spain",
    "worldwide",
    "ColumnView",
    "ColumnSchema",
    "ColumnDef",
    "resolve_api_key",
    "cache",
    "geometry_levels",
]
