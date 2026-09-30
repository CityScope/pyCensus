"""Common-schema column definitions for LODES RAC (Residence Area Characteristics).

This module loads schema from the schema.json file instead of using
SCHEMA.add() calls. The schema is defined in usa/lodes_rac/schema.json.

Source:
    LODES (LEHD Origin-Destination Employment Statistics): https://lehd.ces.census.gov/data/
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnDef, ColumnSchema

# Load schema from JSON file
_schema_path = Path(__file__).parent.parent / "schema" / "lodes_rac_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

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
NATIVE_LEVELS = _schema_data.get("native_levels", _source_levels)

SCHEMA = ColumnSchema(prefix="lodes_rac")
for _feature in _schema_data.get("features", []):
    _feature_name = _feature.get("feature_name", "")
    _codes = _feature.get("codes", [])
    _relative_to = _feature.get("relative_to", "")
    _feature_type = _feature.get("type", "count")
    _agg = _type_to_agg.get(_feature_type, "sum")

    SCHEMA.add(
        name=_feature_name,
        codes=_codes,
        relative_to=_relative_to if _relative_to else None,
        agg=_agg,
        weight_by=None,
    )

# Backward-compat alias for the pre-split combined "lodes" package.
RAC_SCHEMA = SCHEMA
