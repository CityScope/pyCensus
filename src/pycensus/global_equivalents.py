"""Global-schema equivalents of differently named census columns (`schemas/global_equivalents.json`).

`add_global_equivalents(df)` adds, for every local column present, the global-schema column that means the same thing (the local
value repeated) -- unless the global column already exists. A column whose local name already equals the global name is NOT handled
here (the pipelines rename it to the bare global name, so there is only one column).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
from typing import Dict

_FILE = Path(__file__).resolve().parent / "schemas" / "global_equivalents.json"


@lru_cache(maxsize=1)
def equivalents() -> Dict[str, str]:
    """`{local column: global feature name}`."""
    return dict(json.loads(_FILE.read_text(encoding="utf-8"))["equivalents"])


@lru_cache(maxsize=1)
def originals() -> Dict[str, str]:
    """`{global-named column: twin that keeps the census column's original meaning}` (see `originals` in the JSON)."""
    return dict(json.loads(_FILE.read_text(encoding="utf-8")).get("originals", {}))


def latest_equivalents(columns) -> Dict[str, str]:
    """`{global feature: local column}` for the period-carrying columns (latest election per scope, latest-period housing columns).

    Patterns come from `latest_patterns` in the JSON: ordered regexes per global name; the first regex with matches wins and the
    latest period among its matches is chosen (an un-suffixed column = current period).

    Args:
        columns: Column names.
    """
    from .latest_columns import parse_period

    pats = json.loads(_FILE.read_text(encoding="utf-8")).get("latest_patterns", {})
    cols = [c for c in columns if isinstance(c, str)]
    out: Dict[str, str] = {}
    for glob, regexes in pats.items():
        for rx in regexes:
            cre = re.compile(r"(?:[A-Za-z0-9]+_)?(?:%s)" % rx)
            hits = [c for c in cols if cre.fullmatch(c)]
            if hits:
                def period(c):
                    per = parse_period(c)[1]
                    return ((10 ** 6,) if per is None else per, c)
                out[glob] = max(hits, key=period)
                break
    return out


def add_global_equivalents(df):
    """`df` (pandas / geopandas) with the global-named twin of every equivalent local column present (values copied), plus the
    period-free global names (`elec_national_left_share`, `rent_per_m2_mean`, ...) of the LATEST period of each local family.

    Args:
        df: Table.

    Returns:
        The same table.
    """
    for local, glob in equivalents().items():
        if local in df.columns and glob not in df.columns:
            df[glob] = df[local]
    for col, twin in originals().items():
        if col in df.columns and twin not in df.columns:
            df[twin] = df[col]
    for glob, local in latest_equivalents(df.columns).items():
        if glob not in df.columns:
            df[glob] = df[local]
    from .derived_columns import add_derived_columns
    from .year_built import add_year_built_shares

    add_derived_columns(df)   # under18/over65/university/basic-education/foreign-born shares, density, jobs, mobility
    return add_year_built_shares(df)   # dwellings_built_before_1945_share ... from the source's own construction-period bands
