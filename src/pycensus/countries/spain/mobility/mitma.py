"""MITMA open mobility data (mobile-phone study, ``movilidad-opendata.mitma.es``) -> distance and long-distance columns per INE census section.

Public files carry no mode of transport (see README); they do carry trips, great-circle distance bands and trip-kilometres for all of Spain
by MITMA district (``zonificacion_distritos``). A trip is attributed to the *home* district of the traveller: the origin when the origin
activity is ``casa``, else the destination when the destination activity is ``casa``. Trips between two non-home activities are left out.
Values are per day-average of the chosen dates divided by the district's INE population, then given to every census section of the district
(``relacion_ine_zonificacionMitma.csv`` maps sections to districts exactly, no spatial overlay needed).

Columns (``year`` = year of the dates): ``{year}_trips_per_person``, ``{year}_distance_km_per_person``, ``{year}_long_distance_trip_share``
(distance band >50 km), ``{year}_long_distance_km_share``, ``{year}_trip_share_{band}`` for the published bands 0.5-2, 2-10, 10-50 and >50 km.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from pycensus.cache import default_cache_dir

from .._http import download

BASE = "https://movilidad-opendata.mitma.es"
DAY = BASE + "/estudios_basicos/por-distritos/viajes/ficheros-diarios/{ym}/{ymd}_Viajes_distritos.csv.gz"
REL = BASE + "/zonificacion/relacion_ine_zonificacionMitma.csv"
POP = BASE + "/zonificacion/zonificacion_distritos/poblacion_distritos.csv"
BANDS = ("0.5-2", "2-10", "10-50", ">50")
# typical weekdays (Wednesdays outside holidays) of March, June and October
DEFAULT_DATES = {2024: ("20240313", "20240612", "20241016")}


def _day_table(path: Path) -> pd.DataFrame:
    """Home-based trips and trip-km per (home district, distance band) for one daily file."""
    parts = []
    reader = pd.read_csv(path, sep="|", chunksize=2_000_000, dtype=str,
                         usecols=["origen", "destino", "distancia", "actividad_origen", "actividad_destino", "viajes", "viajes_km"])
    for ch in reader:
        home = ch["origen"].where(ch["actividad_origen"] == "casa", ch["destino"].where(ch["actividad_destino"] == "casa"))
        ch = ch.assign(zone=home).dropna(subset=["zone"])
        ch["viajes"] = pd.to_numeric(ch["viajes"], errors="coerce")
        ch["viajes_km"] = pd.to_numeric(ch["viajes_km"], errors="coerce")
        parts.append(ch.groupby(["zone", "distancia"])[["viajes", "viajes_km"]].sum())
    return pd.concat(parts).groupby(level=[0, 1]).sum()


def load_sections(year: int = 2024, dates: Optional[Iterable[str]] = None, cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Distance / long-distance columns indexed by INE census section (``CUSEC`` 10 digits).

    Args:
        year: Survey year.
        dates: Days averaged (``YYYYMMDD``); ``None`` = the defaults.
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per census section.
    """
    dates = tuple(dates or DEFAULT_DATES[year])
    root = Path(cache_dir or default_cache_dir()) / "spain_mitma"
    rel = pd.read_csv(download(REL, root / "relacion.csv"), sep="|", dtype=str)
    pop = pd.read_csv(download(POP, root / "poblacion_distritos.csv"), sep="|", header=None, names=["zone", "pop"], dtype={"zone": str})
    total = sum((_day_table(download(DAY.format(ym=f"{d[:4]}-{d[4:6]}", ymd=d), root / f"{d}.csv.gz")) for d in dates)) / len(dates)
    t = total.reset_index()
    t["band"] = t["distancia"].where(t["distancia"].isin(BANDS), None)
    by_zone = t.groupby("zone")[["viajes", "viajes_km"]].sum()
    shares = t.pivot_table(index="zone", columns="distancia", values="viajes", aggfunc="sum").reindex(columns=BANDS).fillna(0.0)
    long_t = t[t["distancia"] == ">50"].groupby("zone")[["viajes", "viajes_km"]].sum().reindex(by_zone.index).fillna(0.0)
    out = pd.DataFrame(index=by_zone.index)
    pp = pop.drop_duplicates("zone").set_index("zone")["pop"].reindex(out.index)
    out[f"{year}_trips_per_person"] = by_zone["viajes"] / pp
    out[f"{year}_distance_km_per_person"] = by_zone["viajes_km"] / pp
    out[f"{year}_long_distance_trip_share"] = long_t["viajes"] / by_zone["viajes"]
    out[f"{year}_long_distance_km_share"] = long_t["viajes_km"] / by_zone["viajes_km"]
    for b in BANDS:
        out[f"{year}_trip_share_{b}"] = shares[b] / by_zone["viajes"]
    out = out.replace([float("inf")], float("nan"))
    sec = rel.set_index("seccion_ine")["distrito_mitma"]
    return out.reindex(sec.values).set_axis(sec.index)


COMMUTE = BASE + "/estudios_completos/por-distritos/movilidad_obligada/meses-completos/{ym}_Movilidad_obligada_distritos.csv.gz"
# `recurrencia` (methodology report v8, 4.3.6): number of the 14 typical days of the month on which a person makes a trip origin -> destination,
# counted separately for EVERY origin-destination pair. A person with several regular destinations appears once per pair, so counts are
# person-pair counts, not people. The bins are the published ones; 5-7 days straddles 3 days a week (5-6 days <= 3/week, 7 days = 3.5/week).
RECURRENCE_BINS = ("1-2", "3-4", "5-7", "8-10", "11-13", "14")


def load_commuting(year: int = 2024, months: Iterable[str] = ("202403", "202406", "202410"), cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Regular trips from the home district, by how often, on census sections.

    Columns: ``{year}_regular_flows_{bin}`` for all six published bins 1-2, 3-4, 5-7, 8-10, 11-13, 14 (person-pair counts per month, split evenly among
    the district's sections; 1-2 days is incidental travel), ``{year}_regular_flows_share_{bin}`` (bins 3-4 .. 14 over the regular flows, 3+ days),
    ``{year}_regular_flows_up_to_3_days_week_share_{min,est,max}``
    (pairs with 3-6 of 14 days over all pairs with 3+ days; est counts 2/3 of the 5-7 bin, min counts none of it, max all of it).

    Args:
        year: Survey year.
        months: Months averaged (``YYYYMM``).
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        One row per census section.
    """
    root = Path(cache_dir or default_cache_dir()) / "spain_mitma"
    rel = pd.read_csv(download(REL, root / "relacion.csv"), sep="|", dtype=str)
    parts = []
    for ym in months:
        f = download(COMMUTE.format(ym=ym), root / f"obligada_{ym}.csv.gz")
        d = pd.read_csv(f, sep="|", dtype={"origen": str, "destino": str, "recurrencia": str}, usecols=["origen", "recurrencia", "personas"])
        parts.append(d.groupby(["origen", "recurrencia"])["personas"].sum())
    b = (sum(parts) / len(parts)).unstack("recurrencia").reindex(columns=RECURRENCE_BINS).fillna(0.0)
    reg = b[["3-4", "5-7", "8-10", "11-13", "14"]]
    n = reg.sum(axis=1)
    out = pd.DataFrame({f"{year}_regular_flows_{c}": b[c] for c in RECURRENCE_BINS})   # all six bins, counts (the 1-2 bin is incidental travel)
    for c in reg.columns:
        out[f"{year}_regular_flows_share_{c}"] = reg[c] / n   # share of the regular (3+ days) flows
    out[f"{year}_regular_flows_up_to_3_days_week_share_min"] = reg["3-4"] / n
    out[f"{year}_regular_flows_up_to_3_days_week_share_est"] = (reg["3-4"] + reg["5-7"] * 2 / 3) / n
    out[f"{year}_regular_flows_up_to_3_days_week_share_max"] = (reg["3-4"] + reg["5-7"]) / n
    sec = rel.set_index("seccion_ine")["distrito_mitma"]
    res = out.reindex(sec.values).set_axis(sec.index)
    k = sec.map(sec.value_counts())
    for c in res.columns:
        if c.startswith(f"{year}_regular_flows_") and "share" not in c:
            res[c] = res[c] / k
    return res
