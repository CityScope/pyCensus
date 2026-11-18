"""INEGI Censo de Poblacion y Vivienda 2020, Cuestionario Ampliado, "Movilidad cotidiana" tabulado 22: workers by means of transport to
work, per municipality (the finest level INEGI publishes the question at; the sample design does not support AGEB estimates).

One workbook per state (``cpv2020_a_<abbr>_10_movilidad_cotidiana.xlsx``), downloaded once into ``<cache>/mexico/inegi_movilidad/``.
Several means may be reported per person, so the published percentages add to more than 100 %; counts here are commuters x
percentage (persons using the mode).

    from pycensus.countries.mexico import inegi_movilidad
    inegi_movilidad.state_table("14")          # DataFrame: GEOID (5 digits), name, counts
    inegi_movilidad.load(aoi=aoi)              # + municipality geometry (INEGI Marco Geoestadistico)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd

from pycensus.canonical import apply_canonical_names

from ....schema import ColumnSchema

_DATA = json.loads((Path(__file__).parent.parent / "schema" / "inegi_movilidad_schema.json").read_text(encoding="utf-8"))
SCHEMA = ColumnSchema(prefix="inegimov")
for _f in _DATA["features"]:
    SCHEMA.add(name=_f["feature_name"], codes=_f["codes"], relative_to=None, agg="sum", weight_by=None)
_COLS = ["total", "caminando", "bicicleta", "camion", "vehiculo", "otro", "no_especificado"]


def _dir(cache_dir: Optional[str]) -> Path:
    from .... import cache as cache_store

    base = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    d = base / "mexico" / "inegi_movilidad"
    d.mkdir(parents=True, exist_ok=True)
    return d


# INEGI's own file abbreviations of the 2020 tabulados (verified for all 32 states, 2026-11-13)
FILE_ABBR = dict(zip([f"{i:02d}" for i in range(1, 33)], "ags bc bcs cam coa col chs chh cdmx dgo gto gro hgo jal mex mic mor nay nl oax pue qro qroo slp sin son tab tam tla ver yuc zac".split()))


def _abbr(state: str) -> str:
    from .. import utils

    return FILE_ABBR[utils.state_code(state)]


def state_table(state: str, cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Municipal rows of tabulado 22 (sex = Total, estimator = Valor) for one state, as counts.

    Args:
        state: State name, abbreviation or code.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per municipality.
    """
    import openpyxl

    from .. import utils

    code = utils.state_code(state)
    d = _dir(cache_dir)
    pq = d / f"movilidad_trabajo_{code}.parquet"
    if pq.is_file():
        return pd.read_parquet(pq)
    url = _DATA["source_url"].format(abbr=_abbr(code))
    x = d / url.rsplit("/", 1)[1]
    if not x.is_file() or x.stat().st_size < 100_000:
        import requests

        r = requests.get(url, timeout=300)
        r.raise_for_status()
        if "spreadsheet" not in r.headers.get("content-type", "") and not r.content[:2] == b"PK":
            raise RuntimeError(f"INEGI returned no workbook for {url}")
        x.write_bytes(r.content)
    ws = openpyxl.load_workbook(x, read_only=True)["22"]
    rows = []
    for r in ws.iter_rows(values_only=True):
        if len(r) < 11 or r[2] != "Total" or r[3] != "Valor" or not isinstance(r[1], str) or r[1] == "Total":
            continue
        mun, name = r[1].split(" ", 1)
        rows.append([f"{code}{mun.zfill(3)}", name, *[float(v or 0) for v in r[4:11]]])
    t = pd.DataFrame(rows, columns=["GEOID", "name", *_COLS])
    n = t["total"]
    out = pd.DataFrame({"GEOID": t["GEOID"], "name": t["name"]})
    for f in _DATA["features"]:
        c = f["codes"][0]
        out[SCHEMA.column_label(f["feature_name"])] = n if c == "total" else n * t[c] / 100.0
    out.to_parquet(pq)
    return out


def national(states: Optional[List[str]] = None, cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Municipal mode-to-work counts of several states (all by default).

    Args:
        states: State codes; ``None`` = all.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per municipality.
    """
    from .. import constants

    return pd.concat([state_table(s, cache_dir) for s in (states or list(constants.STATE_CODES))], ignore_index=True)


def load(aoi: Optional[gpd.GeoDataFrame] = None, states: Optional[List[str]] = None, level: str = "municipality",
         cache_dir: Optional[str] = None, data_dir: Optional[str] = None, **_) -> gpd.GeoDataFrame:
    """Municipal counts with INEGI municipality geometry, for the states of ``aoi`` (or ``states``).

    Args:
        aoi: Area of interest (GeoDataFrame).
        states: State codes (instead of ``aoi``).
        level: Only ``"municipality"``.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        **_: Ignored.

    Raises:
        NotImplementedError: For another level.
        ValueError: Without ``aoi`` or ``states``.
    """
    from .. import geography

    if level != "municipality":
        raise NotImplementedError(f"INEGI publishes means of transport to work per municipality only, not {level!r}")
    if states is None:
        if aoi is None:
            raise ValueError("Either 'states' or 'aoi' is required")
        states = geography.states_in_aoi(aoi)
    parts = []
    for s in states:
        t = state_table(s, cache_dir)
        g = geography.load_boundaries("municipality", s, data_dir=data_dir).to_crs(4326)
        parts.append(g[["GEOID", "geometry"]].merge(t, on="GEOID", how="inner"))
    res = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
    if aoi is not None:
        res = res[res.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return apply_canonical_names(res, SCHEMA)
