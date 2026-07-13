from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades


def read_seace_export(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    engine = "xlrd" if file_path.suffix.lower() == ".xls" else "openpyxl"
    raw = pd.read_excel(file_path, engine=engine)
    if raw is None or raw.empty:
        return pd.DataFrame()
    normalized = normalize_columns(raw)
    enriched = enriquecer_oportunidades(normalized)
    enriched["origen"] = "SEACE_PUBLICO_EXCEL"
    if "url_detalle" not in enriched.columns:
        enriched["url_detalle"] = ""
    return enriched
