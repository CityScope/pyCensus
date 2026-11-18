# -*- coding: utf-8 -*-
"""Official Census Bureau voting districts (VTD) for the three vintages: 2000, 2010 and 2020.

``vintage_for_election(year)`` returns the vintage in force for an election: 2020 for elections from 2020 on, 2010 for 2012-2018, 2000 for
2000-2010 (the 2010 Census VTDs were released in 2011, after the 2010 election). ``load_vtd(state_fips, vintage)`` returns the state's
voting districts (EPSG:4326, ``GEOID`` = state + county + VTD code). Vintage 2020 comes from the TIGER 2020 state files (via ``pygris``);
2000 and 2010 are the county files ``tl_2010_<county>_vtd00 / vtd10`` of TIGER 2010 (Census Bureau, www2.census.gov/geo/tiger/TIGER2010/VTD).
States that did not submit voting districts (e.g. California, Hawaii and Oregon in 2020) return None.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd

from ...elections_common import default_elections_cache, download

logger = logging.getLogger(__name__)

BASE = "https://www2.census.gov/geo/tiger/TIGER2010/VTD/{v}/"
VINTAGES = (2000, 2010, 2020)


def vintage_for_election(year: int) -> int:
    """Census voting-district vintage matching an election year (2020, 2010 or 2000).

    Args:
        year: Election year.

    Returns:
        The vintage.
    """
    return 2020 if year >= 2020 else 2010 if year >= 2012 else 2000


def _county_files(state_fips: str, vintage: int) -> List[str]:
    import requests

    page = requests.get(BASE.format(v=vintage), timeout=120).text
    return sorted(set(re.findall(rf"tl_2010_{state_fips}\d{{3}}_vtd{str(vintage)[2:]}\.zip", page)))


def load_vtd(state_fips: str, vintage: int, cache_dir: Optional[str] = None) -> Optional[gpd.GeoDataFrame]:
    """Census voting districts (VTDs) of one state and vintage, cached; None when they cannot be downloaded.

    Args:
        state_fips: 2-digit state FIPS.
        vintage: 2000, 2010 or 2020.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame, or None.
    """
    state_fips = str(state_fips).zfill(2)
    root = default_elections_cache(cache_dir) / f"vtd{vintage}"
    parquet = root / f"{state_fips}.parquet"
    if parquet.is_file():
        return gpd.read_parquet(parquet)
    try:
        if vintage == 2020:
            import pygris

            g = pygris.voting_districts(state=state_fips, year=2020, cache=True)
            suffix = "20"
        else:
            names = _county_files(state_fips, vintage)
            if not names:
                return None
            frames = [gpd.read_file(f"zip://{download(BASE.format(v=vintage) + n, root / 'raw' / n)}") for n in names]
            g = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
            suffix = str(vintage)[2:]
    except Exception as exc:  # noqa: BLE001 - a state without voting districts simply has none
        logger.warning("voting districts %s for state %s unavailable: %s", vintage, state_fips, exc)
        return None
    cols = {c.upper(): c for c in g.columns}
    geoid = cols.get("GEOID" + suffix) or cols.get("VTDIDFP" + suffix) or cols.get("GEOID")
    name = cols.get("NAME" + suffix) or cols.get("NAMELSAD" + suffix) or geoid
    out = gpd.GeoDataFrame({"GEOID": g[geoid].astype(str), "NAME": g[name].astype(str)}, geometry=g.geometry, crs=g.crs).to_crs(4326)
    root.mkdir(parents=True, exist_ok=True)
    out.to_parquet(parquet)
    return out
