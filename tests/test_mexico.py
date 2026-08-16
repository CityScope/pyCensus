"""Tests for Mexico census module."""

import tempfile
from pathlib import Path

import pytest

from pycensus.mexico import census2020, constants, geography


class TestConstants:
    """Test Mexico constants module."""

    def test_state_codes_exist(self):
        """Test that all 32 state codes are defined."""
        assert len(constants.STATE_CODES) == 32

    def test_state_abbr_exist(self):
        """Test that state abbreviations are defined."""
        assert len(constants.STATE_ABBR) == 32

    def test_state_code_lookup(self):
        """Test state code lookup by name."""
        # Test by full name
        assert constants.state_code("Jalisco") == "14"
        assert constants.state_code("Ciudad de Mexico") == "09"
        
        # Test by code
        assert constants.state_code("14") == "14"
        
        # Test by abbreviation
        assert constants.state_code("JAL") == "14"

    def test_state_abbr_lookup(self):
        """Test state abbreviation lookup."""
        assert constants.state_abbr("Jalisco") == "JAL"
        assert constants.state_abbr("14") == "JAL"

    def test_level_fallback(self):
        """Test level fallback mappings."""
        assert constants.LEVEL_FALLBACK["province"] == "state"
        assert constants.LEVEL_FALLBACK["county"] == "municipality"
        assert constants.LEVEL_FALLBACK["tract"] == "ageb"
        assert constants.LEVEL_FALLBACK["blockgroup"] == "ageb"
        assert constants.LEVEL_FALLBACK["place"] == "locality"

    def test_latest_year(self):
        """Test latest year configuration."""
        assert constants.LATEST_YEAR["census"] == 2020
        assert constants.LATEST_YEAR["geography"] == 2020


class TestSchema:
    """Test Mexico census 2020 schema."""

    def test_schema_has_prefix(self):
        """Test that schema has correct prefix."""
        assert census2020.SCHEMA.prefix == "census2020"

    def test_schema_has_columns(self):
        """Test that schema has defined columns."""
        assert len(census2020.SCHEMA.columns) > 0

    def test_essential_columns_exist(self):
        """Test that essential columns are defined in schema."""
        essential_columns = [
            "population",
            "population_male", 
            "population_female",
            "households",
            "employed",
            "unemployed",
            "households_renter",
            "households_owner",
            "population_indigenous",
            "population_catholic",
            "population_speaks_indigenous_language",
        ]
        for col in essential_columns:
            assert col in census2020.SCHEMA.columns, f"Missing essential column: {col}"

    def test_column_definitions(self):
        """Test that columns have proper definitions."""
        col = census2020.SCHEMA.columns["population"]
        assert col.name == "population"
        assert col.codes == ["POBTOTAL"]
        assert col.agg == "sum"


class TestGeography:
    """Test Mexico geography module."""

    def test_states_in_aoi_returns_list(self):
        """Test that states_in_aoi returns a list."""
        # This will return all states since we don't have actual AOI data
        result = geography.states_in_aoi(None)
        assert isinstance(result, list)

    def test_load_boundaries_placeholder(self):
        """Test that load_boundaries creates placeholder boundaries without data."""
        import warnings
        import geopandas as gpd
        from pathlib import Path
        
        # Clean up any existing boundary files
        raw_dir = Path("data/mexico/raw")
        if raw_dir.exists():
            for f in raw_dir.glob("estados_*.gpkg"):
                f.unlink()
        
        # This should now return a GeoDataFrame with placeholder boundaries
        # and issue a warning instead of raising an error
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            gdf = geography.load_boundaries("state", "14", 2020)
            
            # Check that a warning was issued
            assert len(w) > 0
            assert "No geographic data source configured" in str(w[0].message)
        
        # Check that we got a GeoDataFrame with the expected structure
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert "GEOID" in gdf.columns
        assert len(gdf) > 0
        assert gdf.crs is not None


class TestLoader:
    """Test Mexico census 2020 loader."""

    def test_download_creates_directory(self, tmp_path):
        """Test that download function creates necessary directories."""
        from pycensus.mexico.census2020.loader import download_census_data
        
        data_dir = str(tmp_path / "test_data")
        result = download_census_data(
            data_type="aggregated",
            level="state",
            data_dir=data_dir,
        )
        
        assert Path(result).exists()

    def test_schema_prefixed_columns(self):
        """Test that schema correctly prefixes column names."""
        assert census2020.SCHEMA.prefixed("population") == "census2020_population"
        assert census2020.SCHEMA.prefixed("households") == "census2020_households"

    def test_schema_strip_prefix(self):
        """Test that schema correctly strips prefixes."""
        assert census2020.SCHEMA.strip_prefix("census2020_population") == "population"
        assert census2020.SCHEMA.strip_prefix("population") == "population"

    def test_schema_relative_to(self):
        """Test that schema correctly resolves relative_to columns."""
        # population_male should be relative to population
        col = census2020.SCHEMA.columns["population_male"]
        assert col.relative_to == "population"
        
        # Check that the prefixed version works
        relative_col = census2020.SCHEMA.relative_to("census2020_population_male")
        assert relative_col == "census2020_population"


class TestAccessors:
    """Test that Mexico accessors are registered."""

    def test_accessor_registered(self):
        """Test that census2020 accessor is registered."""
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Polygon
        
        # Create a simple GeoDataFrame
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        gdf = gpd.GeoDataFrame({"GEOID": ["01"], "geometry": [poly]}, crs="EPSG:4326")
        
        # Add some census2020 columns
        gdf["census2020_population"] = [1000]
        gdf["census2020_households"] = [200]
        
        # Test that accessor exists
        assert hasattr(gdf, "census2020")

    def test_accessor_columns(self):
        """Test that accessor provides column list."""
        import geopandas as gpd
        from shapely.geometry import Polygon
        
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        gdf = gpd.GeoDataFrame({"GEOID": ["01"], "geometry": [poly]}, crs="EPSG:4326")
        
        # Test that we can access columns property
        assert hasattr(gdf.census2020, "columns")
        assert isinstance(gdf.census2020.columns, list)
