"""Common-schema column definitions for Spain's Censo 2021 (SDC21) source.

This module loads schema from ``spain/schema/censo2021_schema.json``. Unlike
the Padron (``spain.ine``) schema, each feature here isn't a single raw
column code -- it's a ``(table, metric, variable, category_value)`` lookup
into INE's SDC21 API (see :mod:`pycensus.countries.spain.censo2021.api` and
``loader.py``). :data:`FEATURE_FETCH_SPEC` carries that fetch metadata,
keyed by bare feature name, for the loader to use; :data:`SCHEMA` itself
only carries the naming/aggregation metadata every other source's schema
carries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ....schema import ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "censo2021_schema.json"

with open(_schema_path) as f:
    _schema_data = json.load(f)

SCHEMA = ColumnSchema(prefix="censo2021")

_type_to_agg = {
    "count": "sum",
    "mean": "mean",
    "median": "mean",
    "percentage": "mean",
    "rate": "mean",
    "density": "mean",
    "area": "sum",
}

# {feature_name: {"table": ..., "metric": ..., "variable": ..., "category_value": ...}}
# ``category_value`` is either a single raw SDC21 category label, a list of
# labels to sum (e.g. secondary education's two sub-stages), or ``None``
# when the whole table/metric total is the feature itself (households).
FEATURE_FETCH_SPEC: Dict[str, dict] = {}

for feature in _schema_data.get("features", []):
    feature_name = feature.get("feature_name", "")
    relative_to = feature.get("relative_to", "")
    feature_type = feature.get("type", "count")
    agg = _type_to_agg.get(feature_type, "sum")

    SCHEMA.add(
        name=feature_name,
        codes=[feature_name],
        relative_to=relative_to if relative_to else None,
        agg=agg,
        weight_by=None,
    )

    FEATURE_FETCH_SPEC[feature_name] = {
        "table": feature.get("table"),
        "metric": feature.get("metric"),
        "variable": feature.get("variable"),
        "category_value": feature.get("category_value"),
    }
