"""Worldwide (not country-specific) census-like data sources.

Unlike :mod:`pycensus.usa`, which holds sources scoped to a single country,
this package holds sources that cover the whole globe (e.g.
:mod:`pycensus.worldwide.worldpop`), keyed by whatever AOI/country the
caller passes in rather than by a fixed national geography.

Note:
    Named ``worldwide`` rather than ``global`` because ``global`` is a
    reserved Python keyword and cannot appear after a dot in an ``import``
    statement (``import pycensus.global.worldpop`` is a ``SyntaxError``),
    even though it is otherwise a legal filesystem/package directory name.
"""
