"""Tests for pycensus.USA.acs.loader, with the Census API and boundary fetch monkeypatched out."""

from __future__ import annotations

import geopandas as gpd
import polars as pl
import pytest
from shapely.geometry import box

from pycensus.USA import api, geography
from pycensus.USA.acs import loader
from pycensus.USA.acs.schema import SCHEMA


def _fake_fetch_variables(dataset, year, level, state, variables, api_key=None):
    return pl.DataFrame({"GEOID": ["25025000100", "25025000200"], **{v: [1.0, 2.0] for v in variables}})


def _fake_load_boundaries(level, state, year, erase_water=None):
    return gpd.GeoDataFrame(
        {"GEOID": ["25025000100", "25025000200"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=4326,
    )


@pytest.fixture(autouse=True)
def patch_network(monkeypatch):
    monkeypatch.setattr(api, "fetch_variables", _fake_fetch_variables)
    monkeypatch.setattr(geography, "load_boundaries", _fake_load_boundaries)


def test_load_returns_all_schema_columns_prefixed(tmp_path):
    gdf = loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))

    expected = {SCHEMA.prefixed(name) for name in SCHEMA.columns}
    assert expected.issubset(set(gdf.columns))
    assert "GEOID" in gdf.columns
    assert gdf.geometry.name == "geometry"


def test_load_accepts_single_state_string(tmp_path):
    gdf = loader.load(states="MA", level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert len(gdf) == 2


def test_load_raises_without_states_or_aoi(tmp_path):
    with pytest.raises(ValueError):
        loader.load(level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))


def test_load_resolves_states_from_aoi(monkeypatch, tmp_path):
    monkeypatch.setattr(geography, "states_in_aoi", lambda aoi, year: ["MA"])
    aoi = gpd.GeoDataFrame(geometry=[box(0, 0, 2, 1)], crs=4326)

    gdf = loader.load(aoi=aoi, level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert len(gdf) == 2


def test_load_clips_result_to_aoi(monkeypatch, tmp_path):
    monkeypatch.setattr(geography, "states_in_aoi", lambda aoi, year: ["MA"])
    aoi = gpd.GeoDataFrame(geometry=[box(0, 0, 0.5, 1)], crs=4326)

    gdf = loader.load(aoi=aoi, level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert gdf["GEOID"].tolist() == ["25025000100"]


def test_load_population_values_come_through(tmp_path):
    gdf = loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert gdf["acs_population"].tolist() == [1.0, 2.0]


def test_load_defaults_to_latest_year(monkeypatch, tmp_path):
    seen_years = []

    def fetch(dataset, year, level, state, variables, api_key=None):
        seen_years.append(year)
        return _fake_fetch_variables(dataset, year, level, state, variables, api_key)

    monkeypatch.setattr(api, "fetch_variables", fetch)
    loader.load(states=["MA"], level="tract", year="latest", api_key="k", cache_dir=str(tmp_path))

    assert seen_years and all(y == seen_years[0] for y in seen_years)


def test_load_second_call_does_not_refetch_from_cache(monkeypatch, tmp_path):
    calls = {"fetch": 0}

    def fetch(dataset, year, level, state, variables, api_key=None):
        calls["fetch"] += 1
        return _fake_fetch_variables(dataset, year, level, state, variables, api_key)

    monkeypatch.setattr(api, "fetch_variables", fetch)

    loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert calls["fetch"] == 1

    loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path))
    assert calls["fetch"] == 1  # second call served entirely from the parquet cache


def test_load_cache_false_bypasses_persistence(monkeypatch, tmp_path):
    calls = {"fetch": 0}

    def fetch(dataset, year, level, state, variables, api_key=None):
        calls["fetch"] += 1
        return _fake_fetch_variables(dataset, year, level, state, variables, api_key)

    monkeypatch.setattr(api, "fetch_variables", fetch)

    loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path), cache=False)
    loader.load(states=["MA"], level="tract", year=2023, api_key="k", cache_dir=str(tmp_path), cache=False)

    assert calls["fetch"] == 2
    assert list(tmp_path.rglob("*.parquet")) == []
