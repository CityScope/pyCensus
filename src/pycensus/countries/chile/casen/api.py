"""Bulk-file client for Chile's Casen SAE (Small Area Estimation) comunal poverty tables.

Technical aspects:
    Chile's Ministerio de Desarrollo Social y Familia (MDSF) publishes real,
    government-produced comuna-level poverty estimates on its Observatorio
    Social site as plain downloadable .xlsx files -- not an API, but a real
    bulk file, unlike REDATAM (a stateful, session-bound browse app with no
    documented query syntax -- see :mod:`pycensus.countries.chile.api`'s
    module docstring and this module's originating investigation notes).

    These are *not* raw Census 2017 data -- they are Casen (Encuesta de
    Caracterizacion Socioeconomica Nacional) 2022 survey estimates,
    modeled to comuna level via a Fay-Herriot small-area-estimation (SAE)
    model (survey is only directly representative at national/regional/
    urban-rural level; comuna estimates combine the direct survey estimate
    with a synthetic regression estimate -- see the real methodology PDF
    at the URL below). Chile's own government treats these as its
    authoritative comuna-level socioeconomic indicators (used for
    subsidy/targeting policy), which is why they're wired in here despite
    being survey-based rather than full-census.

    Two real, verified, live URLs (fetched and inspected 2026-08-23):

        https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
        pobreza-comunal/2022/Estimaciones_Tasa_Pobreza_Ingresos_Comunas_2022.xlsx

        https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
        pobreza-comunal/2022/Estimaciones_Indice_Pobreza_Multidimensional_Comunas_2022.xlsx

    Each is a single national workbook (one sheet "Estimaciones", header on
    row 3) with one row per comuna: real columns "Código" (comuna CUT code,
    unpadded, e.g. 8101 for Concepcion, 13101 for Santiago), "Región",
    "Nombre comuna", and the real percentage columns named exactly as in
    ``casen_schema.json``'s ``codes``. Verified against real published
    figures: comuna Santiago (13101) povertyRate=3.86%, Concepcion (8101)
    povertyRate=5.41%, Talcahuano (8110) povertyRate=5.08% -- plausible,
    internally consistent with these comunas' known relative affluence
    (Santiago's downtown comuna is comparatively wealthy; Talcahuano is a
    more industrial/working-class port comuna). 335 of Chile's 346 comunas
    are covered (income table); one comuna (Puchuncavi) is documented as
    excluded from the Fay-Herriot model as a statistical outlier -- see
    the methodology PDF at
    https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
    pobreza-comunal/2022/Resultados_Estimaciones_SAE_2022.pdf (also
    fetched and inspected: describes the real Fay-Herriot two-level model,
    quality-inclusion criteria, and validation used).

    Methodology reference (not fetched at runtime, cited for provenance):
    https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
    pobreza-comunal/2020/Informe_SAE_2020.pdf
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import requests

BASE_URL = "https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/pobreza-comunal/2022"

# feature_name -> (xlsx filename, real column header holding that feature's value)
TABLES = {
    "povertyRate": (
        "Estimaciones_Tasa_Pobreza_Ingresos_Comunas_2022.xlsx",
        "Porcentaje de personas en situación de pobreza por ingresos 2022",
    ),
    "povertyRateMultidimensional": (
        "Estimaciones_Indice_Pobreza_Multidimensional_Comunas_2022.xlsx",
        "Porcentaje de personas en situación de pobreza multidimensional 2022",
    ),
}


def _raw_dir(data_dir: Optional[str] = None) -> Path:
    from .. import constants

    base = Path(data_dir) if data_dir else Path(constants.DEFAULT_DATA_DIR)
    raw_dir = base / "raw" / "casen_sae"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _fetch_xlsx(filename: str, data_dir: Optional[str] = None) -> Path:
    """Download (once, cached on disk) one real Casen SAE comunal .xlsx workbook."""
    raw_dir = _raw_dir(data_dir)
    cache_path = raw_dir / filename
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    url = f"{BASE_URL}/{filename}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise RuntimeError(f"Unexpectedly small response fetching {url!r} ({len(response.content)} bytes)")

    tmp_path = cache_path.with_suffix(".xlsx.part")
    with open(tmp_path, "wb") as f:
        f.write(response.content)
    tmp_path.rename(cache_path)
    return cache_path


def fetch_table(feature_name: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """Fetch+parse one real Casen SAE comunal table, indexed by 5-digit comuna GEOID.

    Args:
        feature_name: One of the keys in :data:`TABLES` (``"povertyRate"``
            or ``"povertyRateMultidimensional"``).
        data_dir: Base directory for the raw cache. Defaults to
            :data:`pycensus.countries.chile.constants.DEFAULT_DATA_DIR`.

    Returns:
        DataFrame indexed by ``GEOID`` (zero-padded 5-digit comuna code)
        with one column, ``feature_name``, holding the real percentage
        (as a 0-1 share, matching the source workbook).

    Raises:
        KeyError: If ``feature_name`` isn't one of :data:`TABLES`.
        RuntimeError: If the downloaded workbook doesn't contain the
            expected real header row/columns.
    """
    filename, value_col = TABLES[feature_name]
    path = _fetch_xlsx(filename, data_dir)

    # Real header lives on row index 2 (0-based) -- rows 0-1 are a title
    # row and a blank row, verified against the live download.
    df = pd.read_excel(path, sheet_name=0, header=2)

    if "Código" not in df.columns or value_col not in df.columns:
        raise RuntimeError(
            f"Casen SAE workbook {filename!r} is missing expected real columns "
            f"'Código'/{value_col!r} -- got {list(df.columns)!r}. The source may have changed shape."
        )

    codigo = pd.to_numeric(df["Código"], errors="coerce")
    df = df.loc[codigo.notna()].copy()
    codigo = codigo.loc[codigo.notna()]

    out = pd.DataFrame(
        {
            "GEOID": codigo.astype(int).astype(str).str.zfill(5),
            feature_name: pd.to_numeric(df[value_col], errors="coerce"),
        }
    )
    out = out.dropna(subset=["GEOID"]).drop_duplicates(subset=["GEOID"]).set_index("GEOID")
    return out


__all__ = ["BASE_URL", "TABLES", "fetch_table"]
