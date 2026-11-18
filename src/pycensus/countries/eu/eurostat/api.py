"""Client for the Eurostat dissemination API (JSON-stat 2.0, keyless).

Technical aspects:
    ``GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/<dataset>?<dim>=<code>&...`` returns one
    JSON-stat dataset: ``value`` is a sparse ``{flat index: number}`` map over the cartesian product of the dimensions
    listed in ``id`` with sizes ``size``. :func:`fetch` fixes every dimension except ``geo`` and ``time`` (it raises if
    the filters leave another dimension with several categories, so values of different meaning are never mixed) and
    returns a long table ``geo, time, value``. ``geoLevel=nuts0..3`` restricts ``geo`` to one NUTS level. Checked live
    2026-11-17.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from .. import constants


class EurostatError(RuntimeError):
    """The API answered with an error, or the filters do not fix every non-geo dimension."""


def _get(dataset: str, params, timeout: int = 180, tries: int = 4) -> dict:
    """GET with retries: the API occasionally hangs on a request it answers in a second the next time."""
    import time

    base = [("format", "JSON"), ("lang", "EN")]
    items = list(params.items()) if isinstance(params, dict) else list(params)
    for attempt in range(tries):
        try:
            r = requests.get(f"{constants.EUROSTAT_API}/{dataset}", params=base + items, timeout=timeout)
            break
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    try:
        j = r.json()
    except ValueError as e:
        raise EurostatError(f"{dataset}: not JSON (HTTP {r.status_code})") from e
    if "error" in j or r.status_code != 200:
        raise EurostatError(f"{dataset}: {j.get('error', r.status_code)}")
    return j


def parse_jsonstat(j: dict) -> pd.DataFrame:
    """Long table ``geo, time, value`` from a JSON-stat 2.0 dataset whose other dimensions have one category each.

    Args:
        j: Parsed JSON-stat response.

    Returns:
        DataFrame with ``geo`` (str), ``time`` (str) and ``value`` (float).

    Raises:
        EurostatError: if a dimension other than ``geo``/``time`` has more than one category.
    """
    ids, size = j["id"], j["size"]
    extra = [d for d, s in zip(ids, size) if d not in ("geo", "time") and s > 1]
    if extra:
        raise EurostatError(f"fix these dimensions with filters: {extra}")
    cats = {d: [None] * s for d, s in zip(ids, size)}
    for d in ids:
        for code, pos in j["dimension"][d]["category"]["index"].items():
            cats[d][pos] = code
    vals = j.get("value", {})
    if not vals:
        return pd.DataFrame(columns=["geo", "time", "value"])
    flat = np.array([int(k) for k in vals], dtype=np.int64)
    idx = np.unravel_index(flat, size)
    out = {d: np.asarray(cats[d], dtype=object)[i] for d, i in zip(ids, idx) if d in ("geo", "time")}
    return pd.DataFrame({"geo": out["geo"], "time": out["time"], "value": np.array(list(vals.values()), dtype=float)})


def fetch(dataset: str, filters: Optional[Dict[str, str]] = None, nuts_level: Optional[int] = None,
          since: Optional[int] = None, geos: Optional[List[str]] = None, chunk: int = 150) -> pd.DataFrame:
    """One Eurostat dataset as a long ``geo, time, value`` table.

    Args:
        dataset: Eurostat dataset code (``nama_10r_3gdp``).
        filters: ``{dimension: code}`` fixing every dimension except ``geo`` and ``time``.
        nuts_level: 0-3 to keep only that NUTS level (ignored when ``geos`` is given).
        since: first year (``sinceTimePeriod``).
        geos: explicit geo codes (requested in chunks of ``chunk``).
        chunk: geo codes per request.

    Returns:
        DataFrame ``geo, time, value``.
    """
    p = [(k, v) for k, v in (filters or {}).items()]
    if since:
        p.append(("sinceTimePeriod", str(since)))
    if geos:
        parts = [parse_jsonstat(_get(dataset, p + [("geo", g) for g in geos[i:i + chunk]])) for i in range(0, len(geos), chunk)]
        return pd.concat(parts, ignore_index=True)
    if nuts_level is not None:
        p.append(("geoLevel", "country" if nuts_level == 0 else f"nuts{nuts_level}"))
    return parse_jsonstat(_get(dataset, p))


__all__ = ["EurostatError", "parse_jsonstat", "fetch"]
