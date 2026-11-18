"""Custom fields for LODES that require mathematical operations.

This module defines derived fields that are computed from LODES (LEHD Origin-Destination
Employment Statistics) data using custom mathematical operations. LODES provides
job counts and worker residence/workplace data.

Note: LODES data is derived from state unemployment insurance records and federal
administrative data, providing detailed workplace and residence employment data.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def compute_job_density(
    jobs_total: pd.Series,
    area: pd.Series,
) -> pd.Series:
    """Compute job density (jobs per square mile/km).
    
    Args:
        jobs_total: Total number of jobs
        area: Area in square miles or square kilometers
        
    Returns:
        Job density (jobs per unit area)
    """
    return jobs_total / area


def compute_job_concentration_ratio(
    jobs_total: pd.Series,
    population16plus: pd.Series,
) -> pd.Series:
    """Compute jobs-to-working-age-population ratio.
    
    This ratio indicates the balance between jobs and potential workers.
    A ratio > 1 means more jobs than working-age residents (in-commuting).
    A ratio < 1 means more residents than jobs (out-commuting).
    
    Args:
        jobs_total: Total number of jobs
        population16plus: Population aged 16 and over
        
    Returns:
        Jobs-to-working-age-population ratio
    """
    return jobs_total / population16plus


def compute_income_segment_share(
    jobs_income_segment: pd.Series,
    jobs_total: pd.Series,
) -> pd.Series:
    """Compute the share of jobs in a specific income segment.
    
    Args:
        jobs_income_segment: Number of jobs in a specific income segment
                             (low, mid, or high)
        jobs_total: Total number of jobs
        
    Returns:
        Share of jobs in the segment (0-1)
    """
    return jobs_income_segment / jobs_total


def compute_age_segment_share(
    jobs_age_segment: pd.Series,
    jobs_total: pd.Series,
) -> pd.Series:
    """Compute the share of jobs held by a specific age segment.
    
    Args:
        jobs_age_segment: Number of jobs held by a specific age segment
                          (young, prime, or older)
        jobs_total: Total number of jobs
        
    Returns:
        Share of jobs in the age segment (0-1)
    """
    return jobs_age_segment / jobs_total


def compute_mean_job_income(
    jobs_income_low: Optional[pd.Series] = None,
    jobs_income_mid: Optional[pd.Series] = None,
    jobs_income_high: Optional[pd.Series] = None,
    jobs_total: Optional[pd.Series] = None,
) -> pd.Series:
    """Estimate mean job income from income segment counts.
    
    This is an approximation since we don't have actual income values for each
    segment. We use representative values for each segment.
    
    Args:
        jobs_income_low: Number of jobs in low income segment (CE01)
        jobs_income_mid: Number of jobs in mid income segment (CE02)
        jobs_income_high: Number of jobs in high income segment (CE03)
        jobs_total: Total number of jobs (for validation)
        
    Returns:
        Approximate mean job income
        
    Note:
        This uses approximate income thresholds:
        - Low: $0-$1,250/month
        - Mid: $1,250-$3,333/month  
        - High: $3,333+/month
        Annualized: Low ~$15k, Mid ~$30k, High ~$60k
    """
    # Representative annual income for each segment (approximate)
    income_low = 15000  # $15k/year
    income_mid = 30000   # $30k/year
    income_high = 60000  # $60k/year
    
    total_income = 0.0
    total_jobs = 0
    
    if jobs_income_low is not None:
        total_income += jobs_income_low * income_low
        total_jobs += jobs_income_low
    
    if jobs_income_mid is not None:
        total_income += jobs_income_mid * income_mid
        total_jobs += jobs_income_mid
    
    if jobs_income_high is not None:
        total_income += jobs_income_high * income_high
        total_jobs += jobs_income_high
    
    if total_jobs == 0:
        raise ValueError("No job data available to compute mean job income")
    
    return total_income / total_jobs


def compute_worker_age_ratio(
    jobs_age_young: pd.Series,
    jobs_age_prime: pd.Series,
    jobs_age_older: pd.Series,
) -> dict:
    """Compute ratios of jobs across different age groups.
    
    Args:
        jobs_age_young: Number of jobs held by young workers (CA01)
        jobs_age_prime: Number of jobs held by prime-age workers (CA02)
        jobs_age_older: Number of jobs held by older workers (CA03)
        
    Returns:
        Dictionary with ratios:
        - young_to_prime: Ratio of young to prime-age workers
        - older_to_prime: Ratio of older to prime-age workers
        - young_to_older: Ratio of young to older workers
    """
    return {
        'young_to_prime': jobs_age_young / jobs_age_prime,
        'older_to_prime': jobs_age_older / jobs_age_prime,
        'young_to_older': jobs_age_young / jobs_age_older,
    }
