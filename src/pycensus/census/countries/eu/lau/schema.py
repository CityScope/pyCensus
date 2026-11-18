"""Common-schema column definitions of the EU ``lau`` source, read from ``schema/lau_schema.json``."""

from __future__ import annotations

from pycensus.census.countries.eu._schema import build_schema

SCHEMA = build_schema("lau", prefix="eurostat_lau")

__all__ = ["SCHEMA"]
