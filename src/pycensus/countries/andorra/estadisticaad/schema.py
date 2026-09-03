"""Common-schema column definitions for Andorra's Departament d'Estadistica source.

This module loads schema from schema.json rather than hand-writing
``SCHEMA.add()`` calls -- see ``spain/ine/schema.py`` for the pattern this
mirrors.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "estadisticaad_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

SCHEMA = ColumnSchema(prefix="estadisticaad")

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

    SCHEMA.add(
        name=feature_name,
        codes=codes,
        relative_to=relative_to if relative_to else None,
        agg=agg,
        weight_by=None,
    )
