
from io import BytesIO
import pandas as pd
EXPORT_COLUMNS=["vigencia","estado_comercial","fecha_presentacion","fecha_buena_pro","fecha_fin","ruc","entidad","sector","region","nomenclatura","objeto","descripcion","monto","moneda","version_seace","fecha_publicacion","dias_presentacion","estado","motivos_score","semaforo","prioridad","score","url_detalle"]
def build_excel(oportunidades: pd.DataFrame)->bytes:
    output=BytesIO(); df=oportunidades.copy(); cols=[c for c in EXPORT_COLUMNS if c in df.columns]+[c for c in df.columns if c not in EXPORT_COLUMNS]; df=df[cols]
    entidades_cols=[c for c in ["ruc","entidad","sector","region"] if c in df.columns]
    crm=df[entidades_cols].drop_duplicates() if entidades_cols else pd.DataFrame()
    resumen=pd.DataFrame({'indicador':['total_oportunidades','vigentes','evaluacion','cerrados','prioridad_A','prioridad_B','prioridad_C','monto_total'],'valor':[len(df),int((df.get('estado_comercial')=='Vigente').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='En evaluación').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='Cerrado').sum()) if 'estado_comercial' in df else 0,int((df.get('prioridad')=='A').sum()) if 'prioridad' in df else 0,int((df.get('prioridad')=='B').sum()) if 'prioridad' in df else 0,int((df.get('prioridad')=='C').sum()) if 'prioridad' in df else 0,float(df.get('monto',pd.Series(dtype=float)).sum()) if 'monto' in df else 0]})
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Oportunidades'); resumen.to_excel(writer,index=False,sheet_name='Resumen'); crm.to_excel(writer,index=False,sheet_name='CRM_Entidades')
    return output.getvalue()
