# Euskadi (Basque Country) — Eustat

**Source:** https://es.eustat.eus/ayuda_banco_API.html

Eustat's "Banco de Datos" (BDE) exposes a public REST API, no signup/token required:

- List all tables: `GET https://www.eustat.eus/bankupx/api/v1/{lang}/DB`
  (`{lang}` = `es`/`eu`/`en`)
- Table metadata (variables, codes, value labels): `GET .../DB/{table_id}`
- Table data: `POST .../DB/{table_id}` with a JSON `{"query": [...]}` body
  selecting variables/values (or `{"query": []}` for the whole table).
  Output format defaults to JSON-stat 1.2; CSV/CSV2/CSV3/XLSX also available
  via `"response": {"format": ...}`.

**Auth / token:** none — fully open API. `api_keys.json` has no entry for Euskadi.

**Data format:** JSON-stat (recommended, default), or CSV/XLSX on request.

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.

**Verified live, 2026-08-20:** `GET https://www.eustat.eus/bankupx/api/v1/es/DB`
returns HTTP 200 with a real JSON array of 2,324 tables (not the misleading
403 an earlier pass of this module recorded -- that check hit a mistyped
`bancopx` path, not the real `bankupx` one; see `api.py`'s module docstring
for the full correction). A `POST` query against table
`PX_010154_cepv1_ep06b.px` for period `2025/01/01` returned real population
figures: Gipuzkoa 724,797, Bizkaia 1,155,733, Araba 337,680, C.A. de Euskadi
total 2,218,210 -- these match Eustat's own well-known published totals and
are more current than the 2021 GISCO/LAU figures `eustat/loader.py`
currently uses. Switching the loader to pull directly from this API
(richer fields: households, age structure, Basque-language use, income;
current-year vintage) is a real follow-up, not attempted in this pass.

**Deeper follow-up, 2026-08-22 — does EUSTAT beat `pycensus.spain`/INE for
Gipuzkoa?** No. Investigated whether EUSTAT has genuinely finer-than-
municipality data that would justify routing Gipuzkoa through `euskadi`
instead of `spain` (which already gives real, live-verified `section`-level
data, 544 sections, 98.7-99.5% match against real municipal totals).
Findings:

- The prior 403/404s on `opendata.euskadi.eus` / `eustat.eus/geoservicios`
  were a missing-User-Agent bot block, not missing data — both return 200
  with a real browser UA. `www.geo.euskadi.eus` (GeoEuskadi, a separate,
  real Basque Government geoportal) is also live and does publish a real,
  current census-section shapefile: `https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/Unidades_estadisticas/SECCIONES_EUSTAT_5000_ETRS89.zip`
  (200, 6.36 MB, last-modified 2026-07-03 — more current than GISCO LAU
  2021). Not wired up in this pass.
- EUSTAT's Data Bank (BDE/bankupx) catalogue has no table keyed at
  district/section geography — searched all 2,324 tables for
  "distrito"/"sección"/"barrio"/"censal"/"padrón", every hit is unrelated
  (rent by neighbourhood, tariff sections, employment by activity, etc.).
- The real section-level population tables live outside BDE, on EUSTAT's
  "elementos" pages, each with a real downloadable CSV (e.g.
  `/elementos/xls0011434_c.csv` for Gipuzkoa, 537 sections, dated
  01/01/2025). Fetched and parsed it: territory-wide sum = 724,797,
  exactly matching the already-verified BDE total. But at municipality
  level it gives Donostia = 183,388 and Irun = 60,665, vs. real published
  figures of ~188,487-189,093 and ~63,737 — 2.7-4.8% off, worse than
  `spain`/INE's 98.7-99.5% match for the same two cities.
- Conclusion: EUSTAT has real section-level data at the same resolution as
  INE, with even more current geometry, but *less accurate* population
  figures. Not a case for switching Gipuzkoa back to `euskadi` — `spain`
  stays the better source and the routing is unchanged.
