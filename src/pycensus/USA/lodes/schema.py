"""Common-schema column definitions for LODES RAC and WAC files.

Technical aspects:
    RAC (Residence Area Characteristics) and WAC (Workplace Area
    Characteristics) share the same job-count field codes -- they just
    describe jobs held by residents of a block vs. jobs located in a block,
    respectively. :func:`build_schema` builds one :class:`ColumnSchema` per
    file kind, prefixed ``lodes_rac`` / ``lodes_wac`` so both can coexist as
    separate ``gdf.lodes_rac`` / ``gdf.lodes_wac`` accessors on the same
    GeoDataFrame.

Source:
    LODES technical documentation, field code definitions:
    https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.3.pdf
"""

from ...schema import ColumnSchema


def build_schema(prefix: str) -> ColumnSchema:
    """Build the LODES job-count column schema for a given accessor prefix.

    Args:
        prefix: Accessor/column prefix, e.g. ``"lodes_rac"`` or ``"lodes_wac"``.

    Returns:
        A populated :class:`ColumnSchema`.
    """
    schema = ColumnSchema(prefix=prefix)
    schema.add("jobs_total", ["C000"])
    schema.add("jobs_income_low", ["CE01"], relative_to="jobs_total")
    schema.add("jobs_income_mid", ["CE02"], relative_to="jobs_total")
    schema.add("jobs_income_high", ["CE03"], relative_to="jobs_total")
    schema.add("jobs_age_young", ["CA01"], relative_to="jobs_total")
    schema.add("jobs_age_prime", ["CA02"], relative_to="jobs_total")
    schema.add("jobs_age_older", ["CA03"], relative_to="jobs_total")
    return schema


RAC_SCHEMA = build_schema("lodes_rac")
WAC_SCHEMA = build_schema("lodes_wac")
