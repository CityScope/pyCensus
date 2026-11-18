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
Andorra, Taiwan, the EU (Eurostat Census 2021 1 km grid, LAU, NUTS indicators), plus worldwide WorldPop gridded population as a fallback
for anywhere else.

## Documentation

* `docs/GLOBAL_CENSUS_COLUMNS.md` -- every global column (definition, type, unit, resampling, which country sources supply it, which none does). Generated: `python tools/generate_column_docs.py`.
* `docs/AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md` -- how to add a new census, cadastre or other source, what to search online, what to do when a source needs an API key, the resolution classes (for AI agents and people).
* Site: `mkdocs serve` (API reference from the docstrings).
* `tools/census_coverage.py` -- which global columns a result table fills (the census-gap monitor).

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

See [`docs/AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md`](docs/AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md) for the
step-by-step guide to wiring up a new national census source.

## Use as a library

pyCensus never writes into the current working directory. Every loader takes `cache_dir` (parquet cache) and/or
`data_dir` (raw downloads); when omitted they resolve, in order:

1. the explicit argument;
2. the environment variable `PYCENSUS_CACHE_DIR` (sub-folders per namespace: `parquet/`, `elections/`, `data/<country>/`);
3. a temporary folder: `<tempdir>/pycensus-cache/<namespace>`.

```python
import pycensus
from pycensus.cache import get_cache_dir
from pycensus.countries.usa import acs5

gdf = acs5.load(states=["MA"], level="tract", cache_dir="/data/my_project/cache")   # explicit
# or: export PYCENSUS_CACHE_DIR=/data/my_project/cache   (then omit cache_dir)
print(get_cache_dir("parquet"))
```

Other environment variables: `PYCENSUS_API_KEYS_FILE` (path to an `api_keys.json`; keys can also be passed as arguments or
environment variables) and `PYCENSUS_WORLDPOP_DIRS` (os.pathsep-separated folders searched for WorldPop rasters; or pass `worldpop_path`).

WorldPop rasters use the `worldpop` cache namespace: explicit `folder`/`worldpop_path`, else `PYCENSUS_WORLDPOP_DIR`, else `<cache>/worldpop`.

## Large files

A pre-commit hook (`tools/check_large_files.py`, installed with `python3 tools/check_large_files.py --install`) refuses a commit with a file over 10 MB once: run the same commit again to keep it. Files over 50 MB are never committed.

## Local files

This repository is public. API keys (`api_keys.json`, `.env`), notes about a particular machine or its processes (hosting, uploads,
local paths) and upload scripts are never committed: keep notes as `*.local.md` or under `local/`, which `.gitignore` excludes.
