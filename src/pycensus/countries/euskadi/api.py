"""API client info for Euskadi's Eustat (Basque Statistics Office) Data Bank.

Technical aspects:
    Unlike Euskadi's geographic-cartography portals
    (``opendata.euskadi.eus``, ``eustat.eus/geoservicios/descargas.html``),
    which remain genuinely unreachable to a scripted client, Eustat's own
    census/statistics *data* API -- the "Banco de Datos" (BDE) -- IS real
    and reachable, keyless, no signup/token required:

    - List all tables: ``GET https://www.eustat.eus/bankupx/api/v1/{lang}/DB``
      (``{lang}`` = ``es``/``eu``/``en``)
    - Table metadata (variables, codes, value labels):
      ``GET .../DB/{table_id}``
    - Table data: ``POST .../DB/{table_id}`` with a JSON ``{"query": [...]}``
      body selecting variables/values (or ``{"query": []}`` for the whole
      table). Output format defaults to JSON-stat 1.2; CSV/CSV2/CSV3/XLSX
      are also available via ``"response": {"format": ...}``.

    Verified live 2026-08-20: ``GET
    https://www.eustat.eus/bankupx/api/v1/es/DB`` returns HTTP 200 with a
    real JSON array of 2,324 tables. An earlier pass of this module mistyped
    the path as ``bancopx`` (not the real ``bankupx``), got a 403, and
    wrongly recorded the whole API as unreachable -- that was corrected
    here. A ``POST`` query against table ``PX_010154_cepv1_ep06b.px`` for
    period ``2025/01/01`` returned real population figures: Gipuzkoa
    724,797, Bizkaia 1,155,733, Araba 337,680, C.A. de Euskadi total
    2,218,210 -- matching Eustat's own well-known published totals, and more
    current than the 2021 GISCO/LAU figures ``eustat/loader.py`` currently
    uses.

    This module currently only documents the API (see :data:`BASE_URL` and
    :func:`table_url`) -- ``eustat/loader.py`` still sources both geometry
    and population from Eurostat/GISCO's LAU 2021 GeoPackage (see
    ``euskadi/geography.py``'s module docstring), which also carries real,
    verified boundaries that this data-only API doesn't provide. Switching
    the loader to pull attribute data directly from this API (richer
    fields: households, age structure, Basque-language use, income;
    current-year vintage) is a real, documented follow-up, not implemented
    in this pass.

    Deeper follow-up pass, verified live 2026-08-22 -- does EUSTAT have
    finer-than-municipality data, and is it good enough to displace
    ``pycensus.spain``/INE (which already gives real, live-verified
    ``section``-level data for Gipuzkoa, 544 sections, 98.7-99.5% match
    against real municipal totals)? Short answer: EUSTAT genuinely does
    publish census-section-level data (same resolution as INE, real
    geometry included), but its own population totals at that resolution
    are measurably *less* accurate against real published municipal
    figures than what ``pycensus.spain`` already provides, so the
    ``euskadi`` module remains unwired and Gipuzkoa keeps routing through
    ``spain`` (see ``CS_transitLOS/code/city_config.py``).

    What was actually verified:

    - The prior 403/404s on ``opendata.euskadi.eus`` and
      ``eustat.eus/geoservicios`` were a bot-detection block on a missing
      browser ``User-Agent``, not missing data -- with a real UA string
      both return HTTP 200. ``www.geo.euskadi.eus`` (GeoEuskadi, the
      Basque Government's official geoportal -- a separate, real service
      from anything checked in the prior pass) is also live.
    - GeoEuskadi does publish a real, current census-section shapefile:
      ``GET
      https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/Unidades_estadisticas/SECCIONES_EUSTAT_5000_ETRS89.zip``
      -- HTTP 200, 6.36 MB, ``Content-Type: application/x-zip-compressed``,
      ``Last-Modified: 2026-07-03`` (i.e. more current than the GISCO LAU
      2021 vintage ``euskadi/geography.py`` uses today). Genuine
      ``sección censal``/``distrito`` boundaries at 1:5,000 scale, ETRS89,
      confirmed via the Basque Government's own boundary-files page
      (https://www.euskadi.eus/limites-estadisticos-comunidad-autonoma-del-pais-vasco/).
      Not wired up in this pass -- see "not implemented" note below.
    - EUSTAT's own systematically-searched Data Bank table catalogue
      (2,324 tables, same list as above) has **no** table keyed at
      district/section geography -- every ``distrito``/``sección
      censal``/``barrio`` hit in a keyword search over that catalogue is
      about something else entirely (rent by neighbourhood, foreign
      trade tariff sections, employment by activity section, etc.), none
      of it population-by-fine-geography.
    - The real section-level population tables live outside the BDE/
      bankupx system entirely, on EUSTAT's public "elementos" table
      pages (e.g.
      https://www.eustat.eus/elementos/ele0011400/poblacion-por-distritos-y-secciones-censales-de-gipuzkoa-segun-sexo-grupos-de-edad-y-nacionalidad-1/tbl0011434_c.html),
      each with a real downloadable CSV/XLSX
      (``/elementos/xls0011434_c.csv``). Fetched and parsed the Gipuzkoa
      one (537 sections, dated 01/01/2025): its grand total sums to
      exactly 724,797 -- matching the already-verified BDE territory
      total for Gipuzkoa given above -- so the file is real and
      internally consistent. But summed to municipality level it gives
      Donostia/San Sebastián = 183,388 and Irun = 60,665, against real
      published figures of ~188,487-189,093 (Donostia, INE/Wikipedia
      2024) and ~63,737 (Irun, INE January 2025) -- errors of roughly
      2.7-4.8%, worse than ``spain``/INE's already-verified 98.7-99.5%
      section-level match rate for the same two cities.
    - EUSTAT's own published Padrón-derived section data is therefore
      real but *not* more accurate than what ``spain``/INE already
      provides at the same resolution -- likely a reference-date/
      methodology difference between EUSTAT's and INE's post-revision
      Padrón processing, not a fabrication or scraping error (the
      Gipuzkoa-wide total ties out exactly to the independently-verified
      BDE figure).

    Conclusion: equal resolution (section-level), EUSTAT-sourced
    geometry that is even more current than GISCO's, but *worse*
    population accuracy than the already-wired ``spain`` module. Not a
    case for switching Gipuzkoa's routing back to ``euskadi`` -- ``spain``
    stays the better source. Wiring EUSTAT's section geometry/population
    into ``eustat/loader.py`` remains a real, documented, NOT-implemented
    follow-up if a future need specifically wants EUSTAT-sourced fields
    (Basque-language use, income, richer age/nationality breakdowns) at
    section level despite the lower population accuracy -- it would need
    to be clearly flagged as less accurate than ``spain`` if ever wired.

Source:
    https://es.eustat.eus/ayuda_banco_API.html
"""

from __future__ import annotations

BASE_URL = "https://www.eustat.eus/bankupx/api/v1"


def list_tables_url(lang: str = "es") -> str:
    """URL that lists every table in Eustat's Data Bank (verified: 2,324 tables, 2026-08-20)."""
    return f"{BASE_URL}/{lang}/DB"


def table_url(table_id: str, lang: str = "es") -> str:
    """URL for one table's metadata (``GET``) or data (``POST`` with a JSON ``{"query": [...]}`` body)."""
    return f"{BASE_URL}/{lang}/DB/{table_id}"


__all__ = ["BASE_URL", "list_tables_url", "table_url"]
