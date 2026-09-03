"""Small stateless helpers shared by every Chile census source module.

Technical aspects:
    Resolves a region given as a name, or a 1/2-digit CUT code (INE's
    ArcGIS service returns REGION as an unpadded string, e.g. "8" not
    "08"), to this module's canonical zero-padded 2-digit code -- and back
    to the raw unpadded string the FeatureServer's `where` clause expects.
"""

from __future__ import annotations


def region_code(region) -> str:
    """Normalize a region name or CUT code (padded or not) to a canonical 2-digit code.

    Args:
        region: Region name (e.g. "Biobio", "Región del Biobío"), or a CUT
            code as `str` or `int` (e.g. "8", "08", 8).

    Returns:
        Canonical zero-padded 2-digit region code (e.g. "08").

    Raises:
        ValueError: If `region` does not resolve to a known Chile region.
    """
    from .constants import REGION_NAMES

    if isinstance(region, int):
        region = str(region)

    if isinstance(region, str):
        candidate = region.strip().zfill(2)
        if candidate in REGION_NAMES:
            return candidate

        # Try matching by name, ignoring accents/case/"Region de(l)" prefix noise.
        normalized = _normalize_name(region)
        for code, name in REGION_NAMES.items():
            if _normalize_name(name) == normalized or normalized in _normalize_name(name):
                return code

    raise ValueError(f"Unknown Chile region: '{region}'")


def region_api_code(region) -> str:
    """Return the unpadded numeric-string form INE's ArcGIS service stores in REGION.

    Args:
        region: Region name or CUT code (see :func:`region_code`).

    Returns:
        Unpadded region code as used in the FeatureServer's `REGION` field
        (e.g. "8", not "08").
    """
    return str(int(region_code(region)))


def _normalize_name(name: str) -> str:
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ñ": "n",
    }
    out = name.lower()
    for accented, plain in replacements.items():
        out = out.replace(accented.lower(), plain)
    out = out.replace("región", "region")
    for noise in ("region de la ", "region del ", "region de ", "region "):
        out = out.replace(noise, "")
    return out.strip()


__all__ = ["region_code", "region_api_code"]
