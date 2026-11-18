"""`load_boundaries("state", None, year)` returns every state (the US building inventory needs them all to find an area's states)."""

import geopandas as gpd
from shapely.geometry import box

from pycensus.census.countries.usa import constants, geography


def _fake_states(year=None, cache=False):
    return gpd.GeoDataFrame({"STUSPS": ["MA", "NH"], "GEOID": ["25", "33"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326)


def test_all_states_when_state_is_none(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "state", _fake_states)
    g = geography.load_boundaries("state", None, 2023, erase_water=False)
    assert sorted(g["GEOID"]) == ["25", "33"]


def test_one_state(monkeypatch):
    monkeypatch.setitem(constants.GEOMETRY_FUNCS, "state", _fake_states)
    g = geography.load_boundaries("state", "NH", 2023, erase_water=False)
    assert g["GEOID"].tolist() == ["33"]
