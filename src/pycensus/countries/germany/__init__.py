"""Germany census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    ``geography`` has real, keyless GISCO NUTS boundaries (nation/state/
    district). ``destatis`` (GENESIS-Online population) needs a real
    registered account -- see ``destatis/README.md``. ``ba`` (Bundesagentur
    fuer Arbeit jobs-by-workplace) is real and keyless -- see
    ``ba/loader.py``. ``ba_pendler`` (BA Pendlerstatistik: Wohnort/
    Arbeitsort/Einpendler/Auspendler per Gemeinde) is also real and
    keyless -- see ``ba_pendler/loader.py``.
"""

from . import api, ba, ba_pendler, constants, destatis, geography, utils

__all__ = ["api", "ba", "ba_pendler", "constants", "destatis", "geography", "utils"]
