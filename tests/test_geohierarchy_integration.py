"""End-to-end checks that pyCensus loader output plugs directly into geohierarchy.GeoHierarchy."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from geohierarchy import GeoHierarchy
from pycensus.USA.acs.schema import SCHEMA as ACS_SCHEMA


def test_acs_output_shape_adds_to_geohierarchy_and_propagates(acs_gdf):
    hierarchy = GeoHierarchy()
    hierarchy.add_level("tract", acs_gdf, id_col="GEOID", agg=ACS_SCHEMA.aggregations())

    result = hierarchy["tract"]
    assert "acs_population" in result.columns
    assert result["acs_population"].tolist() == [100.0, 200.0]


def test_acs_columns_propagate_to_a_parent_level(acs_gdf):
    hierarchy = GeoHierarchy()
    hierarchy.add_level("tract", acs_gdf, id_col="GEOID", agg=ACS_SCHEMA.aggregations())

    county_gdf = gpd.GeoDataFrame(
        {"GEOID": ["25025"]}, geometry=[box(0, 0, 2, 1)], crs="EPSG:4326"
    )
    hierarchy.add_level("county", county_gdf, id_col="GEOID", parent=None, child="tract")

    county = hierarchy["county"]
    assert county["acs_population"].iloc[0] == 300.0
    assert county["acs_households"].iloc[0] == 130.0


def test_acs_accessor_still_works_after_round_trip_through_geohierarchy(acs_gdf):
    hierarchy = GeoHierarchy()
    hierarchy.add_level("tract", acs_gdf, id_col="GEOID", agg=ACS_SCHEMA.aggregations())

    result = hierarchy["tract"]
    assert result.acs["population"].tolist() == [100.0, 200.0]
    assert (result.acs["population"].density > 0).all()
    assert result.acs["households_owner"].relative.tolist() == pytest.approx([0.5, 50 / 90])
