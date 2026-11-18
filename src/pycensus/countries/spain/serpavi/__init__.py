"""SERPAVI (Sistema Estatal de Referencia del Precio del Alquiler de Vivienda, Ministerio de Vivienda) loader."""
from .loader import SERPAVI_XLSX_URL, load_attributes, municipality_crosswalk

__all__ = ["SERPAVI_XLSX_URL", "load_attributes", "municipality_crosswalk"]
