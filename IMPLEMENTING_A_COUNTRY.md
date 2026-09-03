# Implementing a new country's census module

This is a how-to for adding a new country (or sub-national region) to
`pyCensus`. It exists because this same job was done, badly, five times in
one project history — Mexico, Spain, Germany, Euskadi, and Israel all had
their first `pycensus` module built as **entirely fabricated data**: random
polygons standing in for real boundaries, hardcoded all-zero CSVs standing
in for a real download, schema field codes invented rather than read off a
real file. Four of those five were caught and rebuilt for real later in the
same project. Don't repeat that. Read the whole "Anti-patterns" section
before writing any code.

If you are an AI session picking this up cold, read this whole file before
touching anything, then use the "Kickoff brief" below (filled in for your
target country) as your actual task prompt.

---

## Kickoff brief (copy this, fill in `<COUNTRY>` / `<ISO3>` / `<AGENCY>`)

> Implement a real `pycensus.<country>` module for `<COUNTRY>` (ISO3
> `<ISO3>`), following `pyCensus/IMPLEMENTING_A_COUNTRY.md` exactly.
>
> **Before writing any code:**
> 1. Research `<COUNTRY>`'s real national statistics agency (`<AGENCY>` if
>    known, otherwise find it) and its real boundary/geometry source. Prefer
>    Eurostat/GISCO (NUTS or LAU) if the country is in or near the EU — it's
>    free, keyless, and already used successfully by `pycensus.spain` and
>    `pycensus.germany`. Otherwise find the country's own statistical
>    agency's real, documented, machine-readable API or bulk-download files.
> 2. **Verify every URL/endpoint by actually fetching it and inspecting the
>    response content** — not just checking the HTTP status code. A 200
>    response with an HTML "not found" page, or a redirect to a generic
>    portal homepage, is not real data. Confirm the response actually
>    contains the fields/geometry/numbers you intend to use, and that a
>    population total you compute from it matches a real, independently
>    known figure for that country (its own published total, a Wikipedia
>    figure, etc.).
> 3. If a source needs an API key/account, verify that live (don't assume
>    from documentation) — try the unauthenticated/guest tier if one
>    exists, note exactly which endpoints work and which don't.
>
> **Do not write a single line of loader/geography/schema code before step
> 2 is done and you can name the exact real URLs, exact real field codes,
> and one real cross-checked population number.**
>
> **Architecture — follow it exactly, do not invent a different shape.**
> Read `pyCensus/src/pycensus/spain/` end to end first (cleanest current
> reference: keyless GISCO boundaries + keyless national API). Also read
> `pyCensus/src/pycensus/mexico/` (per-region bulk-file pattern) and, if
> your source needs an account, `pyCensus/src/pycensus/germany/` (the
> correct way to leave a module honestly blocked). Mirror their directory
> layout, function names, and docstring style for the new country.
>
> **Absolute rule: never fabricate data at any stage.** No `np.random`
> geometry, no hardcoded placeholder/zero values, no guessed field codes,
> no invented schema fields "for completeness." If a level or field can't be
> sourced from something you've actually verified, leave it out and say so
> in a docstring/TODO — do not stub it with fake output. See "Anti-patterns"
> below for the exact failures this rule is written to prevent.
>
> **When done:** run the existing test suite (`cd pyCensus && uv run pytest`
> or the repo's normal runner) to confirm no regressions, add mocked-network
> tests for the new module following `tests/test_spain.py`'s pattern, and
> leave the module **unwired** from `CS_transitLOS/code/pipeline.py` /
> `city_config.py` until it is fully verified end-to-end against live data
> for at least one real region. Wiring is a separate, later step — see
> "Wiring into CS_transitLOS" below.

---

## Directory layout

A country module lives at `pyCensus/src/pycensus/<country>/` (lowercase
country name, e.g. `spain`, `mexico`, `germany`, or a sub-national name like
`euskadi`). Inside it:

```
<country>/
  __init__.py
  constants.py        # region codes, name<->code lookups, LEVEL_FALLBACK, LATEST_YEAR
  geography.py         # real boundary fetch/cache, shared by every source
  api.py                # low-level HTTP client for the national statistics API (if any)
  utils.py              # helpers used by more than one source (code-resolution, etc.)
  levels.json            # this country's native levels + global_levels mapping (see below)
  <source>/             # one subpackage per distinct data source, e.g. ine/, inegi/, destatis/, eustat/
    __init__.py
    schema.json           # the ONLY place field codes are declared
    schema.py              # loads schema.json into a ColumnSchema (thin, boilerplate)
    loader.py               # real fetch + cache + assemble into a common-schema GeoDataFrame
    custom_fields.py         # optional: computed_from-derived fields (e.g. density)
```

This is the actual shape of `spain/` (source: `ine/`), `mexico/` (source:
`inegi/`), `germany/` (source: `destatis/`), and `euskadi/` (source:
`eustat/`) as they exist in this repo today — don't restructure it.

A country can have more than one source subpackage if the country publishes
population data from more than one agency/table family (none currently do,
but the shape supports it — see how `usa/` splits `acs1/`, `acs3/`, `acs5/`,
`dhc/`, `lodes_rac/`, `lodes_wac/` into independent source folders, each
with its own `schema.json`/`schema.py`/`loader.py`, rather than one lumped
`usa/schema.json`). A **sub-national** module (Euskadi inside Spain) is
still its own top-level `pycensus.<name>` package, not nested under the
national one — `euskadi/` is a sibling of `spain/`, not `spain/euskadi/`.

---

## `geography.py`: what it must provide

Responsibilities (see `spain/geography.py` and `mexico/geography.py` as the
reference implementations):

- **Real boundary fetching.** Download an actual geometry file (shapefile,
  GeoJSON, GeoPackage) from a real, verified URL. Cache the raw download
  under `<data_dir>/raw/<source_name>/` (separate from `pycensus.cache`'s
  parquet cache — this is the *raw* download cache, persistent and
  independent of the region-level parquet cache used by loaders).
- **Output CRS is always EPSG:4326.** Every `load_boundaries*` function
  must return (or reproject to) EPSG:4326 — `gdf.set_crs(4326)` if the
  source has no CRS set, `gdf.to_crs(4326)` otherwise. This is load-bearing:
  `CS_transitLOS` and `geohierarchy` assume EPSG:4326 throughout.
- **`IMPLEMENTED_LEVELS` — an explicit tuple of only the levels with a real,
  verified source.** If a level's geometry isn't backed by something you
  actually downloaded and checked, don't add it to `IMPLEMENTED_LEVELS`;
  `load_boundaries` should raise `NotImplementedError` for anything else,
  with a docstring/error message explaining what would be needed to add it
  (see `spain/geography.py::load_boundaries`'s handling of
  `district`/`section`/`block`, and `mexico/geography.py`'s handling of
  `ageb`/`block`/`nation`/`locality`).
- **`LEVEL_FALLBACK` in `constants.py`.** Maps the universal level names
  (`nation`, `state`, `province`, `municipality`, `tract`, `blockgroup`,
  `block` — see `global_levels.json`) onto this country's native level
  names where they don't match 1:1 (e.g. Spain's `LEVEL_FALLBACK` maps
  `"state" -> "autonomous_community"`, `"county" -> "municipality"`,
  `"tract"/"blockgroup" -> "section"`). Use
  `pycensus.geometry_levels.resolve_level(level, constants.LEVEL_FALLBACK)`
  at the top of every public function that takes a `level` argument.
- **A `states_in_aoi`-style function** (name doesn't have to match exactly,
  but every country has one) that, given an AOI GeoDataFrame, returns the
  region codes whose boundary intersects it — this is what a loader calls
  when the caller passes `aoi=` instead of explicit `regions=`. **Do not**
  default this to "return every region in the country and let a downstream
  intersects-filter sort it out" if fetching each region is expensive — see
  the "all-32-states" cautionary note below. Use a cheap bounding-box
  pre-filter (hand-set approximate per-region bboxes in `constants.py`,
  padded a few tens of km, see `mexico/constants.py::STATE_BBOX`/
  `STATE_BBOX_PADDING_DEG`) if a real lightweight national boundary index
  isn't available.
- **Region-code resolution helpers in `utils.py`** (name, abbreviation, or
  code -> canonical code), used by both `geography.py` and `loader.py`.

---

## `<source>/schema.json` / `schema.py`: what they must contain

`schema.json` is the single source of truth for every field this source
exposes. **Every entry must be traceable to a code/column you have actually
seen in a real downloaded file or a real API response** — not a code you
inferred from a naming convention or another country's schema. Structure
(see `spain/ine/schema.json`, trimmed to 3 real fields, as the cleanest
example):

```json
{
  "country": "spain",
  "source": "ine",
  "full_name": "INE Padron Municipal (Cifras oficiales de poblacion)",
  "years": [2025],
  "levels": ["municipality", "province", "autonomous_community", "nation"],
  "features": [
    {
      "category": "population",
      "feature_name": "population",
      "country": "spain",
      "source": "ine",
      "codes": ["TOTAL_POB"],
      "definition": "Total population residing in the geographic area (Padron municipal, INE table 29005, sex = Total).",
      "type": "count",
      "resampling_up": "sum",
      "resampling_down": "divide_area_weighted"
    }
  ]
}
```

Field-by-field:

- `feature_name`: the logical, camelCase name used everywhere in pyCensus
  (`population`, `malePopulation`, `incomeMedianHousehold`, ...). This
  becomes the `{feature_name}` segment of a `FieldKey`
  (`{year}_{country}_{source}_{feature_name}`, see
  `pyCensus/src/pycensus/new_schema.py::FieldKey`) — check
  `global_schema.json` first for a canonical name to reuse when an
  equivalent field exists there (e.g. `population`, `households`,
  `malePopulation`, `femalePopulation`, `adultPopulation`,
  `under18Population` are all canonical names already defined there with
  `constant_total`/`constant_density` conventions — match them exactly so
  cross-country comparisons and `geohierarchy` resampling behave
  consistently).
- `codes`: the **real, verified** raw source column/variable code(s) this
  feature is built from (e.g. INE's `TOTAL_POB`, INEGI's `POBTOT` — not
  `POBTOTAL`, which was Mexico's original *fabricated* guess and is wrong).
- `type`: `"count"` for anything additive (population, households, area),
  `"mean"`/`"median"`/`"percentage"`/`"rate"`/`"density"` for anything that
  must be weighted-averaged rather than summed when resampling. **Get this
  right** — see the "median/mean declared as count" anti-pattern below,
  which silently summed medians across regions instead of weighted-
  averaging them.
- `resampling_up` / `resampling_down`: the aggregation method name consumed
  by `NewColumnSchema._build_strategy` (`new_schema.py`) — `"sum"` /
  `"weighted_divide"` for counts, `"weighted_mean"` (or a
  `"<featureName>_weighted_mean"` variant naming the weight feature, see
  `laborForce`) for means/medians/rates. Never leave a mean/median field on
  `"sum"`.
  Also normalize spelling — this codebase's convention settled on
  `"weighted_divide"`, not `"divide_area_weighted"`, after a prior
  inconsistency was found and fixed; check current usage in a sibling
  schema before introducing a third spelling.
- `resampling_weight`: the feature name to weight downscaling by, or
  `"area"` (or omitted) to mean "weight by geometric overlap instead of
  another column."
- `relative_to`: the feature name this one is a share/subset of (e.g.
  `malePopulation`'s `relative_to` is `population`) — powers `.share`/
  `.relative` in `accessors.py`. Don't leave this dangling — every
  `relative_to` value must name a feature that actually exists in the same
  schema (a dangling `relative_to` was found and fixed in `usa/acs3`).
- `constant_total` / `constant_density`: whether this field's *total* or
  *density* is expected to stay invariant under resampling — copy the
  convention from the matching `global_schema.json` field if one exists.
- `description`: fill it in with real text — don't leave it blank (~70
  missing descriptions were found and back-filled in USA schemas during
  this project's audit).

`schema.py` is thin, boilerplate JSON-loading code — copy
`spain/ine/schema.py` or `mexico/inegi/schema.py` verbatim and adjust the
import path; do not hand-write `ColumnSchema.add()` calls, and do not paste
in a broken code-generator artifact (one prior schema.py had the literal
string `"<ast.ListComp object at 0x...>"` baked into a field's `codes` —
inspect the generated JSON, don't trust a generator blindly).

`<source>/custom_fields.py` is where a `computed_from`-derived field goes
(e.g. `compute_population_density` — computed from `population`/`area`
rather than a raw source code). Only keep entries here whose underlying
fields actually exist in the current schema; trim dead computed fields when
you remove the schema fields they depended on.

---

## `loader.py`: what it must do

`loader.py` is where the real network/file I/O happens. Required shape
(mirror `spain/ine/loader.py` and `mexico/inegi/loader.py`):

1. `load(aoi=None, regions=None, level=..., year=..., api_key=None,
   cache_dir=None, cache=True, data_dir=None) -> gpd.GeoDataFrame` — the
   public entry point. Resolves `level` via `LEVEL_FALLBACK`, resolves
   `regions` from `aoi` via `geography.states_in_aoi` (or equivalent) when
   `regions` isn't given, then for each region calls
   `pycensus.cache.load_region(path, id_col="GEOID", columns=..., 
   fetch_boundary=..., fetch_columns=..., use_cache=cache)` — this is what
   makes the parquet cache transparent: `fetch_boundary`/`fetch_columns` are
   only actually called on a cache miss.
2. A private `_fetch_missing(missing_prefixed, level, region, ...)` that
   does the **real** fetch (HTTP GET / bulk-file download / API call),
   parses the **real** response, and returns a DataFrame keyed by `GEOID`
   with one column per requested logical field. This is the function that
   must never fabricate: no unconditional zero-filled columns, no
   `np.random`. If a field genuinely can't be fetched yet (blocked on
   credentials, unverified endpoint), raise a specific, clear exception —
   see `germany/destatis/loader.py::_fetch_missing`'s `NotImplementedError`
   with an exact TODO — never return placeholder values silently.
3. Bind fetch functions dynamically (`getattr(api, "fetch_x")` or a closure
   captured per-call), not via a module-level dict populated at import time
   — a module-level dispatch dict silently defeats test monkeypatching (a
   real bug found and fixed in Mexico's loader).
4. Output columns are `SCHEMA.prefixed(feature_name)` — i.e.
   `"<source>_<feature_name>"` (e.g. `ine_population`, `inegi_population`).
   Don't hand-roll a different naming convention.
5. Final result must be a `gpd.GeoDataFrame` with a `GEOID` column,
   `geometry` in EPSG:4326, one prefixed column per schema field, optionally
   clipped to `aoi` via `result[result.intersects(aoi.to_crs(4326).union_all())]`.

---

## API-key-required sources: the Germany pattern

If the country's real data API needs a registered account/key (not just an
anonymous public endpoint), do **not** leave the module returning fake data
while "waiting" for credentials, and do not crash with a bare
`KeyError`/`requests.HTTPError` either. Follow `germany/api.py` +
`germany/destatis/loader.py` exactly:

1. Add empty-string placeholder key(s) to `pyCensus/api_keys.json`, named
   clearly (`destatis_genesis_username`/`destatis_genesis_password`, not a
   generic `api_key`):
   ```json
   {
     "us_census": "...",
     "destatis_genesis_username": "",
     "destatis_genesis_password": ""
   }
   ```
2. Write a small, specific exception class (`GenesisCredentialsError`, a
   `RuntimeError` subclass) — not a bare `Exception`/`ValueError` — so
   calling code (including, eventually, `CS_transitLOS`'s pipeline) can
   catch it specifically and fall back to something else
   (`pycensus.worldwide.worldpop` is the documented fallback for population
   when a country's real census source is blocked).
3. A `resolve_<x>_credentials(...)` function using
   `pycensus.api_keys.resolve_api_key` (checks an explicit arg, then an env
   var, then `api_keys.json`) that raises that specific exception — with an
   actionable message naming exactly which keys are missing and where to
   register — when nothing is configured.
4. Call the credentials-resolver **first**, before any expensive geometry
   download, so a missing-key failure is immediate and cheap.
5. If you can verify that an anonymous/guest tier of the API works for some
   endpoints but not others (Germany's real `GAST`/`GAST` guest account
   works for `helloworld`/`find` but is rejected by `data/table`), say so
   explicitly in the module docstring with the exact verified behavior —
   don't guess.
6. It's fine — expected, even — to leave the actual data-fetch as a
   `NotImplementedError` with a precise TODO (exact next API calls to make,
   exact table/statistic codes already confirmed) once real credentials
   exist, rather than to fabricate a guess at the final parse logic before
   you can test it against a real authenticated response.

---

## Testing expectations

Two layers, matching `tests/test_spain.py`/`test_mexico.py`/
`test_germany.py`'s established convention:

1. **Committed, offline, mocked-network unit tests** (`pyCensus/tests/
   test_<country>.py`). Monkeypatch the real network-touching functions
   (`api.fetch_*`, `geography._load_*`/`load_boundaries`) with small
   synthetic DataFrames/GeoDataFrames, and test: constants (region-code
   lookups, counts), `LEVEL_FALLBACK`, schema (field set, `relative_to`
   references all resolve, no stale/corrupted codes), geography (implemented
   vs. `NotImplementedError` levels, `states_in_aoi` narrows rather than
   returning everything), and the loader (cache reuse, region resolution,
   real column-naming). These must run fast and offline as part of the
   normal suite (`cd pyCensus && uv run pytest`).
2. **Real, live-network verification during development — required before
   declaring the module done, not optional.** Actually call the real
   endpoint/download, actually parse it, and confirm:
   - A population (or other headline) total for at least one real region
     matches a real, independently known published figure for that region
     — not just "some number came back." Spain's rebuild cross-checked
     Madrid province (7,137,031) against its known ~7.1M population;
     Mexico's cross-checked Jalisco's state-total row (`POBTOT=8,348,151`)
     against INEGI's own published figure.
   - Real geometry bounds land where the region actually is (sanity-check
     lon/lat bounds against the country's known extent).
   - If a level aggregates from finer sub-regions, that the sub-region sum
     equals the parent total exactly (or with an explained near-miss).
   This verification does not need to be a permanently-running test (a
   `@pytest.mark.network` test, as `test_spain.py` added, or a one-off
   scratchpad script, are both fine) — but it must actually have happened,
   with the real numbers recorded in the module's docstring or commit
   message, before the module is considered real rather than assumed.

---

## Wiring into `CS_transitLOS`

Do **not** wire a new/rebuilt module into
`TransitLOSStudies/CS_transitLOS/code/city_config.py` /
`pipeline.py` until it has passed real, live-network verification (above).
An unwired module fails safely — `pipeline.py`'s census-join functions
print a clear "not yet supported, skipping" message and leave the h3 grid
unchanged rather than crashing. A wired-but-fabricated module is worse: it
silently produces real-looking, wrong data. This was the exact mistake this
project avoided by leaving Spain/Germany/Israel/Euskadi unwired in
`pipeline.py`'s dispatch while they were still fabricated.

Once verified, wiring has two parts:

1. **`city_config.py`**: if the whole country's generic census module is
   what a city should use, add `"<ISO3>": "<country>"` to
   `_ISO3_TO_PYCENSUS_MODULE`. If instead a specific city needs a
   *sub-national* module instead of its country's generic one (the
   Gipuzkoa/Euskadi case — Basque Country data instead of generic
   Spain/INE), set that city's `CityConfig.census_module="<subnational_name>"`
   — this overrides `_ISO3_TO_PYCENSUS_MODULE[country]` entirely for that
   one city (see `_census_supported()`'s resolution order and the
   `gipuzkoa` entry in `CITY_CONFIGS`, which sets
   `census_module="euskadi"`).
2. **`pipeline.py`**: `_join_census`/`_join_race`/`_join_jobs` dispatch on
   `country` (and, when set, `census_module`, checked *before* the generic
   country dispatch — see the `if census_module == "euskadi":` branch ahead
   of `if country == "USA":` in `_join_census`). For a new country, add:
   - A `<COUNTRY>_KEEP_COLUMNS` set naming exactly the prefixed columns your
     new schema actually produces (verify this against
     `SCHEMA.prefixed(name)`, not by guessing a naming convention — see the
     stale-keep-list anti-pattern below).
   - A `<COUNTRY>_LEVELS` tuple of the levels your `geography.py` actually
     implements.
   - A `_<country>_census_loader` adapter (if the new module's `load()`
     signature doesn't line up 1:1 with `_join_polygon_stats`'s expected
     `loader(aoi=, states=, ...)` call — Mexico needed one because
     `census_states=None` for non-US cities requires `states_arg = list(states)
     if states else None`, not an unconditional `list(None)`).
   - If the country has no race/ethnicity or workplace-jobs-flow census
     categories (most non-US countries don't), have `_join_race`/
     `_join_jobs` cleanly no-op for that country/module — log why, return
     `h3_grid` unchanged — rather than crash or fabricate placeholder
     columns (see how Mexico's branch handles this).
   - Add or extend `TransitLOSStudies/CS_transitLOS/tests/
     test_keep_columns_match_schema.py` with a staleness guard for the new
     `<COUNTRY>_KEEP_COLUMNS` set, so a future pyCensus rename fails CI
     instead of silently zeroing the join (see the case-sensitive-substring
     and stale-column-name bugs below — this exact test file exists because
     of them).

---

## Anti-patterns to never repeat

These are concrete, specific mistakes made and later fixed in this
project's real history. If you catch yourself about to do any of these,
stop.

- **Fabricated boundary geometry.** Mexico's, Spain's, Germany's,
  Euskadi's, and Israel's first-built `geography.py` all generated
  boundaries via `np.random.seed(hash(region)); np.random.uniform(...)`
  bounding boxes — fake polygons standing in for real administrative
  geometry, silently, with only a code-comment admitting it. If you ever
  see (or are about to write) `np.random` anywhere near a `geography.py`,
  that module is fabricated and must be rebuilt from a real source.
- **Hardcoded all-zero placeholder data.** The same four modules'
  `loader.py`s built a URL string (often pointing at a human-facing HTML
  page, not a data endpoint), never actually parsed what it returned, and
  unconditionally wrote out a placeholder CSV like
  `{"TOTAL_POB": [0], "POB_HOMBRES": [0], "POB_MUJERES": [0]}`. This is
  worse than a dead URL — it doesn't even attempt the network call for the
  real values. Every value in every schema field must trace back to a real
  parsed API/file response, never a literal `0`/`None` written
  unconditionally.
- **Unverified/guessed field codes.** Mexico's original schema used
  `POBTOTAL` for total population; INEGI's real code is `POBTOT`. A field
  code is not real until you've seen it as a literal column name in an
  actual downloaded file or actual API response — never infer it from
  another country's convention or a plausible-sounding abbreviation.
- **Treating HTTP 200 as proof of real data.** INEGI's dead/guessed URLs
  returned a 200 status with a generic "not found" HTML page — a
  misleadingly "successful" response. Always inspect actual response
  *content* (real column names, real numeric values, a total that matches
  a known figure), never just the status code.
- **RAC/WAC column-prefix collision.** USA's LODES RAC and WAC schemas
  originally shared one `"lodes"` cache-parquet prefix, so their columns
  silently collided in the parquet cache. Give every distinct source its
  own prefix (`lodes_rac`/`lodes_wac`), matching its own subpackage name —
  don't let two sources share a prefix just because they come from the
  same underlying dataset family.
- **Stale renamed-column keep-lists.** When pyCensus's own column-naming
  convention changed (from `acs_population`/snake_case to
  `acs5_population`/camelCase), `CS_transitLOS/code/pipeline.py`'s
  `ACS_KEEP_COLUMNS`/`DHC_KEEP_COLUMNS`/`LODES_KEEP_COLUMNS` sets — and the
  separate `prefix` string literals passed at each `_join_polygon_stats`
  call site — were never updated to match. The join then silently matched
  **zero** columns: no exception, no warning, just an empty result. Any
  time you rename a schema's prefix or a feature name, grep every
  downstream consumer (`pipeline.py` had ~80 additional stale references
  beyond the three obvious keep-lists) rather than trusting that "nothing
  broke" because nothing crashed.
- **Case-sensitive substring matching that broke on a naming-convention
  change.** `pipeline.py`'s `_CENSUS_RATE_SUBSTRINGS = ("mean", "median")`
  check (used to decide whether a column should be broadcast as a rate vs.
  apportioned by population share like a count) did a case-sensitive
  substring test. When feature names became camelCase
  (`incomeMedianHousehold`, `householdSizeMean`), `"median" in
  "acs5_incomeMedianHousehold"` evaluated `False` — every mean/median
  column was silently apportioned like a raw count instead of broadcast,
  corrupting values with no error. Lowercase both sides before any
  substring/prefix check driven by a naming convention, since conventions
  change.
- **Median/mean fields declared `type: "count"` with `resampling_up:
  "sum"`.** Several USA ACS fields (`incomeMedianHousehold`,
  `commuteTimeMean`, `medianAge`, etc.) were originally typed as additive
  counts, meaning upscaling would sum two regions' median incomes together
  ($50k + $60k median -> "$110k median") instead of weighted-averaging
  them. Always double-check that anything that isn't a literal countable
  quantity is typed `mean`/`median`/`rate`/`percentage` with
  `resampling_up`/`resampling_down` set to `weighted_mean` (or a
  `<feature>_weighted_mean` variant), never `sum`.
- **Positional/label index confusion in a shared join helper.**
  `_join_polygon_stats` built matched-row indices as pandas *label*
  indices from `gpd.sjoin`, then used them for *positional* numpy indexing.
  This worked by accident when a grid had a clean default `RangeIndex`, but
  crashed (or, worse, silently used the wrong row) once a grid's on-disk
  index was a sparse subset of a larger parent grid — a real, common case
  for any per-city AOI subset of a metro-wide grid. If you write or modify
  shared join/aggregation plumbing, reset to a clean positional index on
  entry and restore the caller's original index on return, rather than
  assuming any input's index is already dense/contiguous.
- **Fetching every region "to be safe" when only a few actually intersect
  the AOI.** `mexico/geography.py::states_in_aoi` originally returned all
  32 Mexican states unconditionally whenever the caller passed `aoi`
  instead of explicit `regions`, relying on a downstream intersects-filter
  to narrow the *final* result back down — functionally correct, but it
  meant a real run would download and process 32 states' worth of data
  (roughly an hour, at ~150s/state observed) to end up using one. Use a
  cheap pre-filter (bounding-box overlap against a hand-set approximate
  per-region extent, padded generously) before committing to any expensive
  per-region download.
- **A silently-swallowed `api_keys.json` parse error.** `pycensus.api_keys.resolve_api_key` catches `JSONDecodeError` and falls back to `{}` rather than raising, so a single trailing comma in `api_keys.json` (real incident, found 2026-08-20) silently made every country's key resolution return `None` — not just the one country someone happened to be debugging. If a country's real key/token stops resolving for no visible reason, check that `api_keys.json` is still valid JSON before assuming the key itself is wrong.
- **An "ArcGIS Hub" portal with no documented API is often not actually keyless-API-less.** A statistics portal built on Esri ArcGIS Hub (URL pattern `.../apps/sites/#/...`, or a page that references Esri's `activation-engine`/`community-engine` frontend modules) usually has a real, public, undocumented ArcGIS Server behind it — hit `<portal>/portal/sharing/rest?f=json` to confirm, then look for FeatureServer layers (`<portal>/server/rest/services/...`). This exact pattern turned "no API exists" into a real, live, verified source for Israel (`pycensus.israel.arcgis`), Andorra (parish boundaries + population by locality), and Chile (INE's Censo 2017 data republished by Esri Chile) — check for it before concluding a country is blocked.
- **A country's own `feature_name`s not matching `global_schema.json`'s canonical camelCase names.** Mexico's schema (built before this convention was reinforced) uses `populationMale`/`populationFemale`/`populationSpeaksIndigenousLanguage` where the canonical global names are `malePopulation`/`femalePopulation`/(no equivalent) — this doesn't break anything today since each source's schema is self-contained, but it silently defeats any cross-country comparison or `geohierarchy` logic that expects the canonical name. Check `global_schema.json` for a matching `feature_name` before inventing your own, and if you're touching an existing schema anyway, prefer renaming to match over leaving a known mismatch.
- **A stale/incorrect region-code table that nothing catches by accident.**
  Spain's `PROVINCE_CODES` had several shifted/fabricated 2-digit INE codes
  (e.g. La Coruña was listed as `"23"`, the real code is `"15"`) and was
  missing two provinces entirely. Nothing about this raised an exception —
  it just produced wrong `GEOID`s silently. Cross-check every region-code
  table against a real, independent source (the boundary file's own region
  IDs are usually the most reliable cross-check, since they came from the
  same real download you're already trusting for geometry).

Whenever you're unsure whether something you're about to write counts as
"real," ask: *if someone downloaded the exact same URL I'm about to hardcode,
would they see the exact numbers/geometry I'm about to put in this schema?*
If you haven't actually done that download-and-look yourself, the answer is
unverified, and unverified is exactly the gap every mistake above fell into.
