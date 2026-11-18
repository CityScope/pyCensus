# -*- coding: utf-8 -*-
"""MIT Election Data + Science Lab (MEDSL) 2024 precinct-level returns (Harvard Dataverse, doi:10.7910/DVN/NYTPDU) -- UNOFFICIAL.

One file per state with the state's own precinct label (``precinct``), ``county_fips``, ``office``, ``party_simplified`` and ``votes`` by vote ``mode``
(some states also carry a ``TOTAL`` mode that equals the sum of the others: it is used when present, else all modes are summed). It has no geometry and no
Census voting-district code, so a precinct only gets a polygon when the state publishes boundaries keyed by the same label (checked on Delaware, where
all 533 precincts equal the official report, and Hawaii, where the statewide totals are exact). Matching to Census VTD NAMEs alone is not reliable
(0-52% of precincts matched on NE, PA, KS, MO, NC, DE).
"""

from __future__ import annotations

import json

import pandas as pd
import requests

from pycensus.elections_common import default_elections_cache, download

DATASET = "doi:10.7910/DVN/NYTPDU"
API = "https://dataverse.harvard.edu/api"
ATTRIBUTION = "MIT Election Data and Science Lab, Precinct-Level Returns 2024 by Individual State (Harvard Dataverse, doi:10.7910/DVN/NYTPDU). Unofficial compilation."


NON_CANDIDATE = r"TOTAL VOTES|TOTAL BALLOTS|BALLOTS CAST|UNDERVOTE|OVERVOTE|BLANK|REGISTERED|TURNOUT|^TOTAL$|NO VOTE"


def _files(cache_dir=None) -> dict:
    root = default_elections_cache(cache_dir) / "medsl_2024"
    root.mkdir(parents=True, exist_ok=True)
    idx = root / "files.json"
    if not idx.is_file():
        d = requests.get(f"{API}/datasets/:persistentId/", params={"persistentId": DATASET}, headers={"User-Agent": "pycensus"}, timeout=120).json()
        idx.write_text(json.dumps({f["label"]: f["dataFile"]["id"] for f in d["data"]["latestVersion"]["files"]}))
    return json.loads(idx.read_text())


def load_president(state_abbr: str, cache_dir=None) -> pd.DataFrame:
    """Presidential votes by (county_fips, precinct): columns ``county_fips``, ``precinct``, ``votes_dem``, ``votes_rep``, ``votes_total``.

    Args:
        state_abbr: State abbreviation.
        cache_dir: Cache folder; ``None`` = the pycensus cache.
    """
    files = _files(cache_dir)
    label = next(k for k in files if k.startswith(f"2024-{state_abbr.lower()}-precinct-general"))
    path = download(f"{API}/access/datafile/{files[label]}?format=original", default_elections_cache(cache_dir) / "medsl_2024" / f"{state_abbr.lower()}.csv", timeout=1800)
    d = pd.read_csv(path, dtype=str, low_memory=False, usecols=lambda c: c in ("precinct", "office", "candidate", "votes", "county_fips", "party_simplified", "mode", "special", "writein"))
    d = d[(d["office"] == "US PRESIDENT") & (d.get("special", "FALSE") != "TRUE")].copy()
    d["votes"] = pd.to_numeric(d["votes"], errors="coerce").fillna(0.0)
    if "candidate" in d.columns:   # some states carry summary rows (total ballots cast, under/overvotes, registered voters): not votes for a candidate
        d = d[~d["candidate"].fillna("").str.upper().str.contains(NON_CANDIDATE)]
    if "mode" in d.columns and (d["mode"] == "TOTAL").any():
        d = d[d["mode"] == "TOTAL"]
    d["county_fips"] = d["county_fips"].astype(str).str.zfill(5)
    g = d.groupby(["county_fips", "precinct"])
    out = pd.DataFrame({
        "votes_dem": d[d["party_simplified"] == "DEMOCRAT"].groupby(["county_fips", "precinct"])["votes"].sum(),
        "votes_rep": d[d["party_simplified"] == "REPUBLICAN"].groupby(["county_fips", "precinct"])["votes"].sum(),
        "votes_total": g["votes"].sum(),
    }).fillna(0.0).reset_index()
    return out
