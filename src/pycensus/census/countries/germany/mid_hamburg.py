"""Hamburg: share of public transport in residents' trips, Mobilitaet in Deutschland 2023 (MiD), Hamburg short report (hvv sample boost).
City of Hamburg 23 % of all trips (2017: 21 %); rest of the hvv area (Umland) 9 %. No Bezirk or Gemeinde breakdown of the Umland is published.

    from pycensus.census.countries.germany import mid_hamburg
    mid_hamburg.load()   # {"hamburg": {...}, "hvv_umland": {...}}
"""
from __future__ import annotations

from typing import Optional

from pycensus.published_shares import fetch

URL = "https://www.hamburg.de/resource/blob/1132384/df391ad7f5773fe715e834e4926039e6/mid2023-kurzbericht-hamburg-data.pdf"
FIGURES = {
    "hamburg": {"transit_share": 0.23, "basis": "all trips of residents (main mode)", "year": 2023, "url": URL,
                "pattern": r"Anteil ÖPNV\s+21%\s+23%", "source": "MiD 2023, Hamburg short report: City of Hamburg, ÖPNV 23 % of trips"},
    "hvv_umland": {"transit_share": 0.09, "basis": "all trips of residents (main mode)", "year": 2023, "url": URL,
                   "pattern": r"hvv-Umland.*\b9%", "source": "MiD 2023, Hamburg short report: rest of the hvv area, ÖV 9 % of trips"},
}


def load(cache_dir: Optional[str] = None, verify: bool = True) -> dict:
    """Published travel-mode figures for Hamburg (MiD survey), checked against the source document.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        verify: Check each figure in its document.

    Returns:
        ``{key: figure}``.
    """
    return fetch(FIGURES, cache_dir, verify)
