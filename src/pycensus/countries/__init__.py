"""Country (and worldwide) census-source packages.

Each submodule here is a country (or ``worldwide``, for globally-scoped
sources like WorldPop) implementing its own ``geography``/``api``/
``constants`` plus one or more source subpackages -- see
``IMPLEMENTING_A_COUNTRY.md`` at the repo root for the shape every
submodule follows.
"""

from . import (
    andorra,
    canada,
    chile,
    euskadi,
    germany,
    israel,
    mexico,
    spain,
    taiwan,
    usa,
    worldwide,
)

__all__ = [
    "andorra",
    "canada",
    "chile",
    "euskadi",
    "germany",
    "israel",
    "mexico",
    "spain",
    "taiwan",
    "usa",
    "worldwide",
]
