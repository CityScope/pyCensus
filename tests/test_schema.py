"""Tests for pycensus.schema.ColumnSchema / ColumnDef."""

from __future__ import annotations

import pytest

from geohierarchy.aggregation import Mean, Sum
from pycensus.schema import ColumnDef, ColumnSchema


def test_add_registers_column_and_returns_self_for_chaining():
    schema = ColumnSchema(prefix="x")
    result = schema.add("population", ["P1"]).add("households", ["H1"], relative_to="population")

    assert result is schema
    assert set(schema.columns) == {"population", "households"}
    assert schema.columns["households"].relative_to == "population"


def test_prefixed():
    schema = ColumnSchema(prefix="acs")
    assert schema.prefixed("population") == "acs_population"


def test_strip_prefix_removes_matching_prefix_only():
    schema = ColumnSchema(prefix="acs")
    assert schema.strip_prefix("acs_population") == "population"
    assert schema.strip_prefix("population") == "population"
    assert schema.strip_prefix("dhc_population") == "dhc_population"


def test_relative_to_resolves_prefixed_denominator():
    schema = ColumnSchema(prefix="acs")
    schema.add("population", ["P1"])
    schema.add("households", ["H1"], relative_to="population")

    assert schema.relative_to("acs_households") == "acs_population"
    assert schema.relative_to("households") == "acs_population"


def test_relative_to_returns_none_when_not_registered():
    schema = ColumnSchema(prefix="acs")
    schema.add("population", ["P1"])

    assert schema.relative_to("acs_population") is None


def test_relative_to_returns_none_for_unknown_column():
    schema = ColumnSchema(prefix="acs")
    assert schema.relative_to("acs_unknown") is None


def test_aggregations_default_to_sum():
    schema = ColumnSchema(prefix="acs")
    schema.add("population", ["P1"])

    aggs = schema.aggregations()
    assert isinstance(aggs["acs_population"], Sum)


def test_aggregations_mean_with_weight_column():
    schema = ColumnSchema(prefix="acs")
    schema.add("households", ["H1"])
    schema.add("income_median", ["I1"], agg="mean", weight_by="households")

    aggs = schema.aggregations()
    assert isinstance(aggs["acs_income_median"], Mean)
    assert aggs["acs_income_median"].weight_column == "acs_households"


def test_aggregations_mean_without_weight_column():
    schema = ColumnSchema(prefix="acs")
    schema.add("rate", ["R1"], agg="mean")

    aggs = schema.aggregations()
    assert isinstance(aggs["acs_rate"], Mean)
    assert aggs["acs_rate"].weight_column is None


def test_aggregations_covers_every_registered_column():
    schema = ColumnSchema(prefix="acs")
    schema.add("a", ["A"])
    schema.add("b", ["B"], agg="mean")

    aggs = schema.aggregations()
    assert set(aggs) == {"acs_a", "acs_b"}


def test_columndef_is_count_and_is_average_reflect_agg():
    count_col = ColumnDef(name="population", codes=["P1"], agg="sum")
    avg_col = ColumnDef(name="income_median", codes=["I1"], agg="mean")

    assert count_col.is_count is True
    assert count_col.is_average is False
    assert avg_col.is_count is False
    assert avg_col.is_average is True


def test_smooth_aggregations_count_column_preserves_total():
    schema = ColumnSchema(prefix="dhc")
    schema.add("population", ["P1"])  # agg="sum" (count) by default

    agg = schema.smooth_aggregations()["dhc_population"]
    assert isinstance(agg, Sum)  # upscale copied as-is; downscale grafted below
    assert agg.mapping == "knn"
    assert agg.preserve_total is True


def test_smooth_aggregations_average_column_does_not_preserve_total():
    schema = ColumnSchema(prefix="acs")
    schema.add("households", ["H1"])
    schema.add("income_median", ["I1"], agg="mean", weight_by="households")

    agg = schema.smooth_aggregations()["acs_income_median"]
    assert isinstance(agg, Mean)
    assert agg.mapping == "knn"
    assert agg.preserve_total is False


def test_smooth_aggregations_uses_smoothmean_downscale_with_matching_density():
    schema = ColumnSchema(prefix="dhc")
    schema.add("population", ["P1"], agg="sum")
    schema.add("rate", ["R1"], agg="mean")

    aggs = schema.smooth_aggregations(k=4, power=1.5)

    # downscale_exprs/consolidate_downscale are grafted from a SmoothMean
    # built with density matching is_count -- verify via behavior markers.
    assert aggs["dhc_population"].knn_k == 4
    assert aggs["dhc_population"].knn_power == 1.5
    assert aggs["dhc_population"].preserve_total is True
    assert aggs["dhc_rate"].preserve_total is False


def test_smooth_aggregations_covers_every_registered_column():
    schema = ColumnSchema(prefix="acs")
    schema.add("a", ["A"])
    schema.add("b", ["B"], agg="mean")

    aggs = schema.smooth_aggregations()
    assert set(aggs) == {"acs_a", "acs_b"}
