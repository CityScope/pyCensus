"""Static Germany geography reference data.

Germany's administrative divisions:
- Nation (country level)
- State (Bundesland) - 16 states
- District (Kreis) - 401 districts (294 rural, 107 urban)
- Municipality (Gemeinde) - ~11,000 municipalities
- Statistical units

Source: https://www.destatis.de/
"""

from typing import Dict, List

# Germany state codes (16 states with 2-letter codes)
STATE_CODES: Dict[str, str] = {
    "BW": "Baden-Wuerttemberg",
    "BY": "Bavaria (Bayern)",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hesse (Hessen)",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Lower Saxony (Niedersachsen)",
    "NW": "North Rhine-Westphalia (Nordrhein-Westfalen)",
    "RP": "Rhineland-Palatinate (Rheinland-Pfalz)",
    "SL": "Saarland",
    "SN": "Saxony (Sachsen)",
    "ST": "Saxony-Anhalt (Sachsen-Anhalt)",
    "SH": "Schleswig-Holstein",
    "TH": "Thuringia (Thueringen)",
}

STATE_ABBR: Dict[str, str] = {
    "Baden-Wuerttemberg": "BW",
    "Bavaria (Bayern)": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Bremen": "HB",
    "Hamburg": "HH",
    "Hesse (Hessen)": "HE",
    "Mecklenburg-Vorpommern": "MV",
    "Lower Saxony (Niedersachsen)": "NI",
    "North Rhine-Westphalia (Nordrhein-Westfalen)": "NW",
    "Rhineland-Palatinate (Rheinland-Pfalz)": "RP",
    "Saarland": "SL",
    "Saxony (Sachsen)": "SN",
    "Saxony-Anhalt (Sachsen-Anhalt)": "ST",
    "Schleswig-Holstein": "SH",
    "Thuringia (Thueringen)": "TH",
}

# State codes with numeric identifiers (AGS - Amtlicher Gemeinschaftschluessel)
STATE_AGS: Dict[str, str] = {
    "BW": "08", "BY": "09", "BE": "11", "BB": "12", "HB": "04",
    "HH": "02", "HE": "06", "MV": "13", "NI": "03", "NW": "05",
    "RP": "07", "SL": "10", "SN": "14", "ST": "15", "SH": "01", "TH": "16",
}

LEVEL_FALLBACK: Dict[str, str] = {
    "state": "state",
    "province": "state",
    "county": "district",
    "tract": "municipality",
    "blockgroup": "municipality",
    "place": "municipality",
}

LATEST_YEAR: Dict[str, int] = {
    "geography": 2022,
    "census": 2022,
}

CENSUS_2022_URLS: Dict[str, str] = {
    "microdata": "https://www.destatis.de/DE/Home/_inhalt.html",
    "tables": "https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus/_inhalt.html",
    "boundaries": "https://www.destatis.de/DE/Service/Geodaten/_inhalt.html",
}

# Default data directory (kept for backward compatibility, but cache is preferred)
DEFAULT_DATA_DIR = "data/germany"

__all__ = ["STATE_CODES", "STATE_ABBR", "STATE_AGS", "LEVEL_FALLBACK", "LATEST_YEAR", "CENSUS_2022_URLS", "DEFAULT_DATA_DIR"]
