"""Static reference data shared by every EU-wide (Eurostat / GISCO) source.

Technical aspects:
    Eurostat and its geographic service GISCO publish keyless, EU-wide data for the EU-27 plus the EFTA countries and
    candidates (Iceland, Liechtenstein, Norway, Switzerland, North Macedonia, Serbia, Albania, Montenegro, Turkey...).
    Coverage differs per dataset: the Census 2021 grid covers the EU-27 plus Norway, Switzerland and Liechtenstein; the
    LAU tables add some candidates (with zero population where the country did not report). Countries use the
    Eurostat two-letter codes, which differ from ISO 3166 for Greece (``EL``, ISO ``GR``) and in older vintages the
    United Kingdom (``UK``, ISO ``GB``).

    All URLs below were checked live on 2026-11-17.
"""

from __future__ import annotations

from typing import Dict, List

#: Eurostat country codes of the EU-27 (Eurostat spelling: Greece is ``EL``).
EU27: List[str] = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
                   "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]
#: EFTA countries that report to Eurostat.
EFTA: List[str] = ["CH", "IS", "LI", "NO"]

#: Eurostat -> ISO 3166-1 alpha-2 where they differ.
EUROSTAT_TO_ISO2: Dict[str, str] = {"EL": "GR", "UK": "GB"}
ISO2_TO_EUROSTAT: Dict[str, str] = {v: k for k, v in EUROSTAT_TO_ISO2.items()}

GISCO = "https://gisco-services.ec.europa.eu/distribution/v2"
#: NUTS boundaries (all levels 0-3 in one file, column ``LEVL_CODE``), 1:1 million, EPSG:4326.
NUTS_GPKG_URL = GISCO + "/nuts/gpkg/NUTS_RG_01M_{year}_4326.gpkg"
NUTS_YEARS = [2024, 2021, 2016]
#: LAU (municipality) boundaries; ``LAU_RG_01M_<year>_4326.csv`` holds the same attributes without geometry.
LAU_GPKG_URL = GISCO + "/lau/gpkg/LAU_RG_01M_{year}_4326.gpkg"
LAU_CSV_URL = GISCO + "/lau/csv/LAU_RG_01M_{year}_4326.csv"
LAU_YEARS = [2024, 2023, 2022, 2021]

#: Eurostat dissemination API (JSON-stat 2.0), keyless.
EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

#: pycensus geometry levels -> Eurostat / GISCO units.
NUTS_LEVEL: Dict[str, int] = {"nation": 0, "state": 1, "nuts1": 1, "region": 2, "nuts2": 2, "province": 3, "nuts3": 3}

#: Levels this module implements, and where a missing standard level falls back to.
IMPLEMENTED_LEVELS = ("nation", "nuts1", "nuts2", "nuts3", "municipality", "grid_1km")
LEVEL_FALLBACK: Dict[str, str] = {"state": "nuts1", "region": "nuts2", "province": "nuts3", "county": "nuts3",
                                  "place": "municipality", "tract": "grid_1km", "blockgroup": "grid_1km", "block": "grid_1km"}


def to_eurostat(code: str) -> str:
    """Eurostat two-letter country code from an ISO 3166-1 alpha-2 (or Eurostat) code.

    Args:
        code: ``"GR"`` or ``"EL"``, ``"ES"``...

    Returns:
        The Eurostat code (``"EL"`` for Greece).
    """
    code = code.upper()
    return ISO2_TO_EUROSTAT.get(code, code)


__all__ = ["EU27", "EFTA", "EUROSTAT_TO_ISO2", "ISO2_TO_EUROSTAT", "GISCO", "NUTS_GPKG_URL", "NUTS_YEARS", "LAU_GPKG_URL",
           "LAU_CSV_URL", "LAU_YEARS", "EUROSTAT_API", "NUTS_LEVEL", "IMPLEMENTED_LEVELS", "LEVEL_FALLBACK", "to_eurostat"]
