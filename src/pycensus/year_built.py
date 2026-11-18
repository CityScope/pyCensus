"""Four year-of-construction shares of dwellings from any source's own construction-period bands.

`dwellings_built_before_1945_share`, `dwellings_built_1945_1970_share`, `dwellings_built_1970_2000_share`, `dwellings_built_after_2000_share` (0-1).
Bands come from `reference/year_built_bands.json` (US ACS B25034, Spain Census 2021 / Catastro, Germany Zensus 2022 grid, Canada StatCan 2021). Each band
[first, last] is spread uniformly over its years (half-open [first, last+1)) and cut at the bin edges 1945 / 1970 / 2000, so a band straddling an edge is
split pro rata (ACS 1940-49 -> 50 % before 1945; German 1919-48 -> 26/30 before 1945; Spanish 1961-70 -> 9/10 before 1970); the oldest open band is
assumed to start in 1900. Unknown-year dwellings are not part of the denominator (the shares of the known ones sum to 1).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

_FILE = Path(__file__).resolve().parent / "reference" / "year_built_bands.json"
SHARE_NAMES = ("dwellings_built_before_1945_share", "dwellings_built_1945_1970_share", "dwellings_built_1970_2000_share", "dwellings_built_after_2000_share")


@lru_cache(maxsize=1)
def config() -> dict:
    """The year-built configuration (band edges and the sources' band columns).

    Returns:
        The config dict.
    """
    return json.loads(_FILE.read_text(encoding="utf-8"))


def band_fractions(first: Optional[int], last: Optional[int], edges: Sequence[int] = (1945, 1970, 2000), open_start: int = 1900, open_end: int = 2030) -> np.ndarray:
    """Fraction of the years `[first, last]` (inclusive) that fall in each of the len(edges)+1 bins.

    Args:
        first: First year of the band (None: open start).
        last: Last year of the band (None: open end).
        edges: Bin edges.
        open_start: Year used for an open start.
        open_end: Year used for an open end.
    """
    a = open_start if first is None else first
    b = (open_end if last is None else last) + 1
    cuts = [-10 ** 9, *edges, 10 ** 9]
    span = max(b - a, 1)
    return np.array([max(0, min(b, hi) - max(a, lo)) / span for lo, hi in zip(cuts[:-1], cuts[1:])], dtype=float)


def shares_from_bands(df, columns: Dict[str, Sequence[Optional[int]]], scale: float = 1.0):
    """`DataFrame` with the four `SHARE_NAMES` columns (NaN where no band has data); `scale` 100 gives percentages.

    Args:
        df: Table with band columns.
        columns: ``{column: (first year, last year)}``.
        scale: 1 for shares, 100 for percentages.
    """
    import pandas as pd

    cfg = config()
    cols = [c for c in columns if c in df.columns]
    vals = np.column_stack([pd.to_numeric(df[c], errors="coerce").to_numpy(float) for c in cols]) if cols else np.zeros((len(df), 0))
    fr = np.array([band_fractions(*columns[c], edges=cfg["edges"], open_start=cfg["open_start_year"]) for c in cols]).reshape(len(cols), len(cfg["edges"]) + 1)
    known = ~np.isnan(vals)
    v = np.where(known, vals, 0.0)
    num = v @ fr
    den = (v * 1.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den[:, None]
    out[(den <= 0) | ~known.any(axis=1)] = np.nan
    return pd.DataFrame(out * scale, index=df.index, columns=list(SHARE_NAMES))


def pick_source(columns) -> Optional[dict]:
    """The first configured source with at least one band column in `columns`.

    Args:
        columns: Column names.
    """
    cols = set(columns)
    for src in config()["sources"]:
        if cols & set(src["columns"]):
            return src
    return None


def add_year_built_shares(df, scale: Optional[float] = None):
    """Add the four share columns to `df` (in place) from the first source whose band columns are present; no-op when none or already present.

    Args:
        df: Table.
        scale: 1 or 100; ``None`` = the package default.

    Returns:
        The same table.
    """
    if all(n in df.columns for n in SHARE_NAMES):
        return df
    src = pick_source(df.columns)
    if src is None:
        return df
    if scale is None:
        from pycensus.derived_columns import SHARE_SCALE

        scale = SHARE_SCALE
    sh = shares_from_bands(df, src["columns"], scale)
    for n in SHARE_NAMES:
        if n not in df.columns:
            df[n] = sh[n].to_numpy()
    return df


def drop_intermediate_bands(df):
    """`df` without the raw band columns of `intermediate` sources once the four shares exist (map inputs only).

    Args:
        df: Table.
    """
    if not all(n in df.columns for n in SHARE_NAMES):
        return df
    drop = [c for src in config()["sources"] if src.get("intermediate") for c in src["columns"] if c in df.columns]
    drop += [c for c in ("acs5_dwellingsBuiltTotal", "destatis_buildingsBuiltTotal") if c in df.columns]
    return df.drop(columns=drop) if drop else df
