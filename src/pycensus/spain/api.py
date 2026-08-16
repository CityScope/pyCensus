"""API client for Spain INE (Instituto Nacional de Estadística) Census data.

Technical aspects:
    Unlike the US Census Bureau which provides a comprehensive REST API,
    Spain's INE does not have a simple public API for census data downloads.
    Data must be downloaded as files from INE's website.
    
    This module provides placeholder functions that match the interface expected
    by the pyCensus system but indicate that manual downloads are required.
    
    In the future, this could be enhanced to use INE's API if one becomes available,
    or to implement scraping/download functionality for INE's data portal.

Source:
    https://www.ine.es/
"""

from __future__ import annotations

from typing import List, Optional
import warnings


def fetch_variables(
    source: str,
    year: int,
    level: str,
    region: str,
    codes: List[str],
    api_key: Optional[str] = None,
) -> None:
    """Fetch census variables from INE for a specific geography.
    
    Note: This is a placeholder function. INE does not currently provide a
    REST API for census data. Data must be downloaded manually from INE's website.
    
    Args:
        source: Source identifier (e.g., "census2021").
        year: Census year.
        level: Geography level (e.g., "municipality", "province").
        region: Region identifier (autonomous community code, province code, etc.).
        codes: List of variable codes to fetch.
        api_key: Optional API key (not currently used for INE).
        
    Returns:
        None - this function raises a warning and returns None.
        
    Raises:
        NotImplementedError: Always, as INE does not have a REST API.
    """
    warnings.warn(
        f"INE (Spain) does not provide a REST API for census data downloads. "
        f"Please download the data manually from https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780 "
        f"and place it in your cache directory."
    )
    raise NotImplementedError(
        "INE census data must be downloaded manually. "
        "Use the download_census_data() function or download from INE's website directly."
    )


def get_variable_info(variable_code: str, year: int = 2021) -> dict:
    """Get metadata information about a specific census variable.
    
    Note: This is a placeholder function.
    
    Args:
        variable_code: The INE variable code.
        year: Census year.
        
    Returns:
        Dictionary with variable metadata (name, description, etc.).
    """
    return {
        "code": variable_code,
        "name": f"Variable {variable_code}",
        "description": f"Description for {variable_code} from INE Census {year}",
        "year": year,
        "source": "INE",
    }


def list_datasets(year: int = 2021) -> List[dict]:
    """List available census datasets for a given year.
    
    Note: This is a placeholder function.
    
    Args:
        year: Census year.
        
    Returns:
        List of dictionaries describing available datasets.
    """
    return [
        {
            "name": "Census 2021 - Population by age and sex",
            "code": "CP2021_EDAD_SEXO",
            "year": year,
            "description": "Population counts by age groups and sex",
            "levels": ["nation", "autonomous_community", "province", "municipality", "section"],
        },
        {
            "name": "Census 2021 - Households and families",
            "code": "CP2021_HOGARES",
            "year": year,
            "description": "Household and family characteristics",
            "levels": ["nation", "autonomous_community", "province", "municipality"],
        },
        {
            "name": "Census 2021 - Housing",
            "code": "CP2021_VIVIENDAS",
            "year": year,
            "description": "Housing stock and characteristics",
            "levels": ["nation", "autonomous_community", "province", "municipality"],
        },
        {
            "name": "Census 2021 - Education",
            "code": "CP2021_EDUCACION",
            "year": year,
            "description": "Educational attainment",
            "levels": ["nation", "autonomous_community", "province", "municipality"],
        },
        {
            "name": "Census 2021 - Employment",
            "code": "CP2021_EMPLEO",
            "year": year,
            "description": "Employment and labor force status",
            "levels": ["nation", "autonomous_community", "province", "municipality"],
        },
        {
            "name": "Census 2021 - Income",
            "code": "CP2021_RENTAS",
            "year": year,
            "description": "Household income data",
            "levels": ["nation", "autonomous_community", "province"],
        },
    ]


__all__ = [
    "fetch_variables",
    "get_variable_info",
    "list_datasets",
]
