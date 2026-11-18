"""Custom fields for DHC (Decennial Census) that require mathematical operations.

This module defines derived fields that are computed from base census fields
using custom mathematical operations. DHC 2020 provides detailed population
and housing data but has limited income data compared to ACS.

Note: DHC data is from the 2020 Decennial Census and provides the most accurate
population counts for the US.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def compute_nonwhite_population(
    population: pd.Series,
    white_population: pd.Series,
) -> pd.Series:
    """Compute non-white population.
    
    Args:
        population: Total population
        white_population: White population (P3_002N)
        
    Returns:
        Non-white population (total - white)
    """
    return population - white_population


def compute_population_density(
    population: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute population density (people per square mile/km).
    
    Args:
        population: Total population
        area: Area in square miles or square kilometers
        
    Returns:
        Population density (people per unit area)
    """
    return population / area


def compute_housing_density(
    housing_units: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute housing unit density.
    
    Args:
        housing_units: Number of housing units
        area: Area in square miles or square kilometers
        
    Returns:
        Housing unit density (units per unit area)
    """
    return housing_units / area


def compute_dependency_ratio(
    under18_population: pd.Series,
    over65_population: pd.Series,
    working_age_population: pd.Series,
) -> pd.Series:
    """Compute dependency ratio.
    
    The dependency ratio is the ratio of dependents (under 18 and over 65) to
    the working-age population (18-64).
    
    Args:
        under18_population: Population under 18
        over65_population: Population over 65
        working_age_population: Working-age population (18-64)
        
    Returns:
        Dependency ratio
    """
    dependents = under18_population + over65_population
    return dependents / working_age_population


def compute_sex_ratio(
    male_population: pd.Series,
    female_population: pd.Series,
) -> pd.Series:
    """Compute sex ratio (males per 100 females).
    
    Args:
        male_population: Male population
        female_population: Female population
        
    Returns:
        Sex ratio (males per 100 females)
    """
    return (male_population / female_population) * 100


def compute_racial_diversity_index(
    white_population: pd.Series,
    black_population: pd.Series,
    asian_population: pd.Series,
    other_race_population: pd.Series,
    hispanic_population: pd.Series,
    total_population: pd.Series,
) -> pd.Series:
    """Compute a simple racial diversity index.
    
    This is based on the Simpson diversity index concept.
    
    Args:
        white_population: White population
        black_population: Black population
        asian_population: Asian population
        other_race_population: Other race population
        hispanic_population: Hispanic population
        total_population: Total population
        
    Returns:
        Diversity index (0-1, higher is more diverse)
    """
    # Calculate proportions
    p_white = white_population / total_population
    p_black = black_population / total_population
    p_asian = asian_population / total_population
    p_other = other_race_population / total_population
    p_hispanic = hispanic_population / total_population
    
    # Simpson index: 1 - sum(p_i^2)
    diversity = 1 - (p_white**2 + p_black**2 + p_asian**2 + p_other**2 + p_hispanic**2)
    return diversity
