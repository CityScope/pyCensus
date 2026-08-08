"""Per-source GeoDataFrame accessors: ``gdf.lodes[...]``, ``gdf.acs[...]``, etc.

Technical aspects:
    Each source registers a `pandas.api.extensions.register_dataframe_accessor`
    accessor named after its :class:`~pycensus.schema.ColumnSchema` prefix.
    GeoDataFrame subclasses DataFrame, so a DataFrame-level accessor works
    identically on ``gdf.<source>`` for any GeoDataFrame.
    The accessor is a thin namespace: indexing it with a logical column name
    (or list of names) returns a :class:`ColumnView`, a wrapper around the
    selected column(s) adding two derivations:

        - ``.density``: value(s) divided by the geometry's area in square
          meters (or length in meters for line geometries), computed with
          :func:`geohierarchy.utils.area` / :func:`geohierarchy.utils.length`.
        - ``.relative``: value(s) divided by the column registered as their
          ``relative_to`` total in the source's :class:`ColumnSchema`.

    Registration is global (like geopandas' own ``.geometry``), so the
    accessor works on any GeoDataFrame carrying that source's prefixed
    columns -- both a source loader's direct output and a GeoDataFrame
    pulled back out of a :class:`geohierarchy.GeoHierarchy` level.
"""

from __future__ import annotations

from typing import List, Union

import geopandas as gpd
import pandas as pd

from .schema import ColumnSchema


class ColumnView:
    """Wraps a selected column (or columns) with `.density` / `.relative` derivations.

    Duck-types the wrapped pandas object by delegating attribute access to
    it, so e.g. ``gdf.lodes["population"].sum()`` works directly on the
    underlying Series without going through ``.data``.

    Attributes:
        data: The selected raw values -- a Series for a single column, a
            DataFrame for several.
    """

    def __init__(self, data: Union[pd.Series, pd.DataFrame], gdf: gpd.GeoDataFrame, schema: ColumnSchema) -> None:
        """Initialize the view.

        Args:
            data: Selected column(s) from ``gdf``.
            gdf: Parent GeoDataFrame, used to compute ``.density``.
            schema: Source's column schema, used to resolve ``.relative``.
        """
        self.data = data
        self._gdf = gdf
        self._schema = schema

    @property
    def density(self) -> Union[pd.Series, pd.DataFrame]:
        """Value(s) divided by geometry area in m2 (length in m for lines)."""
        from geohierarchy.utils import area, length

        geom_types = self._gdf.geometry.geom_type.str.replace("^Multi", "", regex=True)
        is_line = bool((geom_types == "LineString").any())
        denom = length(self._gdf) if is_line else area(self._gdf)
        return self._divide(denom)

    @property
    def relative(self) -> Union[pd.Series, pd.DataFrame]:
        """Value(s) divided by each column's registered ``relative_to`` total."""
        if isinstance(self.data, pd.Series):
            return self.data / self._gdf[self._require_total(self.data.name)]

        out = {}
        for col in self.data.columns:
            out[col] = self.data[col] / self._gdf[self._require_total(col)]
        return pd.DataFrame(out, index=self.data.index)

    def _require_total(self, prefixed_name: str) -> str:
        total_col = self._schema.relative_to(prefixed_name)
        if total_col is None:
            raise ValueError(f"No 'relative_to' total registered for column '{prefixed_name}'")
        return total_col

    def _divide(self, denom: pd.Series) -> Union[pd.Series, pd.DataFrame]:
        if isinstance(self.data, pd.Series):
            return self.data / denom
        return self.data.div(denom, axis=0)

    def __getattr__(self, name: str):
        return getattr(self.data, name)

    def __repr__(self) -> str:
        return repr(self.data)


def register_source_accessor(schema: ColumnSchema) -> type:
    """Register a GeoDataFrame accessor named ``schema.prefix``.

    Args:
        schema: Column schema whose ``prefix`` becomes the accessor name
            (e.g. ``gdf.lodes`` for a schema with ``prefix="lodes"``).

    Returns:
        The registered accessor class.
    """

    @pd.api.extensions.register_dataframe_accessor(schema.prefix)
    class _SourceAccessor:
        def __init__(self, gdf: gpd.GeoDataFrame) -> None:
            self._gdf = gdf

        def __getitem__(self, key: Union[str, List[str]]) -> ColumnView:
            names = [key] if isinstance(key, str) else list(key)
            prefixed = [n if n.startswith(schema.prefix + "_") else schema.prefixed(n) for n in names]
            data = self._gdf[prefixed[0]] if len(prefixed) == 1 else self._gdf[prefixed]
            return ColumnView(data, self._gdf, schema)

        @property
        def columns(self) -> List[str]:
            """Logical (unprefixed) column names available for this source."""
            return list(schema.columns.keys())

    return _SourceAccessor
