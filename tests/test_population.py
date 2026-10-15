import geopandas as gpd
import pytest
import shapely

import pycensus
from pycensus import get_population
from pycensus.worldwide import worldpop

AOI = gpd.GeoDataFrame(geometry=[shapely.box(0, 0, 0.01, 0.01)], crs=4326)


def test_unknown_source():
    with pytest.raises(ValueError):
        get_population(AOI, source="nope")


def test_census_only_for_implemented_countries(monkeypatch):
    monkeypatch.setattr(worldpop, "get_country_region", lambda *a, **k: "US")
    with pytest.raises(NotImplementedError, match="worldpop"):
        get_population(AOI, source="census")


def test_census_rejects_kids_only():
    with pytest.raises(NotImplementedError):
        get_population(AOI, source="census", kids_only=True)


def test_census_countries_lists_spain():
    assert "ES" in pycensus.census_countries()
