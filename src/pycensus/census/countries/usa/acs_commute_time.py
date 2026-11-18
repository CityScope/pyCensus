"""ACS 5-year commute time by means of transportation for census tracts (table B08134: workers by mode x travel-time band).

The aggregate minutes by mode (B08136) are published only down to counties, so the tract mean is estimated from the bands
(band midpoints; 60+ minutes counted as 75). Car = "Car, truck, or van" (B08134_011-020), public transport = B08134_061-070.

    from pycensus.census.countries.usa.acs_commute_time import tract_table
    tract_table("44")      # DataFrame: GEOID (11 digits), car_commuters, car_time_min, transit_commuters, transit_time_min

Downloaded once per state into `<cache>/usa/acs_commute_time/<state fips>_<year>.parquet` (Census API key: pycensus.api_keys).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

YEAR = 2023
MID = [5.0, 12.0, 17.0, 22.0, 27.0, 32.0, 39.5, 52.0, 75.0]   # band midpoints (minutes): <10, 10-14, ..., 45-59, 60+
CAR = [f"B08134_{i:03d}E" for i in range(11, 21)]               # total, then the 9 bands
TRANSIT = [f"B08134_{i:03d}E" for i in range(61, 71)]


def _cache(cache_dir: Optional[str]) -> Path:
    from pycensus.cache import default_cache_dir

    base = Path(cache_dir) if cache_dir else Path(default_cache_dir()).parent
    d = base / "usa" / "acs_commute_time"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mean_time(df: pd.DataFrame, cols) -> tuple:
    tot = pd.to_numeric(df[cols[0]], errors="coerce")
    bands = np.column_stack([pd.to_numeric(df[c], errors="coerce").fillna(0).to_numpy(float) for c in cols[1:]])
    n = bands.sum(axis=1)
    with np.errstate(all="ignore"):
        mean = np.where(n > 0, bands @ np.asarray(MID) / n, np.nan)
    return tot.to_numpy(float), mean


def tract_table(state_fips: str, year: int = YEAR, cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Car and transit commute-time tables (ACS 5-year, by tract) of one state from the Census API, cached.

    Args:
        state_fips: 2-digit state FIPS.
        year: ACS end year.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per tract.
    """
    path = _cache(cache_dir) / f"{state_fips}_{year}.parquet"
    if path.is_file():
        return pd.read_parquet(path)
    import requests

    from pycensus.api_keys import resolve_api_key

    key = resolve_api_key("us_census", "US_CENSUS_API_KEY")
    cols = CAR + TRANSIT
    r = requests.get(f"https://api.census.gov/data/{year}/acs/acs5", params={"get": ",".join(cols), "for": "tract:*", "in": f"state:{state_fips}", "key": key},
                     timeout=180)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    out = pd.DataFrame({"GEOID": df["state"] + df["county"] + df["tract"]})
    out["car_commuters"], out["car_time_min"] = _mean_time(df, CAR)
    out["transit_commuters"], out["transit_time_min"] = _mean_time(df, TRANSIT)
    out.to_parquet(path)
    return out
