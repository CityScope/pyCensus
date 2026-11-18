# -*- coding: utf-8 -*-
"""Regenerate ``schema/elections_schema.json`` by running every election (needs data access)."""

from pathlib import Path

from ....elections_common import schema_features, write_schema
from .loader import ELECTIONS, load_all

SCOPE_DESC = {"national": "45th federal general election 2025", "state": "Ontario general election 2025", "municipal": "Toronto municipal election 2022 (mayor)"}


def build(census_geometry=None, out=None):
    """Write the Canada (Toronto) elections schema JSON from the columns the loaders produce.

    Args:
        census_geometry: ``{"da": dissemination areas}``.
        out: Output file; ``None`` = the package schema.

    Returns:
        The output path.
    """
    cols, years = [], []
    for scope, e in ELECTIONS.items():
        f = load_all(scope, census_geometry=census_geometry)["da"]
        cols += [c for c in f.columns if c not in cols]
        years.append(e["year"])
    feats = schema_features(cols, "canada", "elections", "poll", SCOPE_DESC)
    out = out or Path(__file__).parent.parent / "schema" / "elections_schema.json"
    write_schema(out, "canada", "elections", "Toronto election results (Elections Canada, Elections Ontario, City of Toronto) by poll, resampled to H3 res 8 and dissemination areas",
                 years, ["dissemination-area"], feats)
    return out
