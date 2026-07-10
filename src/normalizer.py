
import re
import pandas as pd
COLUMN_MAP={"RUC":"ruc","N° RUC":"ruc","Nro RUC":"ruc","Número de RUC":"ruc","Nombre o Sigla de la Entidad":"entidad","Entidad":"entidad","Entidad convocante":"entidad","Fecha y Hora de Publicacion":"fecha_publicacion","Fecha y Hora de Publicación":"fecha_publicacion","Nomenclatura":"nomenclatura","Objeto de Contratación":"objeto","Descripción de Objeto":"descripcion","Descripcion de Objeto":"descripcion","VR / VE / Cuantía de la contratación":"monto","Moneda":"moneda","Versión SEACE":"version_seace","Version SEACE":"version_seace","Estado":"estado","URL":"url_detalle","Departamento":"region","Región":"region","Fecha Presentacion":"fecha_presentacion","Fecha Presentación":"fecha_presentacion","Fecha Buena Pro":"fecha_buena_pro","Fecha Fin":"fecha_fin","Estado Comercial":"estado_comercial","Vigencia":"vigencia"}
REQUIRED=["vigencia","estado_comercial","fecha_presentacion","fecha_buena_pro","fecha_fin","ruc","entidad","nomenclatura","objeto","descripcion","monto","moneda","region","fecha_publicacion","estado","url_detalle"]
def limpiar_monto(x):
    if pd.isna(x): return 0.0
    s=str(x).replace('Soles','').replace('PEN','').replace('S/','').replace('$','').replace(',','').replace('---','').strip(); s=re.sub(r"[^0-9.\-]", "", s)
    try: return float(s) if s else 0.0
    except Exception: return 0.0
def normalize_columns(df: pd.DataFrame)->pd.DataFrame:
    df=df.copy(); df=df.rename(columns={c:COLUMN_MAP.get(str(c).strip(),str(c).strip()) for c in df.columns})
    for col in REQUIRED:
        if col not in df.columns: df[col]="" if col not in ["monto"] else 0
    df['monto']=df['monto'].apply(limpiar_monto)
    for c in ['fecha_publicacion','fecha_presentacion','fecha_buena_pro','fecha_fin']:
        if c in df.columns:
            df[c]=pd.to_datetime(df[c], errors='coerce', dayfirst=True).dt.tz_localize(None)
    today=pd.Timestamp.today().normalize(); df['dias_presentacion']=(df['fecha_presentacion']-today).dt.days
    return df
