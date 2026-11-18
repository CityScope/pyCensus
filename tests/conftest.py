"""Shared pytest fixtures for the pyCensus test suite.

Technical aspects:
    Fixtures build small synthetic GeoDataFrames instead of hitting any
    real Census/pygris network endpoint -- network-touching functions
    (`pygris.data.get_census`, `pygris.data.get_lodes`, boundary fetchers)
    are monkeypatched per-test with these fixtures' data instead.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box


@pytest.fixture
def two_tract_gdf() -> gpd.GeoDataFrame:
    """Two adjacent unit-ish squares with a GEOID column, no attributes."""
    return gpd.GeoDataFrame(
        {"GEOID": ["25025000100", "25025000200"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )


@pytest.fixture
def acs_gdf(two_tract_gdf) -> gpd.GeoDataFrame:
    """Two-tract GeoDataFrame carrying ``acs_``-prefixed attribute columns."""
    gdf = two_tract_gdf.copy()
    gdf["acs_population"] = [100.0, 200.0]
    gdf["acs_households"] = [40.0, 90.0]
    gdf["acs_households_owner"] = [20.0, 50.0]
    gdf["acs_households_renter"] = [20.0, 40.0]
    return gdf


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: needs live servers, downloads or API keys (skipped by default; run with `-m network`)"
    )


def pytest_collection_modifyitems(config, items):
    """`test_real_*` tests check real downloads against published figures: marked `network`, run only with `-m network`."""
    run_network = "network" in (config.getoption("-m") or "")
    skip = pytest.mark.skip(reason="needs live servers / downloads / keys: run with -m network")
    for item in items:
        if item.name.startswith("test_real_"):
            item.add_marker(pytest.mark.network)
            if not run_network:
                item.add_marker(skip)
