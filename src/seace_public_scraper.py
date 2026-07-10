from typing import Tuple, List
import pandas as pd

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"


def search_seace_public(
    url: str = SEACE_PUBLIC_URL,
    keyword: str = "satelital",
    objeto: str = "",
    year: str = "2026",
    version: str = "Seace 3",
    mode: str = "procedimientos",
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Fallback del conector requests experimental.

    En la v5 el flujo principal debe ser:
    SEACE Publico - navegador automatico

    Este archivo existe para evitar:
    ModuleNotFoundError: No module named 'src.seace_public_scraper'
    cuando app.py importa el modulo experimental.
    """
    diagnostics = [
        "Conector requests experimental deshabilitado en v5.",
        "Usa la fuente: SEACE Publico - navegador automatico.",
        f"URL configurada: {url}",
        f"Keyword: {keyword}",
        f"Año: {year}",
        f"Version: {version}",
    ]
    return pd.DataFrame(), diagnostics
