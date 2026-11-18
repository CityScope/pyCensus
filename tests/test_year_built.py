"""Year-built shares of dwellings (`pycensus.year_built`): band splitting at 1945 / 1970 / 2000 and the global schema entries."""
import json

import numpy as np
import pandas as pd

from pycensus.canonical import GLOBAL_SCHEMA_PATH
from pycensus.global_equivalents import add_global_equivalents
from pycensus.year_built import SHARE_NAMES, band_fractions, config, shares_from_bands


def test_band_splitting():
    assert np.allclose(band_fractions(1940, 1949), [0.5, 0.5, 0, 0])      # ACS 1940-49 is split 50/50 at 1945
    assert np.allclose(band_fractions(None, 1939), [1, 0, 0, 0])
    assert np.allclose(band_fractions(1919, 1948), [26 / 30, 4 / 30, 0, 0])
    assert np.allclose(band_fractions(1961, 1970), [0, 0.9, 0.1, 0])      # 1970 itself belongs to the 1970-2000 bin
    assert np.allclose(band_fractions(1991, 2000), [0, 0, 0.9, 0.1])


def test_acs_shares_sum_to_one_and_ignore_missing():
    df = pd.DataFrame({"acs5_dwellingsBuilt1939OrEarlier": [10.0, np.nan], "acs5_dwellingsBuilt1940To1949": [10.0, np.nan],
                       "acs5_dwellingsBuilt1970To1979": [60.0, np.nan], "acs5_dwellingsBuilt2000To2009": [20.0, np.nan]})
    sh = add_global_equivalents(df)[list(SHARE_NAMES)]
    assert np.allclose(sh.iloc[0], [0.15, 0.05, 0.6, 0.2]) and sh.iloc[1].isna().all()


def test_spain_censo_shares_renormalise_without_unknown():
    df = pd.DataFrame({"ine_built_1941_a_1950_share": [0.2], "ine_built_2001_a_2010_share": [0.6], "ine_built_No_consta_share": [0.2]})
    sh = shares_from_bands(df, config()["sources"][1]["columns"])
    assert np.allclose(sh.iloc[0], [0.1, 0.15, 0.0, 0.75])


def test_global_schema_entries():
    feats = {x["feature_name"]: x for x in json.loads(GLOBAL_SCHEMA_PATH.read_text())}
    for n in SHARE_NAMES:
        assert feats[n]["category"] == "housing" and feats[n]["resampling_up"] == "weighted_mean"
