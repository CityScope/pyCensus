# -*- coding: utf-8 -*-
"""Statewide calibration of an unofficial precinct file to the FEC's official 2024 state totals (``verification/fec_2024_state_totals.json``).

Compilations differ from the official canvass by a fraction of a percent (late ballots, overvotes, summary rows). When the file is within
``MAX_DEV`` of the official total and Democratic count, the three vote columns are multiplied by one statewide factor each so the state matches the
official result exactly; a larger gap means missing precincts, and the source is refused (``ValueError``) instead of being stretched.
"""

from __future__ import annotations

import json
from pathlib import Path


MAX_DEV = 0.02
_FEC = Path(__file__).resolve().parent / "verification" / "fec_2024_state_totals.json"


def calibrate(gdf, state_abbr: str, max_dev: float = MAX_DEV):
    """Scale a state's precinct votes to the FEC official totals, refusing files that deviate by more than ``max_dev``.

    Args:
        gdf: Precincts with ``votes_*`` columns.
        state_abbr: State abbreviation.
        max_dev: Largest accepted deviation.

    Returns:
        The scaled precincts.

    Raises:
        ValueError: If the file deviates too much.
    """
    ref = json.loads(_FEC.read_text())["states"][state_abbr.lower()]
    tot = float(gdf["votes_total"].sum())
    dem = float(gdf["votes_dem"].sum())
    if abs(tot - ref["total"]) / ref["total"] > max_dev or abs(dem - ref["dem"]) / ref["dem"] > max_dev:
        raise ValueError(f"{state_abbr}: precinct file deviates from the FEC official total by more than {max_dev:.0%}")
    for c, k in (("votes_total", "total"), ("votes_dem", "dem"), ("votes_rep", "rep")):
        s = float(gdf[c].sum())
        if s > 0:
            gdf[c] = gdf[c] * (ref[k] / s)
    return gdf
