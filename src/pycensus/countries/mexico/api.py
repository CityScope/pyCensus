"""INEGI ITER download client shared by Mexico census sources.

Technical aspects:
    Unlike the US Census Bureau's RESTful API, INEGI does not offer a
    queryable API for census 2020 results -- it publishes bulk per-state
    CSV bundles instead. This module downloads and parses "Iter por
    localidad" (ITER), the file INEGI itself recommends for
    state/municipality/locality-level 2020 census totals:

        https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_{state}_cpv2020_csv.zip

    (verified real 2026-08-19 -- see
    :data:`pycensus.mexico.constants.CENSUS_2020_URLS`; several
    superficially-plausible INEGI URLs return a ~2.3KB generic HTML "not
    found" page with a 200 status instead of 404, so every URL used here
    was confirmed with a real ``Content-Type: application/x-zip-compressed``
    and non-trivial ``Content-Length``, not just a 200).

    ITER mixes three grains of row in one file, keyed by
    ``ENTIDAD``/``MUN``/``LOC``:
        - state total:        MUN == "000", LOC == "0000"
        - municipality total: MUN != "000", LOC == "0000"
        - locality:           LOC not in ("0000", "9998", "9999")
    :func:`fetch_state_totals`/:func:`fetch_municipality_totals` pick out
    the right rows for each. AGEB/block-level attribute data lives in a
    *different* INEGI file (RESAGEBURB, not ITER) and is not implemented
    here -- see :mod:`pycensus.mexico.geography` for the equivalent
    boundary-side limitation.

    No microdata (person/household/dwelling-level) downloader is
    implemented: INEGI's microdata files are multi-GB per state and would
    need a genuinely different pipeline (sampling/streaming) to be
    practical here.

    AGEB/block-level attribute data comes from a separate INEGI bulk file,
    RESAGEBURB ("Resumen AGEB Urbana"), one zip per state:

        https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb_manzana/ageb_mza_urbana_{state}_cpv2020_csv.zip

    (verified real 2026-08-20 -- state "14" (Jalisco) returns a real
    ``application/zip``-ish, ~15.9MB zip containing
    ``conjunto_de_datos/conjunto_de_datos_ageb_urbana_14_cpv2020.csv``, a
    real ~230-column, latin-1-encoded CSV with columns
    ``ENTIDAD, NOM_ENT, MUN, NOM_MUN, LOC, NOM_LOC, AGEB, MZA, POBTOT, ...``.
    Cross-checked: summing ``POBTOT`` over AGEB-total rows
    (``AGEB != "0000"`` and ``MZA == "000"``) for ``MUN == "039"``
    (Guadalajara) gives 1,385,621 -- 8 short of INEGI's own published
    1,385,629 municipality total, the expected few-unit gap from INEGI's
    small-cell privacy suppression at the AGEB grain, not a bug here.
    Some states' RESAGEBURB CSVs carry a UTF-8 BOM on the first column
    name (``ï»¿ENTIDAD`` if decoded as latin-1) -- :func:`_read_resageburb`
    strips it explicitly since a naive ``dtype=str`` read leaves it stuck
    on ``ENTIDAD``, breaking every downstream ``df["ENTIDAD"]`` lookup for
    those files.

    Row grain within one RESAGEBURB file:
        - AGEB total: ``AGEB != "0000"`` and ``MZA == "000"``
        - block:      ``MZA != "000"``
    (``AGEB == "0000"`` rows are locality-level rollups, not used here.)

Source:
    INEGI Census 2020 open data: https://www.inegi.org.mx/programas/ccpv/2020/default.html#Datos_abiertos
    RESAGEBURB: https://www.inegi.org.mx/programas/ccpv/2020/#Datos_abiertos
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from . import constants, utils


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "iter"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def download_iter_csv(state: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) and extract the ITER CSV for one state.

    Args:
        state: State code, name, or abbreviation.
        data_dir: Base directory for the raw file cache. Defaults to
            :data:`pycensus.mexico.constants.DEFAULT_DATA_DIR`.

    Returns:
        Path to the extracted ``conjunto_de_datos_iter_{state}CSV20.csv`` file.

    Raises:
        requests.HTTPError: If the download fails.
        FileNotFoundError: If the zip doesn't contain the expected CSV
            (would indicate INEGI changed the file layout).
    """
    state_code = utils.state_code(state)
    raw_dir = _raw_dir(data_dir)

    csv_path = raw_dir / f"iter_{state_code}.csv"
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path

    url = constants.CENSUS_2020_URLS["iter_template"].format(state=state_code)
    zip_path = raw_dir / f"iter_{state_code}.zip"

    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)

    with zipfile.ZipFile(zip_path) as zf:
        candidates = [
            n for n in zf.namelist()
            if n.endswith(".csv") and "conjunto_de_datos" in n
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No 'conjunto_de_datos*.csv' found inside {zip_path} -- "
                f"INEGI may have changed the ITER zip layout"
            )
        with zf.open(candidates[0]) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return csv_path


def _read_iter(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    csv_path = download_iter_csv(state, data_dir)
    return pd.read_csv(csv_path, dtype={"ENTIDAD": str, "MUN": str, "LOC": str})


def fetch_state_totals(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch the single state-total row (``MUN=="000"``, ``LOC=="0000"``) from ITER.

    Returns:
        One-row DataFrame with a ``GEOID`` column (the 2-digit state code)
        plus every raw ITER column.
    """
    df = _read_iter(state, data_dir)
    row = df[(df["MUN"] == "000") & (df["LOC"] == "0000")].copy()
    row["GEOID"] = row["ENTIDAD"]
    return row.reset_index(drop=True)


def fetch_municipality_totals(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every municipality-total row (``MUN!="000"``, ``LOC=="0000"``) from ITER.

    Returns:
        DataFrame with a ``GEOID`` column (5-digit ``ENTIDAD``+``MUN``, matching
        the Marco Geoestadistico ``CVEGEO`` for municipality boundaries)
        plus every raw ITER column.
    """
    df = _read_iter(state, data_dir)
    rows = df[(df["MUN"] != "000") & (df["LOC"] == "0000")].copy()
    rows["GEOID"] = rows["ENTIDAD"] + rows["MUN"]
    return rows.reset_index(drop=True)


def _resageburb_raw_dir(data_dir: Optional[str] = None) -> Path:
    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "resageburb"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def download_resageburb_csv(state: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) and extract the RESAGEBURB CSV for one state.

    Args:
        state: State code, name, or abbreviation.
        data_dir: Base directory for the raw file cache. Defaults to
            :data:`pycensus.mexico.constants.DEFAULT_DATA_DIR`.

    Returns:
        Path to the extracted
        ``conjunto_de_datos_ageb_urbana_{state}_cpv2020.csv`` file.

    Raises:
        requests.HTTPError: If the download fails.
        FileNotFoundError: If the zip doesn't contain the expected CSV
            (would indicate INEGI changed the file layout).
    """
    state_code = utils.state_code(state)
    raw_dir = _resageburb_raw_dir(data_dir)

    csv_path = raw_dir / f"resageburb_{state_code}.csv"
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path

    url = constants.CENSUS_2020_URLS["resageburb_template"].format(state=state_code)
    zip_path = raw_dir / f"resageburb_{state_code}.zip"

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)

    with zipfile.ZipFile(zip_path) as zf:
        candidates = [
            n for n in zf.namelist()
            if n.endswith(".csv") and "conjunto_de_datos_ageb" in n
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No 'conjunto_de_datos_ageb*.csv' found inside {zip_path} -- "
                f"INEGI may have changed the RESAGEBURB zip layout"
            )
        with zf.open(candidates[0]) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return csv_path


def _read_resageburb(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    csv_path = download_resageburb_csv(state, data_dir)
    # Some states' RESAGEBURB CSVs carry a UTF-8 BOM stuck to the first
    # column header. Decoded byte-for-byte as latin-1, the 3-byte UTF-8 BOM
    # (EF BB BF) becomes the 3 separate characters "ï»¿" prepended to
    # "ENTIDAD" -- NOT the single U+FEFF BOM codepoint a naive `.lstrip("﻿")`
    # would expect (verified live 2026-08-20: states 16/18/32 have this
    # prefix, state 14 doesn't). Because the BOM changes the literal column
    # name, passing `dtype={"ENTIDAD": str, ...}` to `read_csv` silently
    # fails to constrain that one column on affected files -- it's read
    # with pandas' default int inference instead, which would lose a
    # leading-zero state code (e.g. "01") once renamed. Read fully
    # unconstrained first, rename off the BOM, then force every id column
    # to zero-preserving string dtype explicitly.
    df = pd.read_csv(csv_path, encoding="latin-1", dtype=str)
    df.columns = [c.lstrip("ï»¿") for c in df.columns]
    for col in ("ENTIDAD", "MUN", "LOC", "AGEB", "MZA"):
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


def fetch_ageb_totals(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every AGEB-total row (``AGEB!="0000"``, ``MZA=="000"``) from RESAGEBURB.

    Returns:
        DataFrame with a ``GEOID`` column (13-digit ``ENTIDAD``+``MUN``+
        ``LOC``+``AGEB``, matching the Marco Geoestadistico urban-AGEB
        ``CVEGEO``) plus every raw RESAGEBURB column.
    """
    df = _read_resageburb(state, data_dir)
    rows = df[(df["AGEB"] != "0000") & (df["MZA"] == "000")].copy()
    rows["GEOID"] = rows["ENTIDAD"] + rows["MUN"] + rows["LOC"] + rows["AGEB"]
    return rows.reset_index(drop=True)


def fetch_block_totals(state: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch every block (manzana) row (``MZA!="000"``) from RESAGEBURB.

    Note:
        Live-verified end-to-end against the real block boundary join
        2026-08-22 (see :mod:`pycensus.mexico.geography` module
        docstring for the match-rate/population cross-check evidence).

    Returns:
        DataFrame with a ``GEOID`` column (16-digit ``ENTIDAD``+``MUN``+
        ``LOC``+``AGEB``+``MZA``, matching the Marco Geoestadistico block
        ``CVEGEO``) plus every raw RESAGEBURB column.
    """
    df = _read_resageburb(state, data_dir)
    rows = df[df["MZA"] != "000"].copy()
    rows["GEOID"] = rows["ENTIDAD"] + rows["MUN"] + rows["LOC"] + rows["AGEB"] + rows["MZA"]
    return rows.reset_index(drop=True)


__all__ = [
    "download_iter_csv",
    "fetch_state_totals",
    "fetch_municipality_totals",
    "download_resageburb_csv",
    "fetch_ageb_totals",
    "fetch_block_totals",
]
