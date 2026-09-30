"""Common-schema column metadata for US election results (MEDSL).

**Structurally different from every other USA source's `schema.py`**:
`loader.py` doesn't fetch numbered Census API variable codes and sum
them -- it aggregates real vote counts from MEDSL's own CSV/precinct
files (see that module's docstring), so every feature's `codes` here is
honestly empty, not a placeholder omission. This module exists purely so
`geometry_levels.is_native_level`/downstream resampling code (e.g.
`usa_study/code/state_pipeline.py`'s district resampling) has the same
`agg` ("sum" for `*_total_votes`, "mean" for `*_share`) and
`NATIVE_LEVELS` metadata every other source declares -- without it,
election columns would silently fall through to whichever default an
aggregation helper happens to assume.

Also unlike every other source, `ColumnSchema.prefix` is deliberately
`""`: `loader.py`'s real output column names (`{year}_{office}_
total_votes`, not `elections_{year}_{office}_total_votes`) already are
the full name with no separate prefix -- registering each feature under
its own full name as `name` (not a short logical name meant to be
prefixed) means `SCHEMA.columns[name].agg` resolves correctly by the
real column name directly. `SCHEMA.column_label(name)` would still
produce a spurious leading-underscore variant (`"_2024_..."`, from
`f"{prefix}_{name}"` with an empty prefix) -- harmless (nothing looks
that variant up), but not a name any real column actually has.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnSchema

_schema_path = Path(__file__).parent.parent / "schema" / "elections_schema.json"

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

_source_levels = _schema_data.get("levels", [])
NATIVE_LEVELS = _schema_data.get("native_levels", _source_levels)

SCHEMA = ColumnSchema(prefix="")
for _feature in _schema_data.get("features", []):
    SCHEMA.add(
        name=_feature.get("feature_name", ""),
        codes=_feature.get("codes", []),
        relative_to=_feature.get("relative_to") or None,
        agg=_type_to_agg.get(_feature.get("type", "count"), "sum"),
        weight_by=None,
    )
