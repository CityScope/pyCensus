# pyCensus

Common-schema census loaders for the [geohierarchy](../geohierarchy) package.

Each source loads national/regional census (or census-like) data into a plain
`GeoDataFrame` with a `GEOID` column and prefixed attribute columns, ready
for `geohierarchy.GeoHierarchy.add_level`. Importing a source registers a
matching accessor on the GeoDataFrame, e.g.:

```python
from pycensus.countries.usa import acs5

gdf = acs5.load(aoi=my_aoi, level="tract")
gdf.acs5["population"]                  # raw values
gdf.acs5["population"].density          # value / geometry area (m2)
gdf.acs5["poverty_below_1_00"].relative # value / its registered total column
```

Logical column names (`population`, `households`, `gdp`, ...) are shared
across sources and countries wherever the underlying concept matches, so a
downstream consumer doesn't need to know whether a value came from the US
ACS or Spain's INE census.

## Countries implemented

United States (ACS 5-year, 2020 Decennial DHC, LODES RAC/WAC), Mexico
(INEGI Census 2020), Spain (INE Census 2021), Israel (CBS Census 2022),
Germany (Destatis Census 2022 + Bundesagentur commuting data), Euskadi/Basque
Country (Eustat Census 2021), Canada (StatCan), Chile (INE/CASEN/SII),
Andorra, Taiwan, plus worldwide WorldPop gridded population as a fallback
for anywhere else.

## Install

```bash
uv sync
```

or, with plain pip:

```bash
pip install -e .
```

## API keys

Some sources need an API key or token. Keys are resolved in order: an
explicit argument, then an environment variable, then a `key_name` entry in
`api_keys.json` at the package root (see
`pycensus.api_keys.resolve_api_key`). `api_keys.json` is gitignored -- copy
the keys you have into your own local copy; nothing is required for sources
that don't need auth.

## Usage

```python
import pycensus
from pycensus.countries.usa import acs5

gdf = acs5.load(aoi=my_aoi, level="tract")
```

Each source's loader returns a plain GeoDataFrame with a `GEOID` id column
and prefixed attribute columns -- pass it straight to
`geohierarchy.GeoHierarchy.add_level` (using the source's
`SCHEMA.aggregations()` for the `agg` argument) to build a hierarchy, or use
it standalone.

## Tests

```bash
uv run pytest
```

## Adding a new country / census API

See [`IMPLEMENTING_A_COUNTRY.md`](IMPLEMENTING_A_COUNTRY.md) for the
step-by-step guide to wiring up a new national census source.
