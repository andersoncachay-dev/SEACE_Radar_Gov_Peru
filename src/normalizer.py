
import re
import pandas as pd
COLUMN_MAP={"RUC":"ruc","Nombre o Sigla de la Entidad":"entidad","Entidad":"entidad","Fecha y Hora de Publicacion":"fecha_publicacion","Fecha y Hora de Publicación":"fecha_publicacion","Nomenclatura":"nomenclatura","Objeto de Contratación":"objeto","Descripción de Objeto":"descripcion","VR / VE / Cuantía de la contratación":"monto","Moneda":"moneda","Versión SEACE":"version_seace","url_detalle":"url_detalle","Departamento":"region","Región":"region","Estado Comercial":"estado_comercial","Vigencia":"vigencia","Dirección Legal":"direccion_legal","Teléfono de la Entidad":"telefono_entidad"}
COLUMN_MAP.update({"Objeto de Contratacion":"objeto","Descripcion de Objeto":"descripcion","VR / VE / Cuantia de la contratacion":"monto","Version SEACE":"version_seace","region":"region","Direccion Legal":"direccion_legal","Telefono de la Entidad":"telefono_entidad"})
REQUIRED=["vigencia","estado_comercial","ruc","entidad","nomenclatura","objeto","descripcion","monto","moneda","region","fecha_publicacion","url_detalle","direccion_legal","telefono_entidad","dias_para_consulta","dias_para_propuesta","cronograma_texto","convocatoria_inicio","convocatoria_fin","registro_inicio","registro_fin","consulta_inicio","consulta_fin","absolucion_inicio","absolucion_fin","integracion_inicio","integracion_fin","propuesta_inicio","propuesta_fin","evaluacion_inicio","evaluacion_fin","buena_pro_inicio","buena_pro_fin"]
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
    date_cols=['fecha_publicacion','convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']
    for c in date_cols:
        if c in df.columns:
            df[c]=pd.to_datetime(df[c], errors='coerce', dayfirst=True)
    return df
