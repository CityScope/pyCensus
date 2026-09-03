"""Small stateless helpers shared by every Taiwan census source module."""

from __future__ import annotations


def county_code(county_name_or_code: str) -> str:
    """Return the 5-digit MOI county/city code for a name, English name, or code.

    Args:
        county_name_or_code: County/city Chinese name (e.g. "臺北市"),
            English name (e.g. "Taipei City"), or 5-digit code.

    Returns:
        Five-digit MOI county/city code.

    Raises:
        ValueError: If the input does not resolve to a known Taiwan county/city.
    """
    from .constants import COUNTY_CODES, COUNTY_NAMES_EN

    if county_name_or_code in COUNTY_CODES:
        return county_name_or_code

    for code, name in COUNTY_CODES.items():
        if name == county_name_or_code:
            return code

    for code, name in COUNTY_NAMES_EN.items():
        if isinstance(county_name_or_code, str) and name.lower() == county_name_or_code.lower():
            return code

    raise ValueError(f"Unknown Taiwan county/city: '{county_name_or_code}'")


def roc_yyymm_to_year(yyymm: str) -> int:
    """Convert an ROC (Republic of China calendar) ``yyymm`` string to a Gregorian year.

    Args:
        yyymm: ROC year-month, e.g. ``"11407"`` (ROC year 114, month 07).

    Returns:
        Gregorian year, e.g. ``2025`` for ``"11407"`` (ROC year + 1911).
    """
    roc_year = int(str(yyymm)[:-2])
    return roc_year + 1911


__all__ = ["county_code", "roc_yyymm_to_year"]
