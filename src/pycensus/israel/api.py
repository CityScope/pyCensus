"""API client for Israel CBS (Central Bureau of Statistics) Census data.

Technical aspects:
    Unlike the US Census Bureau which provides a comprehensive REST API,
    Israel's CBS does not have a simple public API for census data downloads.
    Data must be downloaded as files from CBS's website.
    
    This module provides placeholder functions that match the interface expected
    by the pyCensus system but indicate that manual downloads are required.
    
    In the future, this could be enhanced to use CBS's API if one becomes available,
    or to implement scraping/download functionality for CBS's data portal.

Source:
    https://www.cbs.gov.il/
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
    """Fetch census variables from CBS for a specific geography.
    
    Note: This is a placeholder function. CBS does not currently provide a
    REST API for census data. Data must be downloaded manually from CBS's website.
    
    Args:
        source: Source identifier (e.g., "census2022").
        year: Census year.
        level: Geography level (e.g., "locality", "district").
        region: Region identifier (district code, sub-district code, etc.).
        codes: List of variable codes to fetch.
        api_key: Optional API key (not currently used for CBS).
        
    Returns:
        None - this function raises a warning and returns None.
        
    Raises:
        NotImplementedError: Always, as CBS does not have a REST API.
    """
    warnings.warn(
        f"CBS (Israel) does not provide a REST API for census data downloads. "
        f"Please download the data manually from https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx "
        f"and place it in your cache directory or data/israel/ folder."
    )
    raise NotImplementedError(
        "CBS census data must be downloaded manually. "
        "Use the download_census_data() function or download from CBS's website directly."
    )


def get_variable_info(variable_code: str, year: int = 2022) -> dict:
    """Get metadata information about a specific census variable.
    
    Note: This is a placeholder function.
    
    Args:
        variable_code: The CBS variable code.
        year: Census year.
        
    Returns:
        Dictionary with variable metadata (name, description, etc.).
    """
    return {
        "code": variable_code,
        "name": f"Variable {variable_code}",
        "description": f"Description for {variable_code} from CBS Census {year}",
        "year": year,
        "source": "CBS",
    }


def list_datasets(year: int = 2022) -> List[dict]:
    """List available census datasets for a given year.
    
    Note: This is a placeholder function.
    
    Args:
        year: Census year.
        
    Returns:
        List of dictionaries describing available datasets.
    """
    return [
        {
            "name": "Census 2022 - Population and Housing",
            "code": "CPH2022",
            "year": year,
            "description": "Population and housing characteristics from the 2022 census",
            "levels": ["nation", "district", "subdistrict", "locality", "statistical_area"],
        },
        {
            "name": "Census 2022 - Population by Age and Sex",
            "code": "CPH2022_AGE_SEX",
            "year": year,
            "description": "Population counts by age groups and sex",
            "levels": ["nation", "district", "subdistrict", "locality"],
        },
        {
            "name": "Census 2022 - Households and Families",
            "code": "CPH2022_HOUSEHOLDS",
            "year": year,
            "description": "Household composition and family characteristics",
            "levels": ["nation", "district", "subdistrict", "locality"],
        },
        {
            "name": "Census 2022 - Housing Stock",
            "code": "CPH2022_HOUSING",
            "year": year,
            "description": "Housing stock, types, and characteristics",
            "levels": ["nation", "district", "subdistrict", "locality"],
        },
        {
            "name": "Census 2022 - Education",
            "code": "CPH2022_EDUCATION",
            "year": year,
            "description": "Educational attainment and literacy",
            "levels": ["nation", "district", "subdistrict", "locality"],
        },
        {
            "name": "Census 2022 - Employment and Income",
            "code": "CPH2022_EMPLOYMENT",
            "year": year,
            "description": "Employment status, occupation, industry, and income",
            "levels": ["nation", "district", "subdistrict", "locality"],
        },
        {
            "name": "Census 2022 - Migration",
            "code": "CPH2022_MIGRATION",
            "year": year,
            "description": "Place of birth, year of immigration, and internal migration",
            "levels": ["nation", "district", "subdistrict"],
        },
    ]


__all__ = [
    "fetch_variables",
    "get_variable_info",
    "list_datasets",
]
