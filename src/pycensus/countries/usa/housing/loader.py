"""Downloader / loader for U.S. housing price and rent data, delivered on 2020 census tracts (GEOID, 11 digits).

Sources (all keyless except the Census API key from ``pycensus.api_keys``; raw downloads are cached under ``<data_dir>/raw/us_housing``):

* Census ACS 5-year (API): 2020-24 (``acs5`` 2024) and 2012-16 (``acs5`` 2016). Native: tract (2020 tracts / 2010 tracts respectively).
* Census 2000 SF3 (API, ``2000/dec/sf3``). Native: 2000 tracts. Re-tabulation to 2020 tracts: 2000->2010 with the Census Bureau tract
  relationship files (weights = 2010 housing units in each overlap), then 2010->2020 with ``tab20_tract20_tract10_natl`` (weights = land area of
  each overlap). Medians / shares are carried over as weighted means (an approximation; the Longitudinal Tract Database is no longer
  distributed and NHGIS needs an account key, so neither is used).
* FHFA annual all-transactions House Price Index at tract (2010 tracts) and 5-digit ZIP (experimental), 2000 = 100: fhfa.gov/hpi/download/annual.
  ZIPs are mapped to tracts with the Census 2020 ZCTA-tract relationship file (area-weighted mean over overlapping ZCTAs).
* Realtor.com Research ZIP inventory history (econdata.s3-us-west-2.amazonaws.com/Reports/Core): median asking price per square foot of the
  listings of the last 12 months, converted to ``listing_price_per_m2`` (USD per m2; asking prices, not sale prices) and ``listing_median_area_m2`` (median listed home size, m2), mapped to tracts like the ZIP series above.
* HUD Small Area Fair Market Rents by ZIP (FY2019 first mandatory year onward available; none older) and HUD county FMRs (FY2019+ found).

Output names (suffix = period): ``home_value_median``, ``rent_median``, ``rent_burden_median``, ``rent_burdened_share`` (>=30% of income),
``owner_share``, ``renter_share``, ``rooms_median``, ``rent_per_room_mean`` (median gross rent / median rooms), each with ``_2016`` (ACS 2012-16)
and ``_2000``; ``house_price_index_fhfa[_YYYY]``, ``house_price_index_fhfa_zip[_YYYY]`` (2000=100), ``house_price_cagr_2016_2025_rate``;
``hud_safmr_2br_rent_mean[_FYYYYY]`` and ``hud_fmr_2br_county_rent_mean[_FYYYYY]``. No Census table has dwelling floor area at tract level, so
``rent_per_m2`` cannot be derived; ``rent_per_room_mean`` is the closest size-normalised rent. ``listing_price_per_m2`` is the only per-area price.
"""
from __future__ import annotations
from pycensus.cache import get_data_dir

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"}
DEFAULT_DATA_DIR = str(get_data_dir("usa"))  # env/temp default, resolved at import
ACS_PERIODS = {"": 2024, "_2016": 2016}  # suffix -> ACS 5-year end year
FHFA_YEARS = {"": 2025, "_2016": 2016, "_2006": 2006}
HUD_SAFMR_YEARS = (2019, 2022, 2026)
HUD_FMR_YEARS = (2019, 2022, 2026)
HUD = "https://www.huduser.gov/portal/datasets/fmr/"
HUD_SAFMR_FILES = {2019: "fmr2019/fy2019_safmrs.xlsx", 2022: "fmr2022/fy2022_safmrs.xlsx", 2026: "fmr2026/fy2026_safmrs.xlsx"}
HUD_FMR_FILES = {2019: "fmr2019/FY19_4050_FMRs_rev.xlsx", 2022: "fmr2022/FY22_FMRs_revised.xlsx", 2026: "fmr2026/FY26_FMRs.xlsx"}
FHFA = "https://www.fhfa.gov/hpi/download/annual/"
REL = "https://www2.census.gov/geo/docs/maps-data/data/"


def _raw(data_dir) -> Path:
    p = get_data_dir("usa", data_dir) / "raw" / "us_housing"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _download(url: str, data_dir, name: Optional[str] = None) -> Path:
    path = _raw(data_dir) / (name or url.rsplit("/", 1)[-1])
    if not path.exists() or path.stat().st_size == 0:
        r = requests.get(url, timeout=900, headers=UA)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def _xlsx_rows(path: Path):
    """Rows of the first sheet; HUD files carry malformed docProps that break openpyxl, so that part is dropped."""
    import openpyxl

    buf = io.BytesIO()
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(buf, "w") as zo:
        for n in zi.namelist():
            if n != "docProps/core.xml":
                zo.writestr(n, zi.read(n))
    buf.seek(0)
    return openpyxl.load_workbook(buf, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True)


def _num(s):
    v = pd.to_numeric(s, errors="coerce")
    return v.where(v > -1e6)  # Census sentinels (-666666666 ...)


# ----------------------------------------------------------------------------------------------------------------- Census
def _census_json(url: str, params: dict, data_dir, name: str) -> pd.DataFrame:
    path = _raw(data_dir) / name
    if not path.exists():
        from pycensus.api_keys import resolve_api_key

        r = requests.get(url, params={**params, "key": resolve_api_key("us_census", "US_CENSUS_API_KEY")}, timeout=300)
        r.raise_for_status()
        path.write_text(r.text)
    rows = json.loads(path.read_text())
    return pd.DataFrame(rows[1:], columns=rows[0])


def _acs(year: int, state: str, data_dir) -> pd.DataFrame:
    cols = ["B25077_001E", "B25064_001E", "B25071_001E", "B25003_001E", "B25003_002E", "B25003_003E", "B25018_001E",
            "B25070_001E", "B25070_007E", "B25070_008E", "B25070_009E", "B25070_010E"]
    d = _census_json(f"https://api.census.gov/data/{year}/acs/acs5", {"get": ",".join(cols), "for": "tract:*", "in": f"state:{state} county:*"},
                     data_dir, f"acs5_{year}_{state}.json")
    n = {c: _num(d[c]) for c in cols}
    out = pd.DataFrame({"GEOID": d["state"] + d["county"] + d["tract"]})
    out["home_value_median"] = n["B25077_001E"].where(n["B25077_001E"] > 0)
    out["rent_median"] = n["B25064_001E"].where(n["B25064_001E"] > 0)
    out["rent_burden_median"] = n["B25071_001E"].where(n["B25071_001E"] > 0)
    tot = n["B25003_001E"].where(n["B25003_001E"] > 0)
    out["owner_share"] = n["B25003_002E"] / tot
    out["renter_share"] = n["B25003_003E"] / tot
    rt = n["B25070_001E"].where(n["B25070_001E"] > 0)
    out["rent_burdened_share"] = (n["B25070_007E"] + n["B25070_008E"] + n["B25070_009E"] + n["B25070_010E"]) / rt
    out["rooms_median"] = n["B25018_001E"].where(n["B25018_001E"] > 0)
    return out


def _sf3_2000(state: str, data_dir) -> pd.DataFrame:
    cols = ["H076001", "H063001", "H070001", "H007001", "H007002", "H007003", "H027001"]
    d = _census_json("https://api.census.gov/data/2000/dec/sf3", {"get": ",".join(cols), "for": "tract:*", "in": f"state:{state} county:*"},
                     data_dir, f"sf3_2000_{state}.json")
    n = {c: _num(d[c]) for c in cols}
    out = pd.DataFrame({"GEOID": d["state"] + d["county"] + d["tract"].str.ljust(6, "0")})  # 2000 API drops a trailing "00" suffix
    out["home_value_median"] = n["H076001"].where(n["H076001"] > 0)
    out["rent_median"] = n["H063001"].where(n["H063001"] > 0)
    out["rent_burden_median"] = n["H070001"].where(n["H070001"] > 0)
    tot = n["H007001"].where(n["H007001"] > 0)
    out["owner_share"] = n["H007002"] / tot
    out["renter_share"] = n["H007003"] / tot
    out["rooms_median"] = n["H027001"].where(n["H027001"] > 0)
    return out


# ------------------------------------------------------------------------------------------------------------- crosswalks
def _xw_2000_2010(state: str, abbr: str, data_dir) -> pd.DataFrame:
    """2000 tract -> 2010 tract rows (src, dst, w): w = 2010 housing units of the overlap (land area if no housing units)."""
    p = _download(f"{REL}rel/trf_txt/{abbr.lower()}{state}trf.txt", data_dir)
    d = pd.read_csv(p, header=None, dtype=str)
    out = pd.DataFrame({"src": d[3], "dst": d[12], "hu": pd.to_numeric(d[27]), "land": pd.to_numeric(d[19])})
    out["w"] = out["hu"]
    nohu = out.groupby("dst")["hu"].transform("sum") <= 0
    out.loc[nohu, "w"] = out.loc[nohu, "land"]
    return out[out["w"] > 0][["src", "dst", "w"]]


def _xw_2010_2020(state: str, data_dir) -> pd.DataFrame:
    """2010 tract -> 2020 tract rows (src, dst, w): w = land area of the overlap."""
    p = _download(f"{REL}rel2020/tract/tab20_tract20_tract10_natl.txt", data_dir)
    d = pd.read_csv(p, sep="|", dtype=str, usecols=["GEOID_TRACT_20", "GEOID_TRACT_10", "AREALAND_PART"], encoding="utf-8-sig")
    d = d[d["GEOID_TRACT_20"].str.startswith(state)]
    return pd.DataFrame({"src": d["GEOID_TRACT_10"], "dst": d["GEOID_TRACT_20"], "w": pd.to_numeric(d["AREALAND_PART"])}).query("w > 0")


def _apply_xw(values: pd.DataFrame, xw: pd.DataFrame) -> pd.DataFrame:
    """Weighted mean of every column of ``values`` (indexed by source GEOID) per destination, ignoring missing values."""
    m = xw.merge(values, left_on="src", right_index=True, how="inner")
    res = {}
    for c in values.columns:
        ok = m[c].notna()
        w = m["w"].where(ok, 0.0)
        res[c] = (m[c].fillna(0.0) * w).groupby(m["dst"]).sum() / w.groupby(m["dst"]).sum().replace(0, np.nan)
    return pd.DataFrame(res)


def _to_2020(values: pd.DataFrame, vintage: int, state: str, abbr: str, data_dir) -> pd.DataFrame:
    v = values.drop_duplicates("GEOID").set_index("GEOID")
    if vintage == 2000:
        v = _apply_xw(v, _xw_2000_2010(state, abbr, data_dir))
    if vintage in (2000, 2010):
        v = _apply_xw(v, _xw_2010_2020(state, data_dir))
    return v


def _zcta_tract(state: str, data_dir) -> pd.DataFrame:
    p = _download(f"{REL}rel2020/zcta520/tab20_zcta520_tract20_natl.txt", data_dir)
    d = pd.read_csv(p, sep="|", dtype=str, usecols=["GEOID_ZCTA5_20", "GEOID_TRACT_20", "AREALAND_PART"], encoding="utf-8-sig").dropna()
    d = d[d["GEOID_TRACT_20"].str.startswith(state)]
    return pd.DataFrame({"src": d["GEOID_ZCTA5_20"], "dst": d["GEOID_TRACT_20"], "w": pd.to_numeric(d["AREALAND_PART"])}).query("w > 0")


# ------------------------------------------------------------------------------------------------------------------ FHFA
def _fhfa_tract(state: str, data_dir) -> pd.DataFrame:
    p = _download(FHFA + "hpi_at_tract.csv", data_dir)
    parts = [c[c["tract"].str.startswith(state)] for c in pd.read_csv(p, dtype={"tract": str}, usecols=["tract", "year", "hpi2000"], chunksize=500_000)]
    d = pd.concat(parts)
    d["hpi2000"] = pd.to_numeric(d["hpi2000"], errors="coerce")
    return d.pivot_table(index="tract", columns="year", values="hpi2000")


def _fhfa_zip(data_dir) -> pd.DataFrame:
    p = _download(FHFA + "hpi_at_zip5.xlsx", data_dir)
    cache = _raw(data_dir) / "hpi_at_zip5_2000base.parquet"
    if cache.exists():
        d = pd.read_parquet(cache)
    else:
        rows = [(str(r[0]), r[1], r[5]) for r in _xlsx_rows(p) if r[0] and re.fullmatch(r"\d{5}", str(r[0]))]
        d = pd.DataFrame(rows, columns=["zip", "year", "hpi2000"])
        d["hpi2000"] = pd.to_numeric(d["hpi2000"], errors="coerce")
        d["year"] = d["year"].astype(int)
        d.to_parquet(cache)
    return d.pivot_table(index="zip", columns="year", values="hpi2000")


# -------------------------------------------------------------------------------------------------------------------- HUD
def _hud_safmr(fy: int, data_dir) -> pd.Series:
    p = _download(HUD + HUD_SAFMR_FILES[fy], data_dir, f"hud_safmr_fy{fy}.xlsx")
    it = _xlsx_rows(p)
    head = [re.sub(r"\s+", " ", str(h or "")).strip() for h in next(it)]
    zi = next(i for i, h in enumerate(head) if h.upper().startswith("ZIP"))
    ri = next(i for i, h in enumerate(head) if h.upper() == "SAFMR 2BR")
    d = pd.DataFrame([(str(r[zi]).zfill(5), r[ri]) for r in it if r[zi]], columns=["zip", "v"])
    d["v"] = pd.to_numeric(d["v"], errors="coerce")
    return d.groupby("zip")["v"].mean()


def _hud_fmr(fy: int, data_dir) -> pd.Series:
    p = _download(HUD + HUD_FMR_FILES[fy], data_dir, f"hud_fmr_fy{fy}.xlsx")
    d = pd.DataFrame(list(_xlsx_rows(p)))
    d.columns = [str(c).strip().lower() for c in d.iloc[0]]
    d = d.iloc[1:]
    fips = next(c for c in d.columns if c.startswith("fips"))
    d["county"] = d[fips].astype(str).str.zfill(10).str[:5]
    d["v"] = pd.to_numeric(d["fmr_2"], errors="coerce")
    return d.groupby("county")["v"].mean()


REALTOR_ZIP = "https://econdata.s3-us-west-2.amazonaws.com/Reports/Core/RDC_Inventory_Core_Metrics_Zip_History.csv"
SQFT_PER_M2 = 10.763910417


def _realtor_zip(data_dir) -> pd.DataFrame:
    """Per ZIP: `listing_price_per_m2` (median asking price per m2) and `listing_median_area_m2` (median listed home size) over the latest 12 months of
    the Realtor.com ZIP history (monthly medians averaged), cached as a small parquet."""
    cache = _raw(data_dir) / "realtor_zip_m2.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    src = _raw(data_dir) / "realtor_zip_history.csv"
    if not src.exists() or src.stat().st_size == 0:
        with requests.get(REALTOR_ZIP, timeout=900, headers=UA, stream=True) as r:
            r.raise_for_status()
            with open(src, "wb") as f:
                for blk in r.iter_content(1 << 22):
                    f.write(blk)
    parts = []
    for ch in pd.read_csv(src, usecols=["month_date_yyyymm", "postal_code", "median_listing_price_per_square_foot", "median_square_feet"], dtype={"postal_code": str}, chunksize=2_000_000):
        parts.append(ch.dropna())
    d = pd.concat(parts)
    d = d[d["month_date_yyyymm"] > d["month_date_yyyymm"].max() - 100]   # the latest 12 months
    d["zip"] = d["postal_code"].str.zfill(5)
    g = d.groupby("zip")
    out = pd.DataFrame({"listing_price_per_m2": g["median_listing_price_per_square_foot"].mean() * SQFT_PER_M2,
                        "listing_median_area_m2": g["median_square_feet"].mean() / SQFT_PER_M2})
    out.to_parquet(cache)
    return out


# ----------------------------------------------------------------------------------------------------------------- public
def load_tract_housing(state_fips: str, state_abbr: str, data_dir: Optional[str] = None, fhfa_zip: bool = True, hud: bool = True) -> pd.DataFrame:
    """One state's 2020 tracts (``GEOID``) with every housing column listed in the module docstring (NaN where a source has no value).

    Args:
        state_fips: 2-digit state FIPS.
        state_abbr: State abbreviation.
        data_dir: Folder of the raw downloads; ``None`` = the pycensus cache.
        fhfa_zip: Add the FHFA ZIP-level house price index.
        hud: Add the HUD fair market rents.
    """
    st = str(state_fips).zfill(2)
    parts = []
    for suf, yr in ACS_PERIODS.items():
        raw = _acs(yr, st, data_dir)
        v = _to_2020(raw, 2020 if yr >= 2020 else 2010, st, state_abbr, data_dir)
        parts.append(v.add_suffix(suf))
    v0 = _to_2020(_sf3_2000(st, data_dir), 2000, st, state_abbr, data_dir)
    parts.append(v0.add_suffix("_2000"))
    tr = pd.concat(parts, axis=1)
    for suf in ("", "_2016", "_2000"):
        tr[f"rent_per_room_mean{suf}"] = tr[f"rent_median{suf}"] / tr[f"rooms_median{suf}"]
    # FHFA tract HPI (2010 tracts)
    h = _to_2020(_fhfa_tract(st, data_dir).rename(columns=str).rename_axis("GEOID").reset_index(), 2010, st, state_abbr, data_dir)
    hv = pd.DataFrame({f"house_price_index_fhfa{s}": h[str(y)] for s, y in FHFA_YEARS.items() if str(y) in h.columns})
    tr = tr.join(hv, how="outer")
    cagr = (tr["house_price_index_fhfa"] / tr["house_price_index_fhfa_2016"]) ** (1 / (FHFA_YEARS[""] - FHFA_YEARS["_2016"])) - 1
    tr["house_price_cagr_2016_2025_rate"] = cagr  # annualised growth per year (fraction)
    zxw = _zcta_tract(st, data_dir)
    if fhfa_zip:
        z = _fhfa_zip(data_dir)
        zt = _apply_xw(pd.DataFrame({f"house_price_index_fhfa_zip{s}": z[y] for s, y in FHFA_YEARS.items() if y in z.columns}), zxw)
        tr = tr.join(zt, how="outer")
    tr = tr.join(_apply_xw(_realtor_zip(data_dir), zxw), how="outer")
    if hud:
        for fy in HUD_SAFMR_YEARS:
            tr = tr.join(_apply_xw(_hud_safmr(fy, data_dir).rename(f"hud_safmr_2br_rent_mean_FY{fy}").to_frame(), zxw), how="outer")
        for fy in HUD_FMR_YEARS:
            f = _hud_fmr(fy, data_dir)
            tr[f"hud_fmr_2br_county_rent_mean_FY{fy}"] = tr.index.to_series().str[:5].map(f)
    tr = tr[tr.index.str.startswith(st)]
    return tr.rename_axis("GEOID").reset_index()
