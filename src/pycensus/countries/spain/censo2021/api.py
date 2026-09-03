"""API client for Spain's Censo de Poblacion y Viviendas 2021 (SDC21) dissemination API.

Technical aspects:
    This is a *different* real, public, keyless INE API from
    ``spain.api``'s Tempus3/PC-Axis Padron sources -- INE's "Sistema de
    Difusion de los Censos de Poblacion y Viviendas 2021" (SDC21), a
    dedicated POST-JSON API documented at
    https://www.ine.es/dyngs/DataLab/es/manual.html?cid=1259945952385.

    Verified live 2026-08-22:
        ``POST https://www.ine.es/Censo2021/api``
        ``{"tabla": "per.ppal", "idioma": "ES", "metrica": ["SPERSONAS"],
           "variables": ["ID_RESIDENCIA_N3", "ID_RESIDENCIA_N5"]}``
        returns 36,333 rows, one per real census section nationwide, each
        keyed by a 10-digit ``CUSEC``-format code embedded in
        ``ID_RESIDENCIA_N5`` (e.g. ``"Seccion 0105101001"``) -- the same
        section-code format ``spain.api.fetch_padron_secciones`` already
        uses. Summing every section's value for
        ``variables=["ID_ESREAL_GR5"]`` (education) gives 47,400,798;
        summing ``["ID_RELA2"]`` (activity status) also gives 47,400,798;
        summing ``["ID_LUGAR_NAC_EXT_N1"]`` (birthplace) also gives
        47,400,798 -- all three internally consistent with each other and
        matching Spain's real published 2021 census population
        (47,385,107) to within ~0.03%, the expected effect of INE's
        statistical-disclosure-control rounding of the 2021 census
        microdata. Querying ``table="hog"``, ``metrica="SHOGARES"``
        nationwide gives 18,539,214 households, matching INE's own
        published Censo 2021 household count of "18.539.223" (Nota de
        Prensa) almost exactly. Donostia-San Sebastian (municipality code
        "20069")'s 144 real sections summed to 187,881 residents, matching
        its well-documented ~188,000 2021 population.

    Only census-*section*-level (and coarser, by summing) geography is
    verified here -- the API's ``ID_RESIDENCIA_N4``/``N5`` variables give
    district/section, nothing finer (no manzana-level variable exists in
    this API; see :mod:`pycensus.countries.spain.geography` module
    docstring for why manzana boundaries themselves also aren't
    implemented).

    No API key is required -- this is INE's own public, unauthenticated
    endpoint.

Source:
    https://www.ine.es/Censo2021/api
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

CENSO2021_API_URL = "https://www.ine.es/Censo2021/api"

# Real, live-observed failure modes (2026-08-25, fetching all 8 Gipuzkoa
# censo2021 features nationwide back-to-back): the SDC21 API is genuinely
# slow and occasionally flaky under sequential load, not broken -- a plain
# `curl` retry of the exact same request that failed always succeeded a
# moment later. Two distinct transient errors were observed in the same
# run: (1) an intermittent bare HTTP 404 on a request that succeeds when
# retried seconds later (server-side hiccup, not a real "not found" -- the
# table/variable/metric combination is valid, verified in this module's
# docstring), and (2) a `requests.exceptions.ReadTimeout` at the old 180s
# default -- the `ID_ESREAL_GR5`/`ID_RELA`/`ID_LUGAR_NAC_EXT_N1` category
# requests return ~20MB nationwide payloads that took 76-182s in repeated
# real timing tests, so 180s had no headroom on a slow day. Fixed here with
# a longer default timeout plus bounded retries with backoff, rather than
# raising the exception straight up to `censo2021/loader.py`'s
# swallow-and-fall-back-to-Padron-only handling.
_DEFAULT_TIMEOUT = 300
_MAX_ATTEMPTS = 4
_RETRY_BACKOFF_SECONDS = 10

# Real table names verified against SDC21's own metadata (see module
# docstring) -- "per.ppal" is "Total de Personas" (all persons).
TABLE_PERSONS = "per.ppal"
TABLE_HOUSEHOLDS = "hog"

METRIC_PERSONS = "SPERSONAS"
METRIC_HOUSEHOLDS = "SHOGARES"

# The section-geography variable, present on every SDC21 table.
VAR_SECTION = "ID_RESIDENCIA_N5"

_SECTION_CODE_RE = re.compile(r"(\d{10})")


def fetch_section_breakdown(
    table: str,
    metric: str,
    variable: Optional[str],
    raw_cache_path: Optional[Path] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Fetch (or read cached) nationwide section-level breakdown of one SDC21 category variable.

    Args:
        table: SDC21 table name (e.g. ``"per.ppal"``, ``"hog"``).
        metric: SDC21 metric name for that table (e.g. ``"SPERSONAS"``).
        variable: SDC21 category variable name (e.g. ``"ID_ESREAL_GR5"``),
            combined with :data:`VAR_SECTION` in the request so every row
            is both section-located and category-labeled. If ``None`` (or
            equal to :data:`VAR_SECTION`), the request uses only
            :data:`VAR_SECTION` -- the SDC21 API 404s on a request with the
            same variable named twice -- and every row's ``category`` is
            ``None`` (there is no category breakdown, e.g. households).
        raw_cache_path: If given and it already exists, read the raw JSON
            response from there instead of hitting the network; if given
            and it does not exist, the downloaded response is written
            there for next time.
        timeout: HTTP timeout in seconds.

    Returns:
        Long-format DataFrame with columns ``GEOID`` (10-digit CUSEC
        section code), ``category`` (the raw SDC21 label string for
        ``variable``), ``value``.

    Raises:
        requests.HTTPError: If the SDC21 API request fails.
    """
    has_category = variable is not None and variable != VAR_SECTION

    if raw_cache_path is not None and raw_cache_path.exists():
        payload = json.loads(raw_cache_path.read_text())
    else:
        variables = [VAR_SECTION, variable] if has_category else [VAR_SECTION]
        params = {
            "tabla": table,
            "idioma": "ES",
            "metrica": [metric],
            "variables": variables,
        }
        last_exc: Optional[Exception] = None
        response = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    CENSO2021_API_URL, json=params, headers={"Content-type": "application/json"}, timeout=timeout
                )
                response.raise_for_status()
                last_exc = None
                break
            except (requests.exceptions.RequestException,) as exc:
                last_exc = exc
                response = None
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
        if last_exc is not None or response is None:
            raise last_exc  # type: ignore[misc]
        payload = response.json()
        if raw_cache_path is not None:
            raw_cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw_cache_path.write_text(json.dumps(payload))

    return _parse_section_breakdown(payload, variable if has_category else None, metric)


def _parse_section_breakdown(payload: dict, variable: Optional[str], metric: str) -> pd.DataFrame:
    """Reshape SDC21's ``{"data": [{...}]}`` response into one row per (section, category)."""
    rows: List[dict] = []
    for row in payload.get("data", []):
        section_raw = row.get(VAR_SECTION, "")
        match = _SECTION_CODE_RE.search(str(section_raw))
        if match is None:
            continue
        rows.append(
            {
                "GEOID": match.group(1),
                "category": row.get(variable) if variable is not None else None,
                "value": row.get(metric),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "fetch_section_breakdown",
    "CENSO2021_API_URL",
    "TABLE_PERSONS",
    "TABLE_HOUSEHOLDS",
    "METRIC_PERSONS",
    "METRIC_HOUSEHOLDS",
    "VAR_SECTION",
]
