"""Chile census sources: common geography plumbing plus one submodule per source.

Technical aspects:
    This package holds the functions shared by every Chile source directly
    (``api``, ``constants``, ``geography``, ``utils``), and one subpackage
    per data source (``ine``), each with its own
    :class:`~pycensus.schema.ColumnSchema`, fetch client, and loader that
    returns a GeoDataFrame ready for :meth:`geohierarchy.GeoHierarchy.add_level`.

Sources:
    - INE Chile Censo 2017 (Division Politico Administrativa y Censal, via
      the Esri Chile FeatureServer that republishes it):
      https://services.arcgis.com/r7t1P5pnkoOLRdhr/arcgis/rest/services/
      Divisi%C3%B3n_Pol%C3%ADtico_Administrativa_y_Censal/FeatureServer
    - Casen SAE comunal poverty estimates (Ministerio de Desarrollo Social
      y Familia, real bulk .xlsx download -- see
      :mod:`pycensus.countries.chile.casen.api` module docstring):
      https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/
      pobreza-comunal/2022/
    - SII comunal jobs-by-workplace statistics (Servicio de Impuestos
      Internos, real bulk .xlsx download -- see
      :mod:`pycensus.countries.chile.sii.api` module docstring):
      https://www.sii.cl/estadisticas/region/PUB_Reg_Com.xlsx
"""

from . import api, casen, constants, geography, ine, sii, utils

__all__ = ["api", "casen", "constants", "geography", "ine", "sii", "utils"]
