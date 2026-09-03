"""Tests for pycensus.new_schema: FieldKey, and aggregations() resampling-method wiring."""

from __future__ import annotations

import geohierarchy as gh
import pytest

from pycensus.new_schema import FieldKey, load_schema


# ============================================================
# FieldKey
# ============================================================


def test_field_key_format_with_all_segments():
    key = FieldKey(feature_name="population", year=2020, country="usa", source="acs5")
    assert key.format() == "2020_usa_acs5_population"


def test_field_key_format_omits_year():
    key = FieldKey(feature_name="population", country="usa", source="acs5")
    assert key.format() == "all_usa_acs5_population"


def test_field_key_format_omits_country_and_source():
    key = FieldKey(feature_name="population")
    assert key.format() == "all_population"


def test_field_key_parse_round_trips_with_known_segments():
    original = FieldKey(feature_name="population", year=2020, country="usa", source="acs5")
    parsed = FieldKey.parse(
        original.format(), known_countries={"usa"}, known_sources={"acs5"}
    )
    assert parsed == original


def test_field_key_parse_no_year():
    parsed = FieldKey.parse("all_usa_acs5_population", known_countries={"usa"}, known_sources={"acs5"})
    assert parsed.year is None
    assert parsed.country == "usa"
    assert parsed.source == "acs5"
    assert parsed.feature_name == "population"


def test_field_key_parse_multi_word_feature_name():
    parsed = FieldKey.parse(
        "2020_usa_acs5_median_household_income",
        known_countries={"usa"},
        known_sources={"acs5"},
    )
    assert parsed.feature_name == "median_household_income"
    assert parsed.year == 2020


# ============================================================
# NewColumnSchema.prefixed / strip_prefix / relative_to (now FieldKey-backed)
# ============================================================


@pytest.fixture
def acs5_schema():
    return load_schema("usa", "acs5")


def test_prefixed_and_strip_prefix_round_trip(acs5_schema):
    col = acs5_schema.prefixed("population", 2020)
    assert col == "2020_usa_acs5_population"
    assert acs5_schema.strip_prefix(col) == "population"


def test_get_feature_from_column_resolves_feature(acs5_schema):
    col = acs5_schema.prefixed("population", 2020)
    feature = acs5_schema.get_feature_from_column(col)
    assert feature is not None
    assert feature.feature_name == "population"


def test_relative_to_resolves_prefixed_denominator_with_year(acs5_schema):
    col = acs5_schema.prefixed("households", 2020)
    assert acs5_schema.relative_to(col) == "2020_usa_acs5_population"


# ============================================================
# aggregations(): resampling method -> real geohierarchy strategy
# ============================================================


def test_count_feature_with_named_weight_maps_to_weighted_sum(acs5_schema):
    # `households` (a count) declares resampling_weight in acs5/schema.json.
    feature = acs5_schema.get_feature("households")
    strat = acs5_schema._build_strategy(feature)
    assert isinstance(strat, gh.Sum)


def test_count_feature_with_area_weight_has_no_weight_column(acs5_schema):
    feature = acs5_schema.get_feature("population")
    assert feature.resampling_weight in ("area", "", None)
    strat = acs5_schema._build_strategy(feature)
    assert isinstance(strat, gh.Sum)
    assert strat.weight_column is None
    assert strat.geoweighted is True


def test_intersection_mode_is_threaded_through_aggregations(acs5_schema):
    aggs = acs5_schema.aggregations(intersection_mode="touches")
    col = acs5_schema.prefixed("population")
    assert aggs[col].intersection_mode == "touches"
    # "touches"/"exact" imply geoweighted=True regardless of the caller's default.
    assert aggs[col].geoweighted is True


def test_labour_force_weighted_mean_resolves_to_mean_weighted_by_labor_force():
    # This used to load a real country's schema.json (germany/destatis) to
    # exercise this resampling method, but that schema's unemploymentRate/
    # laborForce fields were fabricated, unverified GENESIS codes and were
    # removed -- see pycensus.countries.germany.destatis.schema module docstring. A
    # synthetic in-test schema keeps this test about the generic
    # "labour_force_weighted_mean" -> gh.Mean(weight_column=...) resolution
    # logic in new_schema.py, independent of any one country's real data.
    from pycensus.new_schema import FeatureDef, NewColumnSchema

    schema = NewColumnSchema(
        country="test",
        source="src",
        features={
            "laborForce": FeatureDef(
                feature_name="laborForce", country="test", source="src", years=[2020], levels={},
                type="count", resampling_up="sum", resampling_down="divide_area_weighted",
            ),
            "unemploymentRate": FeatureDef(
                feature_name="unemploymentRate", country="test", source="src", years=[2020], levels={},
                type="rate", resampling_up="labour_force_weighted_mean", resampling_down="preserve_smooth",
            ),
        },
    )
    feature = schema.features["unemploymentRate"]
    strat = schema._build_strategy(feature)
    assert isinstance(strat, gh.Mean)
    assert strat.weight_column == schema.prefixed("laborForce")


# ============================================================
# Regression: mean/median fields must resolve to gh.Mean, not gh.Sum
# ============================================================
#
# A median/mean field (e.g. "median household income") declared with
# resampling_up="sum" would build a gh.Sum strategy that literally adds
# medians/means across sub-regions on upscale -- nonsense (summing
# per-household medians has no meaningful interpretation). These fields
# must always resolve to gh.Mean via "weighted_mean".

_USA_MEAN_MEDIAN_FIELDS = [
    "householdSizeMean",
    "medianHouseholdIncome",
    "incomeMeanCapita",
    "commuteTimeMean",
    "rentMedianGross",
    "medianAge",
]


@pytest.mark.parametrize("source", ["acs1", "acs3", "acs5"])
@pytest.mark.parametrize("feature_name", _USA_MEAN_MEDIAN_FIELDS)
def test_mean_median_fields_resolve_to_weighted_mean_not_sum(source, feature_name):
    schema = load_schema("usa", source)
    feature = schema.get_feature(feature_name)
    if feature is None:
        pytest.skip(f"{feature_name} not present in usa/{source}")
    assert feature.type in ("mean", "median"), (
        f"usa/{source}/schema.json: {feature_name} has type={feature.type!r}, "
        "expected 'mean' or 'median'"
    )
    strat = schema._build_strategy(feature)
    assert isinstance(strat, gh.Mean), (
        f"usa/{source}/schema.json: {feature_name} (type={feature.type}) built a "
        f"{type(strat).__name__} strategy -- mean/median fields must resolve to gh.Mean"
    )


def test_mexico_education_mean_grade_resolves_to_weighted_mean():
    schema = load_schema("mexico", "inegi")
    feature = schema.get_feature("educationMeanGrade")
    assert feature is not None
    assert feature.type == "mean"
    strat = schema._build_strategy(feature)
    assert isinstance(strat, gh.Mean)
    assert strat.weight_column == schema.prefixed("population15plus")


# ============================================================
# Regression: educational-attainment ACS codes must be real B15003 codes,
# not corrupted placeholder data or the wrong bucket of grade levels.
# ============================================================


@pytest.mark.parametrize("source", ["acs1", "acs3", "acs5"])
def test_education_codes_are_real_b15003_codes_not_corrupted(source):
    schema = load_schema("usa", source)
    for feature_name in ("educationLessThanHs", "educationHighSchool", "educationSomeCollege", "educationBachelorsPlus"):
        feature = schema.get_feature(feature_name)
        if feature is None:
            continue
        assert feature.codes, f"{source}/{feature_name} has no codes"
        for code in feature.codes:
            assert code.startswith("B15003_"), (
                f"{source}/{feature_name} has a non-B15003 or corrupted code: {code!r}"
            )


def test_education_high_school_codes_are_diploma_or_ged_only():
    # B15003_017 = regular HS diploma, B15003_018 = GED/alternative credential.
    # Earlier codes (002-016) are sub-high-school grade levels and must not
    # appear in a field described as "high school diploma or equivalent".
    schema = load_schema("usa", "acs5")
    feature = schema.get_feature("educationHighSchool")
    assert set(feature.codes) == {"B15003_017", "B15003_018"}


# ============================================================
# Regression: no schema should declare `relative_to` pointing at a
# feature_name that doesn't actually exist in that same source -- this
# silently breaks `.share` and any downstream `relative_to` resolution.
# ============================================================


@pytest.mark.parametrize(
    "country,source",
    [
        ("usa", "acs1"),
        ("usa", "acs3"),
        ("usa", "acs5"),
        ("usa", "dhc"),
        ("usa", "lodes_rac"),
        ("usa", "lodes_wac"),
        ("mexico", "inegi"),
    ],
)
def test_no_dangling_relative_to_references(country, source):
    schema = load_schema(country, source)
    known = set(schema.features)
    for feature in schema.features.values():
        if feature.relative_to:
            assert feature.relative_to in known, (
                f"{country}/{source}: {feature.feature_name}.relative_to="
                f"{feature.relative_to!r} is not a feature in this source"
            )
