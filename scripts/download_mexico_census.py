#!/usr/bin/env python
"""Script to automatically download INEGI Census 2020 data for pyCensus.

This script downloads pre-aggregated census data from INEGI's open data portal
and saves it in the data/mexico/ directory in the format expected by pyCensus.

Usage:
    python scripts/download_mexico_census.py [--level LEVEL] [--states STATE1 STATE2 ...]
    
Options:
    --level      Geographic level to download: state, municipality, locality, ageb (default: all)
    --states     Specific states to download (by name, code, or abbreviation)
    --overwrite  Overwrite existing files (default: False)
    --help       Show this help message

Examples:
    # Download all aggregated data
    python scripts/download_mexico_census.py
    
    # Download only municipality-level data
    python scripts/download_mexico_census.py --level municipality
    
    # Download data for specific states
    python scripts/download_mexico_census.py --states Jalisco NuevoLeon
    
    # Download everything and overwrite existing files
    python scripts/download_mexico_census.py --overwrite
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pycensus.mexico import api, constants


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download INEGI Census 2020 data for pyCensus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--level",
        nargs="*",
        choices=["state", "municipality", "locality", "ageb"],
        default=["state", "municipality", "locality", "ageb"],
        help="Geographic level(s) to download (default: all)"
    )
    parser.add_argument(
        "--states",
        nargs="*",
        default=None,
        help="Specific states to download (by name, code, or abbreviation)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing files"
    )
    parser.add_argument(
        "--data-dir",
        default="data/mexico",
        help="Base directory for data (default: data/mexico)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2020,
        help="Census year (default: 2020)"
    )
    return parser.parse_args()


def resolve_states(states: Optional[List[str]]) -> List[str]:
    """Resolve state names/codes/abbreviations to INEGI codes."""
    if states is None:
        return list(constants.STATE_CODES.keys())
    
    resolved = []
    for state in states:
        try:
            code = constants.state_code(state)
            resolved.append(code)
        except ValueError as e:
            print(f"Warning: Unknown state '{state}': {e}")
    
    return resolved


def download_aggregated_data(
    levels: List[str],
    states: Optional[List[str]],
    year: int,
    data_dir: str,
    overwrite: bool,
) -> int:
    """Download aggregated census data.
    
    Returns:
        Number of files successfully downloaded.
    """
    print("=" * 60)
    print("Downloading Aggregated Census Data")
    print("=" * 60)
    
    from pycensus.mexico import utils
    
    # For aggregated data, INEGI provides national-level files for each level
    # (state, municipality, locality, ageb) that contain all states
    
    downloaded = 0
    
    for level in levels:
        print(f"\nDownloading {level}-level data...")
        try:
            result = api.fetch_aggregated_data(
                level=level,
                year=year,
                data_dir=data_dir,
                overwrite=overwrite
            )
            if result is not None:
                print(f"  ✓ Downloaded {level} data to {result}")
                downloaded += 1
            else:
                print(f"  ✗ Failed to download {level} data (file may already exist)")
        except Exception as e:
            print(f"  ✗ Error downloading {level} data: {e}")
    
    return downloaded


def download_boundary_data(
    levels: List[str],
    states: Optional[List[str]],
    year: int,
    data_dir: str,
    overwrite: bool,
) -> int:
    """Download geographic boundary data.
    
    Returns:
        Number of files successfully downloaded/created.
    """
    print("\n" + "=" * 60)
    print("Downloading Boundary Data")
    print("=" * 60)
    
    from pycensus.mexico import utils
    
    # If no states specified, download for all states
    if states is None:
        states = list(constants.STATE_CODES.keys())
    
    downloaded = 0
    
    for level in levels:
        print(f"\nDownloading {level} boundaries...")
        
        # For state-level and above, we can try to download national files
        # For lower levels, we need per-state files
        if level in ["state", "nation"]:
            try:
                result = api.fetch_boundaries(
                    level=level,
                    state=None,
                    year=year,
                    data_dir=data_dir,
                    overwrite=overwrite
                )
                if result is not None:
                    print(f"  ✓ Downloaded {level} boundaries to {result}")
                    downloaded += 1
            except Exception as e:
                print(f"  ✗ Error downloading {level} boundaries: {e}")
        else:
            # For municipality, locality, ageb - download per state
            for state_code in states:
                state_name = constants.STATE_CODES.get(state_code, state_code)
                try:
                    result = api.fetch_boundaries(
                        level=level,
                        state=state_code,
                        year=year,
                        data_dir=data_dir,
                        overwrite=overwrite
                    )
                    if result is not None:
                        print(f"  ✓ Downloaded {level} boundaries for {state_name} to {result}")
                        downloaded += 1
                except Exception as e:
                    print(f"  ✗ Error downloading {level} boundaries for {state_name}: {e}")
    
    return downloaded


def main():
    """Main function."""
    args = parse_args()
    
    # Ensure data directory exists
    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Data directory: {data_dir}")
    print(f"Raw data directory: {raw_dir}")
    
    # Resolve states
    state_codes = resolve_states(args.states)
    print(f"States: {state_codes}")
    
    # Download aggregated data
    agg_downloaded = download_aggregated_data(
        levels=args.level,
        states=state_codes if args.states else None,
        year=args.year,
        data_dir=str(data_dir),
        overwrite=args.overwrite
    )
    
    # Download boundary data
    boundary_downloaded = download_boundary_data(
        levels=args.level,
        states=state_codes if args.states else None,
        year=args.year,
        data_dir=str(data_dir),
        overwrite=args.overwrite
    )
    
    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Aggregated data files downloaded: {agg_downloaded}")
    print(f"Boundary files downloaded: {boundary_downloaded}")
    print(f"Total files: {agg_downloaded + boundary_downloaded}")
    print("\nData saved to:")
    print(f"  {raw_dir}")
    print("\nNext steps:")
    print("  1. Verify files in data/mexico/raw/")
    print("  2. Use pycensus.mexico.census2020.load() to load data")
    print("  3. Example:")
    print("     from pycensus.mexico.census2020 import load")
    print("     gdf = load(states='Jalisco', level='municipality')")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nDownload cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
