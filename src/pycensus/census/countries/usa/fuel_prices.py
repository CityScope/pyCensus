"""US retail motor-gasoline prices by state and year (EIA State Energy Data System, SEDS).

Series MGTCD: motor gasoline price, transportation sector, dollars per million Btu, annual, 1970 onward, every state + DC (+ US).
Converted to dollars per gallon with EIA's heat content of motor gasoline (5.053 MMBtu per barrel / 42 gallons = 0.1203 MMBtu per gallon).
Downloaded once (no API key) into `<cache>/eia_seds/pr_all.csv`.

    from pycensus.census.countries.usa.fuel_prices import gasoline_prices, gasoline_price_mean
    gasoline_prices()                                  # DataFrame: state (USPS), year, usd_per_gallon
    gasoline_price_mean(2019, 2023)                    # {state: mean $/gal over 2019-2023} -- e.g. an ACS 5-year period
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

URL = "https://www.eia.gov/state/seds/sep_prices/total/csv/pr_all.csv"
MMBTU_PER_GALLON = 5.053 / 42.0


def _path(cache_dir: Optional[str] = None) -> Path:
    from pycensus.cache import default_cache_dir

    base = Path(cache_dir) if cache_dir else Path(default_cache_dir()).parent
    d = base / "eia_seds"
    d.mkdir(parents=True, exist_ok=True)
    return d / "pr_all.csv"


def gasoline_prices(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Long table: state (USPS code, 'US' = national), year (int), usd_per_gallon.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    p = _path(cache_dir)
    if not p.is_file() or p.stat().st_size < 100_000:
        import requests

        r = requests.get(URL, timeout=180)
        r.raise_for_status()
        p.write_bytes(r.content)
    d = pd.read_csv(p)
    d = d[d["MSN"] == "MGTCD"].drop(columns=["Data_Status", "MSN"])
    long = d.melt(id_vars="State", var_name="year", value_name="usd_per_mmbtu").dropna()
    long["year"] = long["year"].astype(int)
    long["usd_per_gallon"] = pd.to_numeric(long["usd_per_mmbtu"], errors="coerce") * MMBTU_PER_GALLON
    return long.rename(columns={"State": "state"})[["state", "year", "usd_per_gallon"]].reset_index(drop=True)


def gasoline_price_mean(first_year: int, last_year: int, cache_dir: Optional[str] = None) -> Dict[str, float]:
    """{state: mean $/gal over [first_year, last_year]} (an ACS 5-year estimate's period, e.g. 2019-2023). Years past the last published
    one use the latest year available.

    Args:
        first_year: First year.
        last_year: Last year.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    t = gasoline_prices(cache_dir)
    last = int(t["year"].max())
    years = [min(y, last) for y in range(first_year, last_year + 1)]
    sel = pd.concat([t[t["year"] == y] for y in years])
    return sel.groupby("state")["usd_per_gallon"].mean().round(3).to_dict()
