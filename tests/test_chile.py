"""Tests for pycensus.chile: constants, schema, geography, and the INE loader.

Technical aspects:
    Mirrors ``tests/test_mexico.py``'s pattern: the real network call
    (:func:`pycensus.countries.chile.api.fetch_features`, against the live Esri
    Chile "Division Politico Administrativa y Censal" FeatureServer that
    republishes INE's real Censo 2017 data) is monkeypatched out with a
    small synthetic GeoJSON payload here, to keep the suite offline and
    fast. That real endpoint was verified manually against the live
    network during development: querying region '13' (Region
    Metropolitana) returns T_POB=7,112,808; summing T_POB across all 16
    real regions returns exactly 17,574,003, Chile's real published
    Censo 2017 national population total; comuna 'Santiago' (COMUNA
    '13101') returns T_POB=404,495; comuna 'Concepcion' (COMUNA '8101')
    returns T_POB=223,574 -- see pycensus/chile/api.py's module docstring
    for the full verification notes.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box, mapping

from pycensus.countries.chile import constants, geography, utils
from pycensus.countries.chile.ine import loader
from pycensus.countries.chile.ine.schema import SCHEMA


class TestConstants:
    def test_region_codes_exist(self):
        assert len(constants.REGION_CODES) == 16

    def test_region_names_alias(self):
        assert constants.REGION_NAMES is constants.REGION_CODES

    def test_region_code_lookup(self):
        assert utils.region_code("13") == "13"
        assert utils.region_code(8) == "08"
        assert utils.region_code("Región Metropolitana de Santiago") == "13"
        assert utils.region_code("Bío-Bío") == "08"

    def test_region_api_code_unpadded(self):
        assert utils.region_api_code("08") == "8"
        assert utils.region_api_code("13") == "13"

    def test_unknown_region_raises(self):
        with pytest.raises(ValueError):
            utils.region_code("Not A Real Region")

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["state"] == "region"
        assert constants.LEVEL_FALLBACK["province"] == "region"
        assert constants.LEVEL_FALLBACK["municipality"] == "comuna"
        assert constants.LEVEL_FALLBACK["county"] == "comuna"

    def test_latest_year(self):
        assert isinstance(constants.LATEST_YEAR["census"], int)
        assert isinstance(constants.LATEST_YEAR["geography"], int)

    def test_region_bbox_covers_every_region(self):
        assert set(constants.REGION_BBOX) == set(constants.REGION_CODES)


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "ine_cl"

    def test_schema_has_columns(self):
        assert len(SCHEMA.columns) > 0

    def test_essential_columns_exist(self):
        for col in ["population", "malePopulation", "femalePopulation", "households"]:
            assert col in SCHEMA.columns, f"Missing essential column: {col}"

    def test_column_codes_match_real_dpa_field_names(self):
        """Regression guard: these codes were confirmed against the live
        ArcGIS FeatureServer response's real attribute keys (T_POB, T_HOM,
        T_MUJ, T_VIV), not guessed from another country's convention."""
        assert SCHEMA.columns["population"].codes == ["T_POB"]
        assert SCHEMA.columns["malePopulation"].codes == ["T_HOM"]
        assert SCHEMA.columns["femalePopulation"].codes == ["T_MUJ"]
        assert SCHEMA.columns["households"].codes == ["T_VIV"]

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "ine_cl_population"
        assert SCHEMA.prefixed("households") == "ine_cl_households"

    def test_schema_strip_prefix(self):
        assert SCHEMA.strip_prefix("population") == "population"
        assert SCHEMA.strip_prefix("population") == "population"

    def test_schema_relative_to_resolves(self):
        for name, col in SCHEMA.columns.items():
            if col.relative_to:
                assert col.relative_to in SCHEMA.columns, (
                    f"{name}.relative_to={col.relative_to!r} does not name a real column"
                )


class TestGeography:
    def test_regions_in_aoi_narrows_to_a_small_candidate_set(self):
        # An AOI well inside the Metropolitana region (central Santiago)
        # should resolve to a handful of candidate regions, not all 16.
        aoi = gpd.GeoDataFrame(geometry=[box(-70.68, -33.47, -70.60, -33.40)], crs=4326)
        result = geography.regions_in_aoi(aoi)
        assert isinstance(result, list)
        assert "13" in result  # Region Metropolitana must be included
        assert len(result) < 10

    def test_load_boundaries_requires_region(self):
        with pytest.raises(ValueError):
            geography.load_boundaries("comuna")

    def test_load_boundaries_unimplemented_level_raises(self):
        with pytest.raises(NotImplementedError):
            geography.load_boundaries("nation", region="13")

    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {"region", "provincia", "comuna", "distrito"}


def _fake_geojson(region_value: str) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "REGION": region_value,
                    "PROVINCIA": f"{region_value}1",
                    "COMUNA": f"{region_value}101",
                    "NOM_COMUNA": "Fake Comuna",
                    "T_POB": 100000,
                    "T_HOM": 49000,
                    "T_MUJ": 51000,
                    "T_VIV": 30000,
                },
                "geometry": mapping(box(0, 0, 1, 1)),
            }
        ],
    }


def _fake_fetch_features(level, region, data_dir=None):
    from pycensus.countries.chile import utils as utils_mod

    return _fake_geojson(utils_mod.region_api_code(region))


class TestLoader:
    """INE's own network call (the ArcGIS FeatureServer query) is
    monkeypatched out, same pattern as usa.acs5/mexico.inegi loader tests."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.chile.api as api_mod
        import pycensus.countries.chile.ine.loader as loader_mod

        monkeypatch.setattr(api_mod, "fetch_features", _fake_fetch_features)
        monkeypatch.setattr(loader_mod.api, "fetch_features", _fake_fetch_features)

    def test_load_comuna_level_returns_schema_columns(self, tmp_path):
        gdf = loader.load(regions=["13"], level="comuna", cache_dir=str(tmp_path))
        assert "population" in gdf.columns
        assert gdf["population"].iloc[0] == 100000
        assert gdf["malePopulation"].iloc[0] == 49000
        assert gdf["femalePopulation"].iloc[0] == 51000
        assert gdf["households"].iloc[0] == 30000
        assert gdf.geometry.name == "geometry"
        assert gdf.crs is not None

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="comuna", cache_dir=str(tmp_path))

    def test_load_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(regions=["13"], level="comuna", cache_dir=str(tmp_path))
        cache_file = tmp_path / "chile" / "comuna" / "13.parquet"
        assert cache_file.exists()

        cached = gpd.read_parquet(cache_file)
        assert cached.crs is not None
        # `apply_canonical_names` runs before the cache is written, so
        # the cached file already has bare canonical names too.
        assert "population" in cached.columns
        assert len(cached) == 1

    def test_load_second_call_does_not_refetch(self, monkeypatch, tmp_path):
        # api.fetch_features is shared by geography.load_boundaries (the
        # boundary fetch) and loader._fetch_missing (the attribute fetch),
        # so one cache-miss loader.load() call makes 2 calls to it (one per
        # side) -- what this test guards is that a *second* loader.load()
        # call, once the parquet cache is warm, makes zero more.
        calls = {"n": 0}

        def counting_fetch(level, region, data_dir=None):
            calls["n"] += 1
            return _fake_fetch_features(level, region, data_dir)

        import pycensus.countries.chile.ine.loader as loader_mod

        monkeypatch.setattr(loader_mod.api, "fetch_features", counting_fetch)

        loader.load(regions=["13"], level="comuna", cache_dir=str(tmp_path))
        first_call_count = calls["n"]
        assert first_call_count > 0

        loader.load(regions=["13"], level="comuna", cache_dir=str(tmp_path))
        assert calls["n"] == first_call_count  # second call served from the parquet cache


class TestAccessor:
    def test_accessor_registered(self):
        poly_gdf = gpd.GeoDataFrame(
            {"GEOID": ["13101"], "population": [404495], "households": [166432]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        )
        assert hasattr(poly_gdf, "ine_cl")
        assert poly_gdf.ine_cl["population"].tolist() == [404495]
