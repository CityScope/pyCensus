"""Tests for pycensus.countries.eu (Eurostat / GISCO) and pycensus.resolution, with no network.

Technical aspects:
    Downloads and API calls are monkeypatched with tiny synthetic tables. The real sources were checked live on
    2026-11-17: Census 2021 grid V3 Spain 47.371 M vs INE 47.385 M; LAU 2023 Spain
    48.085 M vs INE 48.09 M; Eurostat API values for ES30 / ES300.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus import resolution as R
from pycensus.countries import eu
from pycensus.countries.eu import census_grid, constants, eurostat, lau
from pycensus.countries.eu.eurostat import api

SCHEMA_DIR = Path(eu.__file__).parent / "schema"
GLOBAL = {f["feature_name"] for f in json.loads((Path(R.__file__).parent / "schemas" / "global_schema.json").read_text())}


# ---- constants / schema ----------------------------------------------------------------------------------------------
def test_eurostat_codes():
    assert constants.to_eurostat("GR") == "EL"
    assert constants.to_eurostat("es") == "ES"
    assert len(constants.EU27) == 27 and "EL" in constants.EU27


@pytest.mark.parametrize("source", ["census_grid", "lau", "eurostat"])
def test_schema_features_are_global_and_complete(source):
    j = json.loads((SCHEMA_DIR / f"{source}_schema.json").read_text())
    assert j["resolution"] == eu.RESOLUTION[source]
    for f in j["features"]:
        for k in ("category", "feature_name", "original_name", "definition", "type", "resampling_up", "resampling_down"):
            assert k in f, (source, f.get("feature_name"), k)
        assert f["feature_name"] in GLOBAL, f["feature_name"]


def test_resolution_flags():
    assert eu.RESOLUTION == {"census_grid": "high", "lau": "low", "eurostat": "low"}


# ---- census grid -----------------------------------------------------------------------------------------------------
def _grid_table():
    codes = list(census_grid.loader.COLUMNS)
    rows = []
    for i, (gid, cc, t) in enumerate([("CRS3035RES1000mN2000000E3000000", "ES", 120), ("CRS3035RES1000mN2000000E3001000", "ES-PT", 80),
                                      ("CRS3035RES1000mN2001000E3000000", "ES", 0), ("ES_unallocated", "ES", 7)]):
        r = {c: 10 for c in codes}
        r.update({"GRD_ID": gid, "CNTR_ID": cc, "T": t, "POPULATED": int(t > 0), "LAND_SURFACE": 1.0})
        rows.append(r)
    rows[0]["EMP"] = -9999
    rows[1]["OTH"] = -8888
    return pd.DataFrame(rows)


@pytest.fixture
def grid(tmp_path, monkeypatch):
    p = tmp_path / "grid.parquet"
    _grid_table().to_parquet(p)
    monkeypatch.setattr(census_grid.loader, "table_path", lambda data_dir=None: p)
    return p


def test_grid_load_cells_and_missing_codes(grid):
    g = census_grid.load()
    assert len(g) == 2   # unpopulated cell and unallocated row dropped
    assert g.crs.to_epsg() == 4326
    assert set(census_grid.loader.COLUMNS.values()) <= set(g.columns)
    a = g.set_index("GEOID")
    assert np.isnan(a.loc["CRS3035RES1000mN2000000E3000000", "employedResidents"])       # -9999 -> NaN
    assert np.isnan(a.loc["CRS3035RES1000mN2000000E3001000", "foreignBornPopulation"])   # -8888 in OTH -> NaN sum
    assert a.loc["CRS3035RES1000mN2000000E3000000", "foreignBornPopulation"] == 20
    areas = g.to_crs(3035).area / 1e6
    assert np.allclose(areas, 1.0, atol=1e-3)
    x0, y0, _, _ = g.to_crs(3035).iloc[[0]].total_bounds
    assert (round(x0), round(y0)) == (3000000, 2000000)   # GRD_ID is the south-west corner


def test_grid_country_filter_keeps_border_cells(grid):
    assert len(census_grid.load(countries="PT")) == 1
    assert len(census_grid.load(countries="ES")) == 2


def test_grid_aoi(grid):
    g = census_grid.load()
    one = gpd.GeoDataFrame(geometry=[g.to_crs(3035).geometry.iloc[0].buffer(-100)], crs=3035)
    assert census_grid.load(aoi=one)["GEOID"].tolist() == [g["GEOID"].iloc[0]]


def test_grid_unallocated(grid):
    u = census_grid.unallocated()
    assert u["GEOID"].tolist() == ["ES_unallocated"] and u["population"].iloc[0] == 7 and u["country"].iloc[0] == "ES"


# ---- LAU -------------------------------------------------------------------------------------------------------------
def test_lau_vintage_per_country(monkeypatch):
    tabs = {2024: pd.DataFrame({"CNTR_CODE": ["ES", "ES", "DE"], "POP_2024": [0, 0, 5]}),
            2023: pd.DataFrame({"CNTR_CODE": ["ES", "ES", "DE"], "POP_2023": [3, 4, 5]}),
            2022: pd.DataFrame({"CNTR_CODE": ["ES"], "POP_2022": [1]}),
            2021: pd.DataFrame({"CNTR_CODE": ["IS"], "POP_2021": [0]})}
    monkeypatch.setattr(lau.loader, "_attrs", lambda y, d=None: tabs[y])
    assert lau.vintage_by_country() == {"DE": 2024, "ES": 2023}


def test_lau_load_area_from_geometry(monkeypatch):
    monkeypatch.setattr(lau.loader, "vintage_by_country", lambda d=None: {"ES": 2023})
    sq = gpd.GeoDataFrame({"GEOID": ["ES_1"], "country": ["ES"], "lau_id": ["1"], "name": ["A"], "POP_2023": [100], "AREA_KM2": [999.0]},
                          geometry=[box(3000000, 2000000, 3002000, 2002000)], crs=3035).to_crs(4326)
    monkeypatch.setattr(lau.loader.geography, "lau", lambda cc, y, d=None: sq)
    g = lau.load("ES")
    assert g["population"].iloc[0] == 100 and g["year"].iloc[0] == 2023
    assert abs(g["landAreaKm2"].iloc[0] - 4.0) < 1e-3   # GISCO's (wrong) AREA_KM2 is not used
    with pytest.raises(ValueError):
        lau.load("IS")


# ---- Eurostat API ----------------------------------------------------------------------------------------------------
def _jsonstat(geo, time, values, extra=None):
    ids = ["freq", "unit"] + (list(extra) if extra else []) + ["geo", "time"]
    dims = {"freq": ["A"], "unit": ["PC"], **(extra or {}), "geo": geo, "time": time}
    size = [len(dims[d]) for d in ids]
    return {"id": ids, "size": size, "value": values,
            "dimension": {d: {"category": {"index": {c: i for i, c in enumerate(dims[d])}}} for d in ids}}


def test_parse_jsonstat_sparse():
    df = api.parse_jsonstat(_jsonstat(["ES30", "ES51"], ["2023", "2024"], {"0": 1.0, "3": 4.0}))
    assert df.to_dict("records") == [{"geo": "ES30", "time": "2023", "value": 1.0}, {"geo": "ES51", "time": "2024", "value": 4.0}]


def test_parse_jsonstat_refuses_unfixed_dimension():
    with pytest.raises(api.EurostatError):
        api.parse_jsonstat(_jsonstat(["ES30"], ["2024"], {"0": 1.0}, extra={"sex": ["M", "F"]}))


def test_eurostat_load_latest_year_scale_and_nesting(monkeypatch):
    n2 = gpd.GeoDataFrame({"GEOID": ["ES30"], "country": ["ES"], "name": ["Madrid"], "nuts_level": [2]}, geometry=[box(0, 0, 1, 1)], crs=4326)
    n3 = gpd.GeoDataFrame({"GEOID": ["ES300"], "country": ["ES"], "name": ["Madrid"], "nuts_level": [3]}, geometry=[box(0, 0, 1, 1)], crs=4326)
    monkeypatch.setattr(eurostat.loader.geography, "nuts", lambda level, cc=None, year=2024, d=None: n2 if level == 2 else n3)
    data = {"lfst_r_lfu3rt": pd.DataFrame({"geo": ["ES30", "ES30"], "time": ["2024", "2025"], "value": [9.0, 8.0]}),
            "nama_10r_3gdp": pd.DataFrame({"geo": ["ES300"], "time": ["2023"], "value": [47900.0]})}
    monkeypatch.setattr(eurostat.loader.api, "fetch", lambda ds, f, since=None, geos=None: data[ds])
    out = eurostat.load("ES", features=["unemploymentRate", "gdpPerCapitaPps"], level=3)
    r = out.iloc[0]
    assert r["GEOID"] == "ES300" and r["gdpPerCapitaPps"] == 47900.0
    assert r["unemploymentRate"] == pytest.approx(0.08) and r["unemploymentRate_year"] == 2025   # latest, % -> share, NUTS2 -> NUTS3
    with pytest.raises(ValueError):
        eurostat.load("ES", features=["gdpPerCapitaPps"], level=2)   # NUTS 3 feature at NUTS 2
    with pytest.raises(ValueError):
        eurostat.load("ES", features=["nope"])


# ---- resolution ------------------------------------------------------------------------------------------------------
def _units(cells, pop):
    return gpd.GeoDataFrame({"GEOID": [str(i) for i in range(len(cells))], "population": pop}, geometry=cells, crs=3035)


def test_resolution_classes():
    muni = _units([box(0, 0, 4000, 4000)], [50_000])                       # one large municipality, 16 km2
    grid = _units([box(x, y, x + 1000, y + 1000) for x in range(0, 4000, 1000) for y in range(0, 4000, 1000)], [6000] * 16)
    assert R.classify(grid, muni).resolution == R.HIGH
    halves = _units([box(0, 0, 2000, 4000), box(2000, 0, 4000, 4000)], [25_000, 25_000])   # split, but 8 km2 units of 25k
    res = R.classify(halves, muni)
    assert res.resolution == R.NORMAL and len(res.high_failures) == 2
    assert R.classify(muni, muni).resolution == R.LOW                       # the municipality itself
    assert R.classify(muni, is_municipal=True).resolution == R.LOW
    small = _units([box(0, 0, 4000, 4000)], [4_000])                       # small municipality may stay whole
    assert R.classify(small, small).resolution == R.HIGH
    village = _units([box(0, 0, 4000, 4000)], [8_000])                     # whole, under 10k (normal) but > 5k on 16 km2
    assert R.classify(village, village).resolution == R.NORMAL
    with pytest.raises(ValueError):
        R.classify(grid)


def test_resolution_rules_of_use():
    assert R.usable_for("high", "census_tab") and not R.usable_for("normal", "census_tab")
    assert R.usable_for("normal", "regression") and not R.usable_for("low", "regression")
    with pytest.raises(ValueError):
        R.usable_for("high", "maps")
