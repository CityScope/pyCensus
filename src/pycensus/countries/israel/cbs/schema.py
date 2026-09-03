"""Common-schema column definitions for Israel Census2022. 

This module now loads schema from the schema.json file instead of using
SCHEMA.add() calls. The schema is defined in israel/cbs/schema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnDef, ColumnSchema

# Load schema from JSON file
_schema_path = Path(__file__).parent.parent / "schema" / "cbs_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

# Build ColumnSchema from JSON data
SCHEMA = ColumnSchema(prefix="cbs")

# Map type from JSON to agg
_type_to_agg = {
    "count": "sum",
    "mean": "mean",
    "median": "mean",
    "percentage": "mean",
    "rate": "mean",
    "density": "mean",
    "area": "sum",
}

# Get source-level years and levels for default values
_source_years = _schema_data.get("years", [])
_source_levels = _schema_data.get("levels", [])

for feature in _schema_data.get("features", []):
    feature_name = feature.get("feature_name", "")
    codes = feature.get("codes", [])
    relative_to = feature.get("relative_to", "")
    
    # Determine agg from type
    feature_type = feature.get("type", "count")
    agg = _type_to_agg.get(feature_type, "sum")
    
    # weight_by is not in the new schema, so we leave it as None
    weight_by = None
    
    SCHEMA.add(
        name=feature_name,
        codes=codes,
        relative_to=relative_to if relative_to else None,
        agg=agg,
        weight_by=weight_by
    )
