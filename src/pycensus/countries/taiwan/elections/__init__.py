"""Taiwan Central Election Commission (中選會, db.cec.gov.tw) election results by village (村里) with H3 res-8 resampling.

Loaders: :func:`load_presidential`, :func:`load_legislative`, :func:`load_mayor`, :func:`load_council` -> ``ElectionResult(census, h3)``.
"""
from .loader import ElectionResult, load_presidential, load_legislative, load_mayor, load_council, load_election

__all__ = ["ElectionResult", "load_presidential", "load_legislative", "load_mayor", "load_council", "load_election"]
