"""Andorra election results at parish (comu) level: Consell General 2 April 2023 (national list) and Comunals 17 Dec 2023.

Sources (verified live 2026-10-25), Govern d'Andorra election site:
  Comunals 2023: ``https://www.eleccions.ad/resultats`` (HTML, one block per parish: electors, escrutats, valids, blancs, nuls, votes per list). Parsed live
    (raw page cached to ``<data_dir>/raw/elections/eleccions_ad_resultats.html``; the site shows only the latest election, so keep the cache).
  Consell General 2023: ``https://www.eleccions.ad/documentacio/anteriors/EG_2023.pdf`` (image-only PDF, no text layer, no machine-readable file
    published). The "Escrutini de la circumscripcio nacional per parroquia" tables were transcribed by hand (visual read) into ``_EG2023`` below;
    all 7 parish rows add up to the published national totals (19,172 valid votes, 537 blank, 341 null, 20,050 cast). Only the national list is used (its
    votes are broken down by parish; the 14 parish-list seats are elected on local lists and are not comparable between parishes).
Native resolution: parish (7). Andorra has no state/regional parliament, so scope ``state`` does not exist. Andorra publishes no polling-station results.
Geometry: parish polygons, ``andorra.geography.load_boundaries('parish')`` (GEOID ``AD-01``..``AD-07``). H3 res 8 is AREA-weighted over parish polygons, i.e. every
cell of a parish gets the parish's vote shares (no sub-parish information exists); counts are split by area.
Blocs: ``schema/elections_blocs.json``. Comunals lists are local coalitions that mix parties; almost all are marked uncertain.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import html
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from ....elections import build_frame, h3_weights, load_blocs, order_columns, to_h3
from .. import geography
from ..constants import PARISH_NAME_TO_CODE

RESULTS_URL = "https://www.eleccions.ad/resultats"
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "elections_blocs.json"
# parish: (electors, cast, blank, null, {list: votes}) -- Consell General 2023, national list by parish
_EG2023 = {
    "AD-01": (1199, 865, 36, 12, {"LIBERALS D'ANDORRA": 40, "CONCORDIA": 142, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 387, "ACCIO": 23, "ANDORRA ENDAVANT": 117, "PS SDP +": 108}),
    "AD-02": (4341, 2803, 77, 67, {"LIBERALS D'ANDORRA": 102, "CONCORDIA": 490, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 921, "ACCIO": 133, "ANDORRA ENDAVANT": 445, "PS SDP +": 568}),
    "AD-03": (1903, 1452, 36, 19, {"LIBERALS D'ANDORRA": 57, "CONCORDIA": 373, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 415, "ACCIO": 34, "ANDORRA ENDAVANT": 199, "PS SDP +": 319}),
    "AD-04": (3483, 2486, 63, 39, {"LIBERALS D'ANDORRA": 87, "CONCORDIA": 568, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 805, "ACCIO": 199, "ANDORRA ENDAVANT": 344, "PS SDP +": 381}),
    "AD-05": (8693, 5401, 126, 60, {"LIBERALS D'ANDORRA": 260, "CONCORDIA": 1000, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 1520, "ACCIO": 183, "ANDORRA ENDAVANT": 877, "PS SDP +": 1375}),
    "AD-06": (4476, 3024, 98, 57, {"LIBERALS D'ANDORRA": 196, "CONCORDIA": 745, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 758, "ACCIO": 97, "ANDORRA ENDAVANT": 552, "PS SDP +": 521}),
    "AD-07": (5863, 4019, 101, 87, {"LIBERALS D'ANDORRA": 151, "CONCORDIA": 791, "DEMOCRATES + CIUTADANS COMPROMESOS + ACCIO COMUNAL D'ORDINO + UN": 1456, "ACCIO": 136, "ANDORRA ENDAVANT": 533, "PS SDP +": 764}),
}


def norm(s: str) -> str:
    """Upper-case ASCII party name with the long SDP coalition name shortened (the key of the blocs file).

    Args:
        s: Party name.

    Returns:
        The normalised name.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("PARTIT SOCIALDEMOCRATA PROGRESSISTES SDP +", "PS SDP +").split())


def _to_int(x: str) -> int:
    return int(x.replace(".", "").replace("&nbsp;", "").strip())


def _comunals(data_dir: Optional[str]):
    p = get_data_dir("andorra", data_dir) / "raw" / "elections" / "eleccions_ad_resultats.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        r = requests.get(RESULTS_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        p.write_bytes(r.content)
    t = p.read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t)).replace("\xa0", " ")
    t = re.sub(r"[|\s]*\|[|\s]*", "|", t)
    if "Eleccions Comunals 2023" not in t:
        raise RuntimeError("eleccions.ad no longer shows Comunals 2023; use the cached raw page")
    votes, tot = [], []
    for blk in re.split(r"Resultats a la parr?òquia d[e']\s?", t)[1:]:
        name = blk.split("|")[0].strip()
        code = PARISH_NAME_TO_CODE[next(n for n in PARISH_NAME_TO_CODE if norm(n) == norm(name))]
        g = lambda lab: _to_int(re.search(lab + r":\|([\d.]+)", blk).group(1))
        tot.append((code, g("Vots blancs"), g("Vots escrutats"), g("Electors convocats")))
        det = blk.split("Escons|", 1)[1]
        for lst, v in re.findall(r"\|?([^|]+)\|([\d.]+)\|[\d,]+%\|\d+", det):
            votes.append((code, norm(lst), _to_int(v)))
    return (pd.DataFrame(votes, columns=["GEOID", "party", "votes"]), pd.DataFrame(tot, columns=["GEOID", "blank", "cast", "electors"]))


def load_election(scope: str, year: int, level: str = "parish", data_dir: Optional[str] = None, min_share: float = 0.03) -> pd.DataFrame:
    """``scope`` 'national' (Consell General 2023) or 'municipal' (Comunals 2023). ``level``: 'parish' (GEOID AD-0X) or 'h3' (h3_cell, res 8).

    Args:
        scope: ``"national"``, ``"state"`` or ``"municipal"``.
        year: Election year (2023).
        level: ``"parish"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        min_share: Parties above this share get their own columns.

    Returns:
        The election frame.
    """
    if (scope, year) == ("national", 2023):
        v = [(c, norm(k), n) for c, (_, _, _, _, d) in _EG2023.items() for k, n in d.items()]
        votes = pd.DataFrame(v, columns=["GEOID", "party", "votes"])
        totals = pd.DataFrame([(c, b, ca, e) for c, (e, ca, b, _, _) in _EG2023.items()], columns=["GEOID", "blank", "cast", "electors"])
    elif (scope, year) == ("municipal", 2023):
        votes, totals = _comunals(data_dir)
        # lists are parish-specific: bloc key = "<parish code>|<list>"
        votes["party"] = votes["GEOID"] + "|" + votes["party"]
    else:
        raise ValueError("Andorra: only ('national', 2023) and ('municipal', 2023); there is no state-level election")
    blocs = load_blocs(BLOCS_PATH)[f"{scope}_{year}"]
    # Comunals lists are single-parish, so none passes a country-wide 3% cut: keep every list (column slug starts with the parish code)
    df = build_frame(votes, totals, blocs, scope, year, 0.0 if scope == "municipal" else min_share)
    if level == "parish":
        return order_columns(df)
    g = geography.load_boundaries("parish")
    return to_h3(df, h3_weights(g, 8), scope, year)


def load_consell_general_2023(level="parish", data_dir=None):
    """Consell General election 2023 (see :func:`load_election`).

    Args:
        level: ``"parish"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("national", 2023, level, data_dir)
def load_comunals_2023(level="parish", data_dir=None):
    """Comunal (parish council) elections 2023 (see :func:`load_election`).

    Args:
        level: ``"parish"`` or ``"h3"``.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        The election frame.
    """
    return load_election("municipal", 2023, level, data_dir)
