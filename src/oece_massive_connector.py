
import gzip, json, tarfile, zipfile
from io import BytesIO
from typing import Tuple, List
import pandas as pd
import requests
DEFAULT_PORTAL_URL = "https://contratacionesabiertas.oece.gob.pe/api"
TIMEOUT=90

def _request(url): return requests.get(url, timeout=TIMEOUT, headers={"User-Agent":"SEACE-Radar-Gov-Peru/0.5"})
def _read_csv_bytes(content):
    for enc in ["utf-8","latin-1","cp1252"]:
        try: return pd.read_csv(BytesIO(content), encoding=enc, low_memory=False)
        except Exception: pass
    return pd.read_csv(BytesIO(content), low_memory=False)
def download_any_dataset(url: str) -> Tuple[pd.DataFrame,str]:
    r=_request(url); r.raise_for_status(); content=r.content; ctype=r.headers.get('content-type',''); lower=url.lower().split('?')[0]
    if lower.endswith('.gz'): content=gzip.decompress(content); lower=lower[:-3]
    if lower.endswith('.csv') or 'csv' in ctype.lower(): return _read_csv_bytes(content), f"CSV descargado: {url}"
    if lower.endswith('.xlsx') or lower.endswith('.xls') or 'spreadsheet' in ctype.lower(): return pd.read_excel(BytesIO(content), engine='openpyxl'), f"Excel descargado: {url}"
    try:
        tables=pd.read_html(BytesIO(content));
        if tables: return tables[0], f"HTML table descargada: {url}"
    except Exception: pass
    raise ValueError(f"Formato no reconocido: {ctype}")
def fetch_massive_by_params(base_url=DEFAULT_PORTAL_URL, source='ocds', file_type='csv', year='2026', month=''):
    diagnostics=[]; return pd.DataFrame(), ["Conector OECE masivo en modo fallback; usa URL directa o navegador SEACE."]
