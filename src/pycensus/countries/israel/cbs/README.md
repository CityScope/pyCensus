# Israel — Central Bureau of Statistics (CBS)

**Source:** https://www.cbs.gov.il/en/cbsNewBrand/Pages/api_interface.aspx

Public REST API, no signup/token required, but a `User-Agent` header is
**mandatory** on every request or the API rejects it.

Key endpoints:

- **Dictionaries** (geography codes — districts, localities, regions, etc.):
  `GET https://api.cbs.gov.il/dictionary/{subject}/{resource}`
  e.g. `https://api.cbs.gov.il/Dictionary/geo/localities` — includes
  `total_population`, `district`, `region`, `metropolin` fields per locality.
- **Price indices**: `GET https://api.cbs.gov.il/index/data/price?id={code}`
  and related `index/catalog/*` endpoints for discovering index codes.
- **General time series (SDMX-style)**: `GET https://apis.cbs.gov.il/series/data/list?id={code}`
  and `series/data/path?id={L1,L2,...}` for hierarchical subject paths;
  `series/catalog/level` / `series/catalog/path` to discover subject codes.

Common query params: `lang` (`he`/`en`), `format` (`xml`/`json`/`csv`/`xls`),
`startPeriod`/`endPeriod` (`mm-yyyy`), `last` (N most recent).

**Auth / token:** none — open API, but requires a `User-Agent` header.
`api_keys.json` has no entry for Israel.

**Data format:** JSON, XML, CSV, or XLS depending on `format` param (JSON recommended).

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.
