"""Builds a :class:`~pycensus.schema.ColumnSchema` from ``schema/<source>_schema.json`` (same pattern as the Andorra
and Spain sources)."""

from __future__ import annotations

import json
from pathlib import Path

from pycensus.schema import ColumnSchema

_TYPE_TO_AGG = {"count": "sum", "mean": "mean", "median": "mean", "percentage": "mean", "rate": "mean",
                "density": "mean", "area": "sum"}


def schema_json(source: str) -> dict:
    """The parsed ``schema/<source>_schema.json``.

    Args:
        source: Source folder name.

    Returns:
        The schema dict.
    """
    return json.loads((Path(__file__).parent / "schema" / f"{source}_schema.json").read_text(encoding="utf-8"))


def build_schema(source: str, prefix: str) -> ColumnSchema:
    """Column schema of ``source`` with prefix ``prefix`` (one entry per feature of the JSON).

    Args:
        source: Source folder name.
        prefix: Column prefix.

    Returns:
        The :class:`~pycensus.schema.ColumnSchema`.
    """
    s = ColumnSchema(prefix=prefix)
    for f in schema_json(source).get("features", []):
        s.add(name=f["feature_name"], codes=f.get("codes", []), relative_to=f.get("relative_to") or None,
              agg=_TYPE_TO_AGG.get(f.get("type", "count"), "sum"), weight_by=None)
    return s
