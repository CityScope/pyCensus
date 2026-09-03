"""Census Bureau data.census.gov API client shared by ACS and DHC (decennial).

Technical aspects:
    Wraps `pygris.data.get_census`, which hits
    ``https://api.census.gov/data/{year}/{dataset}``. The Census API scopes
    a request with a ``for``/``in`` geography predicate (e.g.
    ``for=tract:*&in=state:06+county:001``); :data:`pycensus.usa.constants.GEO_HIERARCHIES`
    supplies that chain per level. LODES does not use this endpoint -- see
    :mod:`pycensus.usa.lodes_rac` and :mod:`pycensus.usa.lodes_wac`.

    ACS (not DHC) fills suppressed/inapplicable estimates with large-magnitude
    negative sentinel codes (``-666666666`` and similar, all more negative
    than ``-111111111``) instead of leaving the cell blank -- see
    "Estimate and margin of error meaning" in the ACS technical docs.
    :func:`fetch_variables` nulls these out so they don't corrupt sums/means
    downstream.

Source:
    https://www.census.gov/data/developers/data-sets.html
    https://www.census.gov/programs-surveys/acs/technical-documentation/table-and-geography-changes.html
"""

from __future__ import annotations

from typing import List, Optional

import polars as pl
from pygris.data import get_census

from . import constants, utils

_SENTINEL_THRESHOLD = -111_111_111
"""Values at or below this are ACS suppression sentinels, not real estimates."""


def fetch_variables(
    dataset: str,
    year: int,
    level: str,
    state: str,
    variables: List[str],
    api_key: Optional[str] = None,
) -> pl.DataFrame:
    """Fetch raw variable codes for one state/level/year from the Census API.

    Args:
        dataset: API dataset path, e.g. ``"acs/acs5"`` or ``"dec/dhc"``.
        year: Vintage year.
        level: Logical geography level, a key of
            :data:`pycensus.usa.constants.GEO_HIERARCHIES`.
        state: State name, abbreviation, or FIPS code.
        variables: Raw Census variable codes to request (max 50 per call,
            the Census API's own limit).
        api_key: Census API key. Requests work without one at low volume,
            but are rate-limited more aggressively.

    Returns:
        Polars DataFrame with a ``GEOID`` column plus one column per
        successfully returned variable code.
    """
    hierarchy = constants.GEO_HIERARCHIES.get(level, ["state", "county", "tract"])
    fips = utils.state_fips(state)

    geo_filter = {h: f"{h}:{fips}" if h == "state" else f"{h}:*" for h in hierarchy[:-1]}

    rows = []
    for batch_start in range(0, len(variables), 50):
        batch = variables[batch_start : batch_start + 50]
        rows_batch = get_census(
            dataset=dataset,
            year=year,
            variables=batch,
            params={"for": f"{hierarchy[-1]}:*", "in": list(geo_filter.values()), "key": api_key},
            return_geoid=True,
        )
        rows.append(pl.DataFrame(rows_batch))

    df = rows[0]
    for extra in rows[1:]:
        new_cols = [c for c in extra.columns if c not in df.columns]
        df = df.join(extra.select(["GEOID", *new_cols]), on="GEOID", how="left")

    value_cols = [c for c in df.columns if c != "GEOID"]
    return df.with_columns(
        pl.col("GEOID").cast(pl.Utf8),
        *[
            pl.when(pl.col(c).cast(pl.Float64, strict=False) <= _SENTINEL_THRESHOLD)
            .then(None)
            .otherwise(pl.col(c))
            .alias(c)
            for c in value_cols
        ],
    )
