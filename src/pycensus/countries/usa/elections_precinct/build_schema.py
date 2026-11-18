# -*- coding: utf-8 -*-
"""Regenerate ``schema/elections_precinct_schema.json`` by running every election (needs data access)."""

from pathlib import Path

from ....elections_common import schema_features, write_schema
from .loader import ELECTIONS, load_all

SCOPE_DESC = {"national": "latest national election (US President 2024)", "state": "latest state election (Governor 2022)", "municipal": "latest municipal election (Mayor; Boston 2025, SF 2024)"}


def build(census_geometry_by_city=None, out=None):
    """Write the US precinct-elections schema JSON from the columns the loader produces.

    Args:
        census_geometry_by_city: ``{city: {level: polygons}}``.
        out: Output file; ``None`` = the package schema.

    Returns:
        The output path.
    """
    cols, years = [], []
    for (city, scope), e in ELECTIONS.items():
        f = load_all(city, scope, census_geometry=(census_geometry_by_city or {}).get(city))["tract"]
        for c in f.columns:
            if c not in cols:
                cols.append(c)
        years.append(e["year"])
    feats = schema_features(cols, "usa", "elections_precinct", "precinct", SCOPE_DESC)
    out = out or Path(__file__).parent.parent / "schema" / "elections_precinct_schema.json"
    write_schema(out, "usa", "elections_precinct",
                 "US precinct-level election results (MEDSL, City of Boston), resampled to H3 res 8 and census tract/block group",
                 years, ["tract", "blockgroup"], feats)
    return out
