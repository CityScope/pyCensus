# -*- coding: utf-8 -*-
"""The one column-naming scheme for US election results, shared by every state, source and level.

    {year}_{office}_{measure}            e.g.  2024_president_democrat_share,  2018_governor_other_share

Measures (all six always written together, so states and sources compare directly). Every ratio is over the people entitled to vote of
the same unit -- the voting-age population (VAP), never over the votes cast:

    eligible_voters    people with the right to vote in the unit: the voting-age population (summed when resampled)
    total_votes        people who voted: all votes cast for the office (summed when resampled)
    democrat_share     Democratic candidate's votes / VAP
    republican_share   Republican candidate's votes / VAP
    other_share        all other candidates' votes (third parties, independents, write-ins) / VAP
    turnout            total_votes / eligible_voters  (= democrat_share + republican_share + other_share; non-voters are 1 - turnout)

VAP is ``population - under18Population`` (2020 Census) for now. Strictly the right to vote is held by citizens aged 18+; the Census Bureau's
CVAP special tabulation (block groups, from the ACS) is the intended denominator and is not loaded yet, so non-citizens (and people barred by
convictions) are still in the denominator. For elections before 2020 the 2020 count is used, so those ratios are approximate.

Offices use fixed names below no matter what the source calls them. ``democrat`` / ``republican`` means the major-party nominee of that
party; fusion lines or a second party label for the same candidate are summed into the party. Years are election years (four digits).
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

import numpy as np

OFFICES = (
    "president", "senate", "house", "governor", "lieutenant_governor", "attorney_general", "secretary_of_state",
    "state_senate", "state_house",
)
MEASURES = ("eligible_voters", "total_votes", "democrat_share", "republican_share", "other_share", "turnout")
SHARE_MEASURES = ("democrat_share", "republican_share", "other_share", "turnout")

_PATTERN = re.compile(r"^(\d{4})_(" + "|".join(OFFICES) + r")_(" + "|".join(MEASURES) + r")$")


def column_name(year: int, office: str, measure: str) -> str:
    """Standard election column name ``<year>_<office>_<measure>``.

    Args:
        year: Election year.
        office: Office key.
        measure: Measure key.

    Returns:
        The column name.

    Raises:
        ValueError: For an unknown office or measure.
    """
    if office not in OFFICES or measure not in MEASURES:
        raise ValueError(f"unknown office/measure: {office!r}, {measure!r}")
    return f"{int(year)}_{office}_{measure}"


def parse_column(name: str) -> Optional[Tuple[int, str, str]]:
    """(year, office, measure) of a standard election column, else None.

    Args:
        name: Column name.
    """
    m = _PATTERN.match(str(name))
    return (int(m.group(1)), m.group(2), m.group(3)) if m else None


def votes_to_columns(year: int, office: str, dem, rep, total, voting_age_population) -> Dict[str, np.ndarray]:
    """The six standard columns from vote counts (arrays); rows with no votes or no voting-age population get NaN ratios.

    Args:
        year: Election year.
        office: Office key.
        dem: Democratic votes.
        rep: Republican votes.
        total: Total votes.
        voting_age_population: Voting-age population.
    """
    dem, rep, total, vap = (np.asarray(x, dtype=float) for x in (dem, rep, total, voting_age_population))
    ok = np.isfinite(total) & (total > 0)
    den = np.where(ok & (vap > 0), vap, np.nan)
    return {
        column_name(year, office, "eligible_voters"): np.where(ok & (vap > 0), vap, np.nan),
        column_name(year, office, "total_votes"): np.where(ok, total, np.nan),
        column_name(year, office, "democrat_share"): dem / den,
        column_name(year, office, "republican_share"): rep / den,
        column_name(year, office, "other_share"): np.clip(total - dem - rep, 0.0, None) / den,
        column_name(year, office, "turnout"): total / den,
    }
