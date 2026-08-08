"""Tests for pycensus.USA.dhc.loader, with the Census API and boundary fetch monkeypatched out."""

from __future__ import annotations

import geopandas as gpd
import polars as pl
import pytest
from shapely.geometry import box

from pycensus.USA import api, geography
from pycensus.USA.dhc import loader
from pycensus.USA.dhc.schema import SCHEMA


def _fake_fetch_variables(dataset, year, level, state, variables, api_key=None):
    return pl.DataFrame({"GEOID": ["25025000100", "25025000200"], **{v: [3.0, 4.0] for v in variables}})


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
    gdf = loader.load(states=["MA"], level="block", year=2020, api_key="k", cache_dir=str(tmp_path))

    expected = {SCHEMA.prefixed(name) for name in SCHEMA.columns}
    assert expected.issubset(set(gdf.columns))


def test_load_uses_unsuffixed_dhc_codes(monkeypatch, tmp_path):
    """DHC variable codes must be requested exactly (no ACS 'E' suffix appended)."""
    seen_variables = []

    def fetch(dataset, year, level, state, variables, api_key=None):
        seen_variables.extend(variables)
        return _fake_fetch_variables(dataset, year, level, state, variables, api_key)

    monkeypatch.setattr(api, "fetch_variables", fetch)
    loader.load(states=["MA"], level="block", year=2020, api_key="k", cache_dir=str(tmp_path))

    assert "P1_001N" in seen_variables
    assert "P1_001NE" not in seen_variables


def test_load_raises_without_states_or_aoi(tmp_path):
    with pytest.raises(ValueError):
        loader.load(level="block", year=2020, api_key="k", cache_dir=str(tmp_path))


def test_load_population_values_come_through(tmp_path):
    gdf = loader.load(states=["MA"], level="block", year=2020, api_key="k", cache_dir=str(tmp_path))
    assert gdf["dhc_population"].tolist() == [3.0, 4.0]


def test_load_shares_cache_file_with_acs_for_same_level_region(tmp_path):
    """DHC and ACS must merge into the same per-level/region parquet file, not separate ones."""
    from pycensus import cache as cache_store

    loader.load(states=["MA"], level="block", year=2020, api_key="k", cache_dir=str(tmp_path))

    path = cache_store.region_path(str(tmp_path), "USA", "block", "25")
    assert path.exists()
    cached = cache_store.read_cache(path)
    assert any(c.startswith("dhc_") for c in cached.columns)
