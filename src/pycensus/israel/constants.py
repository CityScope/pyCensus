"""Static Israel geography reference data shared by every Israel census source.

Technical aspects:
    Boundary files for Israel will be fetched from CBS's geographic data.
    This module maps logical level names to the functions that fetch them,
    the geography hierarchy, and configuration for data loading.

    Israel's administrative divisions:
    - Nation (country level)
    - District (mehoz) - 6 main districts + Judea and Samaria area
    - Sub-district (nafa) - within districts
    - Locality/City (ir/моаца) - municipalities, local councils, cities
    - Statistical Area (area statistit) - for census purposes
    - Street
    - Building Block

Source:
    https://www.cbs.gov.il/
"""

from typing import Dict, List

# Israel district codes (CBS uses 1-7 for main districts)
DISTRICT_CODES: Dict[str, str] = {
    "1": "Northern (Tzfon)",
    "2": "Haifa",
    "3": "Central (Merkez)",
    "4": "Tel Aviv",
    "5": "Jerusalem",
    "6": "Southern (Darom)",
    "7": "Judea and Samaria (Yehuda VeShomron)",
}

# District abbreviations
DISTRICT_ABBR: Dict[str, str] = {
    "Northern (Tzfon)": "NORTH",
    "Haifa": "HAIFA",
    "Central (Merkez)": "CENTRAL",
    "Tel Aviv": "TA",
    "Jerusalem": "JLM",
    "Southern (Darom)": "SOUTH",
    "Judea and Samaria (Yehuda VeShomron)": "J&S",
}

# Hebrew names for districts
DISTRICT_HEBREW: Dict[str, str] = {
    "Northern (Tzfon)": "צפון",
    "Haifa": "חיפה",
    "Central (Merkez)": "מרכז",
    "Tel Aviv": "תל אביב",
    "Jerusalem": "ירושלים",
    "Southern (Darom)": "דרום",
    "Judea and Samaria (Yehuda VeShomron)": "יהודה ושומרון",
}


def district_code(district_name_or_abbr: str) -> str:
    """Return the 1-digit CBS code for a district name, abbreviation, or code.
    
    Args:
        district_name_or_abbr: District name, abbreviation, or 1-digit code.
        
    Returns:
        One-digit CBS district code.
        
    Raises:
        ValueError: If the input does not resolve to a known Israel district.
    """
    # Try as code first
    if district_name_or_abbr in DISTRICT_CODES:
        return district_name_or_abbr
    
    # Try as abbreviation
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_ABBR.get(name) == district_name_or_abbr.upper():
            return code
        # Try case-insensitive match
        if name.lower().replace(" ", "").replace("(", "").replace(")", "") == \
                district_name_or_abbr.lower().replace(" ", "").replace("(", "").replace(")", ""):
            return code
    
    # Try Hebrew name
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_HEBREW.get(name) == district_name_or_abbr:
            return code
    
    # Try as name
    for code, name in DISTRICT_CODES.items():
        if name.lower() == district_name_or_abbr.lower():
            return code
    
    raise ValueError(f"Unknown Israel district: '{district_name_or_abbr}'")


def district_abbr(district_name_or_code: str) -> str:
    """Return the abbreviation for a district name or code.
    
    Args:
        district_name_or_code: District name or 1-digit code.
        
    Returns:
        Abbreviation for the district.
        
    Raises:
        ValueError: If the input does not resolve to a known Israel district.
    """
    if isinstance(district_name_or_code, str) and district_name_or_code in {v.upper() for v in DISTRICT_ABBR.values()}:
        return district_name_or_code.upper()
    
    # Try as code
    if district_name_or_code in DISTRICT_CODES:
        return DISTRICT_ABBR[DISTRICT_CODES[district_name_or_code]]
    
    # Try as Hebrew name
    for code, name in DISTRICT_CODES.items():
        if DISTRICT_HEBREW.get(name) == district_name_or_code:
            return DISTRICT_ABBR[name]
    
    # Try as name
    for code, name in DISTRICT_CODES.items():
        if name.lower() == district_name_or_code.lower():
            return DISTRICT_ABBR[name]
    
    raise ValueError(f"Unknown Israel district: '{district_name_or_code}'")


# Sub-district (nafa) codes - these vary by district
# Format: district_code + sub-district_code (2 digits)
# This is a partial list of major sub-districts
SUBDISTRICT_CODES: Dict[str, str] = {
    "11": "Safed (Tzfat)",
    "12": "Kinneret",
    "13": "Yizre'el (Jezreel)",
    "14": "Ako (Acre)",
    "15": "Golani",
    "21": "Haifa",
    "22": "Hadera",
    "31": "Sharon",
    "32": "Petah Tikva",
    "33": "Ramla",
    "34": "Rehovot",
    "41": "Tel Aviv",
    "42": "Holon",
    "43": "Bnei Brak - Ramat Gan",
    "51": "Jerusalem",
    "61": "Ashkelon",
    "62": "Be'er Sheva",
    "71": "Judea",
    "72": "Samaria",
}

# Major cities with their codes (CBS locality codes)
# These are 4-5 digit codes
MAJOR_CITIES: Dict[str, str] = {
    "0101": "Jerusalem",
    "0201": "Tel Aviv - Yafu",
    "0301": "Haifa",
    "0401": "Rishon LeZion",
    "0501": "Ashdod",
    "0601": "Petah Tikva",
    "0701": "Netanya",
    "0801": "Be'er Sheva",
    "0901": "Holon",
    "1001": "Bnei Brak",
    "1101": "Ramla",
    "1201": "Ashkelon",
    "1301": "Rehovot",
    "1401": "Bat Yam",
    "1501": "Lod",
    "1601": "Ramat Gan",
    "1701": "Raanana",
    "1801": "Hod HaSharon",
    "1901": "Giv'atayim",
    "2001": "Kiryat Gat",
}


# Geography level configuration
# Israel's native levels: nation, district, subdistrict, locality, statistical_area, street, block
LEVEL_FALLBACK: Dict[str, str] = {
    "state": "district",  # Use district as state equivalent
    "province": "district",  # Direct mapping
    "county": "subdistrict",  # Sub-district is closest to county
    "tract": "statistical_area",  # Statistical area is closest to tract
    "blockgroup": "statistical_area",  # Statistical area is closest to blockgroup
    "place": "locality",  # Locality is closest to place
}

# Most recent vintage year for data
LATEST_YEAR: Dict[str, int] = {
    "geography": 2022,
    "census": 2022,
}

# Data download URLs for CBS Census 2022
# CBS (Central Bureau of Statistics) provides census data at:
# https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
CENSUS_2022_URLS: Dict[str, str] = {
    "microdata": "https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx",
    "tables": "https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx",
    "boundaries": "https://www.cbs.gov.il/en/statistics/pages/geographic-information.aspx",
}

# Default data directory
DEFAULT_DATA_DIR = "data/israel"

__all__ = [
    "DISTRICT_CODES",
    "DISTRICT_ABBR",
    "DISTRICT_HEBREW",
    "SUBDISTRICT_CODES",
    "MAJOR_CITIES",
    "district_code",
    "district_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_2022_URLS",
    "DEFAULT_DATA_DIR",
]
