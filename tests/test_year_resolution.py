"""Tests for pycensus.year_resolution.

Covers the three request shapes from the schema-redesign spec: no year
(latest that supports the requested level), a single year applied to all
sources (exact or interpolated), and a {source: year} dict (per-source).
"""

import polars as pl
import pytest

from pycensus.year_resolution import (
    YearResolution,
    interpolate_frames,
    resolve_year,
    resolve_years_for_request,
)

ACS5_AVAILABLE_YEARS = list(range(2009, 2024))
ACS5_MIN_YEAR_BY_LEVEL = {
    "state": 2009,
    "county": 2009,
    "tract": 2009,
    "blockgroup": 2013,
    "block": None,
}


def test_no_year_picks_latest_available():
    res = resolve_year(None, ACS5_AVAILABLE_YEARS)
    assert res == YearResolution(mode="exact", target_year=2023, year=2023)


def test_no_year_picks_latest_that_supports_finest_requested_level():
    # Blockgroup-level ACS5 is only reliable from 2013 on, even though the
    # source overall goes back to 2009 -- "latest" must respect that.
    res = resolve_year(
        None, ACS5_AVAILABLE_YEARS, level="blockgroup", min_year_by_level=ACS5_MIN_YEAR_BY_LEVEL
    )
    assert res.mode == "exact"
    assert res.year == 2023  # still the overall latest, since 2023 >= 2013

    # A source whose blockgroup data stopped earlier should cap there.
    truncated = [y for y in ACS5_AVAILABLE_YEARS if y <= 2015]
    res2 = resolve_year(
        None, truncated, level="blockgroup", min_year_by_level=ACS5_MIN_YEAR_BY_LEVEL
    )
    assert res2.year == 2015


def test_level_never_available_raises():
    with pytest.raises(ValueError):
        resolve_year(
            None, ACS5_AVAILABLE_YEARS, level="block", min_year_by_level=ACS5_MIN_YEAR_BY_LEVEL
        )


def test_exact_year_available_returns_directly():
    res = resolve_year(2015, ACS5_AVAILABLE_YEARS)
    assert res == YearResolution(mode="exact", target_year=2015, year=2015)


def test_unavailable_year_between_two_available_interpolates():
    # e.g. a source that only ever published even years.
    sparse = [2010, 2012, 2014, 2016]
    res = resolve_year(2013, sparse)
    assert res.mode == "interpolate"
    assert res.year_low == 2012
    assert res.year_high == 2014
    assert res.target_year == 2013


def test_year_outside_range_snaps_to_nearest():
    res = resolve_year(1999, ACS5_AVAILABLE_YEARS)
    assert res.mode == "exact"
    assert res.year == 2009  # nearest available, since nothing brackets it below


def test_resolve_years_for_request_single_year_applies_to_all_sources():
    resolved = resolve_years_for_request(
        sources=["acs5", "dhc"],
        year=2015,
        available_years_by_source={"acs5": ACS5_AVAILABLE_YEARS, "dhc": [2010, 2020]},
    )
    assert resolved["acs5"] == YearResolution(mode="exact", target_year=2015, year=2015)
    # DHC only has 2010/2020 -> 2015 interpolates.
    assert resolved["dhc"].mode == "interpolate"
    assert (resolved["dhc"].year_low, resolved["dhc"].year_high) == (2010, 2020)


def test_resolve_years_for_request_per_source_dict():
    resolved = resolve_years_for_request(
        sources=["acs5", "dhc"],
        year={"acs5": 2018},  # dhc omitted -> latest
        available_years_by_source={"acs5": ACS5_AVAILABLE_YEARS, "dhc": [2010, 2020]},
    )
    assert resolved["acs5"] == YearResolution(mode="exact", target_year=2018, year=2018)
    assert resolved["dhc"] == YearResolution(mode="exact", target_year=2020, year=2020)


def test_interpolate_frames_linear_blend_exact_numbers():
    df_low = pl.DataFrame({"GEOID": ["A", "B"], "population": [100.0, 200.0]})
    df_high = pl.DataFrame({"GEOID": ["A", "B"], "population": [200.0, 400.0]})
    # target_year is exactly halfway between 2010 and 2020 -> t=0.5.
    blended = interpolate_frames(
        df_low, 2010, df_high, 2020, 2015, id_col="GEOID", value_cols=["population"]
    )
    values = dict(zip(blended["GEOID"].to_list(), blended["population"].to_list()))
    assert values == {"A": 150.0, "B": 300.0}


def test_interpolate_frames_non_midpoint_weighting():
    df_low = pl.DataFrame({"GEOID": ["A"], "x": [10.0]})
    df_high = pl.DataFrame({"GEOID": ["A"], "x": [50.0]})
    # t = (2013 - 2010) / (2020 - 2010) = 0.3 -> 10 + (50-10)*0.3 = 22.0
    blended = interpolate_frames(df_low, 2010, df_high, 2020, 2013, id_col="GEOID", value_cols=["x"])
    assert blended["x"].to_list() == pytest.approx([22.0])


def test_interpolate_frames_drops_geographies_missing_from_either_year():
    df_low = pl.DataFrame({"GEOID": ["A", "B"], "x": [10.0, 20.0]})
    df_high = pl.DataFrame({"GEOID": ["A"], "x": [30.0]})  # B disappeared (e.g. tract split)
    blended = interpolate_frames(df_low, 2010, df_high, 2020, 2015, id_col="GEOID", value_cols=["x"])
    assert blended["GEOID"].to_list() == ["A"]


def test_interpolate_frames_requires_target_strictly_between():
    df = pl.DataFrame({"GEOID": ["A"], "x": [1.0]})
    with pytest.raises(ValueError):
        interpolate_frames(df, 2010, df, 2020, 2020, id_col="GEOID", value_cols=["x"])
