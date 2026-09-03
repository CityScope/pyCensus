"""Custom derived fields for CBS Israel Census data.

Note:
    These are generic formulas that only depend on fields actually present
    in :mod:`pycensus.israel.cbs.schema` (``population``, ``households``) --
    kept as convenience helpers even though CBS's own ``pop_density`` and
    ``size_avg`` fields already cover the same ground natively (schema.json
    fields ``populationDensity``/``householdSizeMean``). Earlier versions of
    this module defined formulas over fabricated fields (Jewish/Arab share,
    immigration decade breakdowns, fertility rate, etc.) that do not exist
    in the real CBS locality dataset wired up in ``cbs/schema.json`` -- those
    were removed rather than kept as dead code referencing non-existent columns.
"""

from __future__ import annotations

import pandas as pd


def compute_population_density(population: pd.Series, area: pd.Series) -> pd.Series:
    """Compute population density (people per square kilometer).

    Args:
        population: Total population.
        area: Area in square kilometers.

    Returns:
        Population density (people per km²).
    """
    return population / area


def compute_household_size(total_population: pd.Series, households: pd.Series) -> pd.Series:
    """Compute average household size.

    Args:
        total_population: Total population.
        households: Number of households.

    Returns:
        Average household size.
    """
    return total_population / households
