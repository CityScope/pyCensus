"""Hamburg Sozialmonitoring Integrierte Stadtteilentwicklung (Behoerde fuer Stadtentwicklung und Wohnen, with Statistikamt Nord and IfBQ).

Source: Transparenzportal Hamburg, dataset "Sozialmonitoring Integrierte Stadtteilentwicklung Hamburg - Karte Gesamtindex" (CSV with WKT geometry, EPSG:4326),
``https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/sozialmonitoring_csv_232639_snap_5.zip``. One row per Statistisches Gebiet (>= 300 residents) and
reporting year, with the social status class (``sehr niedrig`` ... ``hoch``) and dynamics class (``negativ``/``stabil``/``positiv``). The status index
combines the unemployment, benefit-recipient (SGB II/XII), child-poverty and single-parent shares, so it is the sub-municipal poverty/deprivation proxy of Hamburg.

Output columns (latest reporting year): ``socialStatusIndex`` (1 = very low status ... 4 = high) and ``socialDynamicsIndex`` (-1 / 0 / +1), plus ``statgeb``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkt

from pycensus.cache import get_data_dir

URL = "https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/sozialmonitoring_csv_232639_snap_5.zip"
CSV = "de_hh_up_sozialmonitoring_EPSG_4326.csv"
STATUS = {"sehr niedrig": 1, "niedrig": 2, "mittel": 3, "hoch": 4}
DYNAMICS = {"negativ": -1, "stabil": 0, "positiv": 1}
ATTRIBUTION = "Sozialmonitoring Integrierte Stadtteilentwicklung Hamburg, Freie und Hansestadt Hamburg (Transparenzportal), Datenlizenz Deutschland - Namensnennung 2.0."


def _csv(data_dir: Optional[str]) -> Path:
    raw = get_data_dir("germany", data_dir) / "raw" / "hamburg_sozialmonitoring"
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / CSV
    if not path.exists():
        r = requests.get(URL, timeout=900)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            path.write_bytes(zf.read(CSV))
    return path


def load(aoi=None, data_dir: Optional[str] = None) -> gpd.GeoDataFrame:
    """Hamburg's social monitoring indices (status and dynamics) by statistical area, latest report year.

    Args:
        aoi: Area of interest (GeoDataFrame).
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame (EPSG:4326).
    """
    df = pd.read_csv(_csv(data_dir), sep=";", encoding="utf-8-sig",
                     usecols=["berichtsjahr", "statgeb", "statusindex", "dynamikindex", "geom"])
    df = df[df["berichtsjahr"] == df["berichtsjahr"].max()].copy()
    df["socialStatusIndex"] = df["statusindex"].str.lower().map(STATUS)
    df["socialDynamicsIndex"] = df["dynamikindex"].str.lower().map(DYNAMICS)
    g = gpd.GeoDataFrame(df[["statgeb", "socialStatusIndex", "socialDynamicsIndex"]], geometry=df["geom"].map(wkt.loads), crs=4326)
    if aoi is not None:
        g = g[g.intersects(aoi.to_crs(4326).union_all())]
    return g.reset_index(drop=True)
