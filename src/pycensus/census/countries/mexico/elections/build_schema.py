# -*- coding: utf-8 -*-
"""Regenerate ``schema/elections_schema.json`` (needs data access)."""

from pathlib import Path

from pycensus.elections_common import schema_features, write_schema
from pycensus.census.countries.mexico.elections.loader import ELECTIONS, load_all

SCOPE_DESC = {"national": "2024 federal election, President"}


def build(census_geometry=None, aoi=None, out=None):
    """Write the Mexico elections schema JSON from the columns the loader produces.

    Args:
        census_geometry: ``{level: polygons}``.
        aoi: Study area.
        out: Output file; ``None`` = the package schema.

    Returns:
        The output path.
    """
    cols, years = [], []
    for scope, e in ELECTIONS.items():
        f = load_all(scope, census_geometry=census_geometry, aoi=aoi)["ageb"]
        cols += [c for c in f.columns if c not in cols]
        years.append(e["year"])
    feats = schema_features(cols, "mexico", "elections", "seccion", SCOPE_DESC)
    out = out or Path(__file__).parent.parent / "schema" / "elections_schema.json"
    write_schema(out, "mexico", "elections", "Mexico INE casilla-level election results (federal 2024), resampled to H3 res 8 and AGEB/manzana", years, ["ageb", "block"], feats)
    return out
