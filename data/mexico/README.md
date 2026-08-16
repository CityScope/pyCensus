# Mexico Census Data

This directory contains downloaded INEGI Census 2020 data for use with pyCensus.

## Quick Start

The easiest way to get started is to run the download script:

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

This will automatically download the data from INEGI's open data portal and save it in the correct format.

## Data Sources

Mexico's census data comes from INEGI (Instituto Nacional de Estadistica y Geografia):
- **Census 2020 (CPV 2020)**: https://www.inegi.org.mx/programas/ccpv/2020/

## Directory Structure

```
data/mexico/
├── README.md                    # This file
├── raw/                        # Raw downloaded files from INEGI
│   ├── census2020_state_aggregated.csv       # State-level aggregated data
│   ├── census2020_municipality_aggregated.csv # Municipality-level data
│   ├── census2020_locality_aggregated.csv     # Locality-level data
│   ├── census2020_ageb_aggregated.csv         # AGEB-level data
│   ├── microdatos_personas_*.csv              # Person microdata by state
│   ├── microdatos_hogares_*.csv               # Household microdata by state
│   ├── microdatos_viviendas_*.csv              # Housing microdata by state
│   └── *.gpkg                                  # Geographic boundary files
└── processed/                  # Processed data in common schema
    └── ...
```

## Downloading Data

### Option 1: Use pyCensus's download function

```python
from pycensus.mexico.census2020 import download_census_data

# Download aggregated data for municipality level
download_census_data(data_type="aggregated", level="municipality")

# Download microdata for specific states
download_census_data(data_type="microdata", states=["Jalisco", "Nuevo Leon"])

# Download boundary files
download_census_data(data_type="boundaries", states=["09", "19"])  # CDMX and Nuevo Leon
```

### Option 2: Manual Download from INEGI

#### Aggregated Data (Recommended for most use cases)

1. Go to: https://www.inegi.org.mx/programas/ccpv/2020/#Tabulados
2. Select the geographic level you need:
   - "Entidad" = State
   - "Municipio" = Municipality
   - "Localidad" = Locality
   - "Ageb" = AGEB (statistical area)
3. Download the CSV files
4. Save them in `data/mexico/raw/` with names:
   - `census2020_state_aggregated.csv`
   - `census2020_municipality_aggregated.csv`
   - `census2020_locality_aggregated.csv`
   - `census2020_ageb_aggregated.csv`

#### Microdata (For detailed analysis)

1. Go to: https://www.inegi.org.mx/app/descarga/default.html
2. Select "Microdatos" from the menu
3. Choose "Censo de Poblacion y Vivienda 2020"
4. Select the state(s) you need
5. Choose the dataset type:
   - "Conjunto de datos Personas" = Person-level data
   - "Conjunto de datos Hogares" = Household-level data
   - "Conjunto de datos Viviendas" = Housing-level data
6. Download the ZIP files
7. Extract the CSV files to `data/mexico/raw/`
8. Name them: `microdatos_personas_{state_code}.csv`, etc.

#### Boundary Data

1. Go to: https://www.inegi.org.mx/temas/geografia/
2. Select "Marco Geoestadistico"
3. Choose the appropriate geographic level
4. Download shapefiles or GeoPackage files
5. Save them in `data/mexico/raw/`

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

## Cache System

pyCensus uses an intelligent cache system similar to the US Census implementation:

1. **Raw Data Cache** (`data/mexico/raw/`): Downloaded CSV and boundary files from INEGI
2. **Processed Data Cache** (platform-specific cache dir, e.g., `~/.cache/pycensus/Mexico/`): 
   - Parquet files with processed data in common schema
   - One file per (level, state) combination
   - Only missing columns are fetched and processed

The cache system means:
- **First load**: Downloads raw data → processes → caches as parquet
- **Subsequent loads**: Uses cached parquet (no re-download or reprocessing)
- **Missing columns**: Only missing columns are fetched from raw data

## Notes

1. INEGI does not provide a public API for microdata downloads. Files must be downloaded manually from their website or via the download script.

2. Aggregated data is available via direct download links, but the URLs may change. The pyCensus implementation includes known URLs for 2020 data.

3. Microdata files are very large (typically several GB per state). Consider whether you need microdata or if aggregated data will suffice for your use case.

4. Geographic boundary files are also available from INEGI but require separate downloads.

5. For the most up-to-date information, always check the official INEGI website: https://www.inegi.org.mx/
