from io import BytesIO
import pandas as pd

EXPORT_COLUMNS = [
    "origen", "estado_operativo", "vigencia", "estado_comercial", "estado_portal",
    "fecha_publicacion", "consulta_inicio", "consulta_fin", "cotizacion_inicio", "cotizacion_fin",
    "propuesta_inicio", "propuesta_fin", "buena_pro_inicio", "buena_pro_fin",
    "dias_para_consulta", "dias_para_cotizacion", "dias_para_propuesta",
    "horas_para_consulta", "horas_para_cotizacion", "situacion_consulta", "situacion_cotizacion",
    "ruc", "entidad", "sector", "region", "nomenclatura", "codigo", "objeto", "descripcion", "area_usuaria",
    "monto", "moneda", "version_seace", "direccion_legal", "telefono_entidad",
    "requerimiento_pdf", "requerimiento_pdf_nombre", "requerimiento_pdf_local", "requerimiento_pdf_archivo",
    "motivos_score", "semaforo", "prioridad", "score", "url_detalle", "detalle_url", "cronograma_texto", "cronograma_debug", "detalle_texto"
]


def _cronograma_sheet(df):
    rows = []
    stages = [
        ("Consulta", "consulta_inicio", "consulta_fin"),
        ("Cotización", "cotizacion_inicio", "cotizacion_fin"),
        ("Cotización/Propuesta", "propuesta_inicio", "propuesta_fin"),
        ("Buena Pro", "buena_pro_inicio", "buena_pro_fin"),
        ("Convocatoria", "convocatoria_inicio", "convocatoria_fin"),
        ("Registro", "registro_inicio", "registro_fin"),
        ("Evaluación", "evaluacion_inicio", "evaluacion_fin"),
    ]
    for _, r in df.iterrows():
        for etapa, ci, cf in stages:
            if ci in df.columns or cf in df.columns:
                ini = r.get(ci, "")
                fin = r.get(cf, "")
                if pd.notna(ini) or pd.notna(fin):
                    rows.append({
                        "origen": r.get("origen", ""),
                        "nomenclatura": r.get("nomenclatura", r.get("codigo", "")),
                        "entidad": r.get("entidad", ""),
                        "etapa": etapa,
                        "fecha_inicio": ini,
                        "fecha_fin": fin,
                    })
    return pd.DataFrame(rows)


def build_excel(oportunidades: pd.DataFrame) -> bytes:
    output = BytesIO()
    df = oportunidades.copy()
    cols = [c for c in EXPORT_COLUMNS if c in df.columns] + [c for c in df.columns if c not in EXPORT_COLUMNS]
    df = df[cols]
    if "fecha_publicacion" in df.columns:
        df = df.sort_values(by="fecha_publicacion", ascending=False, na_position="last")
    entidades_cols = [c for c in ["ruc", "entidad", "sector", "region", "direccion_legal", "telefono_entidad", "origen"] if c in df.columns]
    crm = df[entidades_cols].drop_duplicates() if entidades_cols else pd.DataFrame()
    estado_operativo = df.get("estado_operativo", pd.Series(dtype=str)).astype(str) if "estado_operativo" in df else pd.Series(dtype=str)
    resumen_items = {
        "total_oportunidades": len(df),
        "seace_publico": int((df.get("origen") == "SEACE_PUBLICO").sum()) if "origen" in df else 0,
        "menor_8_uit": int((df.get("origen") == "MENOR_8_UIT").sum()) if "origen" in df else 0,
        "accionables": int(estado_operativo.isin(["Vence Hoy", "Vigente"]).sum()) if "estado_operativo" in df else int(df.get("estado_comercial", pd.Series(dtype=str)).astype(str).str.contains("Vigente", na=False).sum()) if "estado_comercial" in df else 0,
        "vence_hoy": int((estado_operativo == "Vence Hoy").sum()) if "estado_operativo" in df else 0,
        "vigentes": int((estado_operativo == "Vigente").sum()) if "estado_operativo" in df else 0,
        "en_evaluacion": int((estado_operativo == "En Evaluación").sum()) if "estado_operativo" in df else 0,
        "cerrados": int((estado_operativo == "Cerrado").sum()) if "estado_operativo" in df else int((df.get("estado_comercial") == "Cerrado").sum()) if "estado_comercial" in df else 0,
        "prioridad_A": int((df.get("prioridad") == "A").sum()) if "prioridad" in df else 0,
        "prioridad_B": int((df.get("prioridad") == "B").sum()) if "prioridad" in df else 0,
        "prioridad_C": int((df.get("prioridad") == "C").sum()) if "prioridad" in df else 0,
        "monto_total": float(pd.to_numeric(df.get("monto", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if "monto" in df else 0,
    }
    resumen = pd.DataFrame({"indicador": list(resumen_items.keys()), "valor": list(resumen_items.values())})
    cron = _cronograma_sheet(df)
    pdf_cols = [c for c in ["nomenclatura", "entidad", "requerimiento_pdf", "requerimiento_pdf_nombre", "requerimiento_pdf_local", "requerimiento_pdf_archivo"] if c in df.columns]
    pdfs = df[pdf_cols].copy() if pdf_cols else pd.DataFrame()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Oportunidades")
        resumen.to_excel(writer, index=False, sheet_name="Resumen")
        crm.to_excel(writer, index=False, sheet_name="CRM_Entidades")
        cron.to_excel(writer, index=False, sheet_name="Cronograma_Detalle")
        pdfs.to_excel(writer, index=False, sheet_name="Requerimientos_PDF")
    return output.getvalue()
