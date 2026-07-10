
from io import BytesIO
import pandas as pd
EXPORT_COLUMNS=["vigencia","estado_comercial","fecha_publicacion","consulta_inicio","consulta_fin","propuesta_inicio","propuesta_fin","buena_pro_inicio","buena_pro_fin","dias_para_consulta","dias_para_propuesta","ruc","entidad","sector","region","nomenclatura","objeto","descripcion","monto","moneda","version_seace","convocatoria_inicio","convocatoria_fin","registro_inicio","registro_fin","absolucion_inicio","absolucion_fin","integracion_inicio","integracion_fin","evaluacion_inicio","evaluacion_fin","direccion_legal","telefono_entidad","motivos_score","semaforo","prioridad","score","url_detalle","cronograma_texto"]
def _cronograma_sheet(df):
    rows=[]
    stages=[('Convocatoria','convocatoria_inicio','convocatoria_fin'),('Registro de participantes','registro_inicio','registro_fin'),('Formulación de consultas y observaciones','consulta_inicio','consulta_fin'),('Absolución de consultas y observaciones','absolucion_inicio','absolucion_fin'),('Integración de las Bases','integracion_inicio','integracion_fin'),('Presentación de propuestas','propuesta_inicio','propuesta_fin'),('Calificación y Evaluación de propuestas','evaluacion_inicio','evaluacion_fin'),('Otorgamiento de la Buena Pro','buena_pro_inicio','buena_pro_fin')]
    for _,r in df.iterrows():
        for etapa,ci,cf in stages:
            if ci in df.columns or cf in df.columns:
                rows.append({'nomenclatura':r.get('nomenclatura',''),'entidad':r.get('entidad',''),'etapa':etapa,'fecha_inicio':r.get(ci,''),'fecha_fin':r.get(cf,'')})
    return pd.DataFrame(rows)
def build_excel(oportunidades: pd.DataFrame)->bytes:
    output=BytesIO(); df=oportunidades.copy(); cols=[c for c in EXPORT_COLUMNS if c in df.columns]+[c for c in df.columns if c not in EXPORT_COLUMNS]; df=df[cols]
    if 'fecha_publicacion' in df.columns: df=df.sort_values(by='fecha_publicacion', ascending=False, na_position='last')
    entidades_cols=[c for c in ["ruc","entidad","sector","region","direccion_legal","telefono_entidad"] if c in df.columns]
    crm=df[entidades_cols].drop_duplicates() if entidades_cols else pd.DataFrame()
    resumen=pd.DataFrame({'indicador':['total_oportunidades','consultas_y_propuesta','solo_propuesta','evaluacion','cerrado','revisar','prioridad_A','prioridad_B','prioridad_C','monto_total'],'valor':[len(df),int((df.get('estado_comercial')=='Vigente para Consultas y Propuesta').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='Vigente sólo para Propuesta').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='En Evaluación').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='Cerrado').sum()) if 'estado_comercial' in df else 0,int((df.get('estado_comercial')=='Revisar').sum()) if 'estado_comercial' in df else 0,int((df.get('prioridad')=='A').sum()) if 'prioridad' in df else 0,int((df.get('prioridad')=='B').sum()) if 'prioridad' in df else 0,int((df.get('prioridad')=='C').sum()) if 'prioridad' in df else 0,float(df.get('monto',pd.Series(dtype=float)).sum()) if 'monto' in df else 0]})
    cron=_cronograma_sheet(df)
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Oportunidades'); resumen.to_excel(writer,index=False,sheet_name='Resumen'); crm.to_excel(writer,index=False,sheet_name='CRM_Entidades'); cron.to_excel(writer,index=False,sheet_name='Cronograma_Detalle')
    return output.getvalue()
