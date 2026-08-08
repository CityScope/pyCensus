"""Tests for pycensus.USA.utils: GEOID column detection and state normalization."""

from __future__ import annotations

import pytest

from pycensus.USA import utils


def test_pick_geoid_column_prefers_exact_geoid():
    assert utils.pick_geoid_column(["GEOID20", "GEOID", "NAME"]) == "GEOID"


def test_pick_geoid_column_falls_back_to_geoid20():
    assert utils.pick_geoid_column(["GEOID20", "NAME"]) == "GEOID20"


def test_pick_geoid_column_falls_back_to_geoid10():
    assert utils.pick_geoid_column(["GEOID10", "NAME"]) == "GEOID10"


def test_pick_geoid_column_falls_back_to_any_geoid_like_column():
    assert utils.pick_geoid_column(["AFFGEOID", "NAME"]) == "AFFGEOID"


def test_pick_geoid_column_returns_none_when_absent():
    assert utils.pick_geoid_column(["NAME", "STATEFP"]) is None


@pytest.mark.parametrize("value", ["MA", "Massachusetts", "25", "ma"])
def test_state_abbr_normalizes_various_forms(value):
    assert utils.state_abbr(value) == "MA"


@pytest.mark.parametrize("value", ["MA", "Massachusetts", "25"])
def test_state_fips_normalizes_various_forms(value):
    assert utils.state_fips(value) == "25"


def test_state_abbr_raises_for_unknown_state():
    with pytest.raises(ValueError):
        utils.state_abbr("Not A State")


def test_state_fips_raises_for_unknown_state():
    with pytest.raises(ValueError):
        utils.state_fips("Not A State")
