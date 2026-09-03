"""Chile Casen SAE comunal poverty source (bulk .xlsx download, Ministerio Desarrollo Social y Familia).

Importing this module registers the ``gdf.casen_cl`` GeoDataFrame accessor
(see :mod:`pycensus.accessors`). Use :func:`load` to fetch data.

Source:
    https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
    pobreza-comunal/2022/Estimaciones_Tasa_Pobreza_Ingresos_Comunas_2022.xlsx
    https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
    pobreza-comunal/2022/Estimaciones_Indice_Pobreza_Multidimensional_Comunas_2022.xlsx
    (real Casen 2022 survey estimates, downscaled to comuna level via a
    Fay-Herriot small-area-estimation model -- see
    :mod:`pycensus.countries.chile.casen.api` module docstring for
    verification notes).
"""

from ....accessors import register_source_accessor
from .loader import load
from .schema import SCHEMA

register_source_accessor(SCHEMA)

__all__ = ["load", "SCHEMA"]
