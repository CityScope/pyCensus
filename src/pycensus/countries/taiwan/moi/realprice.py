"""MOI real-price registry (實價登錄) open data: median sale / pre-sale price and rent per m2 by village/district/county.

Source: https://plvr.land.moi.gov.tw/DownloadOpenData (data.gov.tw dataset 18703). Keyless quarterly zip batches,
``https://plvr.land.moi.gov.tw/DownloadSeason?season={roc}S{q}&type=zip&fileName=lvr_landcsv.zip`` (e.g. ``113S4``), each holding one CSV set per
county letter (a=Taipei, f=New Taipei, ...) with ``_a`` = sales, ``_b`` = pre-sales, ``_c`` = rentals. Verified live: 101S3 (2012 Q3, earliest
batch) through 115S2 exist. Rows carry district (鄉鎮市區) and an address; there is NO village code column, so the village is parsed from the address
(``...區XX里...``) and matched to MOI RIS's village list (ODRP013 ``site_id`` + ``village`` -> 11-digit district_code). Only addresses that
name a village are usable at village level (coverage is reported in ``n_village_matched``/share); district / county_city levels use every row.

Metrics (residential = main use 住家用, building present, non-zero price; excludes related-party/special-note sales):
  realPriceSaleM2   median NTD per m2 of building floor area (parking price/area removed when reported)
  realPricePresaleM2 same for pre-sales (預售屋)
  realRentM2        median monthly rent, NTD per m2 of floor area
  realPriceSaleCount / realPricePresaleCount / realRentCount   number of records (sum when aggregated)
  realPriceSalePing  = realPriceSaleM2 * 3.3058  (NTD per ping)
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
import requests

from .. import api, constants

SEASON_URL = "https://plvr.land.moi.gov.tw/DownloadSeason?season={roc}S{q}&type=zip&fileName=lvr_landcsv.zip"
PING_M2 = 3.3058
CITY_LETTERS = {"a": "臺北市", "b": "臺中市", "c": "基隆市", "d": "臺南市", "e": "高雄市", "f": "新北市", "g": "宜蘭縣", "h": "桃園市",
                "i": "嘉義市", "j": "新竹縣", "k": "苗栗縣", "m": "南投縣", "n": "彰化縣", "o": "新竹市", "p": "雲林縣", "q": "嘉義縣",
                "t": "屏東縣", "u": "花蓮縣", "v": "臺東縣", "w": "金門縣", "x": "澎湖縣", "z": "連江縣"}
_SPECIAL = "親友|員工|關係企業|債權債務|共有人|二親等|特殊關係|急買急賣|畸零地|瑕疵"
_FW = str.maketrans("０１２３４５６７８９", "0123456789")


def _raw_dir(data_dir: Optional[str]) -> Path:
    d = get_data_dir("taiwan", data_dir) / "raw" / "moi_realprice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_season(roc: int, q: int, data_dir: Optional[str] = None, timeout: int = 300) -> Optional[Path]:
    """Download (cached) one quarterly zip; returns None if the batch does not exist.

    Args:
        roc: ROC year.
        q: Quarter (1-4).
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        timeout: Timeout in seconds.

    Returns:
        The zip path, or None.
    """
    p = _raw_dir(data_dir) / f"{roc}S{q}.zip"
    if p.exists() and p.stat().st_size > 100_000:
        return p
    r = requests.get(SEASON_URL.format(roc=roc, q=q), timeout=timeout)
    if r.status_code != 200 or len(r.content) < 100_000 or not r.content.startswith(b"PK"):
        return None
    p.write_bytes(r.content)
    return p


def _read(zf: zipfile.ZipFile, name: str) -> Optional[pd.DataFrame]:
    if name not in zf.namelist():
        return None
    df = pd.read_csv(zf.open(name), dtype=str, encoding="utf-8-sig")
    return df[~df.iloc[:, 0].str.contains("villages and towns", na=False)]  # drop english header row


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _village_from_row(addr: str, district: str) -> Optional[str]:
    addr = (addr or "").translate(_FW)
    i = addr.find(district) if district else -1
    tail = addr[i + len(district):] if i >= 0 else addr
    m = re.match(r"^([^\d路街巷段鄰區鄉鎮市]{1,4}?[里村])", tail)
    return m.group(1) if m else None


def _norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace("臺", "台").str.replace("　", "").str.strip()


def _records(zf: zipfile.ZipFile, letter: str, kind: str) -> pd.DataFrame:
    df = _read(zf, f"{letter}_lvr_land_{kind}.csv")
    if df is None or df.empty:
        return pd.DataFrame()
    c = df.columns
    use = df["主要用途"] if "主要用途" in c else pd.Series("", index=df.index)
    tgt = df["交易標的"]
    price = _num(df["總額元" if kind == "c" else "總價元"])
    area = _num(df[next(k for k in ("建物總面積平方公尺", "建物移轉總面積平方公尺", "建物移轉總面積(平方公尺)") if k in c)])
    def col(*cands):
        for k in cands:
            if k in c:
                return _num(df[k]).fillna(0)
        return pd.Series(0.0, index=df.index)
    park_a = col("車位面積平方公尺", "車位移轉總面積平方公尺", "車位移轉總面積(平方公尺)", "車位總面積平方公尺")
    park_p = col("車位總額元", "車位總價元")
    net_area = area - park_a
    net_area = net_area.where(net_area > 5, area)
    unit = (price - park_p) / net_area
    if "單價元平方公尺" in c:
        unit = unit.where((price - park_p) > 0, _num(df["單價元平方公尺"]))
    note = df["備註"].fillna("") if "備註" in c else pd.Series("", index=df.index)
    ok = tgt.str.contains("建物|房地|房屋", na=False) & (area > 5) & (unit > 0) & use.fillna("").str.contains("住家") & ~note.str.contains(_SPECIAL)
    if kind == "b" and "解約情形" in c:
        ok &= df["解約情形"].isna()
    out = pd.DataFrame({"district": _norm(df["鄉鎮市區"]), "addr": df["土地位置建物門牌"], "value": unit.where(ok), "ok": ok})
    out["city"] = CITY_LETTERS[letter]
    return out[out["ok"]].drop(columns="ok")


def load_raw(year: int, cities: Iterable[str] = ("a", "f"), data_dir: Optional[str] = None) -> pd.DataFrame:
    """All usable residential records of calendar ``year`` for county letters ``cities``; columns kind, city, district, addr, value.

    Args:
        year: Calendar year.
        cities: County letters of the real-price files.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.

    Returns:
        One row per record.
    """
    roc = year - 1911
    frames: List[pd.DataFrame] = []
    for q in (1, 2, 3, 4):
        p = download_season(roc, q, data_dir)
        if p is None:
            continue
        with zipfile.ZipFile(p) as zf:
            for letter in cities:
                for kind, label in (("a", "sale"), ("b", "presale"), ("c", "rent")):
                    d = _records(zf, letter, kind)
                    if len(d):
                        d["kind"] = label
                        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["kind", "city", "district", "addr", "value"])


def _village_lookup(data_dir: Optional[str]) -> pd.DataFrame:
    raw = _raw_dir(data_dir).parent / "moi_ris"
    raw.mkdir(parents=True, exist_ok=True)
    v = api.fetch_resident_population(constants.LATEST_YEAR["census"], raw_cache_path=raw / f"resident_population_{constants.LATEST_YEAR['census']}.json")
    v = v[["district_code", "site_id", "village"]].copy()
    v["key"] = _norm(v["site_id"]) + "|" + _norm(v["village"])
    v["dkey"] = _norm(v["site_id"])
    return v


_COLS = {"sale": ("realPriceSaleM2", "realPriceSaleCount"), "presale": ("realPricePresaleM2", "realPricePresaleCount"), "rent": ("realRentM2", "realRentCount")}


def load_realprice(year: int, level: str = "district", cities: Iterable[str] = ("a", "f"), data_dir: Optional[str] = None,
                   min_obs: int = 1) -> pd.DataFrame:
    """Median price/rent per m2 and record counts by ``level`` ('village' 11-digit, 'district' 8-digit, 'county_city' 5-digit GEOID).

    ``year`` is a calendar year (2012 holds only Q3-Q4). Returns DataFrame GEOID + realPrice*/realRent* columns (NaN median where < min_obs).

    Args:
        year: Calendar year.
        level: ``"village"``, ``"district"`` or ``"county_city"``.
        cities: County letters.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        min_obs: Fewest records for a median.
    """
    raw = load_raw(year, cities, data_dir)
    v = _village_lookup(data_dir)
    raw["dkey"] = _norm(raw["city"]) + _norm(raw["district"])
    dmap = v.assign(g8=v["district_code"].str[:8]).drop_duplicates("dkey").set_index("dkey")["g8"]
    raw["g8"] = raw["dkey"].map(dmap)
    if level == "village":
        raw["vn"] = [_village_from_row(a, d) for a, d in zip(raw["addr"], raw["district"])]
        raw["key"] = raw["dkey"] + "|" + _norm(raw["vn"].fillna(""))
        raw["GEOID"] = raw["key"].map(v.drop_duplicates("key").set_index("key")["district_code"])
    elif level == "district":
        raw["GEOID"] = raw["g8"]
    elif level == "county_city":
        raw["GEOID"] = raw["g8"].str[:5]
    else:
        raise ValueError(level)
    raw = raw.dropna(subset=["GEOID"])
    out = None
    for kind, (mcol, ccol) in _COLS.items():
        g = raw[raw["kind"] == kind].groupby("GEOID")["value"].agg(["median", "count"])
        g.columns = [mcol, ccol]
        g.loc[g[ccol] < min_obs, mcol] = float("nan")
        out = g if out is None else out.join(g, how="outer")
    out["realPriceSalePing"] = out["realPriceSaleM2"] * PING_M2
    for c in ("realPriceSaleCount", "realPricePresaleCount", "realRentCount"):
        out[c] = out[c].fillna(0)
    return out.reset_index()


__all__ = ["load_realprice", "load_raw", "download_season"]
