# Chile

No single official census/statistics API with a documented programmatic
interface has been confirmed yet. Two info files feed this:

- `datoscl/api_info.txt` (see `datoscl/README.md`) — Chile's open data portal,
  browse-and-download only, no dedicated API.
- `lista_de_apis.txt` — a general community-maintained list of Chilean public
  APIs (source: https://github.com/juanbrujo/listado-apis-publicas-en-chile),
  not census-specific. The two entries most relevant to demographic/geographic
  data are:
  - **API BDE (Banco Central de Chile)** — statistical database API with
    Python/R/C# examples and usage docs; likely the best candidate for
    economic indicators.
  - **API División Político Administrativa** (marked `[DEPRECATED]` in the
    list) — used to provide Regiones/Provincias/Comunas boundaries; needs a
    replacement source for administrative geography.

**Auth / token:** none confirmed for any of the above. `api_keys.json` has no
entry for Chile.

**Data format:** varies by source (JSON is most common across the list).

Both `api_info.txt` files are gitignored, not committed — see them locally for
the raw notes.
