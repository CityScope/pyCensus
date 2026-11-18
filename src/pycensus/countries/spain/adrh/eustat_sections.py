"""Eustat population by census section (sex, age groups, foreign nationals) for the three Basque territories (1 Jan 2025 tables).

Source: ``https://www.eustat.eus/elementos/tbl00114{33,34,35}_i.html`` (Araba/Álava, Gipuzkoa, Bizkaia; one HTML table each). A section's
GEOID is the 10-digit INE code: province(2) + municipality(3) + district(2) + section(3). Counts are derived from the published
shares (percentages) and the population total; global-schema names are bare, the others prefixed ``ine_`` (the Spanish census join prefix).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import io
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

TABLES = {"01": "0011433", "20": "0011434", "48": "0011435"}


def load_sections(provinces: Iterable[str], data_dir: Optional[str] = None) -> pd.DataFrame:
    """Eustat income tables by census section for the Basque provinces (which ADRH does not cover).

    Args:
        provinces: 2-digit province codes.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per section.
    """
    frames = []
    raw = get_data_dir("spain", data_dir) / "raw" / "eustat_sections"
    raw.mkdir(parents=True, exist_ok=True)
    for prov in provinces:
        tid = TABLES.get(prov)
        if tid is None:
            continue
        path = raw / f"tbl{tid}.html"
        if not path.exists():
            r = requests.get(f"https://www.eustat.eus/elementos/tbl{tid}_i.html", timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
        t = pd.read_html(io.StringIO(path.read_text(encoding="utf-8", errors="ignore")))[0]
        t.columns = ["cod", "municipality", "dist", "sec", "total", "men", "women", "sex_ratio", "p0_19", "p20_64", "p65", "eu27", "restf"]
        t = t.iloc[1:].copy()
        t["cod"] = t["cod"].ffill(); t["dist"] = t["dist"].ffill()
        t = t[t["sec"].notna() & (t["sec"].astype(str) != "000")]
        for c in ("total", "men", "women", "sex_ratio", "p0_19", "p20_64", "p65", "eu27", "restf"):
            t[c] = pd.to_numeric(t[c], errors="coerce")
        geoid = prov + t["cod"].astype(str).str.zfill(3) + t["dist"].astype(str).str.zfill(2) + t["sec"].astype(str).str.zfill(3)
        out = pd.DataFrame({"GEOID": geoid.values, "malePopulation": t["men"].values, "femalePopulation": t["women"].values,
                            "over65Population": (t["total"] * t["p65"] / 100).values,
                            "ine_population0to19": (t["total"] * t["p0_19"] / 100).values,
                            "ine_population20to64": (t["total"] * t["p20_64"] / 100).values,
                            "ine_foreignEU27Population": (t["total"] * t["eu27"] / 100).values,
                            "ine_foreignOtherPopulation": (t["total"] * t["restf"] / 100).values})
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({"GEOID": []})
