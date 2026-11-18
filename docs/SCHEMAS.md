# Schemas: where each one lives and what it must contain

pyCensus has two kinds of data, each with one **global schema** (the shared vocabulary) and one **source schema** per data
source (how that source fills the vocabulary):

| Data | Global schema | Source schemas |
|---|---|---|
| Census (people, households, jobs, ...) | `src/pycensus/census/global_schema.json` | `census/countries/<country>/schema/<source>_schema.json`, `census/worldwide/schema/<source>_schema.json` |
| Cadaster (buildings) | `src/pycensus/cadaster/global_schema.json` | `cadaster/countries/<country>/<source>/schema.json`, `cadaster/worldwide/<source>/schema.json` |

General reference data that is not a schema lives in `src/pycensus/reference/`.

In code, never build these paths by hand: `pycensus.schema.schema_dir(country)` gives a census source folder's `schema/`
(`"worldwide"` for the worldwide sources), `pycensus.schema.schema_dirs()` all of them, and
`pycensus.canonical.GLOBAL_SCHEMA_PATH` the census global schema.

## 1. Census global schema: `census/global_schema.json`

A list with one entry per global column. Every source column that means the same thing is renamed to (or computed as)
this column, so the maps and studies work the same in every country. Worldwide sources (WorldPop, GBA) are covered too.

| Key | Required | Meaning |
|---|---|---|
| `feature_name` | yes | the global column name (camelCase, e.g. `medianHouseholdIncome`) |
| `category` | yes | topic: `population`, `housing`, `income`, `employment`, `education`, `transport`, `buildings`, `elections`, ... |
| `definition` | yes | what the column measures, in words |
| `type` | yes | `count` (a total), `mean`, `median` or `ratio` |
| `unit` | yes | unit (`""` for plain counts, `m2`, `EUR`, `%`, ...) |
| `resampling_up` | yes | how it aggregates to a coarser geometry: `sum`, `weighted_mean` or `recompute` |
| `resampling_down` | yes | how it splits to a finer geometry: `weighted_divide`, `weighted_mean` or `recompute` |
| `resampling_weight` | for means / medians | the column used as weight (e.g. `population`, `households`) |
| `relative_to` | for shares / rates | the denominator column (e.g. `households` for a share of households) |
| `constant_total` / `constant_density` | optional | whether the total / the density is preserved when resampling |

Add a global column only when a concept recurs across countries and is not already covered (see the agent guide).

## 2. Census source schema: `<source>_schema.json`

One file per source, in the `schema/` folder of its country (`census/countries/<country>/schema/`) or of the worldwide
sources (`census/worldwide/schema/`). The source's `schema.py` reads it and the loader uses it to know which raw codes to
fetch and how to name the columns.

Top level:

| Key | Required | Meaning |
|---|---|---|
| `country` | yes | the country folder name (`usa`, `spain`, ...) or `worldwide` |
| `source` | yes | the source key, also the column prefix (`acs5_population`) |
| `full_name` | yes | the source's own name |
| `years` | yes | years available |
| `levels` | yes | geometry levels the source can be read at (names from `levels.json`) |
| `native_levels` | optional | levels the source publishes itself (others are resampled) |
| `description`, `url` / `source_url`, `resolution` | optional | where it comes from and how fine it is |
| `features` | yes | the list below |

Each entry of `features`:

| Key | Required | Meaning |
|---|---|---|
| `feature_name` | yes | the local name (kept as `<source>_<feature_name>`; never renamed away from the source's meaning) |
| `original_name` | yes | the source's own variable name |
| `codes` | yes | raw source codes summed to build the column |
| `definition` | yes | what it measures |
| `type`, `unit`, `resampling_up`, `resampling_down` | yes | as in the global schema |
| `category` | recommended | as in the global schema |
| `relative_to`, `resampling_weight` | for shares / means | as in the global schema |
| `country`, `source` | recommended | repeated from the top level |
| `native_level` | optional | the level this one feature is published at, when it differs |
| `global_feature` | optional | the global column it means, when the name differs (see also `reference/global_equivalents.json`) |

A local column reaches the global vocabulary in one of three ways: its `feature_name` already is a global name; it is listed
in `reference/global_equivalents.json` (`"<source>_<feature_name>": "<global name>"`); or `derived_columns.py` computes the
global column from it.

## 3. Geometry levels of a census country: `levels.json`

In each country's `schema/` folder (and `census/worldwide/schema/`):

| Key | Meaning |
|---|---|
| `country`, `country_name`, `description` | identification |
| `native_levels` | one entry per level the country publishes: `level`, `description`, `source`, `geoid_pattern`, `is_standard`, `resample_from`, `resample_to`, `resample_intersections` |
| `levels` | the level names in order, coarse to fine |
| `global_to_country_mapping` | every global level (`reference/global_levels.json`: nation, state, province, municipality, tract, blockgroup, block) to this country's level; all seven are required (a test checks it) |
| `country_to_global_mapping` | the reverse |
| `fallback_resolution` | the level used when a requested one does not exist |

## 4. Cadaster global schema: `cadaster/global_schema.json`

Every cadaster source returns one row per building with these columns (unknown values stay null):

| Key | Meaning |
|---|---|
| `description`, `version` | what the schema is |
| `fields` | the unified columns, each with `name`, `type`, `definition` and, where it applies, `unit` and `values` (allowed categories): `building_id`, `source`, `country`, `footprint_m2`, `floors_above`, `floors_below`, `height_m`, `built_area_m2`, `built_area_method`, `use_class`, `use_original`, `dwellings`, `units`, `population_night`, `population_day`, `year_built` |
| `floor_height_m` | metres per floor used to turn a height into floors (3.0) |

## 5. Cadaster source schema: `schema.json`

In each source folder (`cadaster/countries/<country>/<source>/schema.json`, `cadaster/worldwide/<source>/schema.json`):

| Key | Meaning |
|---|---|
| `source` | the source key (`<iso2>_<name>`, e.g. `es_araba`; `gba` for the worldwide one) |
| `country` | ISO3 code (or `worldwide`) |
| `name`, `url`, `license`, `coverage` | what it is and where it comes from |
| `api_key` | `true` when downloading it needs a key |
| `fields` | for each unified field the source fills: how it is obtained from the source's own fields, in words (every name must be a field of the cadaster global schema; a test checks the worldwide ones) |
| `use_map` | the source's use codes to `use_class` |

Register a new source in `cadaster/__init__.py`: `SOURCES[<key>] = "countries.<country>.<source>"` (or `"worldwide.<source>"`)
and its place in `BY_COUNTRY[<ISO3>]`, best first.

## 6. Reference data: `reference/`

| File | What |
|---|---|
| `global_levels.json` | the seven global geometry levels and the resampling rules between them |
| `global_equivalents.json` | `equivalents` (local column -> global column), `originals` (local twins that keep their own meaning), `latest_patterns` (period columns: which one is the latest) |
| `year_built_bands.json` | construction-year band edges of each source, turned into the `dwellings_built_*` shares |
| `categories.json` | the column categories |
| `currency_conversions.json` | `base_currency` and the `conversions` used for money columns |

`tools/generate_column_docs.py` rebuilds `GLOBAL_CENSUS_COLUMNS.md` from the census global schema and the equivalents.
