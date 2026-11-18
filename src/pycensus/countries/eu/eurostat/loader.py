"""Loader for Eurostat regional statistics (NUTS 2 / NUTS 3), EU-wide, through the keyless dissemination API.

Technical aspects:
    The curated tables are the features of ``schema/eurostat_schema.json``: each carries its Eurostat dataset code,
    the filters that fix every dimension but ``geo``/``time``, the NUTS level it is published at and a scale (rates
    published in % are stored as 0-1 shares). :func:`load` fetches the requested features for the NUTS regions of the
    requested countries, keeps for each region the latest year with a value (the year is returned per feature as
    ``<feature>_year``) and joins them to the GISCO NUTS 2024 boundaries. Regions are matched by NUTS id; ids of other
    NUTS versions that do not exist in the 2024 boundaries are dropped (and counted in the returned ``attrs``).

    :func:`load_dataset` does the same for any Eurostat table and filters (not only the curated ones).

    Verified live 2026-11-17: Comunidad de Madrid (ES30) household disposable income 21,900 PPS per person (2022),
    unemployment 9.0 % (2024), passenger cars 614 per 1,000 (2024); Madrid NUTS 3 (ES300) GDP 47,900 PPS per person
    (2024).

    Resolution class: ``low`` (regions much larger than municipalities, :mod:`pycensus.resolution`): context columns
    only, never for regressions or the census tab.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Union

import geopandas as gpd
import pandas as pd

from .. import constants, geography
from .._schema import schema_json
from . import api

RESOLUTION = "low"
NUTS_YEAR = 2024


def tables() -> Dict[str, dict]:
    """The curated tables: ``{feature name: {"dataset", "filters", "nuts_level", "scale"}}``."""
    return {f["feature_name"]: f["eurostat"] for f in schema_json("eurostat")["features"]}


def _latest(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["value"])
    df = df.assign(year=pd.to_numeric(df["time"].str[:4], errors="coerce")).sort_values("year")
    return df.groupby("geo", as_index=False).last()[["geo", "value", "year"]]


def load_dataset(dataset: str, filters: Dict[str, str], nuts_level: int, countries: Union[str, Iterable[str]],
                 name: str = "value", scale: float = 1.0, year: Optional[int] = None, since: int = 2010,
                 data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Any Eurostat table on the NUTS regions of ``countries``.

    Args:
        dataset: Eurostat dataset code.
        filters: ``{dimension: code}`` fixing every dimension except ``geo`` and ``time``.
        nuts_level: NUTS level of the regions (0-3).
        countries: Eurostat or ISO2 code(s).
        name: output column name.
        scale: multiplier applied to the values (0.01 turns % into shares).
        year: a fixed year; ``None`` = the latest year with a value, per region.
        since: first year fetched when ``year`` is ``None``.
        data_dir: Root of the raw cache (boundaries).

    Returns:
        GeoDataFrame ``GEOID, country, name (region name), <name>, <name>_year, geometry`` (EPSG:4326).
    """
    regions = geography.nuts(nuts_level, countries, NUTS_YEAR, data_dir).rename(columns={"name": "region_name"})
    df = api.fetch(dataset, filters, since=year or since, geos=regions["GEOID"].tolist())
    if year:
        df = df[df["time"].str[:4] == str(year)]
    df = _latest(df)
    out = regions.merge(df.rename(columns={"geo": "GEOID", "value": name, "year": f"{name}_year"}), on="GEOID", how="left")
    out[name] = out[name] * scale
    return out


def load(countries: Union[str, Iterable[str]], features: Optional[List[str]] = None, level: Optional[int] = None,
         year: Optional[int] = None, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Curated Eurostat features on the NUTS regions of ``countries``.

    Args:
        countries: Eurostat or ISO2 code(s).
        features: feature names of :func:`tables` (default: every curated feature published at ``level``).
        level: NUTS level of the output (2 or 3). Features published at a coarser level are repeated on each finer
            region of it (a NUTS 2 rate copied to its NUTS 3 regions); finer features cannot be requested at a coarser
            level. Default: the finest level among the requested features.
        year: a fixed year; ``None`` = the latest year per region and feature.
        data_dir: Root of the raw cache.

    Returns:
        GeoDataFrame ``GEOID, country, region_name, <feature>, <feature>_year ..., geometry``.
    """
    tab = tables()
    feats = features or [f for f, t in tab.items() if level is None or t["nuts_level"] <= level]
    unknown = [f for f in feats if f not in tab]
    if unknown:
        raise ValueError(f"unknown Eurostat features {unknown}; curated: {sorted(tab)}")
    level = level if level is not None else max(tab[f]["nuts_level"] for f in feats)
    too_fine = [f for f in feats if tab[f]["nuts_level"] > level]
    if too_fine:
        raise ValueError(f"{too_fine} are published at a finer level than NUTS {level}")
    out = geography.nuts(level, countries, NUTS_YEAR, data_dir).rename(columns={"name": "region_name"})
    for f in feats:
        t = tab[f]
        part = load_dataset(t["dataset"], t["filters"], t["nuts_level"], countries, f, t["scale"], year, data_dir=data_dir)
        part = pd.DataFrame(part[["GEOID", f, f"{f}_year"]])
        if t["nuts_level"] < level:   # repeat the coarser region's value on its finer regions (NUTS ids nest by prefix)
            out["_k"] = out["GEOID"].str[: 2 + t["nuts_level"]]
            out = out.merge(part.rename(columns={"GEOID": "_k"}), on="_k", how="left").drop(columns="_k")
        else:
            out = out.merge(part, on="GEOID", how="left")
    return gpd.GeoDataFrame(out, crs=4326)


__all__ = ["RESOLUTION", "NUTS_YEAR", "tables", "load_dataset", "load"]
