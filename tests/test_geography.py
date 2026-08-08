"""Tests for pycensus.USA.geography, with pygris network calls monkeypatched out."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from pycensus.USA import constants, geography


def _fake_geometry_func(geoid_col="GEOID20", geoms=None, geoids=None):
    geoms = geoms or [box(0, 0, 1, 1), box(1, 0, 2, 1)]
    geoids = geoids or ["25025000100", "25025000200"]

    def func(state=None, year=None, cache=None):
        return gpd.GeoDataFrame({geoid_col: geoids}, geometry=geoms, crs=4326)

    return func


def test_load_boundaries_normalizes_geoid_column(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", _fake_geometry_func(geoid_col="GEOID"))
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": False})

    gdf = geography.load_boundaries("tract", "MA", 2023)

    assert list(gdf.columns) == ["GEOID", "geometry"]
    assert gdf["GEOID"].tolist() == ["25025000100", "25025000200"]


def test_load_boundaries_renames_non_geoid_id_column(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", _fake_geometry_func(geoid_col="GEOID20"))
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": False})

    gdf = geography.load_boundaries("tract", "MA", 2023)

    assert "GEOID" in gdf.columns
    assert "GEOID20" not in gdf.columns


def test_load_boundaries_casts_geoid_to_string(monkeypatch):
    def func(state=None, year=None, cache=None):
        return gpd.GeoDataFrame({"GEOID": [25025000100]}, geometry=[box(0, 0, 1, 1)], crs=4326)

    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", func)
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": False})

    gdf = geography.load_boundaries("tract", "MA", 2023)
    assert gdf["GEOID"].iloc[0] == "25025000100"
    assert isinstance(gdf["GEOID"].iloc[0], str)


def test_load_boundaries_calls_erase_water_when_enabled(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", _fake_geometry_func())
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": True})

    calls = []

    def fake_erase_water(gdf, year=None, cache=None):
        calls.append(True)
        return gdf

    monkeypatch.setattr(geography.pygris.utils, "erase_water", fake_erase_water)

    geography.load_boundaries("tract", "MA", 2023)
    assert calls == [True]


def test_load_boundaries_unknown_level_raises_keyerror():
    with pytest.raises(KeyError):
        geography.load_boundaries("not_a_level", "MA", 2023)


def test_load_boundaries_multi_concatenates_states(monkeypatch):
    def func(state=None, year=None, cache=None):
        offset = 0 if state == "MA" else 10
        return gpd.GeoDataFrame(
            {"GEOID": [f"{offset}1", f"{offset}2"]},
            geometry=[box(offset, 0, offset + 1, 1), box(offset + 1, 0, offset + 2, 1)],
            crs=4326,
        )

    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", func)
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": False})

    gdf = geography.load_boundaries_multi("tract", ["MA", "RI"], 2023)
    assert sorted(gdf["GEOID"].tolist()) == ["01", "02", "101", "102"]


def test_load_boundaries_multi_filters_to_aoi(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "tract", _fake_geometry_func())
    monkeypatch.setattr(constants, "ERASE_WATER", {**constants.ERASE_WATER, "tract": False})

    aoi = gpd.GeoDataFrame(geometry=[box(0, 0, 0.5, 1)], crs=4326)
    gdf = geography.load_boundaries_multi("tract", "MA", 2023, aoi=aoi)

    assert gdf["GEOID"].tolist() == ["25025000100"]


def test_states_in_aoi_returns_intersecting_state_abbrs(monkeypatch):
    fake_states = gpd.GeoDataFrame(
        {"STUSPS": ["MA", "RI"]},
        geometry=[box(0, 0, 1, 1), box(10, 10, 11, 11)],
        crs=4326,
    )
    monkeypatch.setattr(geography.pygris, "states", lambda year=None, cache=None: fake_states)

    aoi = gpd.GeoDataFrame(geometry=[box(0.2, 0.2, 0.5, 0.5)], crs=4326)
    result = geography.states_in_aoi(aoi, 2023)

    assert result == ["MA"]
