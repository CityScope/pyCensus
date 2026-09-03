"""Tests that ACS5's loader actually wires up year_resolution (no network).

`_fetch_missing` (the function that hits the real Census API) is
monkeypatched out; these tests only exercise `_fetch_missing_resolved`'s
branching between an exact-year fetch and a two-year interpolated fetch.
"""

import pandas as pd
import pytest

import pycensus.countries.usa.acs5.loader as loader
from pycensus.year_resolution import YearResolution


def _fake_fetch(fetch_log, year_to_value):
    def _fetch(missing_prefixed, level, state, year, api_key):
        fetch_log.append(year)
        return pd.DataFrame(
            {"GEOID": ["06001", "06003"], missing_prefixed[0]: year_to_value[year]}
        )

    return _fetch


def test_exact_resolution_calls_fetch_missing_once(monkeypatch):
    fetch_log = []
    monkeypatch.setattr(
        loader, "_fetch_missing", _fake_fetch(fetch_log, {2020: [100, 200]})
    )

    resolution = YearResolution(mode="exact", target_year=2020, year=2020)
    result = loader._fetch_missing_resolved(
        ["acs_population"], "tract", "06", resolution, api_key=None
    )

    assert fetch_log == [2020]
    assert result["acs_population"].tolist() == [100, 200]


def test_interpolate_resolution_fetches_both_years_and_blends(monkeypatch):
    fetch_log = []
    monkeypatch.setattr(
        loader,
        "_fetch_missing",
        _fake_fetch(fetch_log, {2010: [100, 200], 2020: [200, 400]}),
    )

    # Halfway between 2010 and 2020 -> exactly the midpoint of each value.
    resolution = YearResolution(
        mode="interpolate", target_year=2015, year_low=2010, year_high=2020
    )
    result = loader._fetch_missing_resolved(
        ["acs_population"], "tract", "06", resolution, api_key=None
    )

    assert sorted(fetch_log) == [2010, 2020]
    values = dict(zip(result["GEOID"], result["acs_population"]))
    assert values == {"06001": pytest.approx(150.0), "06003": pytest.approx(300.0)}
