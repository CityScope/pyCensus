"""Custom fields for INE (Instituto Nacional de Estadistica) that require mathematical operations.

This module defines derived fields that are computed from base census fields
using custom mathematical operations for Spanish census data.

Note: INE is Spain's national statistics institute, providing census data for
Spain including population, housing, and economic data.
"""

from __future__ import annotations

from typing import Optional

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


def compute_housing_density(
    housing_units: Optional[pd.Series] = None,
    households: Optional[pd.Series] = None,
    area: pd.Series = None,
) -> pd.Series:
    """Compute housing density.
    
    Args:
        housing_units: Number of housing units (viviendas)
        households: Number of households (hogares) - fallback if housing_units not available
        area: Area in square kilometers
        
    Returns:
        Housing density (units per km²)
    """
    if housing_units is not None:
        return housing_units / area
    elif households is not None:
        return households / area
    else:
        raise ValueError("Either housing_units or households must be provided")


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


def compute_foreign_born_share(
    foreign_born: pd.Series,
    total_population: pd.Series,
) -> pd.Series:
    """Compute share of foreign-born population.
    
    Args:
        foreign_born: Number of foreign-born residents
        total_population: Total population
        
    Returns:
        Share of foreign-born population (0-1)
    """
    return foreign_born / total_population


def compute_household_size(
    total_population: pd.Series,
    households: pd.Series,
) -> pd.Series:
    """Compute average household size.
    
    Args:
        total_population: Total population
        households: Number of households
        
    Returns:
        Average household size
    """
    return total_population / households


def compute_urbanization_rate(
    urban_population: pd.Series,
    total_population: pd.Series,
) -> pd.Series:
    """Compute urbanization rate (share of population in urban areas).
    
    Args:
        urban_population: Population in urban areas
        total_population: Total population
        
    Returns:
        Urbanization rate (0-1)
    """
    return urban_population / total_population
