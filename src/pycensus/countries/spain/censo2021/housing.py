"""Census 2021 housing columns per census section from the INE SDC21 API.

Technical aspects:
    The API cuts a request off after about two minutes. At section level only the
    two-category dwelling-use cross and the household-size average finish in time;
    tenure, year built, floor space and building type finish only at district level
    (``ID_RESIDENCIA_N4``, the first 7 digits of the 10-digit section code), so those
    shares are district-native and repeated on every section of the district.
    Average floor space and dwelling age (``MEDIA_*``) come back empty at every level.
    Variable names come from https://www.ine.es/censos2021/SDC21_variables_disponibles.xlsx.
"""

from __future__ import annotations
from pycensus.cache import get_data_dir

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from .api import CENSO2021_API_URL, fetch_section_breakdown

DISTRICT_CROSSES = {
    "ID_TENEN_VIV": ("tenure", {"En propiedad": "Owned", "En alquiler": "Rented"}),
    "ID_ANO_CONS_GR11": ("built", None),
    "ID_SUP_VIV": ("area", None),
    "ID_TIPO_EDIF_VIV": ("bldg", None),
}
_DISTRICT_RE = re.compile(r"(\d{7})")


def _district_cross(table: str, metric: str, variable: str, cache: Path) -> pd.DataFrame:
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        r = requests.post(CENSO2021_API_URL, json={"tabla": table, "idioma": "ES", "metrica": [metric],
                          "variables": ["ID_RESIDENCIA_N4", variable]}, timeout=900)
        r.raise_for_status()
        payload = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload))
    rows = []
    for row in payload.get("data", []):
        m = _DISTRICT_RE.search(str(row.get("ID_RESIDENCIA_N4", "")))
        if m:
            rows.append((m.group(1), row.get(variable), row.get(metric)))
    return pd.DataFrame(rows, columns=["district", "category", "value"])


def _share_table(df: pd.DataFrame, prefix: str, wanted: Optional[dict] = None) -> pd.DataFrame:
    piv = df.pivot_table(index="district", columns="category", values="value", aggfunc="sum")
    total = piv.sum(axis=1)
    out = pd.DataFrame(index=piv.index)
    for cat in piv.columns:
        if wanted is not None and cat not in wanted:
            continue
        name = wanted[cat] if wanted else re.sub(r"[^0-9A-Za-z]+", "_", str(cat)).strip("_")
        out[f"{prefix}{name}_share"] = (piv[cat] / total).astype("float32")
    return out


def load_section_housing(data_dir: Optional[str] = None) -> pd.DataFrame:
    """One row per 10-digit section (``GEOID``): dwelling use, household size, district-level tenure/age/area/building shares.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
    """
    root = get_data_dir("spain", data_dir) / "censo2021_housing"
    use = fetch_section_breakdown("viv.fam", "SVIVIENDAS", "ID_TIPO_VIV_USO", root / "viv_use_n5.json")
    piv = use.pivot_table(index="GEOID", columns="category", values="value", aggfunc="sum")
    out = pd.DataFrame(index=piv.index)
    out["dwellings"] = piv.sum(axis=1)
    out["dwellings_main_share"] = piv.get("Viviendas principales") / out["dwellings"]
    out["dwellings_secondary_or_empty_share"] = piv.get("Viviendas no principales") / out["dwellings"]
    size = fetch_section_breakdown("hog", "STAM_HOG", None, root / "hog_size_n5.json").set_index("GEOID")["value"]
    out["household_size_mean"] = size.groupby(level=0).first()
    out = out.reset_index().rename(columns={"index": "GEOID"})
    out["district"] = out["GEOID"].str[:7]
    parts = []
    for var, (prefix, wanted) in DISTRICT_CROSSES.items():
        table, metric = ("viv.fam", "SVIVIENDAS") if var == "ID_ANO_CONS_GR11" else ("hog", "SHOGARES")
        d = _district_cross(table, metric, var, root / f"{prefix}_n4.json")
        pre = {"tenure": "tenure_", "built": "built_", "area": "floor_area_", "bldg": "building_"}[prefix]
        if prefix == "tenure":
            sh = _share_table(d, "", wanted).rename(columns={"Owned_share": "tenure_owned_share", "Rented_share": "tenure_rented_share"})
            other = 1 - sh.sum(axis=1)
            sh["tenure_other_share"] = other.clip(lower=0).astype("float32")
        else:
            sh = _share_table(d, pre)
        parts.append(sh)
    dist = pd.concat(parts, axis=1).reset_index()
    return out.merge(dist, on="district", how="left")


__all__ = ["load_section_housing"]
