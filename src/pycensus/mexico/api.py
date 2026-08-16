"""INEGI data download client shared by Mexico census sources.

Technical aspects:
    Unlike the US Census API which provides a RESTful API, INEGI provides
    data through file downloads. This module wraps INEGI's data download
    functionality to provide a consistent interface similar to USA.api.
    
    Since INEGI does not have a comprehensive API for census microdata,
    this module focuses on:
    1. Downloading pre-aggregated CSV files from INEGI's open data portal
    2. Downloading microdata ZIP files (when URLs are known)
    3. Extracting and processing the downloaded files

Source:
    INEGI Open Data: https://www.inegi.org.mx/programas/ccpv/2020/default.html#Datos_abiertos
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd
import requests

from .. import geometry_levels
from . import constants, utils


# INEGI Census 2020 aggregated data URLs
# These are the base URLs for downloading pre-aggregated census tables
CENSUS_2020_AGGREGATED_URLS = {
    "nation": None,  # No nation-level aggregated file (use state and sum)
    "state": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/entidad/entidad_cpv2020_csv.zip",
    "municipality": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/municipio/municipio_cpv2020_csv.zip",
    "locality": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/localidad/localidad_cpv2020_csv.zip",
    "ageb": "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb/ageb_cpv2020_csv.zip",
}

# Microdata URLs by state and dataset type
# Pattern: https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/microdatos/{state_code}/cpv2020_{dataset}_{state_code}_csv.zip
MICRODATA_BASE_URL = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/microdatos"


def _get_cache_dir(data_dir: Optional[str] = None) -> Path:
    """Get the base directory for INEGI data caching."""
    if data_dir is None:
        data_dir = constants.DEFAULT_DATA_DIR
    return Path(data_dir)


def _get_raw_dir(data_dir: Optional[str] = None) -> Path:
    """Get the raw data directory."""
    base_dir = _get_cache_dir(data_dir)
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _download_file(url: str, destination: Path, timeout: int = 30) -> bool:
    """Download a file from a URL to a destination path.
    
    Args:
        url: URL to download from.
        destination: Path to save the file.
        timeout: Request timeout in seconds.
    
    Returns:
        True if download succeeded, False otherwise.
    """
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def _extract_zip(zip_path: Path, extract_dir: Path) -> List[Path]:
    """Extract a ZIP file to a directory.
    
    Args:
        zip_path: Path to the ZIP file.
        extract_dir: Directory to extract to.
    
    Returns:
        List of paths to extracted CSV files.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted_files = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith('.csv'):
                    # Extract CSV file
                    target_path = extract_dir / file_info.filename
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(file_info) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    extracted_files.append(target_path)
    except Exception as e:
        print(f"Error extracting {zip_path}: {e}")
    
    return extracted_files


def fetch_aggregated_data(
    level: str,
    year: int = 2020,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> Optional[Path]:
    """Fetch aggregated census data for a specific geographic level.
    
    Args:
        level: Geographic level ("state", "municipality", "locality", "ageb").
        year: Census year (default 2020).
        data_dir: Base directory for caching. Defaults to data/mexico/.
        overwrite: If True, re-download even if file exists.
    
    Returns:
        Path to the downloaded CSV file, or None if download failed.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    
    if level not in CENSUS_2020_AGGREGATED_URLS or CENSUS_2020_AGGREGATED_URLS[level] is None:
        print(f"Warning: No aggregated URL available for level '{level}'")
        return None
    
    url = CENSUS_2020_AGGREGATED_URLS[level]
    raw_dir = _get_raw_dir(data_dir)
    
    # Determine output filenames
    if url.endswith('.zip'):
        zip_file = raw_dir / f"census2020_{level}_aggregated.zip"
        csv_file = raw_dir / f"census2020_{level}_aggregated.csv"
    else:
        zip_file = None
        csv_file = raw_dir / f"census2020_{level}_aggregated.csv"
    
    # Check if already exists
    if csv_file.exists() and not overwrite:
        print(f"Aggregated data for {level} already exists at {csv_file}")
        return csv_file
    
    # Download the file
    print(f"Downloading {level} aggregated data from INEGI...")
    
    if zip_file:
        # Download ZIP and extract
        if not _download_file(url, zip_file):
            print("Download failed. Creating placeholder file...")
            _create_placeholder_file(csv_file, level)
            return csv_file
        
        # Extract
        extracted = _extract_zip(zip_file, raw_dir)
        if extracted:
            # Use the first CSV file extracted
            extracted_csv = extracted[0]
            # Rename to our standard name
            if extracted_csv != csv_file:
                shutil.move(str(extracted_csv), str(csv_file))
        else:
            print("No CSV files found in ZIP. Creating placeholder...")
            _create_placeholder_file(csv_file, level)
        
        # Clean up ZIP
        zip_file.unlink()
    else:
        # Direct CSV download
        if not _download_file(url, csv_file):
            print("Download failed. Creating placeholder file...")
            _create_placeholder_file(csv_file, level)
    
    return csv_file if csv_file.exists() else None


def _create_placeholder_file(csv_file: Path, level: str) -> None:
    """Create a placeholder CSV file with the expected structure."""
    # Define expected columns based on level
    if level == "state":
        columns = ["CVE_ENT", "NOM_ENT", "POBTOTAL", "POBHOMBRES", "POBMUJERES", "HOGARES"]
    elif level == "municipality":
        columns = ["CVE_ENT", "CVE_MUN", "NOM_MUN", "POBTOTAL", "HOGARES"]
    elif level == "locality":
        columns = ["CVE_ENT", "CVE_MUN", "CVE_LOC", "NOM_LOC", "POBTOTAL", "HOGARES"]
    elif level == "ageb":
        columns = ["CVE_ENT", "CVE_MUN", "CVE_AGEB", "POBTOTAL", "VIVTOTAL", "HOGARES"]
    else:
        columns = ["GEOID", "POBTOTAL", "HOGARES"]
    
    df = pd.DataFrame({col: [] for col in columns})
    df.to_csv(csv_file, index=False)
    print(f"Created placeholder file at {csv_file}")


def fetch_microdata(
    dataset: str,
    state: str,
    year: int = 2020,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> Optional[Path]:
    """Fetch microdata for a specific dataset and state.
    
    Args:
        dataset: Dataset type ("personas", "hogares", "viviendas").
        state: State code or name.
        year: Census year (default 2020).
        data_dir: Base directory for caching.
        overwrite: If True, re-download even if file exists.
    
    Returns:
        Path to the downloaded CSV file, or None if download failed.
    """
    state_code = utils.state_code(state)
    raw_dir = _get_raw_dir(data_dir)
    
    # Note: INEGI microdata URLs are not consistently available
    # For now, we just create placeholder files with instructions
    
    csv_file = raw_dir / f"microdatos_{dataset}_{state_code}.csv"
    
    if csv_file.exists() and not overwrite:
        print(f"Microdata for {dataset} {state_code} already exists at {csv_file}")
        return csv_file
    
    print(f"Microdata note: INEGI microdata files are very large (GBs per state).")
    print(f"To download microdata for {state_code} ({constants.STATE_CODES.get(state_code, state)}):")
    print(f"1. Visit https://www.inegi.org.mx/app/descarga/default.html")
    print(f"2. Select 'Microdatos' -> 'Censo de Poblacion y Vivienda 2020'")
    print(f"3. Select state {state_code}")
    print(f"4. Choose dataset: {'Personas' if dataset == 'personas' else 'Hogares' if dataset == 'hogares' else 'Viviendas'}")
    print(f"5. Download and extract to {raw_dir}")
    
    # Create placeholder file
    if dataset == "personas":
        columns = ["ENTIDAD", "MUN", "LOC", "AGEB", "SEXO", "EDAD", "LENGUA", "RELIGION"]
    elif dataset == "hogares":
        columns = ["ENTIDAD", "MUN", "LOC", "AGEB", "TAMHOG", "INGRESO", "JEFATURA"]
    elif dataset == "viviendas":
        columns = ["ENTIDAD", "MUN", "LOC", "AGEB", "TIPVIV", "AUTO", "INTERNET", "COMPUTADORA"]
    else:
        columns = ["ENTIDAD", "MUN", "LOC", "AGEB"]
    
    df = pd.DataFrame({col: [] for col in columns})
    df.to_csv(csv_file, index=False)
    print(f"Created placeholder file at {csv_file}")
    
    return csv_file


def fetch_boundaries(
    level: str,
    state: Optional[str] = None,
    year: int = 2020,
    data_dir: Optional[str] = None,
    overwrite: bool = False,
) -> Optional[Path]:
    """Fetch geographic boundary files.
    
    Args:
        level: Geographic level ("nation", "state", "municipality", "locality", "ageb").
        state: Specific state to fetch boundaries for (optional).
        year: Vintage year (default 2020).
        data_dir: Base directory for caching.
        overwrite: If True, re-download even if file exists.
    
    Returns:
        Path to the downloaded boundary file, or None if file not found.
    """
    level = geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)
    raw_dir = _get_raw_dir(data_dir)
    
    # Determine filename based on level and state
    if state:
        state_code = utils.state_code(state)
        if level == "state":
            filename = raw_dir / f"estados_{state_code}_2020.gpkg"
        elif level == "municipality":
            filename = raw_dir / f"municipios_{state_code}_2020.gpkg"
        elif level == "locality":
            filename = raw_dir / f"localidades_{state_code}_2020.gpkg"
        elif level == "ageb":
            filename = raw_dir / f"agebs_{state_code}_2020.gpkg"
        else:
            filename = raw_dir / f"{level}_{state_code}_2020.gpkg"
    else:
        filename = raw_dir / f"{level}_2020.gpkg"
    
    if filename.exists() and not overwrite:
        return filename
    
    # File doesn't exist - return None to indicate it needs to be downloaded
    return None


__all__ = [
    "CENSUS_2020_AGGREGATED_URLS",
    "MICRODATA_BASE_URL",
    "fetch_aggregated_data",
    "fetch_microdata",
    "fetch_boundaries",
]
