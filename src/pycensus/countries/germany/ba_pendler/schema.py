"""Common-schema column definitions for BA (Bundesagentur fuer Arbeit) Pendlerstatistik.

Loads schema from ``germany/schema/ba_pendler_schema.json`` -- see that file
for the live-verification note (Hamburg + Pinneberg, 2025 Wohnort/Arbeitsort/
Pendler cross-tab).
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnDef, ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "ba_pendler_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

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

SCHEMA = ColumnSchema(prefix="ba_pendler")
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

__all__ = ["SCHEMA"]
