# -*- coding: utf-8 -*-
"""US election results, from MIT Election Data and Science Lab (MEDSL).

MEDSL's primary distribution channel is Harvard Dataverse, but its
newer/updated datasets (e.g. "County Presidential Election Returns
2000-2024", doi:10.7910/DVN/VOQCHQ) are gated behind a Dataverse
"Guestbook" survey response that can't be satisfied by a plain scripted
request -- confirmed live 2026-09-29: `GET
/api/access/datafile/<id>` returns `"You may not download this file
without the required Guestbook response for guestbookID 458."` even with
no auth at all, and the same gate applies dataverse-wide. Getting past it
would need a real Harvard Dataverse account + API token that has
answered the guestbook once through the actual web UI -- not something
this module can or should fabricate.

**Two genuinely NATIVE levels, not one** (per Miguel's explicit
2026-09-29 direction: elections should be downloaded at their own real
native level(s), then resampled onto census geography -- not treated as
county-only): President and Senate are both fundamentally STATE-level
contests (winner-take-all electors / one statewide seat), and MEDSL
separately publishes real state-level totals for both, not merely a
derived sum of its own county file -- so `level="state"` is just as
native as `level="county"`, from a different, independently-published
MEDSL file each time.

**What's actually implemented, and why (all verified live 2026-09-29
against real, ungated GitHub URLs, no guessing):**

- **President, county level, 2000-2016**: `github.com/MEDSL/
  county-returns` (`countypres_2000-2016.csv`), one combined CSV, real
  county `FIPS`.
- **President, county level, 2024**: NOT available as a convenient
  county-level file anywhere ungated -- county numbers only exist inside
  `github.com/MEDSL/2024-elections-official`'s `individual_states/
  {state}24.zip` files, at PRECINCT level (confirmed: Rhode Island's file
  has a real `county_fips` column per precinct row). This module
  downloads one state's precinct zip on demand (fits this project's own
  per-state processing architecture) and aggregates it to county itself.
- **Senate, county level, 2024**: `2024-elections-official`'s own
  `2024-senate-county.csv` -- already at county level.
- **President, STATE level, 1976-2016**: `github.com/MEDSL/
  constituency-returns` (`1976-2016-president.csv`) -- a genuinely
  separate, independently-published state-level file (NOT the same file
  as the county one, and NOT summed from it).
- **Senate, STATE level, 1976-2018**: same repo, `1976-2018-senate.csv`.
- **President/Senate, STATE level, 2024**: `2024-elections-official`'s
  own `2024-president-state.csv`/`2024-senate-state.csv`.
- **NOT implemented, genuine gaps** (flagged here rather than silently
  producing partial-looking-complete data):
  - House: no ungated source found at either level, for any year --
    House is its own distinct electoral geography (congressional
    district, not county or state), a real, separate gap from "just
    missing years."
  - Senate at COUNTY level for years other than 2024, and President at
    COUNTY level for 2024's full multi-state convenience (only per-state
    on demand): no ungated county-level source found for these
    specifically (state-level IS available for a wider year range, per
    above -- this gap is about county granularity only).
  - 2026: no election has happened yet as of this module's writing
    (2026-09-29; the midterms are in November 2026) -- there is no data
    to fetch.
  - Local/municipal races: out of scope (see the separately-documented
    decision to drop "local district" as a geography level entirely --
    no national dataset for the districts themselves, let alone results).

Output columns are named `{election_year}_{office}_...` per
`usa_study/prompt.txt` ("Elections info should be `{election_year}_
{election level or name}`"), e.g. `2024_president_total_votes`,
`2016_president_democrat_share`.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_COUNTY_RETURNS_2000_2016_URL = (
    "https://raw.githubusercontent.com/MEDSL/county-returns/master/countypres_2000-2016.csv"
)
_SENATE_2024_COUNTY_URL = (
    "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/2024-senate-county.csv"
)
_PRESIDENT_2024_STATE_ZIP_URL = (
    "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/individual_states/{abbr}24.zip"
)
_CONSTITUENCY_PRESIDENT_STATE_URL = (
    "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/1976-2016-president.csv"
)
_CONSTITUENCY_SENATE_STATE_URL = (
    "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/1976-2018-senate.csv"
)
_PRESIDENT_2024_STATE_URL = (
    "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/2024-president-state.csv"
)
_SENATE_2024_STATE_URL = (
    "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/2024-senate-state.csv"
)

#: (office, year) -> which loader function handles COUNTY level.
COUNTY_AVAILABLE: dict = {
    ("president", 2000): "county_returns",
    ("president", 2004): "county_returns",
    ("president", 2008): "county_returns",
    ("president", 2012): "county_returns",
    ("president", 2016): "county_returns",
    ("president", 2024): "president_2024_precinct",
    ("senate", 2024): "senate_2024_county",
}

#: (office, year) -> which loader function handles STATE level.
STATE_AVAILABLE: dict = {
    ("president", 1976): "constituency_president_state",
    ("president", 1980): "constituency_president_state",
    ("president", 1984): "constituency_president_state",
    ("president", 1988): "constituency_president_state",
    ("president", 1992): "constituency_president_state",
    ("president", 1996): "constituency_president_state",
    ("president", 2000): "constituency_president_state",
    ("president", 2004): "constituency_president_state",
    ("president", 2008): "constituency_president_state",
    ("president", 2012): "constituency_president_state",
    ("president", 2016): "constituency_president_state",
    ("president", 2024): "president_2024_state",
    ("senate", 1976): "constituency_senate_state",
    ("senate", 1978): "constituency_senate_state",
    ("senate", 1980): "constituency_senate_state",
    ("senate", 1982): "constituency_senate_state",
    ("senate", 1984): "constituency_senate_state",
    ("senate", 1986): "constituency_senate_state",
    ("senate", 1988): "constituency_senate_state",
    ("senate", 1990): "constituency_senate_state",
    ("senate", 1992): "constituency_senate_state",
    ("senate", 1994): "constituency_senate_state",
    ("senate", 1996): "constituency_senate_state",
    ("senate", 1998): "constituency_senate_state",
    ("senate", 2000): "constituency_senate_state",
    ("senate", 2002): "constituency_senate_state",
    ("senate", 2004): "constituency_senate_state",
    ("senate", 2006): "constituency_senate_state",
    ("senate", 2008): "constituency_senate_state",
    ("senate", 2010): "constituency_senate_state",
    ("senate", 2012): "constituency_senate_state",
    ("senate", 2014): "constituency_senate_state",
    ("senate", 2016): "constituency_senate_state",
    ("senate", 2018): "constituency_senate_state",
    ("senate", 2024): "senate_2024_state",
}

#: Backward-compat alias -- `AVAILABLE` used to mean "county", before
#: `level` existed as a parameter.
AVAILABLE = COUNTY_AVAILABLE


def _cache_path(cache_dir: str, name: str) -> Path:
    path = Path(cache_dir) / "usa" / "elections"
    path.mkdir(parents=True, exist_ok=True)
    return path / name


def _download_text(url: str, cache_path: Path) -> str:
    if cache_path.is_file():
        return cache_path.read_text()
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    cache_path.write_text(response.text)
    return response.text


def _load_county_returns_2000_2016(year: int, state_fips: Optional[str], cache_dir: str) -> pd.DataFrame:
    """President, county level, 2000-2016, from MEDSL's `county-returns` GitHub mirror."""
    cache_path = _cache_path(cache_dir, "countypres_2000-2016.csv")
    text = _download_text(_COUNTY_RETURNS_2000_2016_URL, cache_path)
    df = pd.read_csv(io.StringIO(text), dtype={"FIPS": str})
    df = df[df["year"] == year]
    if state_fips is not None:
        df = df[df["FIPS"].str[:2] == str(state_fips).zfill(2)]
    df["FIPS"] = df["FIPS"].str.zfill(5)
    return df.rename(columns={"FIPS": "GEOID", "candidatevotes": "votes"})


def _load_senate_2024_county(state_fips: Optional[str], state_abbr: Optional[str], cache_dir: str) -> pd.DataFrame:
    """Senate, county level, 2024, from MEDSL's `2024-elections-official` GitHub repo."""
    cache_path = _cache_path(cache_dir, "2024-senate-county.csv")
    text = _download_text(_SENATE_2024_COUNTY_URL, cache_path)
    df = pd.read_csv(io.StringIO(text), dtype={"county_fips": str})
    if state_abbr is not None:
        df = df[df["state_po"] == state_abbr.upper()]
    df["county_fips"] = df["county_fips"].str.zfill(5)
    return df.rename(columns={"county_fips": "GEOID"})


def _load_president_2024_precinct(state_abbr: str, cache_dir: str) -> pd.DataFrame:
    """President, county level, 2024, aggregated from one state's MEDSL precinct-level zip."""
    zip_path = _cache_path(cache_dir, f"{state_abbr.lower()}24.zip")
    if not zip_path.is_file():
        response = requests.get(_PRESIDENT_2024_STATE_ZIP_URL.format(abbr=state_abbr.lower()), timeout=180)
        response.raise_for_status()
        zip_path.write_bytes(response.content)

    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, dtype={"county_fips": str}, low_memory=False)

    df = df[df["office"].str.upper() == "US PRESIDENT"].copy()
    df["county_fips"] = df["county_fips"].str.zfill(5)
    # Some states' precinct-level files redact small vote counts with a
    # literal "*" (a real privacy-protection convention, not missing/bad
    # data) -- confirmed live 2026-09-29: New Mexico's file has ~135k such
    # cells, Rhode Island's has none. `errors="coerce"` turns those (and
    # any other non-numeric cell) into NaN; treating them as 0 rather than
    # dropping the row is standard practice for this kind of small-cell
    # redaction, but means county totals here can UNDERCOUNT true turnout
    # by a small, bounded amount wherever a state redacts -- summing raw
    # (uncoerced) strings, as an earlier version of this function did, is
    # the wrong alternative: pandas silently string-concatenates instead
    # of raising, producing garbage, not just an undercount.
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").fillna(0)
    grouped = df.groupby(["county_fips", "candidate", "party_simplified"], as_index=False)["votes"].sum()
    grouped["year"] = 2024
    return grouped.rename(columns={"county_fips": "GEOID", "party_simplified": "party"})


def _load_constituency_state(url: str, cache_name: str, year: int, state_fips: Optional[str], cache_dir: str) -> pd.DataFrame:
    """Shared loader for MEDSL's `constituency-returns` state-level president/senate files."""
    cache_path = _cache_path(cache_dir, cache_name)
    text = _download_text(url, cache_path)
    df = pd.read_csv(io.StringIO(text), dtype={"state_fips": str})
    df = df[df["year"] == year]
    if state_fips is not None:
        df = df[df["state_fips"].str.zfill(2) == str(state_fips).zfill(2)]
    df["state_fips"] = df["state_fips"].str.zfill(2)
    votes_col = "candidatevotes" if "candidatevotes" in df.columns else "votes"
    return df.rename(columns={"state_fips": "GEOID", votes_col: "votes"})


def _load_2024_state_file(url: str, cache_name: str, state_fips: Optional[str], state_abbr: Optional[str], cache_dir: str) -> pd.DataFrame:
    """Shared loader for MEDSL 2024-elections-official's `*-state.csv` files."""
    cache_path = _cache_path(cache_dir, cache_name)
    text = _download_text(url, cache_path)
    df = pd.read_csv(io.StringIO(text), dtype={"state_fips": str})
    if state_abbr is not None:
        df = df[df["state_po"] == state_abbr.upper()]
    elif state_fips is not None:
        df = df[df["state_fips"].str.zfill(2) == str(state_fips).zfill(2)]
    df["state_fips"] = df["state_fips"].str.zfill(2)
    party_col = "party_simplified" if "party_simplified" in df.columns else "party"
    return df.rename(columns={"state_fips": "GEOID", party_col: "party"})


def load(
    office: str,
    year: int,
    level: str = "county",
    state_fips: Optional[str] = None,
    state_abbr: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Load election results for one office/year, at its real native level.

    Args:
        office: `"president"` or `"senate"` (see `COUNTY_AVAILABLE`/
            `STATE_AVAILABLE` for exactly which office/year/level
            combinations are implemented -- House and most non-2024
            county-level non-presidential years are genuine, documented
            gaps, not silently wrong output).
        year: Election year.
        level: `"county"` or `"state"` -- BOTH are genuinely native here
            (see module docstring): president/senate are state-decided
            contests with their own independently-published MEDSL
            state-level file, not merely a derived sum of the county one.
        state_fips: Optional state FIPS filter (2-digit, e.g. `"35"`).
            Required (via `state_abbr`) for county-level president/2024
            specifically, since that source has no combined file.
        state_abbr: Optional 2-letter state abbreviation filter/selector.
        cache_dir: Cache root for downloaded source files. Defaults to
            `pycensus.cache.default_cache_dir()`.

    Returns:
        DataFrame with (at least) `GEOID` (5-digit county FIPS if
        `level="county"`, 2-digit state FIPS if `level="state"`),
        `candidate`, `party`, `votes`, `year`.

    Raises:
        NotImplementedError: If `(office, year)` isn't implemented at
            the requested `level`.
        ValueError: If `level` isn't `"county"`/`"state"`, or
            county-level president/2024 is requested with no
            `state_abbr`/resolvable `state_fips`.
    """
    if level not in ("county", "state"):
        raise ValueError(f"level must be 'county' or 'state', got {level!r}")

    registry = COUNTY_AVAILABLE if level == "county" else STATE_AVAILABLE
    key = (office, year)
    if key not in registry:
        raise NotImplementedError(
            f"No implemented MEDSL source for office={office!r}, year={year!r}, level={level!r}. "
            f"See pycensus.countries.usa.elections.loader's module docstring for "
            f"exactly what's available and why the rest is a documented gap."
        )

    if cache_dir is None:
        from pycensus.cache import default_cache_dir

        cache_dir = default_cache_dir()

    kind = registry[key]
    if kind == "county_returns":
        return _load_county_returns_2000_2016(year, state_fips, cache_dir)
    if kind == "senate_2024_county":
        return _load_senate_2024_county(state_fips, state_abbr, cache_dir)
    if kind == "president_2024_precinct":
        if state_abbr is None:
            if state_fips is None:
                raise ValueError("county-level president/2024 requires state_abbr (or a resolvable state_fips).")
            from ..utils import state_abbr as resolve_state_abbr

            state_abbr = resolve_state_abbr(state_fips)
        return _load_president_2024_precinct(state_abbr, cache_dir)
    if kind == "constituency_president_state":
        return _load_constituency_state(
            _CONSTITUENCY_PRESIDENT_STATE_URL, "1976-2016-president.csv", year, state_fips, cache_dir
        )
    if kind == "constituency_senate_state":
        return _load_constituency_state(
            _CONSTITUENCY_SENATE_STATE_URL, "1976-2018-senate.csv", year, state_fips, cache_dir
        )
    if kind == "president_2024_state":
        return _load_2024_state_file(
            _PRESIDENT_2024_STATE_URL, "2024-president-state.csv", state_fips, state_abbr, cache_dir
        )
    if kind == "senate_2024_state":
        return _load_2024_state_file(
            _SENATE_2024_STATE_URL, "2024-senate-state.csv", state_fips, state_abbr, cache_dir
        )

    raise AssertionError(f"Unhandled registry kind {kind!r}")  # pragma: no cover
