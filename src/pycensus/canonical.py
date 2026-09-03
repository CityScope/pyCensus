"""Canonical (global-schema) column naming for every source's ``load()`` output.

Technical aspects:
    ``schemas/global_schema.json`` is pyCensus' cross-country vocabulary:
    a list of ``feature_name`` entries (``population``, ``malePopulation``,
    ``medianHouseholdIncome``, ...) that mean the same thing in every
    country. Each country's ``schema.py`` already names its
    :class:`~pycensus.schema.ColumnDef` after the matching
    ``feature_name`` wherever a genuine equivalent exists (that is a
    stated convention in ``IMPLEMENTING_A_COUNTRY.md``).

    On the GeoDataFrame, however, every column used to carry the source
    prefix (``inegi_population``). :func:`apply_canonical_names` is the
    single shared step -- called by every source's ``load()`` right
    before it returns -- that drops the prefix from exactly those columns
    whose logical name is an exact ``global_schema.json`` feature, and
    leaves every source-specific column prefixed
    (``inegi_populationCatholic``). Callers can therefore read
    ``gdf["population"]`` in any country with no name matching of their
    own, while still seeing every extra column the census offers.

    Nothing is ever dropped -- this is a pure rename.

    On the ``population`` collision question: pyCensus never joins two
    different sources' GeoDataFrames onto one frame internally (each
    ``load()`` returns its own frame; ``worldwide.worldpop`` has no
    ``load()`` at all -- it returns raster paths), so bare canonical
    names cannot collide inside pyCensus. A consumer that merges a
    pyCensus frame onto a frame of its own that already has, say, a
    WorldPop-derived ``population`` column, must resolve that collision
    at its own merge point; it is not special-cased here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Optional

if TYPE_CHECKING:  # pragma: no cover
    import geopandas as gpd

    from .schema import ColumnSchema

GLOBAL_SCHEMA_PATH = Path(__file__).parent / "schemas" / "global_schema.json"


@lru_cache(maxsize=1)
def global_feature_names() -> FrozenSet[str]:
    """Return the set of ``feature_name`` values in ``global_schema.json`` (cached)."""
    with open(GLOBAL_SCHEMA_PATH) as fh:
        features = json.load(fh)
    return frozenset(entry["feature_name"] for entry in features)


def is_canonical(name: str) -> bool:
    """Whether a logical (unprefixed) column name is a global-schema feature."""
    return name in global_feature_names()


def canonical_rename_map(schema: "ColumnSchema") -> Dict[str, str]:
    """Return ``{prefixed_name: bare_name}`` for this schema's canonical columns."""
    return {
        schema.prefixed(name): name
        for name in schema.columns
        if is_canonical(name)
    }


def apply_canonical_names(gdf: "gpd.GeoDataFrame", schema: "ColumnSchema") -> "gpd.GeoDataFrame":
    """Rename a loader's output columns to bare global-schema names in place-ish.

    Every column of ``gdf`` whose logical name (prefix stripped) is an
    exact ``global_schema.json`` ``feature_name`` is renamed to that bare
    name; all other columns keep their prefixed names. No column is ever
    dropped or reordered.

    Args:
        gdf: A source ``load()``'s output GeoDataFrame, with prefixed columns.
        schema: The source's :class:`~pycensus.schema.ColumnSchema`.

    Returns:
        The GeoDataFrame with canonical columns renamed (the same object
        when nothing needed renaming).
    """
    mapping = {k: v for k, v in canonical_rename_map(schema).items() if k in gdf.columns}
    # Never clobber an existing bare column (would silently lose data).
    mapping = {k: v for k, v in mapping.items() if v not in gdf.columns}
    if not mapping:
        return gdf
    return gdf.rename(columns=mapping)


def resolve_column(gdf, schema: "ColumnSchema", name: str) -> Optional[str]:
    """Return the actual column of ``gdf`` holding logical ``name``, or ``None``.

    After :func:`apply_canonical_names`, a logical column may live on the
    frame either bare (canonical) or prefixed (source-specific), and a
    frame that skipped canonicalization has everything prefixed. This is
    the single place that decides which of the two is present.

    Args:
        gdf: Any DataFrame/GeoDataFrame carrying this source's columns.
        schema: The source's column schema.
        name: Logical or already-prefixed column name.

    Returns:
        The matching column label present on ``gdf``, else ``None``.
    """
    logical = schema.strip_prefix(name)
    prefixed = schema.prefixed(logical)
    columns = gdf.columns
    if prefixed in columns:
        return prefixed
    if logical in columns:
        return logical
    return None


__all__ = [
    "global_feature_names",
    "is_canonical",
    "canonical_rename_map",
    "apply_canonical_names",
    "resolve_column",
]
