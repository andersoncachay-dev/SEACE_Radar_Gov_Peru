from typing import Tuple, List
import pandas as pd
SEACE_PUBLIC_URL="https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
def search_seace_public(url=SEACE_PUBLIC_URL, keyword="satelital", objeto="", year="2026", version="Seace 3", mode="procedimientos") -> Tuple[pd.DataFrame, List[str]]:
    return pd.DataFrame(), ["Conector requests experimental deshabilitado en v6. Usa SEACE Público - navegador automático."]
