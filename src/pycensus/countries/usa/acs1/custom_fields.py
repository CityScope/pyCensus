"""Custom fields for ACS1 that require mathematical operations.

This module defines derived fields that are computed from base census fields
using custom mathematical operations. These fields are not directly available
from the ACS API but can be computed from available fields.

Example:
    meanHouseholdIncome = medianHouseholdIncome (approximation)
    Or: meanHouseholdIncome = totalIncome / households

With meanHouseholdSize (population / households), you can exactly convert between
per-household and per-capita values:
    per_capita = per_household * households / population
    per_household = per_capita * population / households
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def compute_mean_household_size(
    population: pd.Series,
    households: pd.Series,
) -> pd.Series:
    """Compute mean household size (people per household).
    
    This is the exact formula: population / households
    
    Args:
        population: Total population
        households: Number of households
        
    Returns:
        Mean household size (people per household)
    """
    return population / households


def compute_mean_household_income(
    median_household_income: Optional[pd.Series] = None,
    total_income: Optional[pd.Series] = None,
    households: Optional[pd.Series] = None,
) -> pd.Series:
    """Compute mean household income.
    
    Mean household income can be computed as total household income divided by
    number of households. If total income is not available, we can approximate
    using median * some factor, but this is less accurate.
    
    Args:
        median_household_income: Median household income (fallback if total not available)
        total_income: Total income for all households (preferred)
        households: Number of households
        
    Returns:
        Mean household income per household
    """
    if total_income is not None and households is not None:
        return total_income / households
    elif median_household_income is not None:
        # Approximation: mean ≈ median for income distributions
        # This is a rough approximation and may not be accurate
        return median_household_income * 1.25  # Rough adjustment factor
    else:
        raise ValueError("Insufficient data to compute meanHouseholdIncome")


def compute_per_capita_from_household(
    household_value: pd.Series,
    mean_household_size: Optional[pd.Series] = None,
    households: Optional[pd.Series] = None,
    population: Optional[pd.Series] = None,
) -> pd.Series:
    """Convert a per-household value to per-capita.
    
    With meanHouseholdSize, you can convert exactly:
        per_capita = per_household / meanHouseholdSize
    Or alternatively:
        per_capita = per_household * households / population
    
    Args:
        household_value: Value per household (e.g., meanHouseholdIncome)
        mean_household_size: Mean household size (preferred, more precise)
        households: Number of households (alternative to mean_household_size)
        population: Total population (alternative to mean_household_size)
        
    Returns:
        Value per capita
        
    Raises:
        ValueError: If insufficient data to compute the conversion
    """
    if mean_household_size is not None:
        return household_value / mean_household_size
    elif households is not None and population is not None:
        return (household_value * households) / population
    else:
        raise ValueError(
            "Insufficient data to compute per-capita from household. "
            "Provide either mean_household_size or both households and population."
        )


def compute_household_from_per_capita(
    per_capita_value: pd.Series,
    mean_household_size: Optional[pd.Series] = None,
    households: Optional[pd.Series] = None,
    population: Optional[pd.Series] = None,
) -> pd.Series:
    """Convert a per-capita value to per-household.
    
    With meanHouseholdSize, you can convert exactly:
        per_household = per_capita * meanHouseholdSize
    Or alternatively:
        per_household = per_capita * population / households
    
    Args:
        per_capita_value: Value per capita (e.g., income per capita)
        mean_household_size: Mean household size (preferred, more precise)
        households: Number of households (alternative to mean_household_size)
        population: Total population (alternative to mean_household_size)
        
    Returns:
        Value per household
        
    Raises:
        ValueError: If insufficient data to compute the conversion
    """
    if mean_household_size is not None:
        return per_capita_value * mean_household_size
    elif households is not None and population is not None:
        return (per_capita_value * population) / households
    else:
        raise ValueError(
            "Insufficient data to compute per-household from per-capita. "
            "Provide either mean_household_size or both households and population."
        )


def compute_household_income_per_capita(
    income_median_household: pd.Series,
    mean_household_size: Optional[pd.Series] = None,
    households: Optional[pd.Series] = None,
    population: Optional[pd.Series] = None,
) -> pd.Series:
    """Compute household income per capita from median household income.
    
    This is an approximation since median != mean, but can be useful for
    comparisons across different geographic levels.
    
    With meanHouseholdSize, you can convert exactly:
        income_per_capita = median_household_income / meanHouseholdSize
    Or alternatively:
        income_per_capita = median_household_income * households / population
    
    Args:
        income_median_household: Median household income
        mean_household_size: Mean household size (preferred, more precise)
        households: Number of households (alternative)
        population: Total population (alternative)
        
    Returns:
        Approximate income per capita
        
    Raises:
        ValueError: If insufficient data to compute the conversion
    """
    if mean_household_size is not None:
        return income_median_household / mean_household_size
    elif households is not None and population is not None:
        return (income_median_household * households) / population
    else:
        raise ValueError(
            "Insufficient data to compute per-capita income. "
            "Provide either mean_household_size or both households and population."
        )

