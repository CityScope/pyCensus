# Andorra — Departament d'Estadistica (estadistica.ad)

**Update 2026-08-20:** a real, keyless, queryable API *was* found, despite
the human-facing portal having no documented one. The portal at
`https://www.estadistica.ad/portal/apps/sites/#/estadistica-ca/pages/base-de-dades`
is itself built on Esri ArcGIS Hub (confirmed live: its page source
references the `activation-engine`/`community-engine` Ember modules Esri's
Hub frontend ships, and `https://www.estadistica.ad/portal/sharing/rest?f=json`
answers with a real ArcGIS Portal API version). That means it has an
underlying ArcGIS Server with real, public FeatureServer layers, the same
pattern used successfully for Israel (`pycensus.israel.arcgis`).

Two real services are used by this module (both verified live, response
content inspected, not just HTTP 200):

- **Parish (comú) boundaries** —
  `https://www.estadistica.ad/server/rest/services/Estadistica/Cartografia_base/FeatureServer/3`
  (layer `Parroquies_Pol_codi`). Returns exactly 7 polygons with real
  `Nom`/`Codi` fields matching Andorra's 7 parishes and their ISO
  3166-2:AD codes (`AD-01`..`AD-07`).
- **Population by locality/year** —
  `https://sig.govern.ad/server/rest/services/Hosted/Poblaci%C3%B3_2010_2021/FeatureServer/0`
  (item title "Població 2010-2025", found via
  `https://www.estadistica.ad/portal/sharing/rest/search?q=poblacio&f=json`).
  Returns 44 real localities, each tagged with its parish (`parroquia`) and
  one `pob_<year>` column per year (2003, 2010-2025). Summed across all
  localities, `pob_2023` = 85,101 — matching Diari d'Andorra's reporting of
  the Departament d'Estadistica's own published 31-Dec-2023 population
  figure.

Neither endpoint needs an API key or auth token (confirmed live).

See `pycensus.andorra.api`, `pycensus.andorra.geography`, and
`pycensus.andorra.estadisticaad.loader` module docstrings for full detail.
`api_info.txt` (gitignored) in this directory has the original,
now-superseded "no known API" note.

## 2026-08-23: systematic check of the statistical-plan program codes

An outside (unverified) source listed a set of Andorran statistical-plan
program codes/topics claimed to have parish-level breakdowns. Each was
checked against estadistica.ad's real portal search API
(`/portal/sharing/rest/search?q=<term>&f=json`) plus direct FeatureServer
inspection. Result, category by category:

- **Buildings (A061/A062 lead)** — REAL, PARISH-LEVEL, WIRED IN. Found
  "Edificis 2019" (`sig.govern.ad/.../Hosted/Edificis_2019/FeatureServer/0`),
  21,529 real building-footprint polygons with a `parròquia` name field.
  Groupby/count by parish, verified live 2026-08-23: Andorra la Vella 4655,
  La Massana 3904, Escaldes-Engordany 3518, Sant Julià de Lòria 3030,
  Encamp 2623, Canillo 2175, Ordino 1624 (sum 21,529). Single vintage year
  (2019) only — no dwelling-count or housing-characteristics breakdown
  found under this or a related item, so only the raw building count is
  wired (`estadisticaad_buildingCount`).
- **Businesses** — REAL, PARISH-LEVEL, WIRED IN. Found "REE_Ubicació"
  (`sig.govern.ad/.../Estadistica/REE_Ubicaci%C3%B3/FeatureServer/1`,
  layer "Ubicació empreses"), a real business register: 18,645 total rows,
  integer `PARROQUIA` (1-7) and `Es_Activa` flag. Active-business count by
  parish, verified live 2026-08-23: Andorra la Vella 3667,
  Escaldes-Engordany 1399, Encamp 998, La Massana 976, Sant Julià de Lòria
  438, Canillo 335, Ordino 329 (sum 8,142). The integer parish code was
  cross-checked live against the ISO 3166-2:AD suffix embedded in the same
  row's `vc_pkBloc_id_c` address code (e.g. every `PARROQUIA=6` row's
  `vc_pkBloc_id_c` starts `AD-06-`), confirming the code mapping rather
  than assuming it. Wired as `estadisticaad_activeBusinessCount`.
- **A047 "Estadística de la distribució personal de la renda" (income)** —
  NOT FOUND as a queryable table. Portal search for "renda" returned only
  a generic "Comparar" web-mapping app, no FeatureServer/table. The
  national income figures cited by the outside source (2025 report: mean
  €41,085/median €29,505 for 2024 income) were not independently located
  in a queryable form at all, let alone parish-level — consistent with the
  source's own warning that this is likely a national, survey-based
  aggregate. Not wired.
- **A231 "Registre estadístic de territori"** — NOT FOUND. No portal
  search result for "A231" or matching title; nothing under this program
  code was located.
- **Births/deaths ("naixements"/"defuncions")** — NOT FOUND. Portal
  searches for both Catalan terms returned zero results.
- **Employment/unemployment ("atur"), social-security ("seguretat
  social"), nationality/migration ("estrangers"/"migracio"), households**
  — NOT FOUND as queryable tables via portal search; "seguretat social"
  and "atur" searches returned only unrelated hits (the population layer
  and generic Esri templates/apps). This matches the pattern already
  found for CASS (national-only) and Servei d'Ocupació (portal/PDF-only)
  in earlier sessions — no new queryable statistical-plan table located
  for any of these topics.
- **Housing prices/real-estate ("habitatge")** — search surfaced only
  dashboards/web maps (`RET_DISTRIBUCIO_HABITATGES`) and the same
  buildings-adjacent `REE_EDIFICI_HABIT_CONSUM` layer (see below); no
  downloadable/queryable price table found.
- **`REE_EDIFICI_HABIT_CONSUM`** (`Estadistica/REE_EDIFICI_HABIT_CONSUM/FeatureServer/1`)
  — real, parish-tagged (`Parroquia` integer field) dwelling-habitability
  point layer, but only 160 total records nationwide — far too small to
  be a real per-dwelling census (Andorra has on the order of tens of
  thousands of dwellings), so treated as a partial/sample table, not
  wired in.

Everything not listed as "wired in" above should be treated as not
found/not queryable, not as confirmed absent — a different search term or
a future portal change could still surface it.

## 2026-08-23 (later): foreign-born population and jobs-by-workplace

Follow-up investigation specifically targeting the two fields flagged as
most important for Andorra: foreign-resident population (Andorra has one
of the highest foreign-resident shares in the world) and jobs-by-workplace.

- **`foreignBornPopulation` — REAL, PARISH-LEVEL, WIRED IN, but from a PDF
  bulletin, not a FeatureServer.** No queryable ArcGIS table anywhere in
  estadistica.ad's/sig.govern.ad's catalogue carries a
  nationality/foreign-resident breakdown (portal search for "nacionalitat",
  "estranger", "residencia", "immigracio" all returned zero hits, both
  tonight and in the prior pass). However, the Departament d'Estadistica's
  regular "Nota de premsa" bulletin (real, keyless, bulk PDF publication --
  the same pattern already established for CASS/Servei d'Ocupació) does
  publish this, at parish granularity: section "2.2 Poblacio per
  nacionalitat" of
  `https://sig.govern.ad/SIGDDE.Public/Files/Documents/Notes_premsa_noticies/A001_20250313_A.pdf`
  (found via web search for "poblacio per nacionalitat parroquia",
  confirmed live by downloading and reading the actual PDF content, not
  just HTTP 200). This table breaks 28-Feb-2025 population estimates down
  by parish x nationality (Andorrana/Espanyola/Francesa/Portuguesa/Altres),
  with an explicit "Estrangera" (non-Andorran) subtotal row and a "Total"
  row. `pycensus.andorra.api.fetch_population_by_nationality_and_parish`
  downloads this PDF and parses that table with `pdfplumber` -- the raw PDF
  renders every digit as a separate text run (no `extract_tables()` grid
  detected), so the parser reassembles numbers from word bounding boxes
  (row-banding by y-position, column-clustering by x-gap within a row) and
  **cross-validates its own parse** before returning: for every column, the
  five single-nationality rows must sum to Total, the (repeated) Andorrana
  row must be internally consistent, and Andorrana + Estrangera must equal
  Total -- if a future bulletin's layout drifts, this raises rather than
  silently mis-parsing. Verified live 2026-08-23: nationwide Estrangera
  (foreign-nationality) population is 48,008 out of 87,486 total (54.9%),
  matching Andorra's well-documented, independently known ~45-55%
  foreign-resident share; per-parish breakdown (Andorra la Vella 13,376,
  Escaldes-Engordany 8,518, Encamp 7,378, La Massana 6,976, Sant Julia de
  Loria 4,436, Canillo 4,381, Ordino 2,943) sums exactly to the total.
  This is a nationality-based proxy for "foreign-born" (documented as such
  in the schema), like most small-country sources -- Andorra's own
  published statistics are nationality-based, not literal place-of-birth.
  It's also a single dated snapshot (the bulletin is published monthly at
  an unpredictable exact URL/date; no index/API was found to auto-resolve
  "the latest" one), so the loader returns this same snapshot regardless
  of the requested year, same as `buildingCount`/`activeBusinessCount`.
  Wired as `estadisticaad_foreignBornPopulation` (canonical bare name
  `foreignBornPopulation`, matching `global_schema.json`).

- **Jobs-by-workplace — NOT FOUND, confirmed absent from the one register
  that could plausibly carry it.** The `REE_Ubicacio` business register
  (already wired for `activeBusinessCount`) was checked field-by-field
  live (`.../FeatureServer/1?f=json`): its real field list is
  `GlobalID_edif`, `vc_pkBloc_id_c`, `GlobalID_empresa`,
  `objectID_empresa`, `PARROQUIA`, `TIPUS_EMPRESA`, `codi_Activitat_N3/N2/N1`,
  `des_Activitat_N1`, `Es_Activa` -- no employee-count, headcount, or
  payroll-size field of any kind, so there is no way to derive a real
  jobs-by-workplace figure by summing per-business. CASS (the social-
  security fund, whose registration is inherently workplace-based) was
  re-checked via portal search ("seguretat social", "afiliats", "cotitzant",
  "treballadors", "ocupacio") and web search specifically for a
  parish-level or nationality-broken-down affiliate table; nothing beyond
  the previously-found national-only aggregate figures was located --
  CASS publishes no queryable parish-level table. Servei d'Immigracio's
  real, current 60,284-active-permits figure (found via web search,
  Diari d'Andorra 2026-04-17) is genuinely useful context for
  foreign-resident scale, but is nationwide-only with no parish breakdown
  published anywhere found. Not wired -- no real, sourced jobs-by-workplace
  field exists for Andorra at any granularity as of this investigation.
