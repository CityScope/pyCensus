"""Common-schema column definitions for WorldPop gridded population data.

Technical aspects:
    Registers the ``worldpop`` GeoDataFrame accessor (``gdf.worldpop[...]``)
    the same way :mod:`pycensus.usa.acs5.schema` registers ``gdf.acs5[...]``:
    a single :class:`pycensus.schema.ColumnSchema` with prefix ``"worldpop"``,
    consumed by :func:`pycensus.accessors.register_source_accessor`. Unlike
    ACS, WorldPop has no raw "codes" to sum -- each logical column here maps
    1:1 to a value sampled/vectorized out of the downloaded GeoTIFF (see
    :mod:`pycensus.worldwide.worldpop.loader`) -- but ``codes`` is populated
    with the column's own name for schema-shape compatibility.

Source:
    WorldPop population and age-structure rasters: https://www.worldpop.org/
    (dataset catalog: https://hub.worldpop.org/rest/data/).
"""

from ....schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="worldpop")

# ---------------- total population ----------------
SCHEMA.add("population", ["population"])

# ---------------- age-structure subsets ----------------
# WorldPop's "age_structures" dataset ships per-age-band population counts;
# mirror the `download_worldpop_population(dataset="age_structures", subset=...)`
# naming (e.g. "under_18"/"U18") as logical columns relative to total population.
SCHEMA.add("population_under_18", ["population_under_18"], relative_to="population")
