
from io import BytesIO
import pandas as pd
EXPORT_COLUMNS = ["semaforo", "prioridad", "score", "entidad", "sector", "region", "nomenclatura", "objeto", "descripcion", "monto", "fecha_publicacion", "fecha_presentacion", "dias_presentacion", "estado", "motivos_score", "url_detalle"]
def build_excel(oportunidades: pd.DataFrame) -> bytes:
    output = BytesIO(); df = oportunidades.copy()
    cols = [c for c in EXPORT_COLUMNS if c in df.columns] + [c for c in df.columns if c not in EXPORT_COLUMNS]
    df = df[cols]
    resumen = pd.DataFrame({"indicador": ["total_oportunidades", "prioridad_A", "prioridad_B", "prioridad_C", "monto_total"], "valor": [len(df), int((df.get("prioridad") == "A").sum()) if "prioridad" in df else 0, int((df.get("prioridad") == "B").sum()) if "prioridad" in df else 0, int((df.get("prioridad") == "C").sum()) if "prioridad" in df else 0, float(df.get("monto", pd.Series(dtype=float)).sum()) if "monto" in df else 0]})
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Oportunidades"); resumen.to_excel(writer, index=False, sheet_name="Resumen")
    return output.getvalue()
