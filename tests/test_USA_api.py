"""Tests for pycensus.USA.api: batching, GEOID typing, and ACS sentinel nulling."""

from __future__ import annotations

import polars as pl
import pytest

from pycensus.USA import api


def _patch_get_census(monkeypatch, pages):
    """Feed successive fake `get_census` responses, one per call."""
    calls = iter(pages)

    def fake_get_census(dataset, year, variables, params, return_geoid):
        return next(calls)

    monkeypatch.setattr(api, "get_census", fake_get_census)


def test_fetch_variables_casts_geoid_to_string(monkeypatch):
    _patch_get_census(monkeypatch, [{"GEOID": [25025000100], "V1": [1.0]}])
    df = api.fetch_variables("acs/acs5", 2023, "tract", "MA", ["V1"])
    assert df["GEOID"].dtype == pl.Utf8
    assert df["GEOID"][0] == "25025000100"


def test_fetch_variables_nulls_acs_sentinel_values(monkeypatch):
    _patch_get_census(
        monkeypatch,
        [{"GEOID": ["1", "2"], "B19013_001E": [75000.0, -666666666.0]}],
    )
    df = api.fetch_variables("acs/acs5", 2023, "tract", "MA", ["B19013_001E"])
    assert df["B19013_001E"].to_list() == [75000.0, None]


def test_fetch_variables_preserves_real_negative_is_not_a_thing_but_zero_is_kept(monkeypatch):
    """A real (non-sentinel) value of exactly 0 must survive, only the sentinel range is nulled."""
    _patch_get_census(monkeypatch, [{"GEOID": ["1"], "V1": [0.0]}])
    df = api.fetch_variables("acs/acs5", 2023, "tract", "MA", ["V1"])
    assert df["V1"].to_list() == [0.0]


def test_fetch_variables_batches_variables_in_groups_of_50(monkeypatch):
    variables = [f"V{i}" for i in range(120)]
    pages = []
    for batch_start in range(0, 120, 50):
        batch = variables[batch_start : batch_start + 50]
        pages.append({"GEOID": ["1"], **{v: [1.0] for v in batch}})

    calls = []

    def fake_get_census(dataset, year, variables, params, return_geoid):
        calls.append(list(variables))
        return pages[len(calls) - 1]

    monkeypatch.setattr(api, "get_census", fake_get_census)

    df = api.fetch_variables("acs/acs5", 2023, "tract", "MA", variables)
    assert len(calls) == 3
    assert set(df.columns) == {"GEOID", *variables}


def test_fetch_variables_uses_state_specific_geo_filter(monkeypatch):
    seen_params = {}

    def fake_get_census(dataset, year, variables, params, return_geoid):
        seen_params.update(params)
        return {"GEOID": ["1"], variables[0]: [1.0]}

    monkeypatch.setattr(api, "get_census", fake_get_census)
    api.fetch_variables("acs/acs5", 2023, "tract", "MA", ["V1"])

    assert seen_params["for"] == "tract:*"
    assert "state:25" in seen_params["in"]
