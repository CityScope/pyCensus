"""Tests for pycensus.cache: parquet persistence and incremental column fetching."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus import cache


@pytest.fixture
def boundary_gdf():
    return gpd.GeoDataFrame(
        {"GEOID": ["1", "2"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326
    )


def test_default_cache_dir_is_stable_and_nonempty():
    assert cache.default_cache_dir()
    assert cache.default_cache_dir() == cache.default_cache_dir()


def test_region_path_uses_default_when_cache_dir_none():
    path = cache.region_path(None, "USA", "tract", "25")
    assert str(path).startswith(cache.default_cache_dir())
    assert path.name == "25.parquet"


def test_region_path_layout():
    path = cache.region_path("/tmp/x", "USA", "tract", "25")
    assert path == cache.region_path("/tmp/x", "USA", "tract", "25")
    assert path.parts[-4:] == ("x", "USA", "tract", "25.parquet")


def test_read_cache_returns_none_when_missing(tmp_path):
    assert cache.read_cache(tmp_path / "nope.parquet") is None


def test_write_then_read_cache_round_trips(tmp_path, boundary_gdf):
    path = tmp_path / "sub" / "25.parquet"
    cache.write_cache(path, boundary_gdf)

    result = cache.read_cache(path)
    assert result is not None
    assert result["GEOID"].tolist() == ["1", "2"]
    assert path.exists()


def test_load_region_fetches_boundary_and_columns_when_no_cache(tmp_path, boundary_gdf):
    path = tmp_path / "25.parquet"
    boundary_calls = []
    column_calls = []

    def fetch_boundary():
        boundary_calls.append(1)
        return boundary_gdf.copy()

    def fetch_columns(missing):
        column_calls.append(list(missing))
        return pd.DataFrame({"GEOID": ["1", "2"], "acs_population": [10.0, 20.0]})

    gdf = cache.load_region(path, "GEOID", ["acs_population"], fetch_boundary, fetch_columns)

    assert boundary_calls == [1]
    assert column_calls == [["acs_population"]]
    assert gdf["acs_population"].tolist() == [10.0, 20.0]
    assert path.exists()


def test_load_region_second_call_reads_fully_from_cache(tmp_path, boundary_gdf):
    path = tmp_path / "25.parquet"

    def fetch_boundary():
        return boundary_gdf.copy()

    def fetch_columns(missing):
        return pd.DataFrame({"GEOID": ["1", "2"], "acs_population": [10.0, 20.0]})

    cache.load_region(path, "GEOID", ["acs_population"], fetch_boundary, fetch_columns)

    calls = []

    def fetch_boundary_2():
        calls.append("boundary")
        return boundary_gdf.copy()

    def fetch_columns_2(missing):
        calls.append(("columns", list(missing)))
        return pd.DataFrame()

    gdf = cache.load_region(path, "GEOID", ["acs_population"], fetch_boundary_2, fetch_columns_2)

    assert calls == []
    assert gdf["acs_population"].tolist() == [10.0, 20.0]


def test_load_region_only_fetches_newly_missing_columns(tmp_path, boundary_gdf):
    path = tmp_path / "25.parquet"

    cache.load_region(
        path,
        "GEOID",
        ["acs_population"],
        lambda: boundary_gdf.copy(),
        lambda missing: pd.DataFrame({"GEOID": ["1", "2"], "acs_population": [10.0, 20.0]}),
    )

    seen_missing = []

    def fetch_columns_2(missing):
        seen_missing.append(list(missing))
        return pd.DataFrame({"GEOID": ["1", "2"], "dhc_population": [30.0, 40.0]})

    gdf = cache.load_region(
        path,
        "GEOID",
        ["acs_population", "dhc_population"],
        lambda: boundary_gdf.copy(),
        fetch_columns_2,
    )

    assert seen_missing == [["dhc_population"]]
    assert gdf["acs_population"].tolist() == [10.0, 20.0]
    assert gdf["dhc_population"].tolist() == [30.0, 40.0]


def test_load_region_use_cache_false_always_fetches_and_never_persists(tmp_path, boundary_gdf):
    path = tmp_path / "25.parquet"
    calls = {"boundary": 0, "columns": 0}

    def fetch_boundary():
        calls["boundary"] += 1
        return boundary_gdf.copy()

    def fetch_columns(missing):
        calls["columns"] += 1
        return pd.DataFrame({"GEOID": ["1", "2"], "acs_population": [10.0, 20.0]})

    cache.load_region(path, "GEOID", ["acs_population"], fetch_boundary, fetch_columns, use_cache=False)
    cache.load_region(path, "GEOID", ["acs_population"], fetch_boundary, fetch_columns, use_cache=False)

    assert calls == {"boundary": 2, "columns": 2}
    assert not path.exists()


def test_load_region_with_no_columns_skips_fetch_columns(tmp_path, boundary_gdf):
    path = tmp_path / "25.parquet"
    called = []

    gdf = cache.load_region(
        path, "GEOID", [], lambda: boundary_gdf.copy(), lambda missing: called.append(missing)
    )

    assert called == []
    assert list(gdf.columns) == ["GEOID", "geometry"]
