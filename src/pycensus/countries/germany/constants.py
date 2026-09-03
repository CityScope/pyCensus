"""Static Germany geography/API reference data.

Germany's administrative divisions:
- Nation (country level) -- GISCO NUTS level 0
- State (Bundesland), 16 states -- GISCO NUTS level 1
- District (Kreis/kreisfreie Stadt), 401 districts -- GISCO NUTS level 3
- Municipality (Gemeinde), 11,001 real municipalities -- GISCO LAU 2021
  (boundary and population both; see :mod:`pycensus.germany.geography`)

Boundary source: Eurostat/GISCO NUTS (see
:data:`GISCO_NUTS_GEOJSON_URL` and :mod:`pycensus.germany.geography`).
Census/population data source: Destatis GENESIS-Online (see
:mod:`pycensus.germany.api` and :mod:`pycensus.germany.destatis.README`).
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

STATE_ABBR: Dict[str, str] = {name: code for code, name in STATE_CODES.items()}

# State codes with numeric identifiers (AGS - Amtlicher Gemeindeschluessel)
STATE_AGS: Dict[str, str] = {
    "BW": "08", "BY": "09", "BE": "11", "BB": "12", "HB": "04",
    "HH": "02", "HE": "06", "MV": "13", "NI": "03", "NW": "05",
    "RP": "07", "SL": "10", "SN": "14", "ST": "15", "SH": "01", "TH": "16",
}

# Each state's GISCO NUTS1 code -- read off a live GISCO NUTS 2021 response
# on 2026-08-19 (see tests/test_germany.py for the specific spot-checks
# regression-guarded: HH->DE6, BE->DE3, BY->DE2).
STATE_NUTS1: Dict[str, str] = {
    "BW": "DE1", "BY": "DE2", "BE": "DE3", "BB": "DE4", "HB": "DE5",
    "HH": "DE6", "HE": "DE7", "MV": "DE8", "NI": "DE9", "NW": "DEA",
    "RP": "DEB", "SL": "DEC", "SN": "DED", "ST": "DEE", "SH": "DEF", "TH": "DEG",
}
NUTS1_TO_STATE: Dict[str, str] = {nuts1: code for code, nuts1 in STATE_NUTS1.items()}

LEVEL_FALLBACK: Dict[str, str] = {
    "state": "state",
    "province": "state",
    "county": "district",
    "tract": "municipality",
    "blockgroup": "municipality",
    "place": "municipality",
}

LATEST_YEAR: Dict[str, int] = {
    "geography": 2021,
    "census": 2022,
}

# Eurostat/GISCO NUTS geojson distribution -- {levl} is 0 (nation), 1
# (state), or 3 (district); see pycensus.germany.geography._load_germany_nuts.
GISCO_NUTS_GEOJSON_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    "NUTS_RG_01M_2021_4326_LEVL_{levl}.geojson"
)

# --- Destatis GENESIS-Online API (see pycensus.germany.api / destatis/README.md) ---

# api_keys.json's real Germany entry is a single personal API token under
# this key name (not a username/password pair) -- GENESIS-Online's "User
# Guide Web Services" v5.1 says the token is used in place of username,
# with password omitted.
GENESIS_TOKEN_KEY = "destatis_genesis"
GENESIS_TOKEN_ENV = "DESTATIS_GENESIS_TOKEN"

# Fallback for a real separate username/password pair, if one is ever
# configured instead of a token.
GENESIS_USERNAME_KEY = "destatis_genesis_username"
GENESIS_USERNAME_ENV = "DESTATIS_GENESIS_USERNAME"
GENESIS_PASSWORD_KEY = "destatis_genesis_password"
GENESIS_PASSWORD_ENV = "DESTATIS_GENESIS_PASSWORD"

# Verified live 2026-08-21: the old "www-genesis.destatis.de" host
# 307-redirects to "genesis.destatis.de" (no "www-" prefix), which is the
# real current host for the RESTful/JSON web service. Per GENESIS'
# "Anwenderdokumentation Webservice/API" v5.1 (01.06.2026,
# https://genesis.destatis.de/datenbank/online/docs/GENESIS-Webservices_Einfuehrung.pdf):
# the SOAP/XML interface was shut down mid-2025, and GET-methods were
# replaced by POST-methods on the RESTful/JSON interface. The URL path
# itself ("genesisWS/rest/2020") is unchanged.
GENESIS_BASE_URL = "https://genesis.destatis.de/genesisWS/rest/2020"

# Real statistic/table/variable codes confirmed live on 2026-08-21 via
# GENESIS' find/find, catalogue/tables2statistic, catalogue/variables2statistic,
# and data/table APIs (real authenticated responses, not the GAST guest
# account) -- see pycensus.germany.destatis.README for the exact
# commands/responses. Statistic 12411 ("Fortschreibung des
# Bevoelkerungsstandes") is real; its real value variable is "BEVSTD"
# ("Bevoelkerungsstand"), not "BEVZ01" ("Bevoelkerung (Zensus)") -- BEVZ01
# is a real GENESIS variable name (found via find/find on 2026-08-19) but
# belongs to the separate Zensus2022 database (ergebnisse.zensus2022.de),
# not GENESIS-Online's public statistic 12411
# (catalogue/tables2variable?name=BEVZ01 returns "no objects" on
# GENESIS-Online). BEVSTD is the code actually present under statistic
# 12411's real tables and live-verified against real published figures:
# Germany total 31.12.2022 = 83,118,501 (table 12411-0001), Bavaria
# 31.12.2022 = 13,105,221 (table 12411-0010), Munich (kreisfreie Stadt)
# 31.12.2022 = 1,490,516 (table 12411-0015) -- all match Destatis'
# independently-published figures for those dates.
GENESIS_POPULATION_STATISTIC = "12411"
GENESIS_POPULATION_VARIABLE = "BEVSTD"

# Real table codes under statistic 12411, one per geography level, found
# live via catalogue/tables2statistic on 2026-08-21 and confirmed to
# return real population data via data/table (see module docstring above).
# "district" (12411-0015, "Bevoelkerung: Kreise, Stichtag") returns rows
# keyed by 5-digit AGS (Amtlicher Gemeindeschluessel) codes, which do not
# match `geography.py`'s NUTS3 GEOID codes without a crosswalk -- see
# destatis/crosswalk.py (wired into destatis/loader.py._fetch_missing,
# live-verified 2026-08-22: 400/400 GENESIS district rows matched).
GENESIS_POPULATION_TABLES = {
    "nation": "12411-0001",
    "state": "12411-0010",
    "district": "12411-0015",
}

# Real sex-breakdown table codes under statistic 12411 (same "Bevoelkerung,
# Stichtag, Geschlecht" family as GENESIS_POPULATION_TABLES, one extra
# dimension). Live-verified 2026-08-22 via data/table: nation
# male=40,919,705 / female=42,198,796 / total=83,118,501 (matches the
# already-verified nation population total exactly); state Hamburg
# male=894,537 / female=938,138 / total=1,832,675; district Hamburg
# (Kreis 02000, the same city-state) male/female match the state row
# exactly, as expected since Hamburg is a single-Kreis state. Not wired for
# "municipality" -- that level sources population from GISCO LAU (see
# destatis/loader.py), which carries no sex breakdown.
GENESIS_SEX_TABLES = {
    "nation": "12411-0003",
    "state": "12411-0011",
    "district": "12411-0016",
}

# Real Auslaenderzentralregister (AZR)-derived foreign-population table,
# statistic 12521 ("Auslaenderstatistik") -- an entirely separate GENESIS
# statistic family from 12411's population-register data above. Live-
# verified 2026-08-23 via catalogue/tables2statistic on statistic 12521:
# only nation/state/district ("Kreise") tables exist in the real catalogue
# (30 real table codes listed for 12521, none mention "Gemeinde") -- no
# Gemeinde-level table exists for this statistic, unlike population. Table
# 12521-0040 ("Auslaender: Kreise, Stichtag, Geschlecht") returns real rows
# shaped identically to GENESIS_SEX_TABLES' district table (one row per
# AGS+name, then male;female;total) -- confirmed live for Muenchen
# (Kreis AGS 09162), 31.12.2022: male=260,335, female=245,420,
# total=505,760 (a plausible ~34% foreign share against Muenchen's already-
# verified 1,490,516 total population for the same date). The real response
# also carries genuine administrative-coverage footnotes (e.g. Saarland's
# 6 Kreise share one Auslaenderbehoerde, so all cases are reported under
# Kreis "Saarlouis" only) -- a real data-quality quirk, not a fetch bug.
# Only "district" is wired (see destatis/loader.py) since that's the level
# CS_transitLOS's `GERMANY_LEVELS` already dispatches to for Germany.
GENESIS_FOREIGN_POPULATION_TABLES = {
    "district": "12521-0040",
}

# Default data directory (kept for backward compatibility, but cache is preferred)
DEFAULT_DATA_DIR = "data/germany"

__all__ = [
    "STATE_CODES",
    "STATE_ABBR",
    "STATE_AGS",
    "STATE_NUTS1",
    "NUTS1_TO_STATE",
    "LEVEL_FALLBACK",
    "LATEST_YEAR",
    "GISCO_NUTS_GEOJSON_URL",
    "GENESIS_TOKEN_KEY",
    "GENESIS_TOKEN_ENV",
    "GENESIS_USERNAME_KEY",
    "GENESIS_USERNAME_ENV",
    "GENESIS_PASSWORD_KEY",
    "GENESIS_PASSWORD_ENV",
    "GENESIS_BASE_URL",
    "GENESIS_POPULATION_STATISTIC",
    "GENESIS_POPULATION_VARIABLE",
    "GENESIS_POPULATION_TABLES",
    "GENESIS_SEX_TABLES",
    "GENESIS_FOREIGN_POPULATION_TABLES",
    "DEFAULT_DATA_DIR",
]
