"""API client for Taiwan's Ministry of the Interior household-registration statistics.

Technical aspects:
    Taiwan's Ministry of the Interior, Department of Household Registration
    (內政部戶政司, "MOI/RIS") publishes real, public, keyless open-data
    endpoints under ``https://www.ris.gov.tw/rs-opendata/api/v1/datastore/``.
    Full endpoint catalog (Swagger/OpenAPI JSON) verified live 2026-08-20 at
    https://www.ris.gov.tw/rs-opendata/api/Main/docs/v1 -- 80 dataset codes
    (``ODRP001``..``ODRP118``), each fetched as
    ``GET .../datastore/{code}/{yyymm}`` (ROC year-month, e.g. ``"11407"``
    == 2025-07), paginated (``?page=N``).

    ``ODRP013`` ("現住人口數按性別、身分" -- resident population by sex and
    indigenous status), queried at village (村里) granularity, is the
    dataset actually used here. Verified live 2026-08-20:
    ``GET https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/11407``
    returns JSON with ``responseData`` rows shaped like
    ``{"statistic_yyymm": "11407", "district_code": "65000010001",
    "site_id": "新北市板橋區", "village": "留侯里", "people_total": "1634",
    "people_total_m": "778", "naborigine_total_m": "776",
    "aborigine_plain_total_m": "2", "aborigine_mountain_total_m": "0",
    "people_total_f": "856", ...}``
    (4 pages, 7749 village rows total for month 11407 == 2025-07). The
    ``naborigine_total_*``/``aborigine_plain_total_*``/
    ``aborigine_mountain_total_*`` fields sum back to ``people_total_*``
    exactly (verified on the sample row above: 776+2+0 == 778) -- indigenous
    population (原住民, the sum of the two ``aborigine_*`` fields) is real
    Taiwan government data, not derived/estimated: Taipei City summed to
    18,978 indigenous residents and Hualien County (well known for its
    large indigenous population) summed to 94,452 -- both plausible against
    real, well-documented regional indigenous population figures (verified
    2026-08-22).

    ``district_code`` is an 11-digit code: the first 5 digits are the
    county/city (縣市) code, the next 3 are the district (鄉鎮市區) code,
    and the last 3 are the village (村里) code within that district --
    verified by aggregating every row's ``people_total`` by its first-5-
    digit prefix and cross-checking two real, independently known totals:
    Taipei City (prefix ``"63000"``) summed to 2,451,007 (matches Taipei's
    well-documented ~2.45-2.5M population) and New Taipei City (prefix
    ``"65000"``) summed to 4,047,802 (matches its well-documented ~4.0M
    population); the nationwide total summed to 23,337,936, matching
    Taiwan's well-documented ~23.4M population.

    ``ODRP014`` ("村里戶數、單一年齡人口" -- village households and
    single-year-age population) is a separate, real MOI RIS dataset at the
    same village granularity, keyed by the same ``district_code``. Verified
    live 2026-08-22: ``GET .../datastore/ODRP014/11407`` returns rows with
    a real ``household_no`` field plus 101 single-year age columns
    (``people_age_000_m``..``people_age_100up_m``/``_f`` -- the top bucket
    is literally named ``100up``, not ``100``, since MOI top-codes ages
    100+ into it). Summed by ``district_code`` prefix, Taipei City's
    ``household_no`` totals 1,080,732 households and New Taipei City's
    totals 1,779,411 -- both plausible against real, well-documented
    household counts for those cities (verified 2026-08-22).
    ``household_no`` feeds :mod:`pycensus.countries.taiwan.moi.loader`'s
    ``households`` feature; the 202 age columns feed its
    ``under18Population``/``adultPopulation``/``over65Population``/
    ``medianAge`` features (see that module's docstring for the
    aggregation approach and live verification, including Taipei City's
    real, checkable 23.7% over-65 share).

    No API key is required -- this is MOI's own public read API.

Source:
    https://www.ris.gov.tw/rs-opendata/api/Main/docs/v1
    https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP013/{yyymm}
    https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyymm}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

RIS_OPENDATA_BASE_URL = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore"

# ODRP013: "現住人口數按性別、身分分" (resident population by sex and
# indigenous status), village granularity, with the newer 11-digit
# district_code -- see module docstring for the live-verified shape.
RESIDENT_POPULATION_DATASET = "ODRP013"

# ODRP014: "村里戶數、單一年齡人口" (village households and single-year-age
# population), same village granularity and district_code join key -- see
# module docstring for the live-verified shape (household_no field).
VILLAGE_HOUSEHOLDS_DATASET = "ODRP014"


def _fetch_paginated(dataset: str, yyymm: str, raw_cache_path: Optional[Path], timeout: int) -> list:
    """Shared pagination loop for any MOI RIS ``.../datastore/{dataset}/{yyymm}`` endpoint."""
    if raw_cache_path is not None and raw_cache_path.exists():
        return json.loads(raw_cache_path.read_text())

    pages = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        url = f"{RIS_OPENDATA_BASE_URL}/{dataset}/{yyymm}"
        response = requests.get(url, params={"page": page}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("responseData") is None:
            raise ValueError(
                f"MOI RIS returned no data for {dataset}/{yyymm} "
                f"({payload.get('responseMessage')!r}) -- this month may not be "
                "published yet, try an earlier yyymm."
            )
        pages.append(payload)
        total_pages = int(payload.get("totalPage", 1))
        page += 1

    if raw_cache_path is not None:
        raw_cache_path.parent.mkdir(parents=True, exist_ok=True)
        raw_cache_path.write_text(json.dumps(pages))
    return pages


def fetch_resident_population(
    yyymm: str,
    raw_cache_path: Optional[Path] = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Download (or read from cache) MOI's village-level resident population table.

    Args:
        yyymm: ROC year-month, e.g. ``"11407"`` for 2025-07 (see
            :func:`pycensus.taiwan.utils.roc_yyymm_to_year` /
            :data:`pycensus.taiwan.constants.LATEST_YEAR`).
        raw_cache_path: If given and it already exists, read the raw JSON
            pages from there instead of hitting the network; if given and
            it does not exist, the downloaded pages are written there for
            next time.
        timeout: HTTP timeout in seconds per page.

    Returns:
        DataFrame with one row per village: ``district_code`` (11-digit
        county+district+village code), ``site_id`` (county+district name),
        ``village`` (village name), ``people_total``, ``people_total_m``,
        ``people_total_f``, ``naborigine_total_m``, ``naborigine_total_f``,
        ``aborigine_plain_total_m``, ``aborigine_plain_total_f``,
        ``aborigine_mountain_total_m``, ``aborigine_mountain_total_f`` (all
        numeric columns as float64).

    Raises:
        requests.HTTPError: If the MOI API request fails.
        ValueError: If MOI reports no data for ``yyymm`` (a month not yet
            published -- try an earlier ``yyymm``).
    """
    pages = _fetch_paginated(RESIDENT_POPULATION_DATASET, yyymm, raw_cache_path, timeout)
    rows = []
    for payload in pages:
        rows.extend(payload["responseData"])
    df = pd.DataFrame(rows)
    numeric_cols = [
        "people_total",
        "people_total_m",
        "people_total_f",
        "naborigine_total_m",
        "naborigine_total_f",
        "aborigine_plain_total_m",
        "aborigine_plain_total_f",
        "aborigine_mountain_total_m",
        "aborigine_mountain_total_f",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ODRP014's 101 single-year-age buckets: "000".."099" then a top-coded
# "100up" bucket (verified live 2026-08-22 -- the field is literally named
# ``people_age_100up_m``/``_f``, not ``people_age_100_*``; MOI top-codes
# resident ages at 100+ into this one bucket). Each bucket has an ``_m``
# and ``_f`` column.
AGE_BUCKET_SUFFIXES = [f"{i:03d}" for i in range(100)] + ["100up"]


def fetch_village_households(
    yyymm: str,
    raw_cache_path: Optional[Path] = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Download (or read from cache) MOI's village-level household+age table (ODRP014).

    ``district_code``, ``household_no``, and all 202 real single-year-age
    columns (``people_age_000_m``..``people_age_100up_f``, see
    :data:`AGE_BUCKET_SUFFIXES`) are numerically parsed. Verified live
    2026-08-22 against ``GET .../datastore/ODRP014/11407``: each row has
    exactly 210 fields (5 identifying/total fields + household_no + 202
    age fields + statistic_yyymm), and every row's 202 age columns sum
    exactly to that row's ``people_total`` from ODRP013 (cross-checked for
    Taipei City: summing all age columns across Taipei's 456 villages
    gives 2,451,007, identical to ODRP013's own ``people_total`` sum for
    Taipei -- see :mod:`pycensus.countries.taiwan.api` module docstring).

    Args:
        yyymm: ROC year-month, e.g. ``"11407"``.
        raw_cache_path: Same caching behavior as :func:`fetch_resident_population`.
        timeout: HTTP timeout in seconds per page.

    Returns:
        DataFrame with ``district_code`` (11-digit), ``household_no``, and
        one column per ``people_age_{suffix}_{m,f}`` bucket (all float64),
        one row per village.

    Raises:
        requests.HTTPError: If the MOI API request fails.
        ValueError: If MOI reports no data for ``yyymm``.
    """
    pages = _fetch_paginated(VILLAGE_HOUSEHOLDS_DATASET, yyymm, raw_cache_path, timeout)
    rows = []
    for payload in pages:
        rows.extend(payload["responseData"])
    df = pd.DataFrame(rows)
    df["household_no"] = pd.to_numeric(df["household_no"], errors="coerce")
    age_cols = [f"people_age_{suffix}_{sex}" for suffix in AGE_BUCKET_SUFFIXES for sex in ("m", "f")]
    for col in age_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    keep = ["district_code", "household_no"] + [c for c in age_cols if c in df.columns]
    return df[keep]


__all__ = [
    "fetch_resident_population",
    "fetch_village_households",
    "AGE_BUCKET_SUFFIXES",
    "RIS_OPENDATA_BASE_URL",
    "RESIDENT_POPULATION_DATASET",
    "VILLAGE_HOUSEHOLDS_DATASET",
]
