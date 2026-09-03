"""Tests for pycensus.countries.usa.lodes_wac.loader, with get_lodes and boundary fetch monkeypatched out."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.usa import geography
from pycensus.countries.usa.lodes_wac import loader
from pycensus.countries.usa.lodes_wac.schema import SCHEMA


def _fake_get_lodes(version, state, year, lodes_type, agg_level, cache=True):
    geocode_col = "h_geocode" if lodes_type == "rac" else "w_geocode"
    return pd.DataFrame(
        {
            geocode_col: ["250250001001000", "250250002001000"],
            "C000": [10, 20],
            "CE01": [1, 2],
            "CE02": [3, 4],
            "CE03": [6, 14],
            "CA01": [2, 3],
            "CA02": [5, 10],
            "CA03": [3, 7],
        }
    )


def _fake_load_boundaries(level, state, year, erase_water=None):
    return gpd.GeoDataFrame(
        {"GEOID": ["250250001001000", "250250002001000"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=4326,
    )


@pytest.fixture(autouse=True)
def patch_network(monkeypatch):
    monkeypatch.setattr(loader, "get_lodes", _fake_get_lodes)
    monkeypatch.setattr(geography, "load_boundaries", _fake_load_boundaries)


def test_load_wac_returns_all_schema_columns_prefixed(tmp_path):
    gdf = loader.load_wac(states=["MA"], level="block", year=2021, cache_dir=str(tmp_path))
    expected = {SCHEMA.prefixed(name) for name in SCHEMA.columns}
    assert expected.issubset(set(gdf.columns))


def test_load_wac_jobs_total_values_come_through(tmp_path):
    gdf = loader.load_wac(states=["MA"], level="block", year=2021, cache_dir=str(tmp_path))
    assert gdf["lodes_wac_jobsTotal"].tolist() == [10.0, 20.0]


def test_load_raises_without_states_or_aoi(tmp_path):
    with pytest.raises(ValueError):
        loader.load_wac(level="block", year=2021, cache_dir=str(tmp_path))


def test_load_uses_geoid_geocode_for_join(monkeypatch, tmp_path):
    seen = {}

    def get_lodes(version, state, year, lodes_type, agg_level, cache=True):
        seen["agg_level"] = agg_level
        return _fake_get_lodes(version, state, year, lodes_type, agg_level, cache)

    monkeypatch.setattr(loader, "get_lodes", get_lodes)
    loader.load_wac(states=["MA"], level="blockgroup", year=2021, cache_dir=str(tmp_path))

    assert seen["agg_level"] == "block group"


def test_load_second_call_does_not_call_get_lodes_again(monkeypatch, tmp_path):
    calls = {"n": 0}

    def get_lodes(version, state, year, lodes_type, agg_level, cache=True):
        calls["n"] += 1
        return _fake_get_lodes(version, state, year, lodes_type, agg_level, cache)

    monkeypatch.setattr(loader, "get_lodes", get_lodes)

    loader.load_wac(states=["MA"], level="block", year=2021, cache_dir=str(tmp_path))
    assert calls["n"] == 1

    loader.load_wac(states=["MA"], level="block", year=2021, cache_dir=str(tmp_path))
    assert calls["n"] == 1


def test_load_cache_false_never_writes_to_disk(tmp_path):
    loader.load_wac(states=["MA"], level="block", year=2021, cache_dir=str(tmp_path), cache=False)
    assert list(tmp_path.rglob("*.parquet")) == []
