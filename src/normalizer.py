
import re
import pandas as pd
COLUMN_MAP={"Nombre o Sigla de la Entidad":"entidad","Fecha y Hora de Publicacion":"fecha_publicacion","Fecha y Hora de Publicación":"fecha_publicacion","Nomenclatura":"nomenclatura","Objeto de Contratación":"objeto","Descripción de Objeto":"descripcion","Descripcion de Objeto":"descripcion","VR / VE / Cuantía de la contratación":"monto","Moneda":"moneda","Versión SEACE":"version_seace","Version SEACE":"version_seace","Estado":"estado","URL":"url_detalle","Entidad":"entidad","Descripcion del Objeto":"descripcion","Descripción del Objeto":"descripcion","Departamento":"region","Región":"region","ocid":"nomenclatura","buyer.name":"entidad","tender.title":"descripcion","tender.description":"descripcion","tender.value.amount":"monto","tender.tenderPeriod.endDate":"fecha_presentacion","date":"fecha_publicacion","tender.status":"estado","uri":"url_detalle"}
REQUIRED=["entidad","nomenclatura","objeto","descripcion","monto","region","fecha_publicacion","fecha_presentacion","estado","url_detalle"]
def limpiar_monto(x):
    if pd.isna(x): return 0.0
    s=str(x).replace('Soles','').replace('PEN','').replace('S/','').replace('$','').replace(',','').strip(); s=re.sub(r"[^0-9.\-]", "", s)
    try: return float(s) if s else 0.0
    except Exception: return 0.0
def normalize_columns(df: pd.DataFrame)->pd.DataFrame:
    df=df.copy(); df=df.rename(columns={c:COLUMN_MAP.get(str(c).strip(),str(c).strip()) for c in df.columns})
    for col in REQUIRED:
        if col not in df.columns: df[col]=None
    df['monto']=df['monto'].apply(limpiar_monto)
    for c in ['fecha_publicacion','fecha_presentacion']:
        df[c]=pd.to_datetime(df[c], errors='coerce').dt.tz_localize(None)
    today=pd.Timestamp.today().normalize(); df['dias_presentacion']=(df['fecha_presentacion']-today).dt.days
    return df
