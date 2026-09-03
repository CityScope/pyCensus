"""Custom fields for WorldPop that require mathematical operations.

This module defines derived fields that are computed from base census fields
using custom mathematical operations for WorldPop population data.

Note: WorldPop provides high-resolution population density and count data
for countries worldwide, particularly useful for low- and middle-income countries.
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


def compute_population_growth_rate(
    population_current: pd.Series,
    population_previous: pd.Series,
    years_difference: int = 5,
) -> pd.Series:
    """Compute population growth rate.
    
    Args:
        population_current: Current population
        population_previous: Previous population
        years_difference: Number of years between measurements (default 5)
        
    Returns:
        Annual growth rate (as a decimal, e.g., 0.02 = 2%)
    """
    growth_factor = population_current / population_previous
    # Annual growth rate: (final/initial)^(1/n) - 1
    return (growth_factor ** (1 / years_difference)) - 1


def compute_urbanization_rate(
    urban_population: pd.Series,
    total_population: pd.Series,
) -> pd.Series:
    """Compute urbanization rate.
    
    Args:
        urban_population: Population in urban areas
        total_population: Total population
        
    Returns:
        Urbanization rate (0-1)
    """
    return urban_population / total_population


def compute_rural_population(
    total_population: pd.Series,
    urban_population: pd.Series,
) -> pd.Series:
    """Compute rural population.
    
    Args:
        total_population: Total population
        urban_population: Population in urban areas
        
    Returns:
        Rural population
    """
    return total_population - urban_population


def compute_urban_rural_ratio(
    urban_population: pd.Series,
    rural_population: Optional[pd.Series] = None,
    total_population: Optional[pd.Series] = None,
) -> pd.Series:
    """Compute urban-to-rural population ratio.
    
    Args:
        urban_population: Population in urban areas
        rural_population: Population in rural areas (optional)
        total_population: Total population (to compute rural if not provided)
        
    Returns:
        Urban-to-rural ratio
    """
    if rural_population is not None:
        return urban_population / rural_population
    elif total_population is not None:
        rural = total_population - urban_population
        return urban_population / rural
    else:
        raise ValueError("Either rural_population or total_population must be provided")


def compute_population_per_pixel(
    population: pd.Series,
    num_pixels: pd.Series,
) -> pd.Series:
    """Compute average population per pixel.
    
    Useful for raster data where population is aggregated across multiple pixels.
    
    Args:
        population: Total population in the area
        num_pixels: Number of pixels in the area
        
    Returns:
        Average population per pixel
    """
    return population / num_pixels


def compute_settlement_density(
    settlements: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute settlement density (settlements per square kilometer).
    
    Args:
        settlements: Number of settlements/villages
        area: Area in square kilometers
        
    Returns:
        Settlement density (settlements per km²)
    """
    return settlements / area


def compute_average_settlement_size(
    total_population: pd.Series,
    settlements: pd.Series,
) -> pd.Series:
    """Compute average settlement size.
    
    Args:
        total_population: Total population
        settlements: Number of settlements
        
    Returns:
        Average population per settlement
    """
    return total_population / settlements
