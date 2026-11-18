"""Shanghai comprehensive transport surveys (上海市综合交通调查), as published by the Shanghai Municipal Transportation Commission. The
releases give no mode split of all trips by district; the only public-transport share of a territory is the central city's (中心城,
inside the outer ring) commuting share of the 6th survey (2019): rail, bus, ferry and coach 41.6 % of commuting trips.

    from pycensus.census.countries.china import shanghai_transport_survey as s
    s.load()   # {"central_city_commute": {...}}
"""
from __future__ import annotations

from typing import Optional

from pycensus.published_shares import fetch

URL = "https://finance.sina.cn/2021-03-31/detail-ikmxzfmi9999167.d.html"
FIGURES = {
    "central_city_commute": {"transit_share": 0.416, "basis": "commuting trips", "year": 2019, "territory": "中心城 (central city, inside the outer ring, ~664 km2)",
                             "url": URL, "pattern": r"通勤出行中的分担率达到41\.6%",
                             "source": "Shanghai 6th comprehensive transport survey (2019), 2020 annual transport report: central-city public transport 41.6 % of commutes"},
}


def load(cache_dir: Optional[str] = None, verify: bool = True) -> dict:
    """Published travel-mode figures of the Shanghai transport survey, checked against the source document.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        verify: Check each figure in its document.

    Returns:
        ``{key: figure}``.
    """
    return fetch(FIGURES, cache_dir, verify)
