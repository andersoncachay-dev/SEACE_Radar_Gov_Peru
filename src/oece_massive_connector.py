import pandas as pd
from typing import Tuple, List
DEFAULT_PORTAL_URL="https://contratacionesabiertas.oece.gob.pe/api"
def download_any_dataset(url: str): return pd.DataFrame(), "Usa navegador SEACE o archivo local."
def fetch_massive_by_params(base_url=DEFAULT_PORTAL_URL, source='ocds', file_type='csv', year='2026', month='') -> Tuple[pd.DataFrame, List[str]]: return pd.DataFrame(), ["Conector OECE masivo en fallback."]
