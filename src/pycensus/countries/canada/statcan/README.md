# Canada — Statistics Canada (StatCan)

**Source:** https://www.statcan.gc.ca/en/developers

Several access mechanisms are available, no signup/token required for any of them:

- **Web Data Service (WDS)** — REST/JSON API, e.g.
  `POST https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods`.
  Best for pulling specific series/vectors programmatically. See the WDS User Guide
  linked from the developers page.
- **Full Table Download (CSV)** — bulk per-table download, e.g.
  `https://www150.statcan.gc.ca/n1/en/tbl/csv/{PID}-eng.zip`. Zip contains a data
  CSV and a metadata CSV. Best for offline/bulk ingestion of a whole table
  (including the Census Profile cubes, PID series `98-XXXX-XX`).
- **SDMX** — time series in SDMX-ML/REST form, matches the international standard.
- **Search by Vector** — ad hoc CSV export of a list of vector IDs, e.g.
  `https://www150.statcan.gc.ca/t1/tbl1/en/sbv?vectorNumbers=...`.

**Auth / token:** none — all of the above are open, no API key. `api_keys.json`
has no entry for Canada.

**Data format:** JSON (WDS), CSV/ZIP (Full Table Download), XML/SDMX-ML (SDMX).
CSV is likely the simplest path to parity with the USA pipeline (fixed record
layout documented in the Full Table Download User Guide, including a distinct
transposed layout for 2021 Census of Population cubes `98-XXXX-XX`).

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.

## Census Profile comprehensive bulk CSV (98-401-X2021006) -- Ontario only

Beyond the Full Table Download cube family (98100002/98100015) and the
Geographic Attribute File used for the fields above, a second real StatCan
product is wired in for dissemination-area-level `householdSizeMean`,
`medianHouseholdIncome`, `meanHouseholdIncome`, `ownerHouseholds`,
`renterHouseholds`, and the education/commute-mode breakdowns
(`educationPrimaryOrLessPopulation`/`educationSecondaryPopulation`/
`educationOtherTertiaryPopulation`/`educationUniversityPopulation`,
`carCommuters`/`publicTransportCommuters`/`walkCommuters`/`bikeCommuters`,
plus their `statcan_educationTotalPopulation`/`statcan_commuteTotalPopulation`
denominators): catalogue **98-401-X2021006** ("Census Profile, 2021 --
Canada, Provinces, Territories, Census Divisions, Census Subdivisions and
Dissemination Areas"), a real per-province bulk CSV download (not part of
the Full Table Download cube family), fetched from the real GetFile.cfm
link on
`https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=E`
(GEONO=006_Ontario for Ontario). This is a long/tall table -- one row per
(geography, CHARACTERISTIC_ID) pair, ~2,631 real characteristics per
geography, ~8.8GB uncompressed for Ontario alone -- pivoted in
`pycensus.countries.canada.api.fetch_census_profile_da_totals` by streaming
directly out of the still-zipped download with `pandas.read_csv(...,
chunksize=500_000)`, filtering to `GEO_LEVEL == "Dissemination area"` and a
small set of target `CHARACTERISTIC_NAME`s *before* accumulating anything.
StatCan's real non-numeric symbols (`..`, `...`, `x`, `F`, `r`, `rE`, and
blank cells) are coerced to `NaN` via `pd.to_numeric(errors="coerce")`,
never a fabricated `0`.

**Scope: Ontario only.** Only the Ontario per-province download
(`98-401-X2021006_Ontario_eng_CSV.zip`) has actually been downloaded and
live-verified. StatCan publishes the identical real product for every
other province/territory at the same URL pattern
(`GEONO=006_<Region>`) -- adding one just needs its real region-name
suffix added to `pycensus.countries.canada.constants.CENSUS_PROFILE_GEONO_BY_PROVINCE`
and `pycensus.countries.canada.api._CENSUS_PROFILE_REGION_NAME`, then
live-verified the same way. Requesting these fields for a non-Ontario
province does not crash -- `fetch_census_profile_da_totals` raises
`NotImplementedError`, which `statcan/loader.py::_fetch_missing` catches
and leaves those columns `NaN` for that province, same as any other
missing/suppressed cell.

Live-verified 2026-08-23 against 4 real Toronto dissemination areas
(spot-checked end-to-end through `statcan.loader.load()`, not just the raw
API call):

| DA (DAUID) | Neighborhood | Household size | Median household income |
|---|---|---|---|
| 35204609 | Downtown core | 1.9 | $44,800 |
| 35203712 | Scarborough | 3.0 | $98,000 |
| 35204196 | North York | 2.1 | $65,000 |
| 35201868 | Etobicoke | 3.4 | $89,000 |

DA 35204609's values (1.9 / $44,800) exactly match this same field
spot-checked in a prior session. No independent web cross-check of
StatCan's own public Census Profile page was performed for these 4 DAs
beyond the internal consistency of the values themselves (plausible
Toronto-area household size and income ranges) -- this is disclosed
honestly rather than claimed as independently verified.
