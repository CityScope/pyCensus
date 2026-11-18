"""Hamburg election results at Wahlbezirk (Stimmbezirk) level + H3 res 8: Bundestag 23-02-2025, Buergerschaft 02-03-2025, Bezirksversammlungen 09-06-2024.

Sources (verified live 2026-10-25; Statistik Nord / Landeswahlleitung Hamburg, official final results; data licence dl-de/by-2.0):
  Buergerschaft 2025 (state)   https://www.wahlen-hamburg.de/B%C3%BCrgerschaftswahl_2025/ergebnis-download-land.csv  (+ Landesliste_F_Feldbezeichner.xlsx)
  Bundestag 2025 (national)    https://www.wahlen-hamburg.de/Bundestagswahl_2025/ergebnis-download.csv  (+ BTW2025_Feldbezeichner_Erst-_Zweitstimmen.xlsx)
  Bezirksversammlungen 2024 (municipal; Hamburg's 7 districts = municipal level)
                               https://www.wahlen-hamburg.de/bezirksversammlungswahlen_2024/ergebnis-download-bezirk.csv (+ Feldbezeichner_Download_2024_Bezirksstimmen.xlsx)
  Geometry: Wahlbezirke polygons (1,272, vintage 02-03-2025), WFS ``https://geodienste.hamburg.de/HH_WFS_Wahlen`` layer ``de.hh.up:wahlbezirke`` (Transparenzportal
  "Geodaten zu Wahlen von Hamburg"). ``wahlbezirksnummer`` == ``Erfassungsgebietsnummer`` (5 digits); 1,268/1,269 match (15001 = special district without polygon, 0 votes).
  The 2025 polygons are also used for Bundestag 2025 (same numbers) and Bezirksversammlung 2024 (all 1,268 numbers present; boundaries may differ slightly).
Votes: Bundestag = Zweitstimmen (Listenstimmen); Buergerschaft = Landesstimmen and Bezirksversammlung = Bezirksstimmen, party "Gesamtstimmen" (list + personal
  votes); voters have 5 votes there, so ``total_votes`` counts votes (not voters); shares are of valid votes. Invalid ballots are excluded, blank = 0.
Postal votes: published for Briefwahlbezirke without geography (~40 % of votes). They are allocated to the Stimmbezirke of the SAME Stadtteil in proportion to the
  Stimmbezirke's electors with Wahlschein (A2, fallback A). Electors = A of the Stimmbezirke; turnout = (voters in Stimmbezirke + allocated postal voters)/electors.
GEOID = 5-digit Wahlbezirk number as string. Hamburg Statistische Gebiete / Zensus 100 m grid are not used as keys (Wahlbezirke do not nest in them): use the H3 frame.
H3 res 8: area-weighted split of each Wahlbezirk (see ``pycensus.elections``).
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

from ....elections import build_frame, h3_weights, load_blocs, order_columns, to_h3

W = "https://www.wahlen-hamburg.de/"
WFS = ("https://geodienste.hamburg.de/HH_WFS_Wahlen?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=de.hh.up:wahlbezirke&SRSNAME=EPSG:4326"
       "&OUTPUTFORMAT=application/geo%2Bjson")
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
SRC = {  # (scope, year): (csv, fieldfile, key of valid-votes column, cast column)
    ("state", 2025): ("B%C3%BCrgerschaftswahl_2025/ergebnis-download-land.csv", "B%C3%BCrgerschaftswahl_2025/Landesliste_F_Feldbezeichner.xlsx",
                      "Stimmen gueltige (F)", "Waehler gesamt (B)"),
    ("national", 2025): ("Bundestagswahl_2025/ergebnis-download.csv", "Bundestagswahl_2025/BTW2025_Feldbezeichner_Erst-_Zweitstimmen.xlsx",
                         "Listenstimmen gueltige (F)", "Waehlende gesamt (B)"),
    ("municipal", 2024): ("bezirksversammlungswahlen_2024/ergebnis-download-bezirk.csv", "bezirksversammlungswahlen_2024/Feldbezeichner_Download_2024_Bezirksstimmen.xlsx",
                          "Stimmen gueltige (F)", "Waehler gesamt (B)"),
}


def _raw(data_dir: Optional[str]) -> Path:
    d = get_data_dir("germany", data_dir) / "raw" / "hamburg_elections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get(url: str, dest: Path) -> Path:
    if not dest.exists() or dest.stat().st_size < 500:
        r = requests.get(url, timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def _party_labels(path: Path, per_bezirk: bool = False):
    """Field -> party label from the Statistik Nord Feldbezeichner workbook. Bezirksversammlung lists differ per Bezirk (7 label columns 6,8,..,18 of the
    transposed sheet = Bezirke 1..7 = first digit of the Wahlbezirk number): then returns {bezirk_digit: {field: label}}."""
    fb = pd.read_excel(path, header=None).T
    out = {}
    for _, r in fb.iterrows():
        v = r.tolist()
        k = next((x for x in v[:7] if isinstance(x, str) and re.fullmatch(r"F\d+", x)), None)
        if not k:
            continue
        cand = [v[6 + 2 * i] for i in range(7)] if per_bezirk else [next((x for x in v if isinstance(x, str) and x != "…" and not re.fullmatch(r"F\d+", x)), None)]
        labs = []
        for lab in cand:
            m = re.search(r"\((.*)\)\s*$", lab if isinstance(lab, str) else "")
            labs.append((m.group(1) if m and "STIMMEN" in str(lab).upper() else lab).strip() if isinstance(lab, str) else None)
        out[k] = labs
    if per_bezirk:
        return {str(i + 1): {k: l[i] for k, l in out.items() if l[i]} for i in range(7)}
    return {k: l[0] for k, l in out.items()}


def load_wahlbezirke(data_dir: Optional[str] = None):
    """Hamburg's 2025 electoral districts (Wahlbezirke) from the city's WFS, one polygon per number.

    Args:
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        GeoDataFrame with ``GEOID`` and geometry.
    """
    import geopandas as gpd
    g = gpd.read_file(_get(WFS, _raw(data_dir) / "wahlbezirke_2025.geojson"))
    g["GEOID"] = g["wahlbezirksnummer"].astype(str)
    return g[["GEOID", "geometry"]].dissolve("GEOID").reset_index()  # a few numbers appear on several polygons


def _tables(scope: str, year: int, data_dir):
    csv, fb, valid_col, cast_col = SRC[(scope, year)]
    raw = _raw(data_dir)
    d = pd.read_csv(_get(W + csv, raw / csv.rsplit("/", 1)[-1]), sep=";", dtype=str)
    lab = _party_labels(_get(W + fb, raw / fb.rsplit("/", 1)[-1]), per_bezirk=(scope == "municipal"))
    num = lambda c: pd.to_numeric(d[c], errors="coerce").fillna(0)
    allk = sorted({k for v in lab.values() for k in v}, key=lambda x: int(x[1:])) if scope == "municipal" else list(lab)
    pcols = [k for k in allk if k in d.columns]
    t = pd.DataFrame({"nr": d["Erfassungsgebietsnummer"], "art": d["Erfassungsgebietsart"], "A": num("Wahlberechtigte gesamt (A)"),
                      "A2": num("Wahlberechtigte mit Wahlschein (A2)"), "cast": num(cast_col)})
    for k in pcols:
        t[k] = num(k)
    t["prefix"] = t["nr"].str[:3]
    # Stadtteil via prefix (first 3 digits) learned from the Stimmbezirke
    stb = t["art"] == "STIMMBEZIRK"
    st = d.loc[stb, "Stadtteil"] if "Stadtteil" in d else None
    if st is None:  # municipal csv has no Stadtteil: take prefix map from the Buergerschaft file
        d2 = pd.read_csv(_get(W + SRC[("state", 2025)][0], raw / SRC[("state", 2025)][0].rsplit("/", 1)[-1]), sep=";", dtype=str)
        m = d2[d2["Erfassungsgebietsart"] == "STIMMBEZIRK"].assign(p=lambda x: x["Erfassungsgebietsnummer"].str[:3]).drop_duplicates("p").set_index("p")["Stadtteil"]
        t["stadtteil"] = t["prefix"].map(m)
    else:
        m = d.loc[stb].assign(p=t.loc[stb, "prefix"]).drop_duplicates("p").set_index("p")["Stadtteil"]
        t["stadtteil"] = t["prefix"].map(m)
    return t, pcols, lab


def _allocate(t: pd.DataFrame, pcols):
    s, b = t[t["art"] == "STIMMBEZIRK"].copy(), t[t["art"] != "STIMMBEZIRK"]
    cols = ["cast"] + pcols
    tot = b.groupby("stadtteil")[cols].sum()
    w = s["A2"].where(s.groupby("stadtteil")["A2"].transform("sum") > 0, s["A"])
    share = w / w.groupby(s["stadtteil"]).transform("sum").replace(0, np.nan)
    add = tot.reindex(s["stadtteil"]).reset_index(drop=True)
    add.index = s.index
    for c in cols:
        s[c] = s[c] + add[c].fillna(0) * share.fillna(0)
    lost = {c: float(b[c].sum() - (tot.reindex(s["stadtteil"].unique())[c].sum())) for c in cols[:1]}
    return s


def load_election(scope: str, year: int, level: str = "wahlbezirk", data_dir: Optional[str] = None, min_share: float = 0.03) -> pd.DataFrame:
    """``scope``/``year``: ('national', 2025) Bundestag, ('state', 2025) Buergerschaft, ('municipal', 2024) Bezirksversammlungen.
    ``level``: 'wahlbezirk' (GEOID, 5-digit string) or 'h3' (h3_cell, res 8).

    Args:
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        year: Election year.
        level: ``"wahlbezirk"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        min_share: Parties above this share get their own columns.

    Returns:
        The election frame.
    """
    t, pcols, lab = _tables(scope, year, data_dir)
    s = _allocate(t, pcols)
    s = s[s["A"] > 0]
    votes = s.melt(id_vars=["nr"], value_vars=pcols, var_name="k", value_name="votes")
    votes["GEOID"] = votes["nr"]
    if scope == "municipal":  # party order differs per Bezirk
        votes["party"] = [lab[n[0]].get(k) for n, k in zip(votes["nr"], votes["k"])]
        votes = votes.dropna(subset=["party"])
    else:
        votes["party"] = votes["k"].map(lab)
    totals = pd.DataFrame({"GEOID": s["nr"], "blank": 0.0, "cast": s["cast"], "electors": s["A"]})
    blocs = load_blocs(BLOCS_PATH)[f"{scope}_{year}"]
    df = build_frame(votes[["GEOID", "party", "votes"]], totals, blocs, scope, year, min_share)
    if level == "wahlbezirk":
        return order_columns(df)
    g = load_wahlbezirke(data_dir)
    out = to_h3(df, h3_weights(g, 8), scope, year)
    out.attrs["unmatched_wahlbezirke"] = sorted(set(df["GEOID"]) - set(g["GEOID"]))
    return out


def load_bundestag_2025(level="wahlbezirk", data_dir=None):
    """Bundestag election 2025 in Hamburg (see :func:`load_election`).

    Args:
        level: ``"wahlbezirk"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("national", 2025, level, data_dir)
def load_buergerschaft_2025(level="wahlbezirk", data_dir=None):
    """Hamburg Bürgerschaft election 2025 (see :func:`load_election`).

    Args:
        level: ``"wahlbezirk"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("state", 2025, level, data_dir)
def load_bezirksversammlung_2024(level="wahlbezirk", data_dir=None):
    """Hamburg district assembly elections 2024 (see :func:`load_election`).

    Args:
        level: ``"wahlbezirk"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("municipal", 2024, level, data_dir)
