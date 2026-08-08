"""Tests for pycensus.accessors: ColumnView (.density / .relative) and accessor registration."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from pycensus.accessors import ColumnView, register_source_accessor
from pycensus.schema import ColumnSchema


@pytest.fixture
def schema() -> ColumnSchema:
    schema = ColumnSchema(prefix="test")
    schema.add("population", ["P1"])
    schema.add("subgroup", ["S1"], relative_to="population")
    schema.add("other_subgroup", ["S2"], relative_to="population")
    return schema


@pytest.fixture
def polygon_gdf() -> gpd.GeoDataFrame:
    # A 1x1 degree square is ~ (111km)^2, used only to check the division
    # runs and shrinks the value, not for an exact expected number.
    return gpd.GeoDataFrame(
        {
            "test_population": [100.0, 200.0],
            "test_subgroup": [40.0, 100.0],
            "test_other_subgroup": [10.0, 20.0],
        },
        geometry=[box(0, 0, 1, 1), box(10, 10, 11, 11)],
        crs="EPSG:4326",
    )


def test_getitem_single_column_returns_series_backed_view(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_population"], polygon_gdf, schema)
    assert isinstance(view.data, pd.Series)
    assert view.data.tolist() == [100.0, 200.0]


def test_density_divides_by_area_for_polygons(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_population"], polygon_gdf, schema)
    density = view.density
    assert (density > 0).all()
    assert (density < view.data).all()  # area in m2 is huge, so density << raw value


def test_density_divides_by_length_for_lines(schema):
    gdf = gpd.GeoDataFrame(
        {"test_population": [10.0]},
        geometry=[LineString([(0, 0), (0, 1)])],
        crs="EPSG:4326",
    )
    view = ColumnView(gdf["test_population"], gdf, schema)
    density = view.density
    assert density.iloc[0] > 0
    assert density.iloc[0] < 10.0


def test_relative_single_column(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_subgroup"], polygon_gdf, schema)
    rel = view.relative
    assert rel.tolist() == pytest.approx([0.4, 0.5])


def test_relative_multi_column(polygon_gdf, schema):
    view = ColumnView(polygon_gdf[["test_subgroup", "test_other_subgroup"]], polygon_gdf, schema)
    rel = view.relative
    assert isinstance(rel, pd.DataFrame)
    assert rel["test_subgroup"].tolist() == pytest.approx([0.4, 0.5])
    assert rel["test_other_subgroup"].tolist() == pytest.approx([0.1, 0.1])


def test_relative_raises_when_no_total_registered(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_population"], polygon_gdf, schema)
    with pytest.raises(ValueError, match="relative_to"):
        _ = view.relative


def test_getattr_delegates_to_underlying_series(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_population"], polygon_gdf, schema)
    assert view.sum() == 300.0
    assert view.mean() == 150.0


def test_repr_delegates_to_underlying_data(polygon_gdf, schema):
    view = ColumnView(polygon_gdf["test_population"], polygon_gdf, schema)
    assert repr(view) == repr(view.data)


def test_register_source_accessor_enables_bracket_access(polygon_gdf):
    schema = ColumnSchema(prefix="regacc")
    schema.add("population", ["P1"])
    register_source_accessor(schema)

    gdf = polygon_gdf.rename(columns={"test_population": "regacc_population"})
    view = gdf.regacc["population"]
    assert isinstance(view, ColumnView)
    assert view.data.tolist() == [100.0, 200.0]


def test_accessor_accepts_already_prefixed_names(polygon_gdf):
    schema = ColumnSchema(prefix="regacc2")
    schema.add("population", ["P1"])
    register_source_accessor(schema)

    gdf = polygon_gdf.rename(columns={"test_population": "regacc2_population"})
    assert gdf.regacc2["regacc2_population"].data.tolist() == gdf.regacc2["population"].data.tolist()


def test_accessor_columns_lists_logical_names():
    schema = ColumnSchema(prefix="regacc3")
    schema.add("population", ["P1"])
    schema.add("households", ["H1"])
    register_source_accessor(schema)

    gdf = gpd.GeoDataFrame(
        {"regacc3_population": [1.0], "regacc3_households": [1.0]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:4326",
    )
    assert set(gdf.regacc3.columns) == {"population", "households"}


def test_accessor_multi_column_getitem_returns_dataframe_view():
    schema = ColumnSchema(prefix="regacc4")
    schema.add("a", ["A"])
    schema.add("b", ["B"])
    register_source_accessor(schema)

    gdf = gpd.GeoDataFrame(
        {"regacc4_a": [1.0, 2.0], "regacc4_b": [3.0, 4.0]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    view = gdf.regacc4[["a", "b"]]
    assert isinstance(view.data, pd.DataFrame)
    assert list(view.data.columns) == ["regacc4_a", "regacc4_b"]
