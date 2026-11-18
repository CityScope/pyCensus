"""Common-schema column definitions of the EU ``eurostat`` source, read from ``schema/eurostat_schema.json``."""

from __future__ import annotations

from pycensus.census.countries.eu._schema import build_schema

SCHEMA = build_schema("eurostat", prefix="eurostat")

__all__ = ["SCHEMA"]
