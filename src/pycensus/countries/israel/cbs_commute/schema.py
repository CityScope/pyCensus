"""Column schema of the Israel Census 2022 means-of-transport-to-work source (from ``schema/cbs_commute_schema.json``)."""
from __future__ import annotations

import json
from pathlib import Path

from ....schema import ColumnSchema

_data = json.loads((Path(__file__).parent.parent / "schema" / "cbs_commute_schema.json").read_text(encoding="utf-8"))
SCHEMA = ColumnSchema(prefix="cbscommute")
for _f in _data["features"]:
    SCHEMA.add(name=_f["feature_name"], codes=_f["codes"], relative_to=None, agg="sum", weight_by=None)
FEATURES = {f["feature_name"]: f for f in _data["features"]}
SOURCE_URL = _data["source_url"]
