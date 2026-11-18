# pyCensus

Census and building data for many countries, in **one shared set of column names**.

Each loader downloads an official source once (cached), and returns a GeoDataFrame: one row per census unit (block, tract,
section, grid cell...), a `GEOID`, and its columns. A column keeps its source name (`acs5_povertyBelow100`), and when the
concept is shared across countries it is also given the global name (`povertyPopulation`), so the same code works for
the US ACS, Spain's INE or Chile's census.

```python
from pycensus.countries.usa import acs5

tracts = acs5.load(aoi=my_area, level="tract")
tracts.acs5["population"]                  # the column; .density and .relative give per-area and per-total values
```

## What is inside

| Part | What |
|---|---|
| `pycensus.countries.<country>` | one package per country, one sub-package per source (census, income, housing, commuting, elections...) |
| `pycensus.countries.eu` | EU-wide Eurostat / GISCO data (Census 2021 1 km grid, municipalities, NUTS indicators) |
| `pycensus.countries.worldwide` | WorldPop population grids and GlobalBuildingAtlas buildings, for anywhere |
| `pycensus.cadaster` | buildings (floor area, floors, use, dwellings) from cadastres in one schema |
| `pycensus.resolution` | how fine a dataset is: `low`, `normal` or `high` |
| `pycensus/schemas/global_schema.json` | the global columns |

## Resolution classes

* **low**: municipalities or larger. Never used in regressions.
* **normal**: split below the municipality wherever a municipality has 10,000 people or more.
* **high**: normal, and no unit with more than 5,000 people is larger than 1 km². Only `high` data go into the census tab
  of the maps.

## Caching and keys

Downloads go to `PYCENSUS_CACHE_DIR` (or a temporary folder). Two sources need a free API key (US Census, Destatis
GENESIS); put it in `api_keys.json` or the environment variable. Everything else is keyless.

## Guides

* [Agent guide](AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md): how to add a census, a cadastre or another source, what to search,
  what to check.
* [Global columns](GLOBAL_CENSUS_COLUMNS.md): every shared column, its definition and which sources supply it.
