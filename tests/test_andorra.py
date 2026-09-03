"""Tests for pycensus.andorra: constants, geography, schema, and the estadisticaad loader.

Technical aspects:
    Network-touching functions (:func:`pycensus.countries.andorra.api.fetch_parish_boundaries`,
    :func:`pycensus.countries.andorra.api.fetch_population_by_locality`) are
    monkeypatched out with small synthetic frames, same pattern as
    ``tests/test_spain.py``. The real ArcGIS endpoints were verified
    manually against the live network during development:
        - ``GET https://www.estadistica.ad/server/rest/services/Estadistica/Cartografia_base/FeatureServer/3/query?where=1%3D1&outFields=*&outSR=4326&f=geojson``
          returns exactly 7 real parish polygons whose ``Codi``/``Nom``
          fields are ``AD-01``..``AD-07`` matching Andorra's real parishes,
          with combined bounds (1.409-1.787 E, 42.429-42.656 N) landing on
          Andorra's known extent.
        - ``GET https://sig.govern.ad/server/rest/services/Hosted/Poblaci%C3%B3_2010_2021/FeatureServer/0/query?where=1%3D1&outFields=*&f=json``
          returns 44 real localities; summing ``pob_2023`` across all of
          them gives 85,101, matching the Departament d'Estadistica's own
          published 31-Dec-2023 total as reported by Diari d'Andorra.
    See the module docstrings in ``pycensus.countries.andorra.api``/``geography``/
    ``estadisticaad.loader`` for the exact URLs.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pycensus.countries.andorra import constants, geography
from pycensus.countries.andorra.estadisticaad import loader
from pycensus.countries.andorra.estadisticaad.schema import SCHEMA


class TestConstants:
    def test_parish_count(self):
        assert len(constants.PARISH_CODES) == 7

    def test_parish_codes_are_real_iso_3166_2(self):
        assert constants.PARISH_CODES["AD-01"] == "Canillo"
        assert constants.PARISH_CODES["AD-05"] == "Andorra la Vella"
        assert constants.PARISH_CODES["AD-07"] == "Escaldes-Engordany"

    def test_level_fallback(self):
        assert constants.LEVEL_FALLBACK["state"] == "parish"
        assert constants.LEVEL_FALLBACK["municipality"] == "parish"

    def test_latest_year(self):
        assert constants.LATEST_YEAR["census"] == 2025

    def test_parish_code_resolves_name(self):
        assert constants.parish_code("Canillo") == "AD-01"
        assert constants.parish_code("AD-01") == "AD-01"

    def test_parish_code_resolves_known_source_typo(self):
        """Regression guard: the population source spells Sant Julia de
        Loria without the 'i' -- verified live, must still resolve."""
        assert constants.parish_code("Sant Julà de Lòria") == "AD-06"

    def test_parish_code_unknown_raises(self):
        with pytest.raises(ValueError):
            constants.parish_code("Nowhere")


class TestSchema:
    def test_schema_has_prefix(self):
        assert SCHEMA.prefix == "estadisticaad"

    def test_population_column_exists(self):
        assert "population" in SCHEMA.columns

    def test_population_codes_are_real_year_columns(self):
        assert "pob_2023" in SCHEMA.columns["population"].codes
        assert "pob_2025" in SCHEMA.columns["population"].codes

    def test_schema_prefixed_columns(self):
        assert SCHEMA.prefixed("population") == "estadisticaad_population"

    def test_building_count_column_exists(self):
        assert "buildingCount" in SCHEMA.columns
        assert "edif_2019" in SCHEMA.columns["buildingCount"].codes

    def test_active_business_count_column_exists(self):
        assert "activeBusinessCount" in SCHEMA.columns
        assert "empreses_actives" in SCHEMA.columns["activeBusinessCount"].codes

    def test_foreign_born_population_column_exists(self):
        assert "foreignBornPopulation" in SCHEMA.columns
        assert "estrangera" in SCHEMA.columns["foreignBornPopulation"].codes
        assert SCHEMA.columns["foreignBornPopulation"].relative_to == "population"


class TestGeography:
    def test_implemented_levels(self):
        assert set(geography.IMPLEMENTED_LEVELS) == {"nation", "parish"}

    def test_unimplemented_level_raises(self):
        with pytest.raises(NotImplementedError):
            geography.load_boundaries("quart")


def _fake_parishes() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "Nom": ["Canillo", "Encamp", "Andorra la Vella"],
            "Codi": ["AD-01", "AD-02", "AD-05"],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)],
        crs=4326,
    )


def _fake_localities() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "poblacio": ["Canillo poble", "Encamp poble", "Andorra la Vella poble"],
            "parroquia": ["Canillo", "Encamp", "Andorra la Vella"],
            "pob_2023": [100, 200, 300],
            "pob_2025": [110, 210, 310],
        }
    )


class TestGeographyWithFakeParishes:
    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.andorra.api as api_mod

        monkeypatch.setattr(api_mod, "fetch_parish_boundaries", lambda: _fake_parishes())

    def test_parish_level_all(self):
        gdf = geography.load_boundaries("parish")
        assert set(gdf["GEOID"]) == {"AD-01", "AD-02", "AD-05"}

    def test_parish_level_one_region(self):
        gdf = geography.load_boundaries("parish", region="Canillo")
        assert len(gdf) == 1
        assert gdf["GEOID"].iloc[0] == "AD-01"

    def test_nation_level_dissolves_parishes(self):
        gdf = geography.load_boundaries("nation")
        assert len(gdf) == 1
        assert gdf["GEOID"].iloc[0] == "AD"


def _fake_buildings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "parròquia": ["Canillo", "Encamp", "Andorra la Vella"],
            "count": [10, 20, 30],
        }
    )


def _fake_businesses() -> pd.DataFrame:
    return pd.DataFrame({"PARROQUIA": [1, 2, 5], "count": [5, 15, 60]})


def _fake_nationality() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GEOID": ["AD-01", "AD-02", "AD-05", "AD"],
            "foreign_nationality": [40, 110, 540, 690],
            "population": [100, 200, 900, 1200],
        }
    )


class TestLoader:
    """Both real network calls (parish boundaries, population-by-locality) are monkeypatched out."""

    @pytest.fixture(autouse=True)
    def patch_network(self, monkeypatch):
        import pycensus.countries.andorra.api as api_mod
        import pycensus.countries.andorra.estadisticaad.loader as loader_mod

        monkeypatch.setattr(api_mod, "fetch_parish_boundaries", lambda: _fake_parishes())
        monkeypatch.setattr(loader_mod.api, "fetch_population_by_locality", lambda: _fake_localities())
        monkeypatch.setattr(loader_mod.api, "fetch_building_counts_by_parish", lambda: _fake_buildings())
        monkeypatch.setattr(loader_mod.api, "fetch_active_business_counts_by_parish", lambda: _fake_businesses())
        monkeypatch.setattr(
            loader_mod.api, "fetch_population_by_nationality_and_parish", lambda: _fake_nationality()
        )

    def test_load_parish_level(self, tmp_path):
        gdf = loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        assert gdf["population"].iloc[0] == 100

    def test_load_nation_level_sums_parishes(self, tmp_path):
        gdf = loader.load(level="nation", year=2023, cache_dir=str(tmp_path))
        assert len(gdf) == 1
        assert gdf["population"].iloc[0] == 600  # 100 + 200 + 300

    def test_load_different_year_gives_different_value(self, tmp_path):
        gdf_2023 = loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        gdf_2025 = loader.load(regions="AD-01", level="parish", year=2025, cache_dir=str(tmp_path))
        assert gdf_2023["population"].iloc[0] == 100
        assert gdf_2025["population"].iloc[0] == 110

    def test_load_raises_without_regions_or_aoi(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(level="parish", cache_dir=str(tmp_path))

    def test_load_invalid_year_raises(self, tmp_path):
        with pytest.raises(ValueError):
            loader.load(regions="AD-01", level="parish", year=1999, cache_dir=str(tmp_path))

    def test_load_writes_geoparquet_cache_file(self, tmp_path):
        loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        cache_file = tmp_path / "andorra" / "parish" / "AD-01_2023.parquet"
        assert cache_file.exists()
        cached = gpd.read_parquet(cache_file)
        # `cache.load_region` writes the raw (prefixed) fetch result --
        # canonical bare names are only applied afterwards, in-memory, by
        # `apply_canonical_names` in `loader.load`'s return value, so the
        # cache file on disk always carries the prefixed name.
        assert "estadisticaad_population" in cached.columns

    def test_load_second_call_does_not_refetch(self, monkeypatch, tmp_path):
        calls = {"n": 0}

        def counting_fetch():
            calls["n"] += 1
            return _fake_localities()

        import pycensus.countries.andorra.estadisticaad.loader as loader_mod

        monkeypatch.setattr(loader_mod.api, "fetch_population_by_locality", counting_fetch)
        loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        assert calls["n"] == 1

    def test_load_building_count_by_parish(self, tmp_path):
        gdf = loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        assert gdf["estadisticaad_buildingCount"].iloc[0] == 10

    def test_load_building_count_nation_sums_parishes(self, tmp_path):
        gdf = loader.load(level="nation", year=2023, cache_dir=str(tmp_path))
        assert gdf["estadisticaad_buildingCount"].iloc[0] == 60  # 10 + 20 + 30

    def test_load_active_business_count_by_parish(self, tmp_path):
        gdf = loader.load(regions="AD-05", level="parish", year=2023, cache_dir=str(tmp_path))
        assert gdf["estadisticaad_activeBusinessCount"].iloc[0] == 60

    def test_load_active_business_count_same_across_years(self, tmp_path):
        """Business counts are a live snapshot, not tied to a real vintage year."""
        gdf_2023 = loader.load(regions="AD-02", level="parish", year=2023, cache_dir=str(tmp_path))
        gdf_2025 = loader.load(regions="AD-02", level="parish", year=2025, cache_dir=str(tmp_path))
        assert gdf_2023["estadisticaad_activeBusinessCount"].iloc[0] == 15
        assert gdf_2025["estadisticaad_activeBusinessCount"].iloc[0] == 15

    def test_load_foreign_born_population_by_parish(self, tmp_path):
        gdf = loader.load(regions="AD-05", level="parish", year=2023, cache_dir=str(tmp_path))
        assert gdf["foreignBornPopulation"].iloc[0] == 540

    def test_load_foreign_born_population_nation_level(self, tmp_path):
        gdf = loader.load(level="nation", year=2023, cache_dir=str(tmp_path))
        assert gdf["foreignBornPopulation"].iloc[0] == 690

    def test_load_foreign_born_population_same_across_years(self, tmp_path):
        """A single dated bulletin snapshot, not tied to the requested year."""
        gdf_2023 = loader.load(regions="AD-01", level="parish", year=2023, cache_dir=str(tmp_path))
        gdf_2025 = loader.load(regions="AD-01", level="parish", year=2025, cache_dir=str(tmp_path))
        assert gdf_2023["foreignBornPopulation"].iloc[0] == 40
        assert gdf_2025["foreignBornPopulation"].iloc[0] == 40


@pytest.mark.network
def test_real_parish_boundary_service_returns_verified_geometry():
    """Hits the live estadistica.ad ArcGIS Server -- no API key required."""
    from pycensus.countries.andorra import api

    gdf = api.fetch_parish_boundaries()
    assert len(gdf) == 7
    assert set(gdf["Codi"]) == set(constants.PARISH_CODES)


@pytest.mark.network
def test_real_population_service_matches_published_total():
    """Hits the live sig.govern.ad ArcGIS Server -- no API key required."""
    from pycensus.countries.andorra import api

    df = api.fetch_population_by_locality()
    assert len(df) == 44
    total_2023 = df["pob_2023"].sum()
    assert total_2023 == 85_101


@pytest.mark.network
def test_real_building_counts_by_parish():
    """Hits the live sig.govern.ad ArcGIS Server -- no API key required."""
    from pycensus.countries.andorra import api, constants

    df = api.fetch_building_counts_by_parish()
    assert set(df["parròquia"]) == set(constants.PARISH_CODES.values())
    assert df["count"].sum() == 21_529


@pytest.mark.network
def test_real_active_business_counts_by_parish():
    """Hits the live sig.govern.ad ArcGIS Server -- no API key required."""
    from pycensus.countries.andorra import api

    df = api.fetch_active_business_counts_by_parish()
    assert set(df["PARROQUIA"]) == set(range(1, 8))
    assert df["count"].sum() == 8_142
    # Andorra la Vella (parish 5, the capital) real-world sanity check:
    # it should have far more active businesses than any other parish.
    row = df[df["PARROQUIA"] == 5].iloc[0]
    assert row["count"] == df["count"].max()


@pytest.mark.network
def test_real_nationality_bulletin_matches_published_totals():
    """Downloads and parses the real Departament d'Estadistica PDF bulletin.

    No API key required. Cross-checks the parsed 'Estrangera' (foreign
    nationality) and 'Total' population figures against the exact real
    numbers read directly off the bulletin's page 6 table during
    development (verified 2026-08-23), and against Andorra's
    well-documented, independently known ~45-55% foreign-resident share.
    """
    from pycensus.countries.andorra import api, constants

    df = api.fetch_population_by_nationality_and_parish()
    assert set(df["GEOID"]) == set(constants.PARISH_CODES) | {"AD"}

    national = df[df["GEOID"] == "AD"].iloc[0]
    assert national["population"] == 87_486
    assert national["foreign_nationality"] == 48_008
    foreign_share = national["foreign_nationality"] / national["population"]
    assert 0.45 < foreign_share < 0.55

    capital = df[df["GEOID"] == "AD-05"].iloc[0]  # Andorra la Vella
    assert capital["foreign_nationality"] == 13_376
    assert capital["population"] == 24_698
