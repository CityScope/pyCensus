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

# Israel district (machoz) codes -- CBS's 6 internationally-recognized
# districts only. Code "7" ("Judea and Samaria" / West Bank) is
# deliberately excluded: it is occupied territory, not a real CBS
# statistical district with population data in the sources this module
# uses -- both the CBS statistical-area layer and the iplan jurisdiction
# layer were queried live for a known West Bank settlement (Ariel) and
# returned zero features from either (verified 2026-08-19). See
# EXCLUDED_MACHOZ / MACHOZ_TO_DISTRICT_CODE below for the defensive
# runtime filter this backs.
DISTRICT_CODES: Dict[str, str] = {
    "1": "Northern (Tzfon)",
    "2": "Haifa",
    "3": "Central (Merkez)",
    "4": "Tel Aviv",
    "5": "Jerusalem",
    "6": "Southern (Darom)",
}

# District abbreviations
DISTRICT_ABBR: Dict[str, str] = {
    "Northern (Tzfon)": "NORTH",
    "Haifa": "HAIFA",
    "Central (Merkez)": "CENTRAL",
    "Tel Aviv": "TA",
    "Jerusalem": "JLM",
    "Southern (Darom)": "SOUTH",
}

# Hebrew names for districts -- these are the exact ``Machoz`` field
# values returned by the real iplan jurisdiction layer
# (IPLAN_JURISDICTION_URL), verified live 2026-08-20 (Be'er Sheva,
# CR_LAMAS=9000, returns Machoz="דרום").
DISTRICT_HEBREW: Dict[str, str] = {
    "Northern (Tzfon)": "צפון",
    "Haifa": "חיפה",
    "Central (Merkez)": "מרכז",
    "Tel Aviv": "תל אביב",
    "Jerusalem": "ירושלים",
    "Southern (Darom)": "דרום",
}

# Reverse lookup used by geography.py to map a real iplan ``Machoz``
# attribute value straight to a CBS district code, without any West Bank
# entry -- deliberately built only from the 6 real DISTRICT_HEBREW
# entries above so a stale/renamed Machoz value can never resolve to a
# code that isn't a genuine district.
MACHOZ_TO_DISTRICT_CODE: Dict[str, str] = {
    hebrew: code for code, hebrew in ((c, DISTRICT_HEBREW[n]) for c, n in DISTRICT_CODES.items())
}

# Defensive list of ``Machoz`` values that must never be treated as a real
# district, applied as a runtime filter in geography.py even though live
# queries against both real boundary sources never actually return them
# (verified 2026-08-19 via a known West Bank settlement, Ariel, returning
# zero features). Kept as defense in depth, not because it was observed to
# trigger.
EXCLUDED_MACHOZ: List[str] = [
    "יהודה ושומרון",  # "Judea and Samaria" / West Bank
]

# Approximate bounding boxes (minx, miny, maxx, maxy in EPSG:4326), padded
# generously, per real district -- used as a cheap pre-filter in
# geography.py before committing to an expensive per-district ArcGIS
# jurisdiction-layer query (the iplan MapServer 500s/times out on an
# unchunked whole-country query, ~1,300+ localities). Hand-set from each
# district's well-known real geographic extent, not fetched from any API.
DISTRICT_BBOX: Dict[str, tuple] = {
    "1": (34.7, 32.5, 35.95, 33.35),  # Northern (Tzfon)
    "2": (34.7, 32.3, 35.3, 32.9),  # Haifa
    "3": (34.6, 31.9, 35.3, 32.5),  # Central (Merkez)
    "4": (34.6, 31.9, 34.95, 32.25),  # Tel Aviv
    "5": (35.05, 31.6, 35.55, 31.95),  # Jerusalem
    "6": (34.2, 29.4, 35.6, 31.9),  # Southern (Darom)
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
    "block": "statistical_area",  # Real CBS block-level boundaries not implemented -- statistical_area is the finest real level
    "place": "locality",  # Locality is closest to place
}

# Most recent vintage year for data
LATEST_YEAR: Dict[str, int] = {
    "geography": 2022,
    "census": 2022,
}

# Real, live, unauthenticated ArcGIS FeatureServer layer for CBS Census 2022
# locality-level population/housing attributes (layer id 1, not 0 -- verified
# live 2026-08-20). Item title "שכבת יישובים 2021 נתוני מפקד 2022" ("2021
# localities layer, 2022 census data"), hosted on CBS's own ArcGIS org
# (services8.arcgis.com/JcXY3lLZni6BK4El). Query SETL_CODE=9000 (Be'er Sheva)
# -> pop_approx=217580.0, matching this project's independently-known figure.
CENSUS_SETL_2022_URL: str = (
    "https://services8.arcgis.com/JcXY3lLZni6BK4El/arcgis/rest/services/"
    "שכבת_יישובים_2021_נתוני_מפקד_2022/"
    "FeatureServer/1"
)

# Real, live, unauthenticated ArcGIS FeatureServer layer for CBS Census 2022
# statistical-area-level attributes (finer than locality) -- a separate
# CBS-owned hosted layer, item id c676b1971f974f5cbd8f209497224b40
# ("נתוני מפקד האוכלוסין 2022 לפי אזורים סטטיסטיים בישראל", owner "yigalm",
# accessInformation = CBS itself), verified live 2026-08-20: fields
# SEMEL_YISHUV (locality code, joins to CENSUS_SETL_2022_URL's SETL_CODE),
# YISHUV_STAT_2022 (statistical-area GEOID), pop_approx and the same
# attribute field names as the locality layer. Querying
# SEMEL_YISHUV=9000 returns 83 statistical areas whose pop_approx sums to
# 217,600 -- matching the locality-level total (217,580) to rounding.
CENSUS_STAT_2022_URL: str = (
    "https://services.arcgis.com/b6zSqPB0TQc3mBgU/arcgis/rest/services/"
    "מפקד_2022/FeatureServer/0"
)

# Real, live, unauthenticated ArcGIS FeatureServer layer for CBS's
# statistical-area *boundary* geometry (owner "sysdata", CBS's official
# GIS account) -- verified live 2026-08-20: fields SEMEL_YISHUV (locality
# code), YISHUV_STAT_2022 (statistical-area GEOID, joins to
# CENSUS_STAT_2022_URL's field of the same name), SHEM_YISHUV_ENGLISH.
# Querying SEMEL_YISHUV=9000 returns the same 83 Be'er Sheva statistical
# areas as CENSUS_STAT_2022_URL's attribute layer.
STAT_AREAS_2022_URL: str = (
    "https://services8.arcgis.com/JcXY3lLZni6BK4El/arcgis/rest/services/"
    "statistical_areas_2022/FeatureServer/0"
)

# Real, live, unauthenticated ArcGIS Server MapServer layer -- the Israel
# Planning Administration's (iplan.gov.il) municipal jurisdiction
# boundaries ("גבולות שיפוט", ownership: gov.il's own ArcGIS Server, not
# ArcGIS Online), verified live 2026-08-20: fields CR_LAMAS (locality
# code, string type, joins to CENSUS_SETL_2022_URL's SETL_CODE), Muni_Eng,
# Machoz (district, Hebrew, matches DISTRICT_HEBREW's values exactly).
# Querying CR_LAMAS='9000' returns Be'er Sheva's real jurisdiction
# polygon (bounds ~lon 34.73-34.85, lat 31.19-31.32) with Machoz="דרום".
# Note: this MapServer does not support resultOffset/resultRecordCount
# pagination and can 500 on an unchunked whole-country query -- callers
# fetching many localities at once should chunk (see
# geography.py::_load_district_boundaries, which chunks per-Machoz rather
# than per-locality).
IPLAN_JURISDICTION_URL: str = (
    "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/"
    "gvulot_retzef/MapServer/1"
)

# Default data directory (kept for backward compatibility, but cache is preferred)
DEFAULT_DATA_DIR = "data/israel"

__all__ = [
    "DISTRICT_CODES",
    "DISTRICT_ABBR",
    "DISTRICT_HEBREW",
    "MACHOZ_TO_DISTRICT_CODE",
    "EXCLUDED_MACHOZ",
    "DISTRICT_BBOX",
    "SUBDISTRICT_CODES",
    "MAJOR_CITIES",
    "district_code",
    "district_abbr",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "CENSUS_SETL_2022_URL",
    "CENSUS_STAT_2022_URL",
    "STAT_AREAS_2022_URL",
    "IPLAN_JURISDICTION_URL",
    "DEFAULT_DATA_DIR",
]
