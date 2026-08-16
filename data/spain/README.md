# Spain Census Data

This directory can contain downloaded INE Census 2021 data for use with pyCensus, but **it is no longer required**. Starting with the cache-based implementation, all data is automatically downloaded to and cached in the platform-specific cache directory (e.g., `~/.cache/pycensus/Spain/` on Linux).

**Note**: This `data/spain/` directory is kept for backward compatibility and for users who want to manually organize their data. For new users, the automatic cache system is recommended.

## Quick Start

The easiest way to get started is to use pyCensus directly in Python:

```python
# Import and load data - it will auto-download on first use
from pycensus.spain.census2021 import load

# Load municipality-level data for a specific autonomous community
gdf = load(regions="Andalucía", level="municipality")

# Load for a specific province
gdf = load(regions="Barcelona", level="municipality")

# Or load for multiple autonomous communities
gdf = load(regions=["Andalucía", "Cataluña"], level="province")

# Load at different geographic levels
gdf = load(regions="Madrid", level="autonomous_community")
gdf = load(regions="08", level="province")  # Barcelona province by code
```

The data will be automatically downloaded from INE's open data portal and cached for subsequent use.

You can also use the download function explicitly:

```python
from pycensus.spain.census2021 import download_census_data

# Download aggregated data for municipality level
download_census_data(data_type="aggregated", level="municipality")

# Download for specific autonomous communities
download_census_data(data_type="aggregated", level="municipality", regions=["01", "09"])  # Andalucía and Cataluña
```

## Data Sources

Spain's census data comes from INE (Instituto Nacional de Estadística):
- **Census 2021 (Censo de Población y Viviendas 2021)**: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780

## Cache System

pyCensus uses an intelligent cache system similar to the US and Mexico Census implementations:

1. **Raw Data Cache** (`~/.cache/pycensus/Spain/raw/` or custom cache_dir): 
   - Downloaded CSV files from INE
   - Extracted CSV files ready for processing
   
2. **Processed Data Cache** (`~/.cache/pycensus/Spain/{level}/{region}.parquet`):
   - Parquet files with processed data in common schema
   - One file per (level, region) combination
   - Only missing columns are fetched and processed

The cache system means:
- **First load**: Downloads raw data -> processes -> caches as parquet
- **Subsequent loads**: Uses cached parquet (no re-download or reprocessing)
- **Missing columns**: Only missing columns are fetched from raw data and merged into existing cache

### Cache Location

By default, data is cached in:
- **Linux**: `~/.cache/pycensus/Spain/`
- **macOS**: `~/Library/Caches/pycensus/Spain/`
- **Windows**: `%LOCALAPPDATA%\pycensus\Spain\`

You can customize the cache directory:

```python
from pycensus.spain.census2021 import load

# Use a custom cache directory
gdf = load(regions="Andalucía", level="municipality", cache_dir="/path/to/my/cache")
```

### Manual Cache Management

You can manually inspect or clean the cache:

```python
from pycensus import cache

# Get the default cache directory
print(cache.default_cache_dir())

# List cached files for Spain
import os
spain_cache = os.path.join(cache.default_cache_dir(), "Spain")
print(os.listdir(spain_cache))
```

## Data Available

The Spain Census 2021 implementation includes the following variables:

### Population & Demographics
- Population total
- Population by gender (male, female)
- Sex ratio
- Population by detailed age groups (0-4, 5-9, 10-14, 15-19, 20-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50-54, 55-59, 60-64, 65-69, 70-74, 75-79, 80-84, 85+)
- Population by broad age groups (0-14, 15-24, 25-44, 45-64, 65+)
- Median age
- Households
- Average household size

### Nationality & Migration
- Spanish nationality population
- Foreign nationality population
- Population born in Africa, America, Asia, Europe, Oceania
- Specific nationalities: Romanian, Moroccan, British, Venezuelan, Colombian
- Foreign-born population
- Naturalized population
- Population mobility (same municipality, same province, different province over 5 years)

### Education
- Population 15+, 16+, 18+
- Educational attainment (no education, primary incomplete, primary, lower secondary, upper secondary, post-secondary, vocational, university)
- Literacy (can read/write, cannot read/write)

### Income & Poverty
- Household income (median and mean)
- Income per capita
- Households by income ranges (10 ranges from no income to 54,000+ euros)

### Employment / Labor Force
- Population 16+
- Labor force (economically active)
- Employed
- Unemployed
- Unemployment rate
- Employment by sector (agriculture, mining, manufacturing, construction, commerce, transport, hostelry, information/communication, financial, real estate, professional, administration, education, health, services)
- Contract type (permanent, temporary, self-employed)
- Employment status (full-time, part-time)

### Housing & Tenure
- Housing tenure (owner, renter, free/ceded, other)
- Housing type (independent house, apartment, semi-detached, other)
- Building type (single-family, multi-family, apartment building)
- Building construction period (9 periods from before 1900 to 2011-2021)

### Car Ownership & Vehicles
- Households with no vehicle
- Households with 1, 2, 3+ vehicles
- Vehicles per household
- Households with motorcycle

### Commuting Mode
- Workers who walk
- Workers who bike
- Workers who use car
- Workers who use motorcycle
- Workers who use public transit
- Workers who use train
- Workers who use bus
- Workers who use metro
- Workers who use taxi
- Workers who use company vehicle
- Workers who use other transport
- Workers who work from home
- Mean commute time

### Housing Amenities
- Water access (piped, well, none)
- Sewer access (sewer system, none)
- Electricity access
- No electricity
- Heating (central, individual, none)
- Internet access
- Computer ownership
- Tablet ownership
- Cellphone ownership
- Landline ownership

### Disability
- Population with disabilities
- Visual, hearing, mobility, cognitive, psychological disabilities

### Health Insurance
- Population with public healthcare coverage
- Population with private health insurance
- Population without healthcare coverage

### Marital Status
- Population single, married, widowed, divorced, separated (for population 15+)

### Family Characteristics
- Households with single person
- Households with couple without children
- Households with couple with children
- Single-parent households
- Other family type households

## Geographic Levels

Spain's census data is available at the following geographic levels:

- **Nation**: Country-level data (Spain)
- **Autonomous Community**: 17 autonomous communities + 2 autonomous cities (Ceuta, Melilla)
- **Province**: 50 provinces + 2 autonomous cities = 52 total
- **Municipality**: Municipal-level (equivalent to city/town)
- **District**: Within municipalities (distrito)
- **Section**: Census section (sección censal, equivalent to tract/blockgroup)
- **Block**: Manzana (city block)

## Notes

1. INE does not provide a public API for microdata downloads. Files must be downloaded manually from their website or via the download script.

2. Aggregated data is available via direct download from INE's open data portal. The pyCensus implementation includes known URLs for 2021 data.

3. Microdata files can be very large. Consider whether you need microdata or if aggregated data will suffice for your use case.

4. Geographic boundary files are also available from INE but require separate downloads. The current implementation uses placeholder boundaries. To get real boundaries:
   - Download from: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780
   - Update the GEOMETRY_FUNCS mapping in `src/pycensus/spain/geography.py`

5. For the most up-to-date information, always check the official INE website: https://www.ine.es/

6. Variable codes in the schema are placeholders based on typical INE naming conventions. The actual column names in downloaded data files may differ and would need to be mapped in `src/pycensus/spain/census2021/loader.py`.
