"""Custom fields for INEGI (Instituto Nacional de Estadistica y Geografia) that require mathematical operations.

This module defines derived fields that are computed from base census fields
using custom mathematical operations for Mexican census data.

Note: INEGI is Mexico's national statistics institute, providing census data for
Mexico including population, housing, and economic data.
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
        Population density (people per km²)
    """
    return population / area


def compute_household_size(
    total_population: pd.Series,
    households: pd.Series,
) -> pd.Series:
    """Compute average household size.
    
    Args:
        total_population: Total population
        households: Number of households (hogares)
        
    Returns:
        Average household size
    """
    return total_population / households


