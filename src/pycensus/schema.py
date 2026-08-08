"""Common-schema column registry shared by every country's census source.

Technical aspects:
    Each source module (e.g. ``USA.acs``, ``USA.lodes``) builds one
    :class:`ColumnSchema` describing its logical columns in the shared
    cross-country wording (``population``, ``households``, ``gdp``, ...):
    which raw source codes are summed to build each column, which other
    logical column is its denominator for ``.relative``, and which
    :mod:`geohierarchy.aggregation` strategy resamples it across levels.

    The schema is the single source of truth consumed by:
        - the source's ``loader.py`` (to know which raw codes to fetch and
          how to name/derive the resulting columns), and
        - :mod:`pycensus.accessors` (to resolve ``.relative`` denominators).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

import geohierarchy as gh


@dataclass
class ColumnDef:
    """A single logical column definition.

    ``agg`` is the single standard place every part of pyCensus reads to
    know whether a column is a count/total or an average/relative
    quantity -- nothing else (loaders, ``.relative``, resampling) infers
    this independently. Concretely:

    - ``"sum"`` (:attr:`is_count`): an additive count or total (e.g.
      population, jobs, households). Its value can be validly summed
      across rows, and resampling it across geohierarchy levels should
      reproduce that total exactly (:attr:`~geohierarchy.aggregation.AggregationStrategy.preserve_total`).
    - ``"mean"`` (:attr:`is_average`): an intensive/relative quantity with
      no meaningful total (e.g. a median, a rate, a per-capita figure).
      Resampling it produces a representative value, not a sum, and no
      total-preservation is expected or attempted.

    Attributes:
        name: Common logical name, unprefixed (e.g. ``"population"``).
        codes: Raw source variable codes summed to build this column.
        relative_to: Logical name of the column used as the denominator
            for ``.relative``, or ``None`` if not applicable (e.g. a
            median that has no meaningful ratio).
        agg: ``"sum"`` for an additive count/total, ``"mean"`` for an
            intensive/average quantity -- see class docstring.
        weight_by: Logical name of the column used to weight a
            ``"mean"``-aggregated column (e.g. a median income weighted
            by ``households``). Ignored for ``"sum"``.
    """

    name: str
    codes: List[str]
    relative_to: Optional[str] = None
    agg: Literal["sum", "mean"] = "sum"
    weight_by: Optional[str] = None

    @property
    def is_count(self) -> bool:
        """Whether this is an additive count/total column (``agg == "sum"``)."""
        return self.agg == "sum"

    @property
    def is_average(self) -> bool:
        """Whether this is an intensive/relative column with no real total (``agg == "mean"``)."""
        return self.agg == "mean"


@dataclass
class ColumnSchema:
    """Registry of a source's logical columns.

    Attributes:
        prefix: Column name prefix used on the GeoDataFrame and as the
            accessor name (e.g. ``"lodes"`` for ``gdf.lodes``).
        columns: Mapping of unprefixed logical column name to its
            :class:`ColumnDef`.
    """

    prefix: str
    columns: Dict[str, ColumnDef] = field(default_factory=dict)

    def add(
        self,
        name: str,
        codes: List[str],
        relative_to: Optional[str] = None,
        agg: Literal["sum", "mean"] = "sum",
        weight_by: Optional[str] = None,
    ) -> "ColumnSchema":
        """Register a logical column and return ``self`` for chaining.

        Args:
            name: Unprefixed logical column name.
            codes: Raw source variable codes summed to build this column.
            relative_to: Unprefixed logical name of the ``.relative``
                denominator column.
            agg: ``"sum"`` for additive counts, ``"mean"`` for intensive
                quantities (rates, medians).
            weight_by: Unprefixed logical name of the weighting column
                for ``"mean"`` aggregation.
        """
        self.columns[name] = ColumnDef(
            name=name, codes=codes, relative_to=relative_to, agg=agg, weight_by=weight_by
        )
        return self

    def prefixed(self, name: str) -> str:
        """Return the on-GeoDataFrame column name for a logical name."""
        return f"{self.prefix}_{name}"

    def strip_prefix(self, prefixed_name: str) -> str:
        """Return the logical (unprefixed) name for an on-GeoDataFrame column name."""
        head = self.prefix + "_"
        return prefixed_name[len(head):] if prefixed_name.startswith(head) else prefixed_name

    def relative_to(self, prefixed_name: str) -> Optional[str]:
        """Resolve the prefixed denominator column for ``.relative``, if any."""
        col = self.columns.get(self.strip_prefix(prefixed_name))
        if col is None or col.relative_to is None:
            return None
        return self.prefixed(col.relative_to)

    def aggregations(self) -> Dict[str, "gh.AggregationStrategy"]:
        """Build a ``{prefixed_column: AggregationStrategy}`` map for :meth:`geohierarchy.GeoHierarchy.add_level`.

        Always geoweighted: census geographies (tracts, block groups, H3
        cells, ...) rarely nest cleanly, so an un-geoweighted mapping falls
        back to matching each destination row to whichever single source
        polygon contains its centroid -- any source row with no
        destination centroid landing inside it (common for small source
        polygons matched against much coarser or differently-shaped
        destination cells) is silently dropped from the result entirely,
        which can lose the large majority of a column's total. Area-based
        overlap weighting doesn't have that failure mode.
        """
        strategies: Dict[str, gh.AggregationStrategy] = {}
        for col in self.columns.values():
            prefixed = self.prefixed(col.name)
            if col.is_count:
                strategies[prefixed] = gh.Sum(geoweighted=True)
            else:
                weight_col = self.prefixed(col.weight_by) if col.weight_by else None
                strategies[prefixed] = gh.Mean(weight_column=weight_col, geoweighted=True)
        return strategies

    def smooth_aggregations(self, k: int = 6, power: float = 2.0) -> Dict[str, "gh.AggregationStrategy"]:
        """Build a ``{prefixed_column: AggregationStrategy}`` map using :class:`geohierarchy.SmoothMean` downscale.

        Same upscale behavior as :meth:`aggregations`, but every column's
        downscale is :class:`~geohierarchy.aggregation.SmoothMean` instead
        of the default geoweighted split -- for a much finer destination
        level (e.g. an H3 grid several resolutions past the source data),
        where a hard geometric split would look blocky. Each column's
        ``is_count``/``is_average`` (from its registered ``agg``) is passed
        straight through as ``SmoothMean(density=...)``, so count columns
        keep their totals exact (:attr:`~geohierarchy.aggregation.AggregationStrategy.preserve_total`)
        while relative/average columns are blended without that constraint
        -- exactly the "totals maintained except for relative columns"
        rule, applied automatically for every column in this schema.

        Args:
            k: Number of nearest source neighbors to blend per destination row.
            power: Inverse-distance weighting exponent.

        Returns:
            Mapping suitable for :meth:`geohierarchy.GeoHierarchy.set_aggregation`
            (one call per column) or as a per-column override at a specific level.
        """
        strategies: Dict[str, gh.AggregationStrategy] = {}
        for col in self.columns.values():
            prefixed = self.prefixed(col.name)
            downscale = gh.SmoothMean(k=k, power=power, density=col.is_count)
            if col.is_count:
                upscale = gh.Sum(geoweighted=True)
            else:
                weight_col = self.prefixed(col.weight_by) if col.weight_by else None
                upscale = gh.Mean(weight_column=weight_col, geoweighted=True)
            strategies[prefixed] = gh.aggregation_strategy(upscale=upscale, downscale=downscale)
        return strategies
