"""Custom fields for Destatis (Statistisches Bundesamt) that require mathematical operations.

Technical aspects:
    Only :func:`compute_population_density` is kept -- every other derived
    field in the earlier version of this module (dependency ratio, foreign
    population share, household size, sex ratio, ageing index, ...)
    depended on base columns (``households``, ``populationForeign``, ...)
    that were removed from :mod:`pycensus.germany.destatis.schema` for
    being fabricated, unverified GENESIS codes -- see that module's
    docstring. Add these back once their base columns are real and
    verified.
"""

from __future__ import annotations

import pandas as pd


def compute_population_density(
    population: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute population density (people per square kilometer).

    Args:
        population: Total population (Bevoelkerung).
        area: Area in square kilometers.

    Returns:
        Population density (people per km²).
    """
    return population / area
