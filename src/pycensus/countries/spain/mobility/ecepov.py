"""INE ECEPOV-2021 (Encuesta de Caracteristicas Esenciales de la Poblacion y las Viviendas): persons aged 16+ by main means of transport to
their place of work or study -- municipalities of more than 50,000 inhabitants and provincial capitals (table 55377), provinces (table 55371).
No finer geography is published (the survey is a sample of the 2021 census population).

    from pycensus.countries.spain.mobility import ecepov
    ecepov.municipalities()   # {municipality name as INE writes it: {total, public, private, walk, other, transit_share, car_share, walk_share}}
    ecepov.provinces()        # same per province ("Total Nacional" included)
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

URL = "https://www.ine.es/jaxi/files/tpx/es/csv_bdsc/{t}.csv"
TABLES = {"muni": 55377, "prov": 55371}
MODES = {"Público": "public", "Particular": "private", "Andando": "walk", "De empresa u otro medio": "other", "Total": "total"}


def norm_name(s: str) -> str:
    """Comparable municipality name: article moved to the front (``Rozas, Las`` -> ``las rozas``), ASCII, lower case.

    Args:
        s: Municipality name.

    Returns:
        The normalised name.
    """
    s = str(s).strip()
    m = re.match(r"^(.*), (El|La|Los|Las|L'|Les|Lo|Els|A|O|As|Os|Es|Sa|Ses)$", s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s.replace("/", " ")).strip()


def _cache(cache_dir: Optional[str]) -> Path:
    from ....cache import default_cache_dir

    d = (Path(cache_dir) if cache_dir else Path(default_cache_dir())) / "spain" / "ine_ecepov"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _table(t: int, cache_dir: Optional[str] = None) -> pd.DataFrame:
    f = _cache(cache_dir) / f"ecepov2021_{t}.csv"
    if not f.is_file():
        import requests

        r = requests.get(URL.format(t=t), timeout=120)
        r.raise_for_status()
        f.write_bytes(r.content)
    d = pd.read_csv(f, sep=";", encoding="utf-8-sig", dtype=str)
    d = d[(d["Edad"] == "Total") & (d["Sexo"] == "Ambos Sexos")]
    d["v"] = pd.to_numeric(d["Total"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
    return d


def _entries(d: pd.DataFrame, key: str) -> dict:
    out = {}
    for name, g in d.groupby(key):
        c = {MODES[m]: float(v) for m, v in zip(g["Medio de transporte"], g["v"]) if m in MODES and pd.notna(v)}
        tot = c.get("total") or sum(c.get(k, 0.0) for k in ("public", "private", "walk", "other"))
        if not tot:
            continue
        out[name] = {**{k: round(c.get(k, 0.0)) for k in ("total", "public", "private", "walk", "other")},
                     "transit_share": round(c.get("public", 0.0) / tot, 4), "car_share": round(c.get("private", 0.0) / tot, 4),
                     "walk_share": round(c.get("walk", 0.0) / tot, 4)}
    return out



def municipalities(cache_dir: Optional[str] = None) -> dict:
    """ECEPOV commuting figures of the municipalities in the survey table.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        ``{normalised name: figures}``.
    """
    return _entries(_table(TABLES["muni"], cache_dir), "Municipios")


def provinces(cache_dir: Optional[str] = None) -> dict:
    """ECEPOV commuting figures of the provinces.

    Args:
        cache_dir: Cache folder; ``None`` = the pycensus cache.

    Returns:
        ``{normalised name: figures}``.
    """
    return _entries(_table(TABLES["prov"], cache_dir), "Provincias")
