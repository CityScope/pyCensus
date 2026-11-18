"""Global schema: election (national/state/municipal) + housing features and the latest-period mappings."""
import json

import pandas as pd

from pycensus.canonical import GLOBAL_SCHEMA_PATH
from pycensus.global_equivalents import add_global_equivalents, equivalents, latest_equivalents
from pycensus.latest_columns import latest_column_filter

SCHEMA = {x["feature_name"]: x for x in json.loads(GLOBAL_SCHEMA_PATH.read_text())}
SCOPES = ("national", "state", "municipal")
METRICS = ("left_share", "right_share", "other_share", "turnout_rate", "total_votes")
HOUSING = ("home_size_m2_mean", "rent_per_m2_mean", "price_per_m2_mean", "rent_per_home_mean", "price_per_home_mean")


def test_schema_has_election_and_housing_features():
    for sc in SCOPES:
        for m in METRICS:
            assert SCHEMA[f"elec_{sc}_{m}"]["category"] == "elections"
    for h in HOUSING:
        assert SCHEMA[h]["category"] == "housing" and SCHEMA[h]["type"] == "mean" and SCHEMA[h]["resampling_up"] == "weighted_mean"


def test_every_mapping_target_is_a_schema_feature():
    targets = set(equivalents().values()) | set(json.loads(open(__import__("pycensus.global_equivalents", fromlist=["x"])._FILE).read())["latest_patterns"])
    assert targets <= set(SCHEMA)


def test_latest_election_and_housing_mapping():
    df = pd.DataFrame({c: [1.0] for c in ["elec_national_2019_left_share", "elec_national_2023_left_share", "ine_elec_state_2024_total_votes",
                                          "ine_serpavi_rent_m2_median_vc_2016", "ine_serpavi_rent_m2_median_vc_2024", "rent_median_2016", "rent_median"]})
    m = latest_equivalents(df.columns)
    assert m["elec_national_left_share"] == "elec_national_2023_left_share"
    assert m["elec_state_total_votes"] == "ine_elec_state_2024_total_votes"
    assert m["rent_per_m2_mean"] == "ine_serpavi_rent_m2_median_vc_2024"
    assert m["rent_per_home_mean"] == "rent_median"
    assert "elec_national_left_share" in add_global_equivalents(df).columns


def test_latest_column_filter():
    keep, dropped = latest_column_filter(["rent_median", "rent_median_2016", "hud_FY2019", "hud_FY2026", "elec_state_2019_left_share",
                                          "elec_state_2024_left_share", "population"])
    assert set(dropped) == {"rent_median_2016", "hud_FY2019", "elec_state_2019_left_share"} and "population" in keep


def test_turnout_rate_global_names():
    for sc in SCOPES:
        f = SCHEMA[f"elec_{sc}_turnout_rate"]
        assert "ballots cast divided by eligible" in f["definition"] and f["type"] == "mean" and f["resampling_up"] == "weighted_mean"
    df = pd.DataFrame({c: [1.0] for c in ["elec_state_2022_turnout_rate", "elec_state_2024_turnout_rate", "ine_elec_municipal_2023_turnout_rate", "elec_national_2024leg_turnout_rate"]})
    m = latest_equivalents(df.columns)
    assert m["elec_state_turnout_rate"] == "elec_state_2024_turnout_rate"
    assert m["elec_municipal_turnout_rate"] == "ine_elec_municipal_2023_turnout_rate"
    assert m["elec_national_turnout_rate"] == "elec_national_2024leg_turnout_rate"
