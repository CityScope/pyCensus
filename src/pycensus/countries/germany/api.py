"""API client for Destatis GENESIS-Online (Germany census/population data).

Technical aspects:
    See :mod:`pycensus.germany.destatis.README` for the full verification
    log. In short: GENESIS-Online is a real RESTful/JSON API (base
    ``https://genesis.destatis.de/genesisWS/rest/2020`` -- note: no
    "www-" prefix; the old ``www-genesis.destatis.de`` host 307-redirects
    here), and a registered account (username/password, or a personal API
    token used in place of username with password omitted, per GENESIS'
    "Anwenderdokumentation Webservice/API" v5.1) is required to
    authenticate. ``api_keys.json``'s ``"destatis_genesis"`` entry is a
    single token string, resolved here as ``(token, "")`` by
    :func:`resolve_genesis_credentials`.

    Verified live 2026-08-21: the token currently configured in
    ``api_keys.json`` DOES authenticate and DOES retrieve real data, once
    two things are fixed relative to the 2026-08-20 attempt: (1) the
    current host (above, no "www-" prefix -- the old host's REST path had
    started 307/302-redirecting to a generic "announcement" page, which is
    what made this look like a dead endpoint rather than a URL staleness
    issue), and (2) per GENESIS' real spec ("Zugangsdaten: Felder im
    HTTP-Header"), ``username``/``password`` must be sent as literal HTTP
    request headers, not as fields in the POST body -- the 2026-08-20
    attempt only tried body fields, HTTP Basic Auth, and a bearer header,
    never a plain ``username``/``password`` header pair, which is the one
    shape GENESIS actually documents and accepts. A real
    ``helloworld/logincheck`` call with the configured token as the
    ``username`` header (no password) returned
    ``{"Status":"Sie wurden erfolgreich an- und abgemeldet! ...",
    "Username":"<token>"}`` -- a real successful login, not the GAST
    guest-account rejection.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import requests

from ...api_keys import resolve_api_key
from . import constants


class GenesisCredentialsError(RuntimeError):
    """Raised when no GENESIS-Online credentials (token or username/password) are configured."""


def resolve_genesis_credentials(
    api_key: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve GENESIS-Online credentials.

    Resolution order:
        1. Explicit ``username``/``password`` args, if either is given.
        2. A personal API token, resolved via :func:`pycensus.api_keys.resolve_api_key`
           with key name :data:`pycensus.germany.constants.GENESIS_TOKEN_KEY`
           (``api_keys.json``'s ``"destatis_genesis"`` entry) or the
           :data:`pycensus.germany.constants.GENESIS_TOKEN_ENV` env var, or
           ``api_key`` if passed explicitly -- used as ``(token, "")`` per
           GENESIS' token-in-place-of-username convention.
        3. A real separate username/password pair, if configured under
           :data:`pycensus.germany.constants.GENESIS_USERNAME_KEY` /
           :data:`pycensus.germany.constants.GENESIS_PASSWORD_KEY`.

    Returns:
        ``(username, password)`` tuple to send to GENESIS-Online.

    Raises:
        GenesisCredentialsError: If none of the above resolve.
    """
    if username is not None or password is not None:
        return (username, password or "")

    token = resolve_api_key(constants.GENESIS_TOKEN_KEY, constants.GENESIS_TOKEN_ENV, api_key)
    if token:
        return (token, "")

    user = resolve_api_key(constants.GENESIS_USERNAME_KEY, constants.GENESIS_USERNAME_ENV)
    pw = resolve_api_key(constants.GENESIS_PASSWORD_KEY, constants.GENESIS_PASSWORD_ENV)
    if user and pw:
        return (user, pw)

    raise GenesisCredentialsError(
        "No Destatis GENESIS-Online credentials configured. Add a personal API token under "
        f"'{constants.GENESIS_TOKEN_KEY}' in pyCensus/api_keys.json (or the "
        f"{constants.GENESIS_TOKEN_ENV} env var), or a real username/password pair under "
        f"'{constants.GENESIS_USERNAME_KEY}'/'{constants.GENESIS_PASSWORD_KEY}'. Register an "
        "account at https://www.destatis.de/EN/Service/OpenData/api-webservice.html. Note: the "
        "token currently in api_keys.json was verified live (2026-08-20) to not authenticate "
        "for real data endpoints -- see pycensus.germany.destatis.README."
    )


def _post(namespace: str, endpoint: str, params: dict, api_key: Optional[str] = None) -> dict:
    """POST one real GENESIS-Online request and return the parsed JSON body.

    Per GENESIS' real spec ("2.1.3 Authentifizierung": "Zugangsdaten: Felder
    im HTTP-Header. Weitere Parameter: Felder im Request-Body."),
    credentials go in HTTP request headers, not the POST body -- everything
    else goes in the URL-encoded body. This is the piece the earlier
    (2026-08-20) verification attempt missed; see this module's docstring.

    Raises:
        GenesisCredentialsError: If no credentials are configured.
        requests.HTTPError: If GENESIS rejects the request (e.g. the
            documented ``Code: 15`` "not authorized" response).
    """
    username, password = resolve_genesis_credentials(api_key)
    url = f"{constants.GENESIS_BASE_URL}/{namespace}/{endpoint}"
    headers = {"username": username, "password": password}
    response = requests.post(url, headers=headers, data=params, timeout=60)
    response.raise_for_status()
    body = response.json()
    status = body.get("Status", {})
    if isinstance(status, dict) and status.get("Type") == "Error":
        raise requests.HTTPError(f"GENESIS-Online error {status.get('Code')}: {status.get('Content')}")
    return body


def fetch_table(
    table_code: str,
    area: Optional[str] = None,
    startyear: Optional[int] = None,
    endyear: Optional[int] = None,
    regionalvariable: Optional[str] = None,
    regionalkey: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Fetch one real GENESIS table (semicolon-delimited flat text) by table code.

    Args:
        table_code: GENESIS table code, e.g. ``"12411-0010"``.
        area: GENESIS ``area`` parameter (``"all"``/``"Alle"`` for the full
            table).
        startyear/endyear: Restrict to a single ``Stichtag``/``Jahr``
            column when equal -- verified live to return a single-year
            column instead of the table's full multi-year matrix.
        regionalvariable: The table's regional dimension code (e.g.
            ``"DLAND"`` for states, ``"KREISE"`` for districts).
        regionalkey: A region code (or ``"<prefix>*"`` wildcard) to filter
            to -- e.g. ``"09"`` (Bavaria's AGS code) filters
            ``12411-0010`` to one row, ``"09*"`` filters ``12411-0015`` to
            every district within Bavaria.

    Raises:
        GenesisCredentialsError: If no credentials are configured.
    """
    # Fails fast (before any network call) if credentials aren't configured.
    resolve_genesis_credentials(api_key)
    params = {"name": table_code, "area": area or "all"}
    if startyear is not None:
        params["startyear"] = str(startyear)
    if endyear is not None:
        params["endyear"] = str(endyear)
    if regionalvariable:
        params["regionalvariable"] = regionalvariable
    if regionalkey:
        params["regionalkey"] = regionalkey
    body = _post("data", "table", params, api_key)
    return body.get("Object", {}).get("Content", "")


def list_datasets(year: int = 2022) -> List[dict]:
    """List the Destatis datasets pyCensus knows about (metadata only, no network call)."""
    return [
        {
            "name": "Fortschreibung des Bevoelkerungsstandes (Population)",
            "code": "12411",
            "statistic": constants.GENESIS_POPULATION_STATISTIC,
            "population_variable": constants.GENESIS_POPULATION_VARIABLE,
            "tables": constants.GENESIS_POPULATION_TABLES,
            "year": year,
            "levels": ["nation", "state", "district"],
        },
    ]


__all__ = [
    "GenesisCredentialsError",
    "resolve_genesis_credentials",
    "fetch_table",
    "list_datasets",
]
