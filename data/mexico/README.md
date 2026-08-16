# Mexico Census Data

This directory can contain downloaded INEGI Census 2020 data for use with pyCensus, but **it is no longer required**. Starting with the cache-based implementation, all data is automatically downloaded to and cached in the platform-specific cache directory (e.g., `~/.cache/pycensus/Mexico/` on Linux).

**Note**: This `data/mexico/` directory is kept for backward compatibility and for users who want to manually organize their data. For new users, the automatic cache system is recommended.

## Quick Start

The easiest way to get started is to use pyCensus directly in Python:

```python
# Import and load data - it will auto-download on first use
from pycensus.mexico.census2020 import load

# Load municipality-level data for a specific state
gdf = load(states="Jalisco", level="municipality")

# Or load for multiple states
gdf = load(states=["Jalisco", "Nuevo Leon"], level="municipality")
```

The data will be automatically downloaded from INEGI's open data portal and cached for subsequent use.

You can also use the download function explicitly:

```python
from pycensus.mexico.census2020 import download_census_data

# Download aggregated data for municipality level
download_census_data(data_type="aggregated", level="municipality")
```

Or use the CLI script:

```bash
# Download all aggregated data for all levels
python scripts/download_mexico_census.py

# Download only municipality-level data
python scripts/download_mexico_census.py --level municipality

# Download data for specific states
python scripts/download_mexico_census.py --states Jalisco NuevoLeon

# Download with overwrite
python scripts/download_mexico_census.py --overwrite
```

## Data Sources

Mexico's census data comes from INEGI (Instituto Nacional de Estadistica y Geografia):
- **Census 2020 (CPV 2020)**: https://www.inegi.org.mx/programas/ccpv/2020/

## Cache System

pyCensus uses an intelligent cache system similar to the US Census implementation:

1. **Raw Data Cache** (`~/.cache/pycensus/Mexico/raw/` or custom cache_dir): 
   - Downloaded ZIP and CSV files from INEGI
   - Extracted CSV files ready for processing
   
2. **Processed Data Cache** (`~/.cache/pycensus/Mexico/{level}/{state}.parquet`):
   - Parquet files with processed data in common schema
   - One file per (level, state) combination
   - Only missing columns are fetched and processed

The cache system means:
- **First load**: Downloads raw data -> processes -> caches as parquet
- **Subsequent loads**: Uses cached parquet (no re-download or reprocessing)
- **Missing columns**: Only missing columns are fetched from raw data and merged into existing cache

### Cache Location

By default, data is cached in:
- **Linux**: `~/.cache/pycensus/Mexico/`
- **macOS**: `~/Library/Caches/pycensus/Mexico/`
- **Windows**: `%LOCALAPPDATA%\pycensus\Mexico\`

You can customize the cache directory:

```python
from pycensus.mexico.census2020 import load

# Use a custom cache directory
gdf = load(states="Jalisco", level="municipality", cache_dir="/path/to/my/cache")
```

### Manual Cache Management

You can manually inspect or clean the cache:

```python
from pycensus import cache

# Get the default cache directory
print(cache.default_cache_dir())

# List cached files for Mexico
import os
mexico_cache = os.path.join(cache.default_cache_dir(), "Mexico")
print(os.listdir(mexico_cache))
```

## Data Available

The Mexico Census 2020 implementation includes the following variables:

### Population & Demographics
- Population total
- Population by gender (male, female)
- Population by age groups (0-4, 5-14, 15-19, 20-24, 25-29, 30-39, 40-49, 50-59, 60-69, 70-79, 80+)
- Median age
- Households
- Average household size

### Ethnicity & Race
- Indigenous population
- Population speaking indigenous languages
- Specific languages: Nahuatl, Maya, Otomi, Mixe, Zapotec
- Afro-Mexican population

### Religion
- Catholic
- Protestant
- Other Christian
- Jewish
- No religion

### Education
- Population 15+
- Population 18+
- Educational attainment (no education, preschool, primary, secondary, preparatory, professional, bachelors, postgraduate)
- Literacy

### Income & Employment
- Household income (median and mean)
- Households by income ranges
- Economically active population (12+)
- Employed
- Unemployed
- Unemployment rate
- Employment by sector (agriculture, mining, manufacturing, construction, commerce, services, transport)
- Formal vs informal employment

### Housing & Tenure
- Housing tenure (owner, renter, other)
- Housing type (house, apartment, mobile home)
- Renters

### Car Ownership & Vehicles
- Households with no vehicle
- Households with 1, 2, 3+ vehicles
- Vehicles per household

### Commuting Mode
- Workers who walk
- Workers who bike
- Workers who use car
- Workers who use motorcycle
- Workers who use public transit
- Workers who use taxicab
- Workers who use company vehicle
- Workers who use other transport
- Workers who work from home
- Mean commute time

### Housing Amenities
- Water access (piped, well, none)
- Sewer access
- Electricity access
- Internet access
- Computer ownership
- Cellphone ownership
- Landline ownership
- Stove types (gas, electric, wood)

### Disability
- Population with disabilities
- Visual, hearing, mobility, cognitive disabilities

### Health Insurance
- Population with healthcare access
- Population without healthcare access
- Types: IMSS, ISSSTE, Seguro Popular, other

## Geographic Levels

Mexico's census data is available at the following geographic levels:

- **Nation**: Country-level data
- **State**: 32 states (estados) + Ciudad de Mexico
- **Municipality**: Municipal-level (equivalent to county)
- **Locality**: City/town-level (equivalent to place)
- **AGEB**: Area Geoestadistica Basica (equivalent to tract/blockgroup)
- **Block**: Manzana (city block)

## Notes

1. INEGI does not provide a public API for microdata downloads. Files must be downloaded manually from their website or via the download script.

2. Aggregated data is available via direct download links from INEGI's open data portal. The pyCensus implementation includes known URLs for 2020 data.

3. Microdata files are very large (typically several GB per state). Consider whether you need microdata or if aggregated data will suffice for your use case.

4. Geographic boundary files are also available from INEGI but require separate downloads. The current implementation uses placeholder boundaries. To get real boundaries:
   - Download from: https://www.inegi.org.mx/temas/geografia/
   - Update the GEOMETRY_FUNCS mapping in `src/pycensus/mexico/geography.py`

5. For the most up-to-date information, always check the official INEGI website: https://www.inegi.org.mx/
