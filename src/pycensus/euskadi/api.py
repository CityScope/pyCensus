"""API client for Euskadi Eustat (Basque Statistics Office) Census data.

Technical aspects:
    Unlike the US Census Bureau which provides a comprehensive REST API,
    Euskadi's Eustat does not have a simple public API for census data downloads.
    Data must be downloaded as files from Eustat's website.
    
    This module provides placeholder functions that match the interface expected
    by the pyCensus system but indicate that manual downloads are required.
    
    In the future, this could be enhanced to use Eustat's API if one becomes available,
    or to implement scraping/download functionality for Eustat's data portal.

Source:
    https://www.eustat.eus/
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
    """Fetch census variables from Eustat for a specific geography.
    
    Note: This is a placeholder function. Eustat does not currently provide a
    REST API for census data. Data must be downloaded manually from Eustat's website.
    
    Args:
        source: Source identifier (e.g., "census2021").
        year: Census year.
        level: Geography level (e.g., "territory", "comarca", "municipality").
        region: Region identifier (territory code, comarca code, etc.).
        codes: List of variable codes to fetch.
        api_key: Optional API key (not currently used for Eustat).
        
    Returns:
        None - this function raises a warning and returns None.
        
    Raises:
        NotImplementedError: Always, as Eustat does not have a REST API.
    """
    warnings.warn(
        f"Eustat (Basque Country) does not provide a REST API for census data downloads. "
        f"Please download the data manually from https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html "
        f"and place it in your cache directory."
    )
    raise NotImplementedError(
        "Eustat census data must be downloaded manually. "
        "Use the download_census_data() function or download from Eustat's website directly."
    )


def get_variable_info(variable_code: str, year: int = 2021) -> dict:
    """Get metadata information about a specific census variable.
    
    Note: This is a placeholder function.
    
    Args:
        variable_code: The Eustat variable code.
        year: Census year.
        
    Returns:
        Dictionary with variable metadata (name, description, etc.).
    """
    return {
        "code": variable_code,
        "name": f"Variable {variable_code}",
        "description": f"Description for {variable_code} from Eustat Census {year}",
        "year": year,
        "source": "Eustat",
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
            "description": "Population counts by age groups and sex for Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Households and families",
            "code": "CP2021_HOGARES",
            "year": year,
            "description": "Household and family characteristics in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Housing",
            "code": "CP2021_VIVIENDAS",
            "year": year,
            "description": "Housing stock and characteristics in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Education",
            "code": "CP2021_EDUCACION",
            "year": year,
            "description": "Educational attainment in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Employment",
            "code": "CP2021_EMPLEO",
            "year": year,
            "description": "Employment and labor force status in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Income",
            "code": "CP2021_RENTAS",
            "year": year,
            "description": "Household income data in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca"],
        },
        {
            "name": "Census 2021 - Language",
            "code": "CP2021_LENGUA",
            "year": year,
            "description": "Language use (Basque, Spanish) in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Basque language skills",
            "code": "CP2021_EUSKERA",
            "year": year,
            "description": "Basque language reading, writing, and speaking skills",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Commuting",
            "code": "CP2021_DESPLAZAMIENTOS",
            "year": year,
            "description": "Mode of transportation to work in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
        {
            "name": "Census 2021 - Disability",
            "code": "CP2021_DISCAPACIDAD",
            "year": year,
            "description": "Population with disabilities in Euskadi",
            "levels": ["autonomous_community", "territory", "comarca", "municipality"],
        },
    ]


__all__ = [
    "fetch_variables",
    "get_variable_info",
    "list_datasets",
]
