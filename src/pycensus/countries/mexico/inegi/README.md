# Mexico — INEGI (Instituto Nacional de Estadística y Geografía)

**Source:** https://www.inegi.org.mx/servicios/api_indicadores.html

**API del Banco de Indicadores v2.0** — REST API over indicators available at
national, state (`entidad federativa`), and municipal level.

- Indicator query:
  `https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/{IdIndicador}/{lang}/{geo}/{recent}/{source}/{version}/{token}?type={format}`
  - `{geo}`: `00` national, `99` state, `999` municipality
  - `{recent}`: `true` latest value only, `false` full historical series
  - `{format}`: `json` / `jsonp` / `xml`
- Metadata catalog query:
  `https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/{Catalogo}/{IdCatalogo}/{lang}/{source}/{token}?type={format}`

**Auth / token:** required. Get one by registering at:
https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx

Stored in `api_keys.json` under the `"inegi"` key (already populated).

**Data format:** JSON, JSONP, or XML.

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.
