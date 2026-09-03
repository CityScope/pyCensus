"""Common-schema column definitions for Canada StatCan 2021 Census.

Loads schema from ``schema.json`` (the single source of truth for field
codes) into a :class:`~pycensus.schema.ColumnSchema`. Mirrors
``pycensus.mexico.inegi.schema``'s pattern -- thin, boilerplate JSON
loading, no hand-written ``ColumnSchema.add()`` calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "statcan_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

SCHEMA = ColumnSchema(prefix="statcan")

_type_to_agg = {
    "count": "sum",
    "mean": "mean",
    "median": "mean",
    "percentage": "mean",
    "rate": "mean",
    "density": "mean",
    "area": "sum",
}

for feature in _schema_data.get("features", []):
    feature_name = feature.get("feature_name", "")
    codes = feature.get("codes", [])
    relative_to = feature.get("relative_to", "")
    feature_type = feature.get("type", "count")
    agg = _type_to_agg.get(feature_type, "sum")
    weight_by = feature.get("resampling_weight") or None

    SCHEMA.add(
        name=feature_name,
        codes=codes,
        relative_to=relative_to if relative_to else None,
        agg=agg,
        weight_by=weight_by,
    )
