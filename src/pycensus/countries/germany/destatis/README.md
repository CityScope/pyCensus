# Germany — Destatis (GENESIS-Online)

**Source:** https://www.destatis.de/EN/Service/OpenData/api-webservice.html

**GENESIS web service** — RESTful/JSON API over GENESIS-Online, Destatis's
statistical database. Real current base host (verified live 2026-08-21):
`https://genesis.destatis.de/genesisWS/rest/2020` — **note: no `www-`
prefix**. The old `www-genesis.destatis.de` host now 307-redirects to
`genesis.destatis.de`, which itself used to 302-redirect further to a
generic `datenbank/online/announcement` page for the specific REST paths
that had been tried without the header-auth fix below — that combination
made the API look deprecated/moved when it was actually just being hit
with an invalid transport shape. The current official documentation PDF
(GENESIS "Anwenderdokumentation Webservice/API" v5.1, 01.06.2026) is at
`https://genesis.destatis.de/datenbank/online/docs/GENESIS-Webservices_Einfuehrung.pdf`
and confirms: the SOAP/XML interface was shut down mid-2025, GET-methods
were replaced by POST-methods, and the REST path itself
(`genesisWS/rest/2020`) is unchanged.

Key endpoints used here: `POST /helloworld/logincheck` (auth smoke test),
`POST /find/find` (search), `POST /catalogue/tables2statistic` (list tables
under a statistic), `POST /catalogue/variables2statistic` (list variables
under a statistic), `POST /data/table` (fetch a table). Full list in
`api_into.txt`/the GENESIS docs.

There's also a community-maintained `deutschland` Python package
(https://github.com/bundesAPI/deutschland) with generated clients for several
German government APIs, including one for destatis, plus unrelated datasets
(geographic address data, company filings, weather, etc.) that aren't relevant
here.

**Auth / token:** required — a GENESIS-Online account (username/password, or
a personal API token used in place of username with password omitted) must
be registered to authenticate requests. `api_keys.json`'s `"destatis_genesis"`
entry is a single token string (not a username/password pair); `germany/api.py`'s
`resolve_genesis_credentials` resolves it as `(token, "")` per that
in-place-of-username convention, falling back to
`destatis_genesis_username`/`destatis_genesis_password` if present instead.

**Critically, per GENESIS' real spec** ("2.1.3 Authentifizierung":
*"Zugangsdaten: Felder im HTTP-Header. Weitere Parameter: Felder im
Request-Body."*) — `username`/`password` must be sent as literal HTTP
request headers, not as fields in the POST body. Everything else (`name`,
`term`, `startyear`, `regionalkey`, etc.) goes in the URL-encoded body.

**Verified working 2026-08-21:** the token currently in `api_keys.json`
**does** authenticate and **does** retrieve real data once both of the
above are fixed. A 2026-08-20 session had verified the token failed against
`www-genesis.destatis.de/genesisWS/rest/2020` with credentials as body
fields, HTTP Basic Auth, and a bearer header — but never tried the one
shape GENESIS documents (plain `username`/`password` headers) against the
current host. With both fixed:

```
POST https://genesis.destatis.de/genesisWS/rest/2020/helloworld/logincheck
Headers: username: <token>
Body: language=de
-> {"Status":"Sie wurden erfolgreich an- und abgemeldet! ...","Username":"<token>"}
```

— a real successful login, not the `GAST` guest-account rejection. Real
data pulls (statistic 12411, "Fortschreibung des Bevoelkerungsstandes")
confirmed live against Destatis' own independently-published figures:

| Table | Region | Date | Value | Matches published figure |
|---|---|---|---|---|
| `12411-0001` | Germany (nation) | 31.12.2022 | 83,118,501 | Yes |
| `12411-0010` | Bavaria (state) | 31.12.2022 | 13,105,221 | Yes |
| `12411-0015` | Munich, kreisfreie Stadt (district, AGS 09162) | 31.12.2022 | 1,490,516 | Yes |

The real value variable is **`BEVSTD`** ("Bevoelkerungsstand"), not the
earlier placeholder `BEVZ01` — `BEVZ01` ("Bevoelkerung (Zensus)") is a real
GENESIS variable name (found via a real `find/find` call on 2026-08-19) but
belongs to the separate Zensus2022 database
(`ergebnisse.zensus2022.de`), not GENESIS-Online's public statistic 12411
(`catalogue/tables2variable?name=BEVZ01` returns "no objects" here).

**Data format:** GENESIS' plain `data/table` response is a
semicolon-delimited flat text block (table title/statistic name/column
headers, one data line per region or date, a `__________` marker, then
footnotes/copyright) — not JSON rows and not the documented `ffcsv`
row-per-record format. `pycensus.germany.destatis.loader._parse_flat_table`
parses it for the single-value-per-line case produced by filtering to one
`startyear`/`endyear`. (Also available: XML/CSV table exports via
GENESIS-Online directly, and true `ffcsv`/other `format=` values not used
here.)

**Status note:**
- `nation` and `state` levels are real and wired end-to-end
  (`loader.py:_fetch_missing`), using tables `12411-0001`/`12411-0010` and
  `constants.STATE_AGS`/`STATE_NUTS1` to filter/match regions.
- `district` has a real, live-verified table (`12411-0015`, confirmed
  against Munich above) but is **not** wired yet: GENESIS keys district
  rows by 5-digit AGS (Amtlicher Gemeindeschluessel) codes, and
  `geography.py`'s district `GEOID` is the GISCO NUTS3 code (e.g.
  `"DE212"`) — there's no fixed arithmetic AGS-to-NUTS3 mapping, only a
  real crosswalk (e.g. name-matching), which hasn't been built/verified
  yet. Requesting `level="district"` raises a specific `NotImplementedError`
  pointing at the TODO in `loader.py`, not fabricated data.
- `geography.py`/`levels.json` have real GISCO boundaries for
  nation/state/district, independent of credentials.
  statistical_district/census_block levels are defined in the schema for
  completeness but have no boundary source implemented.
- `municipality` (Gemeinde) is now wired too -- verified live 2026-08-22.
  GENESIS-Online's public catalogue has no Gemeinde-level population table
  under statistic 12411 (confirmed by exhausting `catalogue/tables2statistic`
  and `find/find`); instead, population and boundary both come from
  Eurostat/GISCO's LAU (Local Administrative Units) geojson
  (`LAU_RG_01M_2021_4326.geojson`, ~120MB, cached like NUTS), which already
  carries a real `POP_2021` field per feature -- no GENESIS account needed
  for this level. GISCO's `LAU_ID` for Germany is literally the 8-digit
  AGS code (verified against Flensburg 01001000, Kiel 01002000, Munich
  09162000, Stuttgart 08111000, Berlin 11000000, Hamburg 02000000), so no
  name-matching crosswalk is needed. Sum-to-parent check: Landkreis
  Starnberg's 15 real LAU municipalities (2021 vintage) summed to 136,610
  vs. GENESIS' district-level 138,488 (31.12.2022) for the same Kreis --
  +1.37% over ~1.5 years, in line with growth already verified for other
  districts. National total (11,001 municipalities, 2021 vintage):
  83,155,031, close to the independently verified 2022 national total
  (83,118,501) -- the small excess is consistent with the well-documented
  nationwide downward correction Zensus 2022 applied to pre-census
  registry-based population estimates (see `crosswalk.py`'s Hamburg/Berlin
  notes for the same pattern at district level).

  **Vintage caveat:** GISCO LAU's `POP_2021` is a 2021 registry-based
  estimate, not the district level's 31.12.2022 GENESIS/Zensus-corrected
  figure -- the two vintages are not perfectly comparable, and no GENESIS
  Gemeinde table exists to get an equivalent 2022 municipality figure.

See `api_into.txt` (note: typo'd filename, not `api_info.txt`; gitignored, not
committed) in this directory for the raw notes an earlier version of this
README was derived from.

## Gemeinde-level coverage beyond population (checked 2026-08-23, nothing new wired)

An outside, unverified lead suggested GENESIS-Online (`genesis.destatis.de`)
publishes Gemeinde-level tables for age structure, births/deaths,
marriages/divorces, migration, foreign population, households, employment,
businesses, building permits, housing, vehicles, and income tax (table
`73111`). This was checked live via real `find/find` catalogue searches
(same authenticated account already verified above) -- **none of it
panned out**; every category tested caps out above Gemeinde level in this
system, matching the pattern already documented for population (which is
why municipality population is sourced from GISCO LAU, not GENESIS).

Real `find/find` results, `category=tables`, checked for any hit whose
title contains "Gemeinden":

| Term (German) | Category | Total tables found | Gemeinde-titled tables |
|---|---|---|---|
| `Altersgruppen` (age groups) | Population by age | 100 (cap) | 0 |
| `Geburten` (births) | Births | 71 | 0 |
| `Gestorbene` (deaths) | Deaths | 20 | 0 |
| `Arbeitslose` (unemployment) | Labor market | 33 | 0 |
| `Wohnungsbestand` (housing stock) | Housing | 18 | 0 |
| `Wanderungen`/`Ausländer`/`Erwerbstätige` | Migration/foreign pop/employment | 0 | 0 (likely an umlaut-encoding artifact in the search term over HTTP form-encoding, not necessarily a real "no tables exist" signal -- not re-verified with escaped umlauts) |

**Income tax (`73111`) specifically**: `find/find` on both `Einkommensteuer`
and `73111` returned all seven real `73111-*` sub-tables
(`73111-0001` through `73111-0020`); every one of them is titled
`"... : Deutschland, Jahre"` (or `Bundesländer` for the related `71231`
municipal-share-of-income-tax family) -- national or state granularity
only, no Gemeinde variant under any `73111-*` code. This confirms the
outside source's own caveat: the standard published income tax tables do
**not** have a Gemeinde-level breakdown in GENESIS-Online.

**Conclusion**: consistent with the already-documented population finding,
GENESIS-Online's public catalogue appears to bottom out at Kreise
(district) for nearly all statistics -- true Gemeinde-level detail for
these categories, if it exists at all, would live in the separate
Regionalstatistik/regionaldatenbank system (`regionalstatistik.de`), which
is a different service from `genesis.destatis.de` and has **not** been
investigated or verified here. Nothing from this list has been wired into
`schema.json`/`loader.py`/`CS_transitLOS`'s `GERMANY_KEEP_COLUMNS` --
wiring any of it would require first verifying real Gemeinde-level tables
in that separate system, which is future work, not done.
