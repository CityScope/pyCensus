"""New schema system that loads from JSON files instead of using ColumnSchema.add().

This module provides a new way to define and use schemas based on JSON files
with a standardized structure. Each country/source has a schema.json file that
defines its features, and the NewColumnSchema class loads and uses this data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import geohierarchy as gh


@dataclass(frozen=True)
class FieldKey:
    """A parsed `{year}_{country}_{source}_{feature_name}` column-name key.

    Replaces the old ad-hoc string formatting in `prefixed()`/`strip_prefix()`
    with a structured, round-trippable type: any of `year`, `country`,
    `source` may be omitted (``None``) -- not just `year` -- e.g. a
    cross-country comparison column with no `country`/`source` component at
    all, just `all_population`.

    Attributes:
        feature_name: The feature name segment (required).
        year: Year segment, or ``None`` if omitted ("any year").
        country: Country segment, or ``None`` if omitted.
        source: Source segment, or ``None`` if omitted.
    """

    feature_name: str
    year: Optional[int] = None
    country: Optional[str] = None
    source: Optional[str] = None

    def format(self) -> str:
        """Render back to a column name, e.g. "2020_usa_acs5_population" or "all_population"."""
        parts = [
            str(self.year) if self.year is not None else "all",
            self.country,
            self.source,
            self.feature_name,
        ]
        return "_".join(p for p in parts if p)

    @classmethod
    def parse(
        cls,
        column_name: str,
        known_countries: Optional[set] = None,
        known_sources: Optional[set] = None,
    ) -> "FieldKey":
        """Parse a column name back into its segments.

        Because any segment but `feature_name` can be omitted, unambiguous
        parsing needs to know which leading tokens are plausible
        `country`/`source` values -- pass `known_countries`/`known_sources`
        (e.g. from a loaded schema registry) when available. Without them,
        parsing falls back to a best-effort heuristic: a leading numeric
        token is `year` ("all" means "no year"), and if exactly two more
        leading tokens remain before what looks like a `feature_name`, they
        are treated as `country`, `source`.
        """
        parts = column_name.split("_")
        year: Optional[int] = None
        if parts and (parts[0].isdigit() or parts[0] == "all"):
            year = int(parts[0]) if parts[0].isdigit() else None
            parts = parts[1:]

        country: Optional[str] = None
        source: Optional[str] = None
        if known_countries is not None or known_sources is not None:
            if parts and parts[0] in (known_countries or set()):
                country = parts[0]
                parts = parts[1:]
            if parts and parts[0] in (known_sources or set()):
                source = parts[0]
                parts = parts[1:]
        elif len(parts) >= 3:
            # Heuristic fallback: assume the first two remaining tokens are
            # country/source and everything else is the feature name.
            country, source = parts[0], parts[1]
            parts = parts[2:]

        feature_name = "_".join(parts)
        return cls(feature_name=feature_name, year=year, country=country, source=source)


@dataclass
class FeatureDef:
    """A single feature definition from a schema.json file.
    
    Attributes:
        feature_name: The clean feature name (e.g., "population", "malePopulation").
        country: The country identifier (e.g., "usa").
        source: The source identifier (e.g., "acs", "dhc").
        years: List of years this feature is available.
        levels: Dictionary mapping years to available levels.
        category: The category this feature belongs to.
        codes: Raw source variable codes used to build this feature.
        definition: Human-readable definition.
        type: Data type (count, mean, median, percentage, etc.).
        unit: Unit of measurement.
        resampling_up: Resampling strategy for upscaling.
        resampling_down: Resampling strategy for downscaling.
        relative_to: Feature name this feature is relative to.
        absolute_field: The absolute field this is derived from.
    """
    
    feature_name: str
    country: str
    source: str
    years: List[int]
    levels: Dict[int, List[str]]
    category: str = ""
    codes: List[str] = field(default_factory=list)
    definition: str = ""
    type: str = ""
    unit: str = ""
    resampling_up: str = ""
    resampling_down: str = ""
    resampling_weight: str = ""
    relative_to: str = ""
    absolute_field: str = ""
    constant_total: bool = False
    constant_density: bool = False
    
    @property
    def is_count(self) -> bool:
        """Whether this is a count-type feature."""
        return self.type == "count"
    
    @property
    def is_average(self) -> bool:
        """Whether this is an average/relative-type feature."""
        return self.type in ("mean", "median", "percentage", "rate", "density")


@dataclass
class NewColumnSchema:
    """Schema loaded from a JSON file with features.
    
    This replaces the old ColumnSchema class that used SCHEMA.add() calls.
    Instead, it loads schema information from a schema.json file.
    
    Attributes:
        country: Country identifier.
        source: Source identifier.
        prefix: Column name prefix (default: f"{country}_{source}").
        features: Dictionary mapping feature names to FeatureDef objects.
        global_mapping: Optional mapping from global variable names to feature identifiers.
    """
    
    country: str
    source: str
    prefix: str = ""
    features: Dict[str, FeatureDef] = field(default_factory=dict)
    global_mapping: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        if not self.prefix:
            self.prefix = f"{self.country}_{self.source}"
    
    @classmethod
    def from_file(cls, filepath: str, global_mapping: Optional[Dict[str, str]] = None) -> "NewColumnSchema":
        """Load a schema from a JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        
        country = data.get("country", "")
        source = data.get("source", "")
        prefix = f"{country}_{source}"
        
        features = {}
        for feat_data in data.get("features", []):
            feature = FeatureDef(
                feature_name=feat_data.get("feature_name", ""),
                country=feat_data.get("country", country),
                source=feat_data.get("source", source),
                years=feat_data.get("years", []),
                levels=feat_data.get("levels", {}),
                category=feat_data.get("category", ""),
                codes=feat_data.get("codes", []),
                definition=feat_data.get("definition", ""),
                type=feat_data.get("type", ""),
                unit=feat_data.get("unit", ""),
                resampling_up=feat_data.get("resampling_up", ""),
                resampling_down=feat_data.get("resampling_down", ""),
                resampling_weight=feat_data.get("resampling_weight", ""),
                relative_to=feat_data.get("relative_to", ""),
                absolute_field=feat_data.get("absolute_field", ""),
                constant_total=feat_data.get("constant_total", False),
                constant_density=feat_data.get("constant_density", False),
            )
            features[feature.feature_name] = feature
        
        return cls(
            country=country,
            source=source,
            prefix=prefix,
            features=features,
            global_mapping=global_mapping
        )
    
    def get_feature(self, feature_name: str) -> Optional[FeatureDef]:
        """Get a feature by its feature_name."""
        return self.features.get(feature_name)
    
    def prefixed(self, feature_name: str, year: Optional[int] = None) -> str:
        """Return the column name for a feature.

        If year is provided: year_country_source_feature_name
        If year is None: all_country_source_feature_name
        """
        return FieldKey(
            feature_name=feature_name, year=year, country=self.country, source=self.source
        ).format()

    def key(self, feature_name: str, year: Optional[int] = None) -> FieldKey:
        """Return the structured :class:`FieldKey` for a feature (preferred over `prefixed`)."""
        return FieldKey(
            feature_name=feature_name, year=year, country=self.country, source=self.source
        )

    def parse_column(self, column_name: str) -> FieldKey:
        """Parse a column name produced by this schema back into a :class:`FieldKey`."""
        return FieldKey.parse(
            column_name, known_countries={self.country}, known_sources={self.source}
        )

    def strip_prefix(self, column_name: str) -> str:
        """Extract the feature name from a prefixed column name."""
        return self.parse_column(column_name).feature_name

    def get_feature_from_column(self, column_name: str) -> Optional[FeatureDef]:
        """Get the feature definition for a column name."""
        parsed = self.parse_column(column_name)
        if parsed.country == self.country and parsed.source == self.source:
            return self.features.get(parsed.feature_name)
        return None

    def relative_to(self, column_name: str) -> Optional[str]:
        """Resolve the denominator column for .relative, if any."""
        feature = self.get_feature_from_column(column_name)
        if feature and feature.relative_to:
            parsed = self.parse_column(column_name)
            return self.prefixed(feature.relative_to, parsed.year)
        return None
    
    def _resolve_weight_column(self, feature: FeatureDef) -> Optional[str]:
        """Resolve `resampling_weight` (a feature_name, or "area"/"" for none) to a column name."""
        w = feature.resampling_weight
        if not w or w == "area":
            return None
        return self.prefixed(w)

    def _build_strategy(
        self, feature: FeatureDef, intersection_mode: Optional[str] = None
    ) -> "gh.AggregationStrategy":
        """Map one feature's `resampling_up`/`resampling_down` strings onto a real strategy.

        `resampling_up`/`resampling_down` are schema-declared method names
        (currently: "sum", "weighted_divide", "weighted_mean", and source-
        specific variants like "labour_force_weighted_mean"). `gh.Sum`
        already implements both directions of "sum"/"weighted_divide"
        (upscale = weighted sum, downscale = proportional split by the same
        weight), and `gh.Mean` implements both directions of
        "weighted_mean" -- so a single strategy instance, keyed by the
        resolved weight column, covers both `resampling_up` and
        `resampling_down` for a feature. `resampling_weight == "area"` (or
        unset) means "no explicit weight column, split by intersection
        area/`intersection_mode` instead", which is `geoweighted=True` with
        no `weight_column`.
        """
        weight_col = self._resolve_weight_column(feature)
        # "area" (or no weight declared) means the split should be driven by
        # geometric overlap rather than another column, and any weighted_*
        # method implies geoweighting so `_geoweight` is actually consumed
        # (see AggregationStrategy.__init__).
        geoweighted = weight_col is None or bool(
            feature.resampling_up or feature.resampling_down
        )

        up = (feature.resampling_up or "").lower()
        down = (feature.resampling_down or "").lower()
        methods = {up, down} - {""}

        if "weighted_mean" in methods or methods == {"labour_force_weighted_mean"} or any(
            m.endswith("weighted_mean") for m in methods
        ):
            # e.g. "labour_force_weighted_mean" -> weight by the laborForce feature
            # specifically, regardless of what resampling_weight says, since the
            # method name itself names the weight.
            for m in methods:
                if m.endswith("_weighted_mean") and m != "weighted_mean":
                    implied_feature = m[: -len("_weighted_mean")].replace("_", "")
                    # Try a couple of naming variants (snake_case source name ->
                    # camelCase feature_name) since schema.json feature names are
                    # camelCase (e.g. "laborForce") while method names are
                    # snake_case ("labour_force_weighted_mean").
                    for candidate in (implied_feature, "laborForce", "laborForce".lower()):
                        if candidate in self.features:
                            weight_col = self.prefixed(candidate)
                            break
            return gh.Mean(
                weight_column=weight_col,
                geoweighted=True,
                intersection_mode=intersection_mode,
            )

        if "sum" in methods or "weighted_divide" in methods or feature.is_count:
            return gh.Sum(
                weight_column=weight_col,
                geoweighted=geoweighted,
                intersection_mode=intersection_mode,
            )

        # Fallback for anything unrecognized: plain (optionally weighted) mean,
        # matching the module's pre-redesign default behavior for non-count types.
        if not weight_col and feature.relative_to:
            weight_col = self.prefixed(feature.relative_to)
        return gh.Mean(
            weight_column=weight_col, geoweighted=True, intersection_mode=intersection_mode
        )

    def aggregations(
        self, intersection_mode: Optional[str] = None
    ) -> Dict[str, "gh.AggregationStrategy"]:
        """Build a {column: AggregationStrategy} map for geohierarchy.

        Args:
            intersection_mode: Optional ``"centroid"`` | ``"touches"`` |
                ``"exact"`` override applied to every built strategy (see
                :class:`geohierarchy.aggregation.AggregationStrategy`).
                geohierarchy bakes one `intersection_mode` per strategy
                instance, not per level-pair, so callers resampling through
                several level-pairs with different `intersection_mode`s
                (per `global_levels.json`) should call this once per
                level-pair with that pair's mode rather than reuse a single
                map everywhere.
        """
        strategies: Dict[str, Any] = {}
        for feature in self.features.values():
            prefixed = self.prefixed(feature.feature_name)
            strategies[prefixed] = self._build_strategy(feature, intersection_mode)
        return strategies

    def smooth_aggregations(
        self, k: int = 6, power: float = 2.0, intersection_mode: Optional[str] = None
    ) -> Dict[str, "gh.AggregationStrategy"]:
        """Build a {column: AggregationStrategy} map using SmoothMean downscale."""
        strategies: Dict[str, Any] = {}
        for feature in self.features.values():
            prefixed = self.prefixed(feature.feature_name)
            upscale = self._build_strategy(feature, intersection_mode)
            downscale = gh.SmoothMean(k=k, power=power, density=feature.is_count)
            strategies[prefixed] = gh.aggregation_strategy(upscale=upscale, downscale=downscale)
        return strategies


def load_schema(country: str, source: Optional[str] = None) -> NewColumnSchema:
    """Load a schema for a given country and source.
    
    Args:
        country: Country identifier (e.g., "usa", "mexico").
        source: Optional source identifier (e.g., "acs", "dhc"). 
               If None, loads the combined schema for the country.
    
    Returns:
        A NewColumnSchema instance loaded from the appropriate JSON file.
    """
    base_path = Path(__file__).parent / "countries" / country

    if source:
        schema_path = base_path / "schema" / f"{source}_schema.json"
        global_mapping = None
    else:
        schema_path = base_path / "schema" / "combined_schema.json"
        # Load global_mapping from country schema if it exists
        if schema_path.exists():
            with open(schema_path) as f:
                data = json.load(f)
            global_mapping = data.get("global_mapping")
        else:
            global_mapping = None
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    schema = NewColumnSchema.from_file(str(schema_path), global_mapping)
    return schema
