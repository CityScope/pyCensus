"""Common-schema column definitions of the EU ``census_grid`` source, read from ``schema/census_grid_schema.json``."""

from __future__ import annotations

from .._schema import build_schema

SCHEMA = build_schema("census_grid", prefix="eurostat_grid")

__all__ = ["SCHEMA"]
