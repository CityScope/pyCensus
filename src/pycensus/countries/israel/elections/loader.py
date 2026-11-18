"""Israel Knesset results by ballot box (kalpi) -> H3 res 8 -> CBS statistical areas.

Sources (official Central Elections Committee data, republished on data.gov.il; the CKAN datastore JSON API is open, whereas the CSV
download links and votes25.bechirot.gov.il / gov.il sit behind a CloudFront/WAF 403 for scripted clients and are NOT used):
  results per kalpi  https://data.gov.il/api/3/action/datastore_search?resource_id=cc223336-07bc-485d-b160-62df92967c0a   (Knesset 25, 1 Nov 2022;
                     dataset 'votes-knesset'; other Knesset terms have their own resource ids in RESOURCES)
  polling places     https://data.gov.il/api/3/action/datastore_search?resource_id=68c4d7e8-2218-48ee-996f-2db2f72b2395   (dataset 'voting-polls':
                     street, house number, venue name per locality symbol and kalpi*10)
No published geometry for ballot boxes or statistical areas exists, so polling-place ADDRESSES are geocoded with OSM Nominatim (cached; venue name tried
first, then street+number, then street). Positional error is typically 100-500 m: results are therefore a polling-station-location surrogate of where
voters live, not residential results. Kalpi without a polling-place record (code mismatch between the 2022 result file and the 2023 list) borrow the location of the
numerically nearest located box (reported in ``attrs['borrowed_location_share']``).

Pipeline: kalpi counts -> H3 res 8 cell of the geocoded point (sum) -> CBS 2022 statistical areas by AREA-WEIGHTED split of each cell's counts over
the polygons it overlaps (counts rescaled so each locality total is conserved) -> shares recomputed from counts.
Municipal (local authority) results: not obtainable, see :func:`load_local_authorities`.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import json
import time
import zlib
from collections import namedtuple
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd
import requests

from .... import electoral
from .. import constants, geography

ElectionResult = namedtuple("ElectionResult", ["census", "h3"])
CKAN = "https://data.gov.il/api/3/action/datastore_search"
RESOURCES = {25: "cc223336-07bc-485d-b160-62df92967c0a"}  # Knesset 25 (2022) ballot-box results; election date below
ELECTION_YEAR = {25: 2022}
POLLS_RESOURCE = "68c4d7e8-2218-48ee-996f-2db2f72b2395"
BLOCS_PATH = Path(__file__).parent.parent / "schema" / "israel_elections_blocs.json"
LETTER_SLUG = {"מחל": "likud", "ט": "religious_zionism", "שס": "shas", "ג": "utj", "ף": "jewish_home", "פה": "yesh_atid", "כן": "national_unity",
               "אמת": "labor", "מרצ": "meretz", "ום": "hadash_taal", "עם": "raam", "ד": "balad", "ל": "yisrael_beytenu"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "pycensus-research/1.0 (election loader)"}


def _raw_dir(data_dir: Optional[str]) -> Path:
    d = get_data_dir("israel", data_dir) / "raw" / "israel_elections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ckan(resource: str, locality: int, data_dir) -> pd.DataFrame:
    cache = _raw_dir(data_dir) / f"ckan_{resource}_{locality}.json"
    if cache.exists():
        return pd.DataFrame(json.loads(cache.read_text(encoding="utf-8")))
    r = requests.get(CKAN, params={"resource_id": resource, "limit": 20000, "filters": json.dumps({"סמל ישוב": locality})}, headers=UA, timeout=120)
    r.raise_for_status()
    recs = r.json()["result"]["records"]
    cache.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    return pd.DataFrame(recs)


def _geocode(queries, bbox, cache_file: Path):
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    out = None
    for q in queries:
        if q not in cache:
            time.sleep(1.1)
            r = requests.get(NOMINATIM, params={"q": q, "format": "json", "limit": 1, "viewbox": ",".join(map(str, bbox)), "bounded": 1}, headers=UA, timeout=60)
            j = r.json() if r.status_code == 200 else []
            cache[q] = [float(j[0]["lat"]), float(j[0]["lon"]), j[0].get("class", "")] if j else None
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if cache[q]:
            out = cache[q]
            if out[2] != "highway":  # venue or building hit; street hits are a fallback
                return out
    return out


def _polling_points(locality: int, city_name: str, bbox, data_dir) -> pd.DataFrame:
    b = _ckan(POLLS_RESOURCE, locality, data_dir)
    b["addr_key"] = b["שם רחוב"].astype(str) + "|" + b["מספר בית"].astype(str) + "|" + b["תיאור מקום הקלפי"].astype(str)
    cf = _raw_dir(data_dir) / f"nominatim_{locality}.json"
    pts = {}
    for k, row in b.drop_duplicates("addr_key").set_index("addr_key").iterrows():
        venue = str(row["תיאור מקום הקלפי"]).replace(")", "").replace("(", "").strip()
        street = f"{int(row['מספר בית'])} {row['שם רחוב']}, {city_name}" if row["מספר בית"] else f"{row['שם רחוב']}, {city_name}"
        pts[k] = _geocode([f"{venue}, {city_name}", street, f"{row['שם רחוב']}, {city_name}"], bbox, cf)
    b["lat"] = b["addr_key"].map(lambda k: pts[k][0] if pts[k] else np.nan)
    b["lng"] = b["addr_key"].map(lambda k: pts[k][1] if pts[k] else np.nan)
    return b[["סמל קלפי", "lat", "lng"]].rename(columns={"סמל קלפי": "code"})


def load_knesset(election: int = 25, localities: Iterable[int] = (9000,), data_dir: Optional[str] = None, party_threshold: float = 0.03) -> ElectionResult:
    """Knesset election results for ``localities`` (CBS locality symbols; 9000 = Beersheba).

    Returns ``ElectionResult(census, h3)``: ``census`` keyed by 8-digit CBS statistical-area ``GEOID`` (same GEOIDs as
    ``israel.geography.load_boundaries('statistical_area', ...)``), ``h3`` keyed by ``h3_cell`` (res 8) with shares and ``cnt_*`` counts.
    Columns: ``elec_national_<year>_{total_votes,turnout_rate,left_share,right_share,other_share,party_<slug>_share}`` (total_votes = valid votes).

    Args:
        election: Knesset number (e.g. 25).
        localities: CBS locality symbols.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        party_threshold: Parties above this share get their own columns.

    Raises:
        ValueError: For a Knesset not wired.
    """
    import geopandas as gpd
    if election not in RESOURCES:
        raise ValueError(f"Knesset {election} not wired (available: {sorted(RESOURCES)}); the 26th is scheduled for 27 Oct 2026 and has no results yet")
    year = ELECTION_YEAR[election]
    tag = f"national_{year}"
    blocs = electoral.load_blocs(BLOCS_PATH)
    kb = blocs[f"knesset_{election}"]
    all_k, all_sa, h3parts = [], [], []
    for loc in localities:
        res = _ckan(RESOURCES[election], loc, data_dir)
        if res.empty:
            raise ValueError(f"No ballot-box rows for locality {loc}")
        sa = geography.load_boundaries("statistical_area", str(loc))
        name = res["שם ישוב"].iloc[0]
        b = sa.total_bounds
        pts = _polling_points(loc, name, (b[0] - .02, b[3] + .02, b[2] + .02, b[1] - .02), data_dir)
        cl = list(res.columns)
        letters = cl[cl.index("אמת"):cl.index("ת") + 1]
        res["code"] = (res["קלפי"].astype(float).astype(int) * 10)
        res = res.merge(pts.drop_duplicates("code"), on="code", how="left")
        ok = res.dropna(subset=["lat"])
        for i in res.index[res["lat"].isna()]:  # kalpi absent from the (2023) polling-place list: borrow the numerically nearest located box
            j = (ok["code"] - res.at[i, "code"]).abs().idxmin()
            res.loc[i, ["lat", "lng"]] = ok.loc[j, ["lat", "lng"]].values
            res.at[i, "borrowed"] = True
        res["eligible"], res["ballots"], res["valid"] = res["בזב"], res["מצביעים"], res["כשרים"]
        for bl in ("left", "right", "other"):
            res[bl] = sum(res[c] for c in letters if kb.get(c, {}).get("bloc", blocs["default_bloc"]) == bl)
        for c in letters:
            res[f"L_{c}"] = res[c]
        res["locality"] = loc
        all_k.append(res)
        all_sa.append(sa)
    k = pd.concat(all_k, ignore_index=True)
    letters = [c for c in k.columns if c.startswith("L_")]
    shares = k[letters].sum() / k["valid"].sum()
    keepL = [c[2:] for c in shares[shares >= party_threshold].index]
    slug = {c: LETTER_SLUG.get(c, f"list_{zlib.crc32(c.encode()) % 10**4}") for c in keepL}
    for c in keepL:
        k[f"party_{slug[c]}"] = k[f"L_{c}"]
    keep = sorted(slug.values())
    cols = electoral.BASE_COUNTS + [f"party_{s}" for s in keep]
    unl = k.loc[k["borrowed"].fillna(False).astype(bool), "valid"].sum() / k["valid"].sum()
    hc_parts = []
    for loc, grp in k.groupby("locality"):
        hc_parts.append(electoral.points_to_h3(grp, cols, lat="lat", lng="lng"))
    hc = pd.concat(hc_parts).groupby("h3_cell", as_index=False)[cols].sum()
    sa_all = pd.concat(all_sa, ignore_index=True)
    sa_all = gpd.GeoDataFrame(sa_all, geometry="geometry", crs=4326)
    c = electoral.h3_to_polygons(hc, sa_all, "GEOID", cols)
    c = sa_all[["GEOID"]].merge(c, on="GEOID", how="left")  # statistical areas with no overlapping cell stay NaN
    for col in cols:  # conserve the total over the statistical areas (cells partly outside the locality lose mass)
        c[col] = c[col] * hc[col].sum() / c[col].sum(skipna=True)
    census = electoral.finalize(c, tag, "GEOID", keep)
    h3df = electoral.finalize(hc, tag, "h3_cell", keep).merge(hc.rename(columns={x: f"cnt_{x}" for x in cols}), on="h3_cell")
    census.attrs.update(borrowed_location_share=float(unl), party_letters=slug)
    return ElectionResult(census, h3df)


def load_local_authorities(*args, **kw):
    """Not available: the Interior Ministry / Central Elections Committee local-authority (mayor + council) results by ballot box
    (Feb 2024 round) are only on gov.il / bechirot.gov.il pages that answer scripted clients with an HTTP 403 WAF block, and data.gov.il has
    no local-election results dataset (only polling-place lists). Not circumvented; see the module report.

    Args:
        *args: Ignored.
        **kw: Ignored.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError("Israeli local-authority election results are not retrievable (gov.il / bechirot.gov.il blocked, no data.gov.il dataset).")
