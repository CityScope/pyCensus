"""Census-source packages of each country (the worldwide sources are in `pycensus.census.worldwide`).

Each submodule here is a country (or ``worldwide``, for globally-scoped
sources like WorldPop) implementing its own ``geography``/``api``/
``constants`` plus one or more source subpackages -- see
``docs/AGENT_GUIDE_NEW_CITY_OR_COUNTRY.md`` for the shape every
submodule follows.
"""

from pycensus.census.countries import (
    andorra,
    canada,
    chile,
    eu,
    euskadi,
    germany,
    israel,
    mexico,
    spain,
    taiwan,
    usa,
)

__all__ = [
    "andorra",
    "canada",
    "chile",
    "eu",
    "euskadi",
    "germany",
    "israel",
    "mexico",
    "spain",
    "taiwan",
    "usa",
]
