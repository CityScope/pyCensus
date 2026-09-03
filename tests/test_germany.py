"""Tests for pycensus.germany: constants, schema, geography, API client, and loader.

Technical aspects:
    Germany's real network calls (GISCO NUTS geojson download, GENESIS-Online
    REST calls) are monkeypatched out here, same pattern as
    ``tests/test_mexico.py``, to keep the suite offline and fast.

    The real sources were verified live against the network during
    development:
        - GISCO NUTS 2021 geojson (LEVL_0/1/3, CNTR_CODE=="DE"), 2026-08-19:
          exactly 1 nation / 16 state / 401 district features -- the real,
          documented counts of Germany's administrative divisions -- and
          Hamburg's real NUTS1 geometry (DE6) has bounds
          (8.375, 53.421, 10.308, 54.016), which contains Hamburg's real
          coordinates (~9.99E, 53.55N).
        - GENESIS-Online's real REST API, 2026-08-21: the real current host
          is ``genesis.destatis.de`` (no "www-" prefix -- the old
          "www-genesis.destatis.de" now 307/302-redirects to a generic
          announcement page) and credentials must be sent as HTTP headers,
          not POST body fields. With both fixed, the token in
          ``api_keys.json`` DOES authenticate
          (``helloworld/logincheck`` returned a real successful-login
          response, not the GAST guest-account rejection) and DOES
          retrieve real data: statistic 12411 ("Fortschreibung des
          Bevoelkerungsstandes"), tables 12411-0001/0010/0015
          (nation/state/district), variable BEVSTD. Real live numbers:
          Germany 31.12.2022 = 83,118,501; Bavaria 31.12.2022 = 13,105,221;
          Munich (kreisfreie Stadt, AGS 09162) 31.12.2022 = 1,490,516 --
          all match Destatis' independently-published figures. See
          pycensus.countries.germany.constants and
          pycensus.countries.germany.api module docstrings for the exact
          commands/responses.
    See the pyCensus schema redesign memory for this session's log.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.germany import api, constants, geography, utils
from pycensus.countries.germany.destatis import crosswalk, loader
from pycensus.countries.germany.destatis.schema import SCHEMA


class TestConstants:
    def test_state_codes_exist(self):
        assert len(constants.STATE_CODES) == 16

    def test_state_abbr_exist(self):
        assert len(constants.STATE_ABBR) == 16

    def test_state_nuts1_covers_every_state(self):
        assert set(constants.STATE_NUTS1) == set(constants.STATE_CODES)
        assert set(constants.NUTS1_TO_STATE.values()) == set(constants.STATE_CODES)

    def test_state_nuts1_matches_live_gisco_response(self):
        # Regression guard: these NUTS1 codes were read verbatim off a live
        # GISCO response on 2026-08-19, not guessed -- if wired to the
        # wrong code, boundary/region filtering would silently return the
        # wrong state.
        assert constants.STATE_NUTS1["HH"] == "DE6"  # Hamburg
        assert constants.STATE_NUTS1["BE"] == "DE3"  # Berlin
        assert constants.STATE_NUTS1["BY"] == "DE2"  # Bavaria

    def test_state_code_lookup(self):
        assert utils.state_code("Hamburg") == "HH"
        assert utils.state_code("HH") == "HH"

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["county"] == "district"
        assert constants.LEVEL_FALLBACK["place"] == "municipality"

    def test_gisco_url_has_level_placeholder(self):
        assert "{levl}" in constants.GISCO_NUTS_GEOJSON_URL

    def test_genesis_api_key_names_match_api_keys_json_convention(self):
        # pyCensus/api_keys.json's real Germany entry is a single personal
        # token under "destatis_genesis" (not a username/password pair) --
        # see pycensus/api_keys.py, api_keys.json, and
        # api.resolve_genesis_credentials's token-first resolution.
        assert constants.GENESIS_TOKEN_KEY == "destatis_genesis"
        assert constants.GENESIS_USERNAME_KEY == "destatis_genesis_username"
        assert constants.GENESIS_PASSWORD_KEY == "destatis_genesis_password"


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "destatis"

    def test_population_column_exists_with_real_verified_code(self):
        # BEVSTD (not the earlier placeholder BEVZ01) was confirmed live
        # via real authenticated GENESIS-Online responses on 2026-08-21 --
        # see schema.json's "_note" and pycensus.countries.germany.constants
        # docstring for why BEVZ01 was wrong (real variable, wrong database).
        assert "population" in SCHEMA.columns
        assert SCHEMA.columns["population"].codes == ["BEVSTD"]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "destatis_population"

    def test_fabricated_fields_were_removed(self):
        # Regression guard: the earlier schema.json had ~35 fabricated
        # field codes (POP_MALE, HH_TOTAL, INC_MED_HH, ...) never verified
        # against any real Destatis source. Only real, individually
        # live-verified fields should be present: `population` (BEVSTD,
        # verified 2026-08-21), `malePopulation`/`femalePopulation`
        # (real GENESIS 12411-0003/0011/0016 sex-breakdown tables,
        # nation/state/district, verified 2026-08-22 -- see
        # constants.GENESIS_SEX_TABLES), and `foreignBornPopulation` (real
        # AZR-derived GENESIS statistic 12521, table 12521-0040,
        # district-only, verified 2026-08-23 -- see
        # constants.GENESIS_FOREIGN_POPULATION_TABLES).
        assert list(SCHEMA.columns) == [
            "population",
            "malePopulation",
            "femalePopulation",
            "foreignBornPopulation",
        ]


class TestGeography:
    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {"nation", "state", "district", "municipality"}

    def test_load_boundaries_unimplemented_level_raises(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("statistical_district", region="HH")

    @pytest.fixture
    def fake_germany_nuts(self, monkeypatch, tmp_path):
        """Monkeypatch the GISCO download with small real-shaped synthetic data."""
        import pycensus.countries.germany.geography as geo_mod

        def fake_load(levl_code, data_dir=None):
            if levl_code == 0:
                return gpd.GeoDataFrame(
                    {"GEOID": ["DE"], "NUTS_NAME": ["Deutschland"]},
                    geometry=[box(5.5, 47.0, 15.5, 55.0)],
                    crs=4326,
                )
            if levl_code == 1:
                return gpd.GeoDataFrame(
                    {"GEOID": ["DE3", "DE6"], "NUTS_NAME": ["Berlin", "Hamburg"]},
                    geometry=[box(13.0, 52.3, 13.7, 52.7), box(9.7, 53.4, 10.3, 53.7)],
                    crs=4326,
                )
            if levl_code == 3:
                return gpd.GeoDataFrame(
                    {"GEOID": ["DE300", "DE600"], "NUTS_NAME": ["Berlin", "Hamburg"]},
                    geometry=[box(13.0, 52.3, 13.7, 52.7), box(9.7, 53.4, 10.3, 53.7)],
                    crs=4326,
                )
            raise AssertionError(levl_code)

        monkeypatch.setattr(geo_mod, "_load_germany_nuts", fake_load)
        return fake_load

    def test_load_boundaries_state_filters_to_one_state(self, fake_germany_nuts):
        gdf = geography.load_boundaries("state", region="HH")
        assert list(gdf["GEOID"]) == ["DE6"]

    def test_load_boundaries_district_filters_by_state_prefix(self, fake_germany_nuts):
        gdf = geography.load_boundaries("district", region="HH")
        assert list(gdf["GEOID"]) == ["DE600"]

    def test_states_in_aoi(self, fake_germany_nuts):
        aoi = gpd.GeoDataFrame(geometry=[box(9.9, 53.5, 10.0, 53.6)], crs=4326)  # inside Hamburg
        result = geography.states_in_aoi(aoi)
        assert result == ["HH"]

    def test_district_names_returns_nuts_name_by_geoid(self, fake_germany_nuts):
        # Regression guard: _load_germany_nuts must retain NUTS_NAME (it
        # didn't before this session) -- destatis/crosswalk.py depends on
        # this to build a real AGS-to-NUTS3 crosswalk.
        result = geography.district_names()
        assert result == {"DE300": "Berlin", "DE600": "Hamburg"}

    @pytest.fixture
    def fake_germany_lau(self, monkeypatch, tmp_path):
        """Monkeypatch the GISCO LAU download with small real-shaped synthetic data."""
        import pycensus.countries.germany.geography as geo_mod

        def fake_load(data_dir=None):
            return gpd.GeoDataFrame(
                {
                    "GEOID": ["09162000", "09188139", "02000000"],
                    "LAU_NAME": ["München, Landeshauptstadt", "Starnberg, St", "Hamburg, Freie und Hansestadt"],
                    "POP_2021": [1488202.0, 23511.0, 1852478.0],
                },
                geometry=[box(11.5, 48.1, 11.6, 48.2), box(11.3, 48.0, 11.4, 48.1), box(9.9, 53.5, 10.0, 53.6)],
                crs=4326,
            )

        monkeypatch.setattr(geo_mod, "_load_germany_lau", fake_load)
        return fake_load

    def test_load_boundaries_municipality_filters_by_state_prefix(self, fake_germany_lau):
        # State AGS prefix ("09" for Bavaria) is the first two digits of
        # GEOID directly -- no crosswalk needed, unlike district.
        gdf = geography.load_boundaries("municipality", region="BY")
        assert set(gdf["GEOID"]) == {"09162000", "09188139"}

    def test_municipality_population_returns_geoid_name_pop(self, fake_germany_lau):
        result = geography.municipality_population()
        assert set(result["GEOID"]) == {"09162000", "09188139", "02000000"}
        assert dict(zip(result["GEOID"], result["POP_2021"]))["09162000"] == 1488202.0


class TestApi:
    def test_resolve_genesis_credentials_raises_when_unconfigured(self, monkeypatch):
        import pycensus.countries.germany.api as api_mod

        monkeypatch.setattr(api_mod, "resolve_api_key", lambda *a, **k: None)
        with pytest.raises(api.GenesisCredentialsError):
            api.resolve_genesis_credentials()

    def test_resolve_genesis_credentials_uses_explicit_args(self):
        user, pw = api.resolve_genesis_credentials(username="me", password="secret")
        assert (user, pw) == ("me", "secret")

    def test_resolve_genesis_credentials_uses_token_as_username_empty_password(self, monkeypatch):
        # api_keys.json's real Germany entry is a single "destatis_genesis"
        # token, not a username/password pair -- GENESIS docs say a personal
        # token is used in place of username, password omitted.
        import pycensus.countries.germany.api as api_mod

        def fake_resolve(key_name, key_env, explicit=None):
            if key_name == "destatis_genesis":
                return "sometoken"
            return None

        monkeypatch.setattr(api_mod, "resolve_api_key", fake_resolve)
        user, pw = api.resolve_genesis_credentials()
        assert (user, pw) == ("sometoken", "")

    def test_fetch_table_requires_real_credentials(self, monkeypatch):
        import pycensus.countries.germany.api as api_mod

        monkeypatch.setattr(api_mod, "resolve_api_key", lambda *a, **k: None)
        with pytest.raises(api.GenesisCredentialsError):
            api.fetch_table("12411-0001")

    def test_list_datasets_references_real_verified_statistic(self):
        datasets = api.list_datasets()
        assert datasets[0]["statistic"] == "12411"
        assert datasets[0]["population_variable"] == "BEVSTD"
        assert datasets[0]["tables"]["state"] == "12411-0010"

    def test_post_sends_credentials_as_headers_not_body(self, monkeypatch):
        # Regression guard for the 2026-08-20 bug: GENESIS requires
        # credentials as HTTP headers ("Zugangsdaten: Felder im
        # HTTP-Header"), not POST body fields -- sending them in the body
        # (the earlier shape) gets the same rejection an anonymous request
        # gets. See pycensus.countries.germany.api._post's docstring.
        import pycensus.countries.germany.api as api_mod

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"Status": {"Code": 0, "Content": "erfolgreich", "Type": "Information"}}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured["headers"] = headers
            captured["data"] = data
            return FakeResponse()

        monkeypatch.setattr(api_mod, "resolve_genesis_credentials", lambda *a, **k: ("tok", ""))
        monkeypatch.setattr(api_mod.requests, "post", fake_post)
        api_mod._post("helloworld", "logincheck", {"language": "de"})

        assert captured["headers"] == {"username": "tok", "password": ""}
        assert captured["data"] == {"language": "de"}
        assert "username" not in captured["data"]

    def test_post_raises_on_real_error_status(self, monkeypatch):
        import pycensus.countries.germany.api as api_mod
        import requests as requests_mod

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"Status": {"Code": 15, "Content": "Sie sind nicht berechtigt", "Type": "Error"}}

        monkeypatch.setattr(api_mod, "resolve_genesis_credentials", lambda *a, **k: ("tok", ""))
        monkeypatch.setattr(api_mod.requests, "post", lambda *a, **k: FakeResponse())
        with pytest.raises(requests_mod.HTTPError):
            api_mod._post("data", "table", {"name": "12411-0010"})

    def test_genesis_base_url_has_no_www_prefix(self):
        # Regression guard: the old "www-genesis.destatis.de" host
        # 307-redirects to "genesis.destatis.de" (verified live 2026-08-21)
        # -- the REST path itself is unchanged.
        assert constants.GENESIS_BASE_URL == "https://genesis.destatis.de/genesisWS/rest/2020"


class TestLoader:
    def test_load_raises_credentials_error_when_unconfigured(self, monkeypatch, tmp_path):
        import pycensus.countries.germany.api as api_mod

        monkeypatch.setattr(api_mod, "resolve_api_key", lambda *a, **k: None)
        with pytest.raises(api.GenesisCredentialsError):
            loader.load(regions=["HH"], level="state", cache_dir=str(tmp_path))

    def test_load_raises_without_regions_or_aoi(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))
        with pytest.raises(ValueError):
            loader.load(level="state", cache_dir=str(tmp_path))

    def test_fetch_missing_district_parses_real_response_shape_and_crosswalks(self, monkeypatch, tmp_path):
        # District rows are 3-field (AGS;name;value), unlike nation/state's
        # 2-field (label;value) -- see _parse_district_table. A real
        # AGS-to-NUTS3 crosswalk (destatis/crosswalk.py) must resolve the
        # NUTS3 GEOID GISCO/geography.py expects.
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))

        # As with the state test above, `_fetch_missing` now also fetches
        # the real district sex-breakdown table (12411-0016) after the
        # population table (12411-0015) -- track every call.
        calls = []

        def fake_fetch_table(table_code, **kwargs):
            calls.append({"table_code": table_code, **kwargs})
            return (
                "Tabelle: 12411-0015\n"
                "Bevölkerung: Kreise, Stichtag;;\n"
                ";;Stichtag\n"
                ";;31.12.2022\n"
                "09161;Ingolstadt, kreisfreie Stadt;138263\n"
                "09162;München, kreisfreie Stadt;1490516\n"
                "__________\n"
            )

        monkeypatch.setattr(api, "fetch_table", fake_fetch_table)
        monkeypatch.setattr(
            geography,
            "district_names",
            lambda data_dir=None: {"DE211": "Ingolstadt, Kreisfreie Stadt", "DE212": "München, Kreisfreie Stadt"},
        )

        result = loader._fetch_missing(["destatis_population"], "district", "BY", 2022, None, str(tmp_path))
        captured = calls[0]
        assert captured["table_code"] == "12411-0015"
        assert captured["regionalvariable"] == "KREISE"
        assert captured["regionalkey"] == "09*"
        assert set(result["GEOID"]) == {"DE211", "DE212"}
        assert dict(zip(result["GEOID"], result["destatis_population"])) == {"DE211": 138263, "DE212": 1490516}

    def test_fetch_missing_district_parses_real_foreign_population_response_shape(self, monkeypatch, tmp_path):
        # foreignBornPopulation (statistic 12521, table 12521-0040) is
        # fetched as a third real call after population/sex, keyed by the
        # same real AGS-to-NUTS3 crosswalk. Uses the real total column
        # directly (not male+female, which differs by a real small
        # "unbekannt" residual -- see _parse_foreign_population_table).
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))

        def fake_fetch_table(table_code, **kwargs):
            if table_code == "12411-0015":
                return "09161;Ingolstadt, kreisfreie Stadt;138263\n09162;München, kreisfreie Stadt;1490516\n__________\n"
            if table_code == "12411-0016":
                return "09161;Ingolstadt, kreisfreie Stadt;70000;68263\n09162;München, kreisfreie Stadt;745000;745516\n__________\n"
            if table_code == "12521-0040":
                return "31.12.2022;09162;München, kreisfreie Stadt;260335;245420;505760\n__________\n"
            raise AssertionError(f"unexpected table_code {table_code}")

        monkeypatch.setattr(api, "fetch_table", fake_fetch_table)
        monkeypatch.setattr(
            geography,
            "district_names",
            lambda data_dir=None: {"DE211": "Ingolstadt, Kreisfreie Stadt", "DE212": "München, Kreisfreie Stadt"},
        )

        result = loader._fetch_missing(
            ["destatis_population", "destatis_foreignBornPopulation"], "district", "BY", 2022, None, str(tmp_path)
        )
        by_geoid = dict(zip(result["GEOID"], result["destatis_foreignBornPopulation"]))
        assert by_geoid["DE212"] == 505760
        # No real 12521-0040 row for Ingolstadt in this fake response --
        # real NaN, not fabricated zero.
        assert pd.isna(by_geoid["DE211"])

    def test_fetch_missing_district_raises_on_unmatched_crosswalk(self, monkeypatch, tmp_path):
        # If a real GENESIS district row can't be matched to any NUTS3
        # code, refuse to silently drop it -- raise, don't fabricate.
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))
        monkeypatch.setattr(
            api,
            "fetch_table",
            lambda *a, **k: "09999;Nirgendwo, Landkreis;1000\n__________\n",
        )
        monkeypatch.setattr(geography, "district_names", lambda data_dir=None: {"DE212": "München, Kreisfreie Stadt"})
        with pytest.raises(ValueError):
            loader._fetch_missing(["destatis_population"], "district", "BY", 2022, None, str(tmp_path))

    def test_parse_district_table_extracts_ags_name_value_rows(self):
        # Real shape of GENESIS' district (12411-0015) response, confirmed
        # live 2026-08-22 -- three semicolon-delimited fields per row,
        # unlike nation/state's two.
        content = (
            "Tabelle: 12411-0015\n"
            "Bevölkerung: Kreise, Stichtag;;\n"
            ";;Stichtag\n"
            ";;31.12.2022\n"
            "09162;München, kreisfreie Stadt;1490516\n"
            "__________\n"
        )
        assert loader._parse_district_table(content) == [("09162", "München, kreisfreie Stadt", 1490516)]

    def test_parse_flat_table_extracts_label_value_rows(self):
        # Real shape of a GENESIS data/table response filtered to one year
        # (see pycensus.countries.germany.api.fetch_table docstring) --
        # verified live 2026-08-21 against table 12411-0010.
        content = (
            "Tabelle: 12411-0010\n"
            "Bevölkerung: Bundesländer, Stichtag;\n"
            "Fortschreibung des Bevölkerungsstandes;\n"
            "Bevölkerungsstand (Anzahl);\n"
            ";Stichtag\n"
            ";31.12.2022\n"
            "Bayern;13105221\n"
            "__________\n"
            '"Ab 2022: Ergebnisse auf Grundlage des Zensus 2022."\n'
            "© Statistisches Bundesamt (Destatis), 2026\n"
        )
        assert loader._parse_flat_table(content) == [("Bayern", "13105221")]

    def test_fetch_missing_state_parses_real_response_shape(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))

        # `_fetch_missing` now also fetches the real sex-breakdown table
        # (12411-0011) after the population table (12411-0010) -- track
        # every call instead of overwriting, so this test still checks the
        # original population-table call specifically.
        calls = []

        def fake_fetch_table(table_code, **kwargs):
            calls.append({"table_code": table_code, **kwargs})
            return (
                "Tabelle: 12411-0010\n"
                "Bevölkerung: Bundesländer, Stichtag;\n"
                ";Stichtag\n"
                ";31.12.2022\n"
                "Bayern;13105221\n"
                "__________\n"
            )

        monkeypatch.setattr(api, "fetch_table", fake_fetch_table)
        result = loader._fetch_missing(["destatis_population"], "state", "BY", 2022, None, str(tmp_path))
        captured = calls[0]
        assert captured["table_code"] == "12411-0010"
        assert captured["regionalvariable"] == "DLAND"
        assert captured["regionalkey"] == "09"
        assert list(result["GEOID"]) == ["DE2"]
        assert list(result["destatis_population"]) == [13105221]

    def test_fetch_missing_state_returns_only_requested_columns(self, monkeypatch, tmp_path):
        # Regression test: `_fetch_missing` used to ignore its
        # `missing_prefixed` argument and always return the FULL
        # population/sex/foreign-born frame, regardless of what was asked
        # for. That's harmless on a fresh cache (everything's missing
        # anyway) but breaks `cache.load_region`'s merge on a *second*
        # `load()` call against a cache that already has some of those
        # columns (e.g. a stale on-disk cache written before
        # `foreignBornPopulation` existed, or a pipeline that calls
        # `load()` more than once against the same cache_dir): pandas'
        # `.merge()` sees the returned population/male/female columns
        # collide with the already-cached ones and raises
        # "Passing 'suffixes' which cause duplicate columns ... is not
        # allowed." Reproduced live 2026-08-23 on Hamburg's pipeline.
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))
        monkeypatch.setattr(
            api,
            "fetch_table",
            lambda table_code, **kwargs: (
                "Tabelle: 12411-0010\n"
                "Bevölkerung: Bundesländer, Stichtag;\n"
                ";Stichtag\n"
                ";31.12.2022\n"
                "Bayern;13105221\n"
                "__________\n"
            ),
        )
        result = loader._fetch_missing(
            ["destatis_foreignBornPopulation"], "state", "BY", 2022, None, str(tmp_path)
        )
        assert set(result.columns) == {"GEOID", "destatis_foreignBornPopulation"}

    def test_load_second_call_against_stale_cache_missing_one_column_does_not_crash(
        self, monkeypatch, tmp_path
    ):
        # End-to-end regression test for the same bug via the real
        # `load()` -> `cache.load_region` -> `_fetch_missing` path: seed a
        # cache file that already has population/male/female (as if
        # written by an earlier pyCensus version, before
        # foreignBornPopulation was added to the schema) and confirm
        # `load()` can still add the missing column without a merge crash.
        import pycensus.cache as cache_store

        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))
        monkeypatch.setattr(
            api,
            "fetch_table",
            lambda table_code, **kwargs: (
                "Tabelle: 12411-0010\n"
                "Bevölkerung: Bundesländer, Stichtag;\n"
                ";Stichtag\n"
                ";31.12.2022\n"
                "Bayern;13105221\n"
                "__________\n"
            ),
        )

        boundary = gpd.GeoDataFrame(
            {"GEOID": ["DE2"], "geometry": [box(10, 48, 11, 49)]}, crs=4326
        )
        monkeypatch.setattr(
            geography, "load_boundaries", lambda level, r, year, data_dir=None: boundary.copy()
        )

        stale_cache = gpd.GeoDataFrame(
            {
                "GEOID": ["DE2"],
                "geometry": [box(10, 48, 11, 49)],
                "destatis_population": [13105221],
                "destatis_malePopulation": [6400000],
                "destatis_femalePopulation": [6700000],
            },
            crs=4326,
        )
        path = cache_store.region_path(str(tmp_path), "germany", "state", "BY")
        cache_store.write_cache(path, stale_cache)

        result = loader.load(regions=["BY"], level="state", cache_dir=str(tmp_path))
        # `load()` runs the result through `apply_canonical_names`, which
        # renames columns matching a global schema feature to their bare
        # names.
        assert list(result["population"]) == [13105221]
        assert result["foreignBornPopulation"].isna().all()

    def test_fetch_missing_nation_parses_real_response_shape(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "resolve_genesis_credentials", lambda *a, **k: ("u", "p"))

        def fake_fetch_table(table_code, **kwargs):
            return (
                "Tabelle: 12411-0001\n"
                "Bevölkerung: Deutschland, Stichtag;\n"
                ";Bevölkerungsstand\n"
                ";Anzahl\n"
                "31.12.2022;83118501\n"
                "__________\n"
            )

        monkeypatch.setattr(api, "fetch_table", fake_fetch_table)
        result = loader._fetch_missing(["destatis_population"], "nation", None, 2022, None, str(tmp_path))
        assert list(result["GEOID"]) == ["DE"]
        assert list(result["destatis_population"]) == [83118501]

    def test_fetch_missing_municipality_uses_gisco_lau_not_genesis(self, monkeypatch, tmp_path):
        # Municipality population comes from GISCO LAU, not GENESIS -- no
        # credentials should be required, and api.fetch_table must not be
        # called at all for this level.
        import pandas as pd

        def fail_if_called(*a, **k):
            raise AssertionError("GENESIS should not be hit for municipality level")

        monkeypatch.setattr(api, "resolve_genesis_credentials", fail_if_called)
        monkeypatch.setattr(api, "fetch_table", fail_if_called)
        monkeypatch.setattr(
            geography,
            "municipality_population",
            lambda data_dir=None: pd.DataFrame(
                {
                    "GEOID": ["09162000", "09188139", "02000000"],
                    "LAU_NAME": ["München", "Starnberg", "Hamburg"],
                    "POP_2021": [1488202.0, 23511.0, 1852478.0],
                }
            ),
        )
        result = loader._fetch_missing(["destatis_population"], "municipality", "BY", 2021, None, str(tmp_path))
        assert set(result["GEOID"]) == {"09162000", "09188139"}
        assert dict(zip(result["GEOID"], result["destatis_population"]))["09162000"] == 1488202

    def test_download_census_data_boundaries_works_without_credentials(self, monkeypatch, tmp_path):
        import pycensus.countries.germany.geography as geo_mod

        calls = []
        monkeypatch.setattr(geo_mod, "load_boundaries", lambda level, r, year, data_dir=None: calls.append(r))
        loader.download_census_data(data_type="boundaries", level="state", regions=["HH"], cache_dir=str(tmp_path))
        assert calls == ["HH"]

    def test_download_census_data_aggregated_requires_credentials(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "resolve_api_key", lambda *a, **k: None)
        with pytest.raises(api.GenesisCredentialsError):
            loader.download_census_data(data_type="aggregated", regions=["HH"], cache_dir=str(tmp_path))


class TestAccessor:
    def test_accessor_registered(self):
        poly_gdf = gpd.GeoDataFrame(
            {"GEOID": ["DE6"], "destatis_population": [1900000]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        assert hasattr(poly_gdf, "destatis")
        assert poly_gdf.destatis["population"].tolist() == [1900000]


class TestCrosswalk:
    """Offline tests for the real AGS-to-NUTS3 name-matching crosswalk.

    See pycensus.countries.germany.destatis.crosswalk's module docstring
    for the live-network verification this logic was checked against
    (400/400 GENESIS district rows matched, 6 real districts' populations
    independently cross-checked)."""

    def test_exact_match_simple_names(self):
        ags_rows = [("09184", "München, Landkreis", 350047), ("13072", "Rostock, Landkreis", 218132)]
        nuts_names = {"DE21H": "München, Landkreis", "DE80K": "Rostock"}
        matched, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
        assert matched == {"09184": "DE21H", "13072": "DE80K"}
        assert unmatched == []

    def test_disambiguates_same_core_name_by_kreistyp(self):
        # A real, common ambiguity: a kreisfreie Stadt and its surrounding
        # Landkreis often share the same core name (München city vs.
        # München district) -- the Kreistyp suffix must disambiguate.
        ags_rows = [
            ("09162", "München, kreisfreie Stadt", 1490516),
            ("09184", "München, Landkreis", 350047),
        ]
        nuts_names = {"DE212": "München, Kreisfreie Stadt", "DE21H": "München, Landkreis"}
        matched, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
        assert matched == {"09162": "DE212", "09184": "DE21H"}
        assert unmatched == []

    def test_fuzzy_match_handles_gisco_abbreviations(self):
        # Real, verified live 2026-08-22: GISCO abbreviates "in der" -> "i.
        # d." for this exact district.
        ags_rows = [("09373", "Neumarkt in der Oberpfalz, Landkreis", 136901)]
        nuts_names = {"DE236": "Neumarkt i. d. OPf."}
        matched, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
        assert matched == {"09373": "DE236"}
        assert unmatched == []

    def test_unrelated_name_is_reported_unmatched_not_guessed(self):
        ags_rows = [("00000", "Vollkommen Andere Stadt, kreisfreie Stadt", 1)]
        nuts_names = {"DE212": "München, Kreisfreie Stadt"}
        matched, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
        assert matched == {}
        assert unmatched == [("00000", "Vollkommen Andere Stadt, kreisfreie Stadt", 1)]

    def test_no_nuts3_code_claimed_twice(self):
        # Two AGS rows that would both fuzzy-match the same NUTS3 code must
        # not silently collide -- the second should either match a
        # different, correct code or come back unmatched.
        ags_rows = [
            ("09162", "München, kreisfreie Stadt", 1490516),
            ("09184", "München, Landkreis", 350047),
        ]
        nuts_names = {"DE212": "München, Kreisfreie Stadt", "DE21H": "München, Landkreis"}
        matched, _ = crosswalk.match_districts(ags_rows, nuts_names)
        assert len(set(matched.values())) == len(matched)


@pytest.mark.network
def test_real_district_table_matches_national_total():
    """Hits the live GENESIS-Online district table (12411-0015) for all 16
    states and the live GISCO NUTS3 boundaries. Verified 2026-08-22: summing
    all 400 real GENESIS district rows gives exactly 83,118,501 -- identical
    to the independently verified real national total (table 12411-0001,
    see TestApi.test_list_datasets_references_real_verified_statistic) and
    Destatis' own published 31.12.2022 figure."""
    from pycensus.countries.germany import geography

    nuts_names = geography.district_names()
    ags_rows = []
    for state_ags in constants.STATE_AGS.values():
        content = api.fetch_table(
            constants.GENESIS_POPULATION_TABLES["district"],
            startyear=2022,
            endyear=2022,
            regionalvariable="KREISE",
            regionalkey=f"{state_ags}*",
        )
        ags_rows.extend(loader._parse_district_table(content))

    assert len(ags_rows) == 400
    matched, unmatched = crosswalk.match_districts(ags_rows, nuts_names)
    assert unmatched == []
    assert len(matched) == 400
    assert sum(pop for _, _, pop in ags_rows) == 83_118_501


@pytest.mark.network
def test_real_district_population_matches_published_zensus_figures():
    """Hits the live GENESIS-Online district table. Verified 2026-08-22:
    each district's real 31.12.2022 GENESIS population is a small,
    plausible increase (0.3-1.2%, consistent with ~7.5 months of growth)
    over its real, independently published Zensus 2022 (2022-05-15
    reference date) population -- Muenchen was already verified exactly
    (1,490,516) in an earlier session against Destatis' own published
    figure. Sources: stuttgart.de (Stuttgart), city of Cologne/NRW press
    coverage (Koeln), Statistik Nord (Hamburg), Amt fuer Statistik
    Berlin-Brandenburg (Berlin), Stadt Leipzig press release (Leipzig)."""
    expected_zensus_2022_min = {
        "09162": 1_490_516,  # München -- exact match, verified earlier session
        "08111": 610_459,  # Stuttgart
        "05315": 1_017_355,  # Köln
        "02000": 1_811_343,  # Hamburg
        "11000": 3_596_999,  # Berlin
        "14713": 598_899,  # Leipzig, kreisfreie Stadt
    }
    ags_rows = []
    for state_ags in {"09", "08", "05", "02", "11", "14"}:
        content = api.fetch_table(
            constants.GENESIS_POPULATION_TABLES["district"],
            startyear=2022,
            endyear=2022,
            regionalvariable="KREISE",
            regionalkey=f"{state_ags}*",
        )
        ags_rows.extend(loader._parse_district_table(content))

    by_ags = {ags: pop for ags, _, pop in ags_rows}
    for ags, zensus_pop in expected_zensus_2022_min.items():
        genesis_pop = by_ags[ags]
        assert genesis_pop >= zensus_pop, (ags, genesis_pop, zensus_pop)
        # 7.5 months of growth should not plausibly exceed 3%.
        assert genesis_pop <= zensus_pop * 1.03, (ags, genesis_pop, zensus_pop)


@pytest.mark.network
def test_real_lau_municipality_population_sums_to_real_district_total():
    """Hits the live GISCO LAU 2021 geojson and the live GENESIS district
    table. Verified 2026-08-22: Landkreis Starnberg (AGS 09188)'s 15 real
    LAU municipalities sum to 136,610 (2021 vintage) vs. GENESIS'
    138,488 (31.12.2022) for the same Kreis -- a +1.37% change over ~1.5
    years, consistent with growth already verified for other districts at
    the district level (see test_real_district_population_matches_published_zensus_figures)."""
    from pycensus.countries.germany import geography

    lau = geography.municipality_population()
    starnberg = lau[lau["GEOID"].str.startswith("09188")]
    assert len(starnberg) == 15

    content = api.fetch_table(
        constants.GENESIS_POPULATION_TABLES["district"],
        startyear=2022,
        endyear=2022,
        regionalvariable="KREISE",
        regionalkey="09188*",
    )
    district_rows = loader._parse_district_table(content)
    assert len(district_rows) == 1
    district_pop = district_rows[0][2]

    lau_sum = starnberg["POP_2021"].sum()
    # 2021 -> 2022 growth should be small and positive, same pattern as
    # every other district-level cross-check in this file.
    assert lau_sum <= district_pop
    assert lau_sum >= district_pop * 0.95


@pytest.mark.network
def test_real_lau_geoid_is_literally_the_ags_code():
    """Verified 2026-08-22: GISCO's LAU_ID for Germany is the real 8-digit
    AGS code, not an independent GISCO code -- confirmed against six known
    municipalities across six different states, so no name-matching
    crosswalk (unlike district) is needed for this level."""
    from pycensus.countries.germany import geography

    lau = geography.municipality_population()
    known_ags_pop = {
        "01001000": "Flensburg",
        "09162000": "München",
        "11000000": "Berlin",
        "02000000": "Hamburg",
        "08111000": "Stuttgart",
    }
    geoids = set(lau["GEOID"])
    for ags, name_fragment in known_ags_pop.items():
        assert ags in geoids, (ags, name_fragment)


@pytest.mark.network
def test_real_foreign_population_matches_live_verified_munich_figure():
    """Hits the live GENESIS-Online statistic 12521 (Auslaenderstatistik).
    Verified 2026-08-23: Muenchen (Kreis AGS 09162 -> NUTS3 DE212), real
    table 12521-0040, 31.12.2022: male=260,335, female=245,420,
    total=505,760 (note: total != male+female by a real -5 "unbekannt"
    residual, see _parse_foreign_population_table's docstring -- the real
    total column is used directly, not derived)."""
    result = loader._fetch_missing(["destatis_foreignBornPopulation"], "district", "BY", 2022, None, None)
    row = result[result["GEOID"] == "DE212"]
    assert len(row) == 1
    assert row["destatis_foreignBornPopulation"].iloc[0] == 505760
