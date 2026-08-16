"""API client for Germany Destatis Census data."""

from __future__ import annotations
from typing import List, Optional
import warnings


def fetch_variables(source: str, year: int, level: str, region: str, codes: List[str], api_key: Optional[str] = None):
    warnings.warn(f"Destatis does not provide a REST API. Download manually from https://www.destatis.de/")
    raise NotImplementedError("Destatis data must be downloaded manually.")


def list_datasets(year: int = 2022) -> List[dict]:
    return [
        {"name": "Census 2022 - Population", "code": "C2022_POP", "year": year, "levels": ["nation", "state", "district", "municipality"]},
        {"name": "Census 2022 - Housing", "code": "C2022_HOUSING", "year": year, "levels": ["nation", "state", "district"]},
        {"name": "Census 2022 - Buildings", "code": "C2022_BUILDINGS", "year": year, "levels": ["nation", "state", "district"]},
        {"name": "Census 2022 - Households", "code": "C2022_HH", "year": year, "levels": ["nation", "state", "district", "municipality"]},
    ]


__all__ = ["fetch_variables", "list_datasets"]
