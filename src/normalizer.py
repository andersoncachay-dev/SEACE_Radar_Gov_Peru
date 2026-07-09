
import re
import pandas as pd

COLUMN_MAP = {
    "Nombre o Sigla de la Entidad": "entidad", "Entidad convocante": "entidad", "Entidad": "entidad",
    "N° RUC": "ruc_entidad", "Nomenclatura": "nomenclatura", "N° de Requerimiento": "nomenclatura",
    "Objeto de Contratación": "objeto", "Objeto de contratación": "objeto",
    "Descripción de Objeto": "descripcion", "Descripcion de Objeto": "descripcion", "Descripción del Objeto": "descripcion", "Descripcion del Objeto": "descripcion", "Descripción de Requerimiento": "descripcion",
    "Fecha y Hora de Publicacion": "fecha_publicacion", "Fecha de Publicación": "fecha_publicacion", "Fecha Publicación": "fecha_publicacion",
    "VR / VE / Cuantía de la contratación": "monto", "VR / VE / Cuantía de la contratacion": "monto", "Monto": "monto",
    "Moneda": "moneda", "Versión SEACE": "version_seace", "Version SEACE": "version_seace", "Departamento": "region", "Región": "region", "Estado": "estado", "URL": "url_detalle",
    "ocid": "nomenclatura", "main_ocid": "nomenclatura", "id": "nomenclatura", "main_id": "nomenclatura", "buyer.name": "entidad", "tender.procuringEntity.name": "entidad", "tender.mainProcurementCategory": "objeto", "tender.title": "descripcion", "tender.description": "descripcion", "tender.value.amount": "monto", "value.amount": "monto", "contracts.value.amount": "monto", "date": "fecha_publicacion", "tender.tenderPeriod.startDate": "fecha_publicacion", "tender.tenderPeriod.endDate": "fecha_presentacion", "tender.status": "estado", "uri": "url_detalle",
}
REQUIRED = ["entidad", "nomenclatura", "objeto", "descripcion", "monto", "region", "fecha_publicacion", "fecha_presentacion", "estado", "url_detalle"]

def limpiar_monto(x):
    if pd.isna(x): return 0.0
    s = str(x).replace("Soles", "").replace("PEN", "").replace("S/", "").replace("$", "").replace(",", "").strip()
    s = re.sub(r"[^0-9.\-]", "", s)
    try: return float(s) if s else 0.0
    except Exception: return 0.0

def _coalesce_duplicate_columns(df, col):
    matches = [c for c in df.columns if c == col]
    if len(matches) <= 1: return df
    base = df[matches[0]]
    for m in matches[1:]: base = base.combine_first(df[m])
    df = df.drop(columns=matches)
    df[col] = base
    return df

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns={c: COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    for col in set(COLUMN_MAP.values()):
        if list(df.columns).count(col) > 1: df = _coalesce_duplicate_columns(df, col)
    for col in REQUIRED:
        if col not in df.columns: df[col] = None
    text_candidates = [c for c in df.columns if any(k in c.lower() for k in ["description", "title", "objeto", "item", "name", "descripcion"])]
    if text_candidates:
        df["descripcion"] = df["descripcion"].combine_first(df[text_candidates].astype(str).agg(" | ".join, axis=1))
    df["monto"] = df["monto"].apply(limpiar_monto)
    for c in ["fecha_publicacion", "fecha_presentacion"]:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.tz_localize(None)
    today = pd.Timestamp.today().normalize()
    df["dias_presentacion"] = (df["fecha_presentacion"] - today).dt.days
    return df
