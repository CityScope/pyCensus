"""Custom fields for Euskadi census data that require mathematical operations.

Technical aspects:
    Only keeps a computed field whose inputs actually exist in
    ``schema.json`` (``population``, ``areaKm2``). An earlier version of
    this file had seven more functions (Basque-language rate, bilingual
    rate, dependency ratio, household size, ageing index, immigration
    rate, educational attainment rate) whose input fields
    (``basque_speakers``, ``households``, ``over64_population``, etc.)
    were never added to ``schema.json`` and were never fetched from any
    real source -- dead, speculative scaffolding for data this module
    doesn't produce. Per ``IMPLEMENTING_A_COUNTRY.md``'s guidance to trim
    dead computed fields, they were removed rather than kept "for
    completeness." Eustat's real Data Bank API does publish
    language-use/household/age-structure tables (see ``api.py``'s
    docstring) -- if/when the loader is extended to fetch them, the
    corresponding compute function belongs back here alongside the new
    ``schema.json`` entries, not before.
"""

from __future__ import annotations

import pandas as pd


def compute_population_density(
    population: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute population density (people per square kilometer).

    Args:
        population: Total population
        area: Area in square kilometers

    Returns:
        Population density (people per km^2)
    """
    return population / area
