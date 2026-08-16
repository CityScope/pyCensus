#!/usr/bin/env python
"""Test script for Spain census implementation."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_constants():
    """Test constants module."""
    print("Testing constants module...")
    from pycensus.spain.constants import (
        AUTONOMOUS_COMMUNITY_CODES, 
        AUTONOMOUS_COMMUNITY_ABBR,
        PROVINCE_CODES,
        PROVINCE_ABBR,
        LEVEL_FALLBACK,
        LATEST_YEAR
    )
    
    print(f"  ✓ Autonomous Communities: {len(AUTONOMOUS_COMMUNITY_CODES)}")
    print(f"  ✓ Provinces: {len(PROVINCE_CODES)}")
    print(f"  ✓ Level Fallback: {LEVEL_FALLBACK}")
    print(f"  ✓ Latest Year: {LATEST_YEAR}")
    
    # Test code lookups
    from pycensus.spain.constants import autonomous_community_code, province_code
    
    ac_code = autonomous_community_code("Andalucía")
    print(f"  ✓ Andalucía code: {ac_code}")
    
    prov_code = province_code("Barcelona")
    print(f"  ✓ Barcelona code: {prov_code}")
    
    return True


def test_utils():
    """Test utils module."""
    print("\nTesting utils module...")
    from pycensus.spain.utils import (
        autonomous_community_code,
        autonomous_community_abbr,
        province_code,
        province_abbr
    )
    
    ac_code = autonomous_community_code("Cataluña")
    print(f"  ✓ Cataluña code: {ac_code}")
    
    ac_abbr = autonomous_community_abbr("Madrid (Comunidad de Madrid)")
    print(f"  ✓ Madrid abbreviation: {ac_abbr}")
    
    prov_code = province_code("08")  # Barcelona
    print(f"  ✓ Province 08 name: {prov_code}")
    
    return True


def test_geography():
    """Test geography module."""
    print("\nTesting geography module...")
    from pycensus.spain.geography import (
        GEOMETRY_FUNCS,
        GEO_HIERARCHIES,
        ERASE_WATER
    )
    
    print(f"  ✓ Geometry Functions: {list(GEOMETRY_FUNCS.keys())}")
    print(f"  ✓ Geo Hierarchies: {list(GEO_HIERARCHIES.keys())}")
    print(f"  ✓ Erase Water: {ERASE_WATER}")
    
    return True


def test_schema():
    """Test schema module."""
    print("\nTesting schema module...")
    from pycensus.spain.census2021.schema import SCHEMA
    
    print(f"  ✓ Schema prefix: {SCHEMA.prefix}")
    print(f"  ✓ Schema has {len(SCHEMA.columns)} columns")
    
    # List some columns
    sample_cols = list(SCHEMA.columns.keys())[:10]
    print(f"  ✓ Sample columns: {sample_cols}")
    
    # Check some specific columns
    population = SCHEMA.columns.get('population')
    if population:
        print(f"  ✓ Population column codes: {population.codes}")
    
    households = SCHEMA.columns.get('households')
    if households:
        print(f"  ✓ Households column codes: {households.codes}")
    
    return True


def test_api():
    """Test api module."""
    print("\nTesting api module...")
    from pycensus.spain.api import list_datasets
    
    datasets = list_datasets(2021)
    print(f"  ✓ Available datasets: {len(datasets)}")
    for ds in datasets[:3]:
        print(f"    - {ds['name']}")
    
    return True


def test_census2021_init():
    """Test census2021 __init__ module."""
    print("\nTesting census2021 __init__ module...")
    from pycensus.spain.census2021 import SCHEMA, load, download_census_data
    
    print(f"  ✓ SCHEMA imported: {SCHEMA.prefix}")
    print(f"  ✓ load function imported")
    print(f"  ✓ download_census_data function imported")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Spain Census Implementation")
    print("=" * 60)
    
    tests = [
        test_constants,
        test_utils,
        test_geography,
        test_schema,
        test_api,
        test_census2021_init,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
