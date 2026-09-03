"""Common-schema column definitions for Chile's Casen SAE comunal poverty estimates.

Loads schema from schema.json rather than hand-written SCHEMA.add() calls --
mirrors pycensus.countries.chile.ine.schema's shape exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "casen_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

SCHEMA = ColumnSchema(prefix="casen_cl")

_type_to_agg = {
    "count": "sum",
    "mean": "mean",
    "median": "mean",
    "percentage": "mean",
    "rate": "mean",
    "density": "mean",
    "area": "sum",
}

_source_years = _schema_data.get("years", [])
_source_levels = _schema_data.get("levels", [])

for feature in _schema_data.get("features", []):
    feature_name = feature.get("feature_name", "")
    codes = feature.get("codes", [])
    relative_to = feature.get("relative_to", "")

    feature_type = feature.get("type", "count")
    agg = _type_to_agg.get(feature_type, "sum")

    weight_by = None

    SCHEMA.add(
        name=feature_name,
        codes=codes,
        relative_to=relative_to if relative_to else None,
        agg=agg,
        weight_by=weight_by,
    )
