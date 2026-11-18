# -*- coding: utf-8 -*-
"""Regenerate ``schema/elections_schema.json`` (needs data access)."""

from pathlib import Path

from ....elections_common import schema_features, write_schema
from .loader import ELECTIONS, load_all

SCOPE_DESC = {"national": "2025 presidential runoff"}


def build(census_geometry=None, aoi=None, out=None):
    """Write the Chile elections schema JSON from the columns the loader produces.

    Args:
        census_geometry: ``{level: polygons}``.
        aoi: Comuna polygons.
        out: Output file; ``None`` = the package schema.

    Returns:
        The output path.
    """
    cols, years = [], []
    for scope, e in ELECTIONS.items():
        f = load_all(scope, census_geometry=census_geometry, aoi=aoi)["manzana"]
        cols += [c for c in f.columns if c not in cols]
        years.append(e["year"])
    feats = schema_features(cols, "chile", "elections", "local", SCOPE_DESC)
    out = out or Path(__file__).parent.parent / "schema" / "elections_schema.json"
    write_schema(out, "chile", "elections", "Chile Servel mesa-level election results (presidential 2025), Voronoi-of-geocoded-locales catchments, resampled to H3 res 8 and manzana/zona", years, ["manzana", "zona"], feats)
    return out
