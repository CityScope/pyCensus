"""IMEPLAN Encuesta Origen-Destino 2023 of the Guadalajara metropolitan area: commuters by main means of transport, per AGEB of residence.

The survey (17,901 dwellings, 154,662 trips, January-May 2023) is published with its expansion factors in the CentroFuturoCiudades/eodgdl
repository; the dwelling and trip tables are downloaded once into ``<cache>/mexico/imeplan_eod/``. A commuter is a surveyed person with a
work trip (purpose ``Trabajar``); the mode is the main means of their first work trip of the day; the person sits at their dwelling's AGEB.
Counts are expanded with the trip's factor; ``sampleCommuters`` keeps the surveyed number (a few per AGEB -- the survey is designed for its
64 centralidades, so AGEB shares are noisy and a fit should weight them by the sample, not the expanded count).

    from pycensus.census.countries.mexico import imeplan_eod
    imeplan_eod.table()                 # DataFrame: GEOID (13-digit AGEB), counts
    imeplan_eod.load(aoi=aoi)           # + AGEB geometry (the survey's 2020 AGEBs, INEGI urban + rural AGEBs)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from pycensus.canonical import apply_canonical_names
from pycensus.schema import ColumnSchema

_DATA = json.loads((Path(__file__).parent.parent / "schema" / "imeplan_eod_schema.json").read_text(encoding="utf-8"))
SCHEMA = ColumnSchema(prefix="imepeod")
for _f in _DATA["features"]:
    SCHEMA.add(name=_f["feature_name"], codes=_f["codes"], relative_to=None, agg="sum", weight_by=None)
FILES = ("IMEPLAN_Base_Viviendas_Master.csv", "IMEPLAN_Base_Viajes_Master.csv")
ZONES = "RELACION_AGEBS-ZONA_con_datos_censales.parquet"   # the survey's own 2020 urban AGEB polygons (CVEGEO_EOD)
STATE = "14"   # Jalisco


def _dir(cache_dir: Optional[str]) -> Path:
    from pycensus import cache as cache_store

    base = Path(cache_dir) if cache_dir else Path(cache_store.default_cache_dir())
    d = base / "mexico" / "imeplan_eod"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _raw(name: str, cache_dir: Optional[str]) -> pd.DataFrame:
    p = _dir(cache_dir) / name
    if not p.is_file() or p.stat().st_size < 100_000:
        import requests

        r = requests.get(_DATA["source_url"].format(file=name), timeout=600)
        r.raise_for_status()
        p.write_bytes(r.content)
    return pd.read_csv(p, encoding="latin1", low_memory=False)


LEVELS = ("ageb", "microzone", "centralidad")   # finest first: AGEB of residence, the survey's 601 microzones (MZONA), its 81 centralidades
_ZONE_KEY = {"microzone": "MZONA", "centralidad": "ID_CENTRAL"}


def _zones(cache_dir: Optional[str]) -> gpd.GeoDataFrame:
    p = _dir(cache_dir) / ZONES
    if not p.is_file() or p.stat().st_size < 100_000:
        import requests

        r = requests.get(_DATA["source_url"].format(file=ZONES), timeout=600)
        r.raise_for_status()
        p.write_bytes(r.content)
    z = gpd.read_parquet(p)
    z["CVEGEO_EOD"] = z["CVEGEO_EOD"].astype(str).str.strip()
    return z.set_crs(4326, allow_override=True)


def table(cache_dir: Optional[str] = None, level: str = "ageb") -> pd.DataFrame:
    """Commuter counts per AGEB of residence, or per survey zone (microzone / centralidad: the AGEBs' commuters summed by the survey's own
    AGEB-to-zone table; the 27 rural AGEBs are in no zone). Cached as parquet.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        level: ``"ageb"``, ``"microzone"`` or ``"centralidad"``.

    Returns:
        One row per unit with surveyed commuters: GEOID and the schema's counts.
    """
    if level != "ageb":
        t = table(cache_dir, "ageb")
        key = _zones(cache_dir).drop_duplicates("CVEGEO_EOD").set_index("CVEGEO_EOD")[_ZONE_KEY[level]]
        t = t.assign(GEOID=t["GEOID"].map(key)).dropna(subset=["GEOID"])
        t["GEOID"] = t["GEOID"].astype(int).astype(str)
        return t.groupby("GEOID", as_index=False).sum(numeric_only=True)
    pq = _dir(cache_dir) / "commute_ageb_2023.parquet"
    if pq.is_file():
        return pd.read_parquet(pq)
    viv, trips = (_raw(f, cache_dir) for f in FILES)
    home = viv.set_index("Folio Vivienda")["AGEB"]
    w = trips[trips["Motivo de su viaje"] == "Trabajar"].sort_values(["Folio Vivienda", "Folio Habitante", "Folio Viaje"])
    w = w.drop_duplicates(["Folio Vivienda", "Folio Habitante"])           # each commuter once: the first work trip of the day
    w = w.assign(GEOID=w["Folio Vivienda"].map(home), wt=pd.to_numeric(w["Ponderador"], errors="coerce").fillna(0.0))
    w = w.dropna(subset=["GEOID"])
    w["GEOID"] = w["GEOID"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)   # 13 characters urban, 9 rural AGEBs
    mode = w["Medio del viaje"].astype(str).str.strip()
    g = w.groupby("GEOID")
    out = pd.DataFrame(index=g.size().index)
    for f in _DATA["features"]:
        c = f["codes"]
        if c == ["#"]:
            v = g.size()
        elif c == ["*"]:
            v = g["wt"].sum()
        else:
            v = w[mode.isin(c)].groupby("GEOID")["wt"].sum()
        out[SCHEMA.column_label(f["feature_name"])] = v.reindex(out.index).fillna(0.0).astype(float)
    out = out.reset_index()
    out.to_parquet(pq)
    return out


def boundaries(cache_dir: Optional[str] = None, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """AGEB polygons of every surveyed AGEB: the survey's own 2020 urban AGEBs, then INEGI's urban and rural AGEB layers for the rest.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        data_dir: Folder of the raw INEGI boundary downloads; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame (EPSG:4326) with GEOID and geometry.
    """
    from pycensus.census.countries.mexico import geography

    z = _zones(cache_dir)[["CVEGEO_EOD", "geometry"]].rename(columns={"CVEGEO_EOD": "GEOID"})
    parts = [z]
    for lv in ("ageb", "ageb_rural"):
        parts.append(geography.load_boundaries(lv, STATE, data_dir=data_dir).to_crs(4326))
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
    return g.drop_duplicates("GEOID").reset_index(drop=True)   # first source wins


def load(aoi: Optional[gpd.GeoDataFrame] = None, level: str = "ageb", cache_dir: Optional[str] = None, data_dir: Optional[str] = None,
         **_) -> gpd.GeoDataFrame:
    """Commuter counts with the AGEB polygons (:func:`boundaries`), inside ``aoi``.

    Args:
        aoi: Area of interest (GeoDataFrame).
        level: ``"ageb"`` (urban and rural AGEBs of residence), ``"microzone"`` or ``"centralidad"`` (the survey's zones).
        cache_dir: Cache folder; ``None`` = the pycensus cache.
        data_dir: Folder of the raw boundary downloads; ``None`` = the pycensus cache.
        **_: Ignored.

    Returns:
        GeoDataFrame with global column names.

    Raises:
        NotImplementedError: For another level.
    """
    if level not in LEVELS:
        raise NotImplementedError(f"levels: {LEVELS}, not {level!r}")
    t = table(cache_dir, level)
    if level == "ageb":
        g = boundaries(cache_dir, data_dir)
    else:   # the zone = its AGEBs' polygons dissolved
        z = _zones(cache_dir)
        g = z.dissolve(by=_ZONE_KEY[level], as_index=False)[[_ZONE_KEY[level], "geometry"]]
        g["GEOID"] = g[_ZONE_KEY[level]].astype(int).astype(str)
        g = g[["GEOID", "geometry"]]
    res = gpd.GeoDataFrame(g.merge(t, on="GEOID", how="inner"), geometry="geometry", crs=4326)
    if aoi is not None:
        res = res[res.intersects(aoi.to_crs(4326).union_all())].reset_index(drop=True)
    return apply_canonical_names(res, SCHEMA)


__all__ = ["load", "table", "boundaries", "LEVELS"]
