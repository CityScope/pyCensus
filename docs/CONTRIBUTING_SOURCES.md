# Adding a source (downloader)

pyCensus has two kinds of data, each split into worldwide and country sources:

```
src/pycensus/
  census/
    global_schema.json                the shared census columns
    worldwide/<source>/               a census source that covers the whole world (WorldPop, GBA population, ...)
    worldwide/schema/<source>_schema.json
    countries/<country>/              geography.py, constants.py, api.py, schema/levels.json
    countries/<country>/<source>/     loader.py (+ schema.py)
    countries/<country>/schema/<source>_schema.json
  cadaster/
    global_schema.json                the shared building fields
    worldwide/<source>/               loader.py + schema.json (GlobalBuildingAtlas)
    countries/<country>/<source>/     loader.py + schema.json
```

What each schema file must contain is in [SCHEMAS.md](SCHEMAS.md). The step-by-step guide for a new city or country,
written for an AI agent but valid for anyone, is [AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md](AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md).

## A census source of a country

1. **The country package** (only for a new country): `census/countries/<country>/` with `geography.py` (official boundaries
   of each level, EPSG:4326), `constants.py`, `api.py` and `schema/levels.json` (every global level mapped to a country
   level). Add the country to `census/countries/__init__.py`.
2. **The schema** `census/countries/<country>/schema/<source>_schema.json`: one entry per column, local names kept, each
   with its codes, definition, type, unit and resampling rules.
3. **The loader** `census/countries/<country>/<source>/loader.py`: `load(aoi, level=..., year=..., data_dir=...)` returns a
   GeoDataFrame with `GEOID`, geometry and the schema's columns (`<source>_<feature_name>`). Download once into the cache
   (`pycensus.cache`), never into the repository; files a browser has to download go in the agent guide's manual-download
   table.
4. **Global columns**: map each local column to the global vocabulary (same name, `reference/global_equivalents.json`, or
   `derived_columns.py`); add a global column to `census/global_schema.json` only when the concept recurs across countries.
5. **Keys**: a source that needs one reads it with `pycensus.api_keys.resolve_api_key("<name>", "<ENV_VAR>")` (the file
   `~/.config/ptlos/api_keys.json`); add the name to `api_keys.example.json` and to the agent guide's keys table.

## A worldwide census source

The same, under `census/worldwide/<source>/` with its schema in `census/worldwide/schema/<source>_schema.json`
(`"country": "worldwide"`). Its columns must be in `census/global_schema.json` (directly or through the equivalents); a test
checks it.

## A cadaster (buildings) source

1. `cadaster/countries/<country>/<source>/` (or `cadaster/worldwide/<source>/`) with `schema.json` (source key, country,
   name, url, license, coverage, `api_key`, how each unified field is obtained, `use_map`) and `loader.py` with
   `load(aoi, cache_dir=None)` returning one row per building through `standardize(df, source, country)`.
2. Register it in `cadaster/__init__.py`: `SOURCES[<key>] = "countries.<country>.<source>"` and its place in
   `BY_COUNTRY[<ISO3>]` (most local first: a regional cadastre before the national one).

## Before you open a pull request

* Tests in `tests/` that run without network (a small saved answer or a hand-made table); live downloads only in tests
  named `test_real_*`, marked `network`.
* The docs build: `mkdocs build --strict` (regenerate the API pages when you add modules).
* No keys, local paths or downloaded data in the commit.
