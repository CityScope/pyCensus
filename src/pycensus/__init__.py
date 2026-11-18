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
    - Israel (:mod:`pycensus.israel`): CBS Census 2022 disaggregated data
      including population, religion, immigration, education, employment, housing.
    - Germany (:mod:`pycensus.germany`): Destatis Census 2022 disaggregated data
      including population, nationality, education, employment, housing, religion.
    - Worldwide (:mod:`pycensus.census.worldwide`): WorldPop gridded population
      rasters.
    - Euskadi (:mod:`pycensus.euskadi`): Eustat Census 2021 disaggregated data
      for the Basque Country, including population, Basque/Spanish language skills,
      nationality, education, employment, housing, car ownership, and commuting mode.
"""

from pycensus import cache, cadaster, census, geometry_levels
from pycensus.accessors import ColumnView
from pycensus.api_keys import resolve_api_key
from pycensus.schema import ColumnDef, ColumnSchema

# Real regression fixed 2026-08-25: this used to also eagerly import
# `USA`/`euskadi`/`germany`/`israel`/`mexico`/`spain` as direct submodules
# of `pycensus` -- that flat layout was superseded by `pycensus.census.countries.*`
# (every real country loader lives there now: `pycensus.census.countries.usa`,
# `pycensus.census.countries.israel.cbs`, ...), and those top-level directories no
# longer exist on disk. Importing them here unconditionally meant ANY bare
# `import pycensus` crashed with a circular-import `ImportError` the moment
# something (e.g. `code.city_core`) imported `pycensus.census.countries.usa...`
# before `pycensus/__init__.py` had finished running. `countries` needs no
# explicit import here -- `pycensus.census.countries.X` imports work as a normal
# subpackage regardless, and nothing in real, current code reads
# `pycensus.USA`/`pycensus.mexico`/etc. as a pre-imported attribute (only
# some now-stale test files under `tests/` still do, pre-existing breakage
# unrelated to this fix).
__all__ = [
    "census",
    "cadaster",
    "ColumnView",
    "ColumnSchema",
    "ColumnDef",
    "resolve_api_key",
    "cache",
    "geometry_levels",
]
