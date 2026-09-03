# Spain — INE (Instituto Nacional de Estadística)

**Source:** https://www.ine.es/dyngs/DAB/index.htm?cid=1099

**API JSON INE** — REST API over INEbase, INE's statistical publication system.
Data comes from three underlying sources depending on the table: the Tempus3
database, a PC-Axis file repository, or a tpx file repository — all queryable
through the same JSON API via URL requests. Table/series identifier codes
determine which backing source a given table uses.

- OpenAPI/Swagger UI docs are available for interactive exploration of
  endpoints, parameters, and formats (linked from the source page above).
- An R package, `INEapir`, wraps the API if R tooling is ever useful for
  cross-checking.

**Auth / token:** none noted — appears to be an open API. `api_keys.json` has
no entry for Spain.

**Data format:** JSON.

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.
