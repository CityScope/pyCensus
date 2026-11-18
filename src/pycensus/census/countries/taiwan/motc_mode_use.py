"""Taiwan: public-transport market share of residents' daily trips per city / county, MOTC survey of daily mode use (民眾日常使用運具狀況調查),
2022, as tabulated for the six special municipalities by Taichung City's statistics office (the MOTC tables are per city / county only).
Taipei City 37.2 %, New Taipei City 28.7 %.

    from pycensus.census.countries.taiwan import motc_mode_use
    motc_mode_use.load()   # {"taipei_city": {...}, "new_taipei_city": {...}}
"""
from __future__ import annotations

from typing import Optional

from pycensus.published_shares import fetch

URL = "https://www.dbas.taichung.gov.tw/media/998929/112-012-%E8%87%BA%E4%B8%AD%E5%B8%82%E9%81%8B%E5%85%B7%E4%BD%BF%E7%94%A8%E8%AE%8A%E5%8C%96.pdf"
FIGURES = {
    "taipei_city": {"transit_share": 0.372, "basis": "all trips", "year": 2022, "url": URL, "pattern": r"臺北市\s*37\.2%",
                    "source": "MOTC daily mode-use survey 2022 (Taichung City statistics report 112-012): Taipei City 37.2 % public transport"},
    "new_taipei_city": {"transit_share": 0.287, "basis": "all trips", "year": 2022, "url": URL, "pattern": r"新北市\s*28\.7%",
                        "source": "MOTC daily mode-use survey 2022 (Taichung City statistics report 112-012): New Taipei City 28.7 % public transport"},
}


def load(cache_dir: Optional[str] = None, verify: bool = True) -> dict:
    """Published travel-mode shares of the MOTC mode-use survey, checked against the source document.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        verify: Check each figure in its document.

    Returns:
        ``{key: figure}``.
    """
    return fetch(FIGURES, cache_dir, verify)
