# Guide for an AI agent: census for a new city or country, and completing the global census

Audience: an agent (or person) who must (a) add the census of a **new city / country** to pyCensus, or (b) **fill more of the global census** for a place that already has a module.
Read first: `GLOBAL_CENSUS_COLUMNS.md` (every global column, what it means, which country sources supply it, which none supplies), then this file. This file replaces the old `AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md` (anti-fabrication rules, key-required sources and anti-patterns are in sections 0 and 7 below).

## 0. Hard rules

1. **Never fabricate.** No random geometry, placeholder zeros, guessed field codes, invented columns. Every number must come from a file or API you opened and checked. If a column cannot be sourced, leave it out and say so in the country's README under "Not available".
2. **Check the source with a known total.** Sum the population (or households) of what you loaded and compare with an independent figure (the agency's published total, Wikipedia). A 200 response that is an HTML error page is not data.
3. **Sub-municipal data only** where it exists: the finest published unit (block, enumeration area, grid cell, statistical area, census tract). Municipality-only data is a last resort and must be flagged. Exceptions the study accepts: Andorra parishes, travel-survey zones, small municipalities, a district level when nothing finer exists.
4. **Elections are sub-county**: precinct / polling place / station / mesa results with the **official electoral districts as the native geometry**, then resampled to the census levels (see `elections_common.py`). County- or municipality-only election data is not accepted when polling-unit data exist.
5. **Keep original column names.** A source column keeps its own prefixed name (`acs5_povertyBelow100`); the global column repeats the value under the shared name. If a global column's name is unlike its source column, **both** exist (the global one and the original). See `reference/global_equivalents.json`.
6. **Shared cache**: raw downloads go to the shared cache (`TransitLOSStudies/cache/...`, reachable as `cache/pycensus`), never into the package or the repo. Large files: the pre-commit hook (`tools/check_large_files.py`) refuses a file over 10 MB once and never commits one over 50 MB; raw data belongs in the cache, not in git.
7. API keys: `pycensus.api_keys.resolve_api_key` (argument -> env var -> `api_keys.json`, gitignored). If a source needs a key you do not have, leave the module honestly blocked (section 7) and document how to get one.
8. Never `git commit` / `git push` for the user.

## 1. Orientation: what already exists

The schema files (where each one lives and what it must contain): [SCHEMAS.md](SCHEMAS.md).

```
src/pycensus/
  census/global_schema.json        the global columns (category, feature_name, definition, type, unit, relative_to, resampling_up/down, resampling_weight)
  reference/global_equivalents.json   local->global renames ("equivalents"), local twins that keep the original meaning ("originals"), period patterns ("latest_patterns")
  reference/global_levels.json        geometry levels: nation, state, province, municipality, ... down to the finest, with resampling rules between them
  reference/year_built_bands.json     construction-year bands -> dwellings_built_* shares
  derived_columns.py                add_derived_columns + add_gap_columns: global columns computed from local ones (copy / sum / rate x base / commute bins / area)
  elections_common.py, electoral.py shared election machinery (units -> WorldPop pixels -> H3 -> census geometry)
  census/countries/<country>/       geography, constants, levels.json, schema/*_schema.json, <source>/loader.py
  census/worldwide/                 WorldPop and GBA population, UN metropolitan areas (worldwide fallback); schema/*_schema.json
  cadaster/global_schema.json       the unified building fields
  cadaster/countries/<country>/     cadaster (building) sources of a country, <source>/schema.json + loader.py
  cadaster/worldwide/               GlobalBuildingAtlas buildings (worldwide fallback)
  census/countries/eu/              EU-wide Eurostat / GISCO: census_grid (Census 2021 1 km grid, high), lau (municipal population, low), eurostat (NUTS 2/3 indicators, low)
  resolution.py                     resolution class of a dataset (low / normal / high) and the rules of use
tools/generate_column_docs.py       regenerate GLOBAL_CENSUS_COLUMNS.md
tools/census_coverage.py            report which global columns a result table fills (the gap monitor)
```

Run the monitor on the results of the city you work on and read the columns marked `missing` / `empty` / `partial`:

```bash
python tools/census_coverage.py ../TransitLOSStudies/city_science_network/<city>/results/downloads/h3_res7.parquet
python tools/generate_column_docs.py        # after any schema change
```

## 1b. Resolution class (every new source must declare it)

Every source and level carries `resolution` = `low` / `normal` / `high` (`pycensus/resolution.py`), computed with
`resolution.classify(units, municipalities)` on real data, never typed by hand:

* **low**: finest unit is the municipality or larger.
* **normal**: sub-municipal in every municipality (or county) of 10,000 residents or more; small municipalities may stay whole.
* **high**: normal, and **no unit with more than 5,000 residents is larger than 1 km2**.

Rules of use: regressions never use `low`; the census tab uses only `high` (`resolution.usable_for`). Put the class in
the source's schema JSON (`"resolution"`) and as `RESOLUTION` in its loader, and record the classifier's failures in
the country README.

In an EU country, start from `census/countries/eu` (keyless, all member states): the Census 2021 1 km grid is `high`, so it
already satisfies the census tab for population, sex, broad age, employment, place of birth and recent moves; look
for national sub-municipal sources only for the other topics.

## 2. New country or city: the steps

1. **Find the agency and the finest geography.**
   * Search in the local language: "censo <año> microdatos / resultados por manzana / AGEB / sección censal", "Volkszählung Gitter", "统计区", "recensement carreaux", "census tract shapefile".
   * Where the country is in/near the EU: Eurostat GISCO (NUTS/LAU, keyless) for boundaries and Eurostat census hub tables; Zensus-style 100 m grids (Germany), INSEE carroyés 200 m, ISTAT sezioni, INE secciones.
   * United States/Canada: ACS/Decennial via Census API (key) / pygris; StatCan Census Profile and dissemination areas.
   * Latin America: INE/INEGI/DANE/INEI/IBGE "setores censitários" bulk files; Chile INE publishes the Censo 2024 per manzana in a public bucket (`bktdescargascenso2024`).
   * Asia/Middle East: national statistics bureau open data (Taiwan MOI/DGBAS statistical areas, Israel CBS statistical areas), municipal open-data portals; China publishes almost nothing below district: use WorldPop and say so.
   * Always also check: national open-data portal, the agency's FTP/bucket, GitHub mirrors, Wayback Machine, academic repositories (Zenodo, Figshare), and Humanitarian Data Exchange (HDX).
2. **Fetch for real and inspect** (`curl -I`, then open the file): field list, row count, CRS, a population total. Keep the raw download in the shared cache with its URL and date in the country README.
3. **Boundaries.** Fill `geography.py`: real boundary download, EPSG:4326 output, `IMPLEMENTED_LEVELS` only for levels backed by a verified source, `levels.json` mapping the country's native levels to the global levels (`reference/global_levels.json`). Prefer many levels (municipality -> census tract -> block): the study resamples between them.
4. **Schema** `schema/<source>_schema.json`: one feature per column you take, with `feature_name` (use the **global name** when the concept is the same), `category`, `definition`, `type`, `unit`, `resampling_up/down`, `original_name` (the source's own column code), `country`, `source`, `codes`. Copy the shape of `census/countries/chile/schema/ine_manzana_schema.json`. Fields the source documents but you did not verify are not added.
5. **Loader** `<source>/loader.py`: download (cached), assemble into a GeoDataFrame with a `GEOID` and the schema's columns, sums for counts, weighted means for averages. Mirror `census/countries/chile/ine/manzana.py` (bulk file) or `census/countries/spain/ine/` (API).
6. **Tests with mocked network** (`tests/test_<country>.py`, pattern of `tests/test_andorra.py`): schema loads, a tiny fixture produces the expected columns and totals, no network in CI.
7. **Wire the city** (city-science only): ISO3 -> module in `city_config.py::_ISO3_TO_PYCENSUS_MODULE`, a `<country>_census_loader` in `pipeline.py`, its `*_LEVELS` and `KEEP_COLUMNS`. Not before the loader is verified end to end for one real area.
8. Run `tools/generate_column_docs.py` and `tools/census_coverage.py` on a rebuilt city and record the result in the country README.

## 3. Completing the global census (a place that already has a module)

Take the list of `missing`/`empty`/`partial` columns from `census_coverage.py` and work through each in this **order of cheapness**:

| Step | When | How |
|---|---|---|
| a. rename | the source has the concept under another name | add `local -> global` to `global_equivalents.json["equivalents"]` (the pipeline then writes both columns) |
| b. derive | the concept is a sum / rate / combination of source columns | add a rule to `derived_columns.py` (`_COPY_RULES` first present column, `_SUM_RULES` sum of all, `_RATE_RULES` rate x base column, `_COMMUTE_BINS` mean commute from bin mid-points; the file shows the form). State the approximation in a comment (e.g. births = women who gave birth in the last 12 months). |
| c. second table of the same source | the agency publishes it in another table | extend the loader's extra tables (e.g. Zensus 2022 `EXTRA_TABLES` "home_size" -> `homeSizeM2Mean`) and add the feature to the schema |
| d. other agency | tax, social security, labour, transport, health, housing registries | a new `<source>` subpackage for the same country (Chile: `ine`, `casen`, `sii`; Germany: `destatis`, `ba`, `ba_pendler`; Canada: `statcan`, `toronto`) |
| e. gridded / remote sensing | no tabular source | WorldPop (population by age/sex) is already the fallback; for housing/commute use national grids if they exist; state resolution |
| f. mark as unavailable | nothing found after a, b, c, d | write it in the country README "Not available" with what you searched (so the next agent does not repeat it) |

Concept hints for the columns that are usually missing:

* **cars / carHouseholds / twoCarHouseholds / motorcycleHouseholds / bicycleHouseholds**: household vehicle availability tables (ACS B25044, StatCan, INEGI vivienda `VPH_AUTOM`, Zensus, Chile CASEN); registry of vehicles by commune (Chile INE parque vehicular, Germany KBA by municipality) as a fallback with a note.
* **commute columns** (`carCommuters`, `publicTransportCommuters`, `walkCommuters`, `bikeCommuters`, `commuteTimeMean`, `commuteDistanceMean`, `motorizedCommuters`): journey-to-work tables; Germany Pendler (BA), US ACS B08, Canada census commuting, travel surveys by zone (accepted at zone level).
* **income** (`medianHouseholdIncome`, `meanHouseholdIncome`, `incomePerCapitaMean`, `giniIndex`, `lowIncomeHouseholds`, `povertyPopulation`): tax-based small-area income (Germany, Nordics), census income brackets, household surveys (CASEN, ENIGH at municipality only: flag it).
* **housing** (`rent_per_m2_mean`, `price_per_m2_mean`, `rent_per_home_mean`, `price_per_home_mean`, `home_size_m2_mean`, `dwellings`, tenure): census, cadastre / land registry price data (Taiwan MOI real price, Spain/Euskadi, Germany Zensus rent), open real-estate datasets.
* **employment** (`laborForce`, `employedResidents`, `workplaceJobs`, `populationAndJobs`): census employment tables for residents; LODES (US), BA employment by municipality (Germany), business registers for jobs by workplace.
* **education, migration, religion, ethnicity**: census tables; religion and ethnicity are often absent by law (France, Germany partly) -> mark unavailable.
* **elections**: see section 4.
* **indices** (`socialStatusIndex`, `socialDynamicsIndex`, `deprivationIndex`): only where an official index exists (Berlin MSS, Index of Multiple Deprivation, Chile IVS). Do not invent a composite.

### Adding a NEW global column
Only when a concept recurs or is clearly useful across countries and is not already covered (search the glossary first). Steps: add an entry to `census/global_schema.json` (category from `categories.json`, definition in one sentence, `type`, `unit`, `relative_to` if it is a share of another column, `resampling_up` (sum for counts), `resampling_down` (`weighted_divide` with `resampling_weight` = population for counts)); fill it from at least one country; run `tools/generate_column_docs.py`; add equivalents/rules for the countries that already have the concept under another name. **Whenever you meet a topic the schema has no column for, add the column** -- the global schema is meant to grow with every new topic. Keep names in `camelCase` for counts (`ownerHouseholds`) and `snake_case` for units/shares that already follow it (`rent_per_m2_mean`, `dwellings_built_*_share`).

## 4. Elections

* Find the **finest result unit** (precinct / polling place / station / mesa / circuit) and the polygons of the **official electoral districts**; where polygons do not exist (Chile voting locals), build a Voronoi of the locals clipped to the commune and weight by WorldPop (`chile/elections/loader.py`).
* Counts are resampled, shares recomputed (`elections_common.finalize`). Output names `elec_<scope>_<year><type>_<measure>` with scopes `national`, `state`, `municipal`; the global column (`elec_national_left_share`...) holds the **latest** election of that scope (patterns in `global_equivalents.json["latest_patterns"]`).
* Party -> left / right / other mapping lives in the country's election constants; cite the source of the classification.
* If the official site blocks scripted download (403), cache the files by hand in `cache/pycensus/<country>/raw/elections` and make the loader read the cache first (Spain `*_MESA.zip` pattern). Browser-only exports (Servel per-mesa, INE Mexico portals) are listed as "needs manual export" in the country README.

## 4b. Cadastre and building stock

One row per building, every source in one unified schema (`cadaster/global_schema.json`): `building_id`, `source`,
`country`, `footprint_m2`, `floors_above`, `floors_below`, `height_m`, `built_area_m2` (+ `built_area_method`), `use_class`
(+ `use_original`), `dwellings`, `units`, `population_night`, `population_day`, `year_built`. Missing fields stay null.

**Layout of a new source** `pycensus/cadaster/countries/<country>/<source>/`:

1. `schema.json`: `source` key (`<iso2>_<name>`, e.g. `es_navarra`), `country` (ISO3), `name`, `url`, `license`, `coverage`,
   `api_key` (true/false), `fields` (how each unified field is obtained from the source's own fields, in words), `use_map`
   (source use code -> `use_class`). Copy `cadaster/countries/spain/araba/schema.json`.
2. `loader.py` with `load(aoi, cache_dir=None) -> GeoDataFrame`: download once into `cache_root(cache_dir) / <source>`, parse,
   map uses with `map_use`, compute areas with `true_area_m2`, return through `standardize(df, source, country)` (it fills
   `built_area_m2` from floors x footprint, else height x footprint / 3 m).
3. Register it in `cadaster/__init__.py`: `SOURCES[<key>] = "countries.<country>.<source>"` and its place in `BY_COUNTRY[<ISO3>]`
   (best first: a regional cadastre before the national one). `load_buildings` then takes it, and fills every H3 cell no
   cadastre covers with GlobalBuildingAtlas (GBA) footprints and heights.
4. A mocked test with a tiny GML / GeoJSON fixture: the unified columns exist, areas and floors are right.

**What to search** (local language first):

* EU countries: the INSPIRE **Buildings (BU)** download service of the national or regional cadastre, usually an ATOM feed
  with one zip per municipality or province (`"INSPIRE BU ATOM <country>"`, `"edificios INSPIRE descarga"`,
  `"Gebäude INSPIRE Download"`). `cadaster/countries/spain/_inspire_bu.py` already reads ATOM feeds and BU GML: reuse it.
* City or state 3D models: CityGML / LoD2 building models (`"LoD2 Gebäudemodell Download"`, `"3D massing open data"`);
  they give heights and floors for every building.
* United States: the National Structure Inventory (USACE NSI, keyless API and state bundles), with use and floor area.
* Everywhere else: national open-data portals ("building footprints", "catastro edificaciones", "地籍 建物"), then GBA
  (already the fallback; it merges OSM, Microsoft and Google footprints with heights).

**Rules**: the building stock is never rescaled to census totals (only population-type grids are); keep the source's own
use codes in `use_original`; say in the schema's `fields` how floors and areas were derived.

## 4c. Other kinds of data

* **Gridded population** (`census/worldwide`): WorldPop 100 m is the fallback anywhere; GBA built floor area spreads it
  more precisely (`census/worldwide/gba/population.py`). Grids are rescaled to the census total with one factor, and the
  factor is saved.
* **Travel surveys and published mode shares**: only figures the agency published for the territory, fetched with
  `published_shares.fetch` (each figure carries its URL and a pattern that must appear in the document, so a changed
  publication fails loudly). Never estimate a share yourself.
* **EU-wide indicators** (`census/countries/eu`): Eurostat tables at NUTS 2 / 3 are `low` resolution: context only, never in
  regressions.

## 5. Documentation to leave behind

In the loader's module docstring: sources with URL, date retrieved and licence; levels available; the columns taken and their original names; the global columns obtained (renamed/derived); **Not available** with what was searched; verification (total checked and against what). Longer working notes go in a local `README.local.md` (not committed). Regenerate `GLOBAL_CENSUS_COLUMNS.md`.

## 6. Checklist before you stop

- [ ] population total matches an independent figure (state both numbers)
- [ ] no fabricated or placeholder values; unavailable columns are absent, not zero
- [ ] original column names kept next to the global ones
- [ ] elections are sub-county with official districts as native geometry
- [ ] tests (mocked network) pass; `tools/check_large_files.py` is clean
- [ ] `tools/generate_column_docs.py` run; `tools/census_coverage.py` shows the improvement
- [ ] README of the country updated (sources, gaps, what was searched)

## 7. Sources that need a key, and mistakes made before (never repeat)

See *API keys* below for where keys go and what to tell the user. Never use someone else's key, a key found online, or a
workaround that avoids the registration.

Keys in use today:

| Key name | Environment variable | Source | Sign up |
|---|---|---|---|
| `us_census` | `US_CENSUS_API_KEY` | US Census Bureau API (ACS, Decennial) | https://api.census.gov/data/key_signup.html |
| `destatis_genesis` (token) or `destatis_genesis_username` + `destatis_genesis_password` | `DESTATIS_GENESIS_TOKEN` (or `DESTATIS_GENESIS_USERNAME` + password key) | Destatis GENESIS-Online (German census tables) | https://www-genesis.destatis.de (register an account) |

Every other source in pyCensus is keyless, including all cadastre sources and `census/countries/eu`.

**Key-required sources (Germany GENESIS pattern).** Give each key a specific name (`destatis_genesis_username`, not `api_key`) and add it to `api_keys.example.json`; raise a small specific exception (`GenesisCredentialsError(RuntimeError)`) from a `resolve_<x>_credentials()` that uses `resolve_api_key` and names the missing keys and where to register; call it **before** any expensive download; state in the module docstring exactly which endpoints a guest account was verified to work for; if the authenticated parse cannot be tested yet, leave `NotImplementedError` with the exact next calls instead of guessing. Fall back to WorldPop for population meanwhile.

**Anti-patterns that really happened**
* Fabricated geometry (`np.random` bounding boxes standing in for boundaries) and placeholder all-zero CSVs in five first-built modules; every value must trace to a parsed file or response.
* Guessed field codes (`POBTOTAL` for INEGI's real `POBTOT`): a code is real only after you saw it as a column name in an actual download.
* Treating HTTP 200 as data (an "not found" HTML page): check column names, numbers and a known total.
* Two sources sharing a cache prefix (LODES RAC/WAC) so their columns collided: one prefix per source subpackage.
* Renaming a schema prefix or feature without updating the downstream keep-lists in `pipeline.py` (`*_KEEP_COLUMNS` and the prefix literals at each `_join_polygon_stats` call): the join matched zero columns with no error. After any rename, grep every consumer.
* Case-sensitive substring matching that broke on a naming-convention change: match on exact keys or normalised names.
* A new country module wired into the pipeline before it was verified end to end on one real area.

## API keys (the one standard place)

Every key of every package of the project lives in **one file outside every repository**: `~/.config/ptlos/api_keys.json`,
a JSON object `{"<key name>": "<key>"}` (permissions 600). Both pyCensus (`pycensus.api_keys.resolve_api_key`) and pyGTFSHandler
(`pyGTFSHandler.downloaders.utils.config.get_api_key`) read it. Order: a key passed as an argument, then the source's
environment variable, then the file (`API_KEYS_FILE=<path>` points to another file). The key names are listed in
`api_keys.example.json` at the root of each package. Never put a key in a repository, a notebook, a log or a message to anyone
but the user.

**When a source needs a key you do not have, stop and tell the user**, in one short message:

1. which source needs it and what it would add;
2. where to sign up (the registration page) and whether it is free;
3. what to do with the key: *either* paste it to you in the chat, *or* add it themselves to `~/.config/ptlos/api_keys.json`
   as `"<key name>": "<key>"`.

When the user gives you a key, write it into `~/.config/ptlos/api_keys.json` under its key name (create the file with
permissions 600 if it is missing, keep the other entries), never echo it back or print it, and check it works with one small
request. Then continue. Meanwhile do what needs no key and leave the module raising its credentials error.

## Files a person must download in a browser

Some sources block every script (bot challenge, browser-only pages). Do not work around the block: give the user the page, the
file to pick and the exact path to save it under (the loaders use a file already on disk and skip the download). Today:

| Source | Page | Save as (in the pycensus cache, `PYCENSUS_CACHE_DIR`) |
|---|---|---|
| StatCan Census Profile 2021, Ontario (DA income, education, commute ...) | https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=E -> Comprehensive download files -> Ontario (CSV) | `canada/raw/census_profile/98-401-X2021006_Ontario_eng_CSV.zip` |
| StatCan Geographic Attribute File 2021 (people per dissemination block) | https://www12.statcan.gc.ca/census-recensement/2021/geo/aip-pia/attribute-attribs/index-eng.cfm | `canada/raw/full_table/2021_92-151_X.zip` |

## 8. Tests
Mocked-network tests per country (`tests/test_<country>.py`, pattern `tests/test_andorra.py`, `tests/test_chile_*`): schema loads and every feature has the required keys; a tiny fixture yields the expected columns and totals; no network in CI. Run `cd pyCensus && python -m pytest`.
