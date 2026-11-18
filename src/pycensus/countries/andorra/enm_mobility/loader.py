"""Andorra has no census question on the means of transport; the only parish-level figures are those of the representative citizen
survey of the National Mobility Strategy 2021-2050 (ENM 2050; Centre de Recerca Sociologica, July 2021, 403 residents aged 18+), annex 2,
table "Mode de desplacament en relacio amb les variables sociodemografiques (N=356)": share of respondents who travelled the day before
the survey and used each mode at least once, by parish (several modes per person, so the rows add to more than 100 %).

The memoria (PDF) is downloaded once from the Govern d'Andorra into ``<cache>/andorra/enm_mobility/`` and the table is read from its
text (``pdftotext -layout``, else pypdf).

    from pycensus.countries.andorra import enm_mobility
    enm_mobility.parish_table()      # GEOID (AD-0X), parish, respondents, walk / bike / pmv / transit / car / moto / other share (0-1)
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

SOURCE_URL = "https://govern.ad/documents/d/guest/memoria_enm"
COLS = ["walk_share", "bike_share", "pmv_share", "transit_share", "car_share", "moto_share", "other_share"]


def _dir(cache_dir: Optional[str]) -> Path:
    from .... import cache as cache_store

    base = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    d = base / "andorra" / "enm_mobility"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _text(pdf: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        from pypdf import PdfReader

        return "\n".join(p.extract_text(extraction_mode="layout") or "" for p in PdfReader(str(pdf)).pages)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("'", "").replace("’", "").strip()


def parish_table(cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Travel modes by parish from the 2021 national mobility survey (ENM) report, parsed from its PDF and cached.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per parish (``GEOID``).
    """
    from ..constants import PARISH_CODES

    d = _dir(cache_dir)
    pq = d / "enm2021_modes_by_parish.parquet"
    if pq.is_file():
        return pd.read_parquet(pq)
    pdf = d / "memoria_enm.pdf"
    if not pdf.is_file() or pdf.stat().st_size < 500_000:
        import requests

        r = requests.get(SOURCE_URL, timeout=300)
        r.raise_for_status()
        pdf.write_bytes(r.content)
    lines = _text(pdf).splitlines()
    start = next(i for i, l in enumerate(lines) if "Mode de despla" in l and "sociodemogr" in l)
    p0 = next(i for i in range(start, len(lines)) if lines[i].strip() == "Parròquia")
    names = {_norm(v): k for k, v in PARISH_CODES.items()}
    rows = []
    for l in lines[p0 + 1: p0 + 12]:
        m = re.match(r"^\s*(\D+?)\s{2,}(\d+)\s+([\d,\s]+)$", l)
        if not m:
            continue
        code = names.get(_norm(m.group(1)))
        vals = [float(v.replace(",", ".")) / 100.0 for v in m.group(3).split()]
        if code and len(vals) == 7:
            rows.append([code, PARISH_CODES[code], int(m.group(2)), *vals])
    t = pd.DataFrame(rows, columns=["GEOID", "parish", "respondents", *COLS])
    if len(t) != 7:
        raise RuntimeError(f"ENM survey table: parsed {len(t)} parishes, expected 7")
    t.to_parquet(pq)
    return t


def load(cache_dir: Optional[str] = None, **_) -> pd.DataFrame:
    """The parish table (no geometry needed: join on GEOID with :func:`pycensus.countries.andorra.geography.load_boundaries`).

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        **_: Ignored (common loader signature).

    Returns:
        The parish table.
    """
    return parish_table(cache_dir)
