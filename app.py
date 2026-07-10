
import streamlit as st
import pandas as pd
from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.seace_browser_scraper import search_seace_public_browser, SEACE_PUBLIC_URL
from src.seace_public_scraper import search_seace_public
from src.oece_massive_connector import download_any_dataset, fetch_massive_by_params, DEFAULT_PORTAL_URL

st.set_page_config(page_title="SEACE Radar Gov Peru v7", layout="wide")
st.title("SEACE Radar Gov Peru v7 - Estado y Fechas")
st.caption("Extracción automática SEACE + estado comercial + fechas de presentación/Buena Pro + RUC preparado.")

source = st.sidebar.radio("Fuente de datos", [
    "SEACE Público - navegador automático",
    "SEACE Público - requests experimental",
    "Auto OECE - descarga construida",
    "URL pública directa",
    "Archivo local CSV/XLSX",
])
raw = pd.DataFrame(); diagnostics=[]

if source == "SEACE Público - navegador automático":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripción / palabra clave", "satelital")
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    headless = not st.sidebar.checkbox("Navegador visible", value=True)
    max_wait = st.sidebar.slider("Espera de resultados (segundos)", 5, 90, 30)
    enrich_details = st.sidebar.checkbox("Enriquecer con detalle (RUC y cronograma)", value=False)
    max_details = st.sidebar.slider("Máximo detalles a revisar", 1, 25, 10)
    if st.sidebar.button("Buscar con navegador"):
        with st.spinner("Consultando SEACE Público..."):
            raw, diagnostics = search_seace_public_browser(
                url=url,
                keyword=keyword,
                year=year,
                version=version,
                headless=headless,
                max_wait=max_wait,
                enrich_details=enrich_details,
                max_details=max_details,
            )

elif source == "SEACE Público - requests experimental":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripción / palabra clave", "satelital")
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Versión SEACE", ["Seace 3", "Seace 2", ""], index=0)
    if st.sidebar.button("Buscar con requests"):
        raw, diagnostics = search_seace_public(url=url, keyword=keyword, objeto="", year=year, version=version)

elif source == "Auto OECE - descarga construida":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    source_name = st.sidebar.text_input("source", "ocds")
    file_type = st.sidebar.selectbox("type", ["csv", "excel", "xlsx", "json", "jsonl"], index=0)
    year = st.sidebar.text_input("year", "2026")
    month = st.sidebar.text_input("month", "")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Conectar y descargar automáticamente"):
        raw, diagnostics = fetch_massive_by_params(base_url, source_name, file_type, year, month)
        if not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]

elif source == "URL pública directa":
    url = st.sidebar.text_input("URL directa CSV/XLSX/JSON/JSONL/GZ/ZIP/TAR.GZ")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Descargar URL") and url:
        raw, msg = download_any_dataset(url); diagnostics=[msg]
        if not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]

else:
    uploaded = st.sidebar.file_uploader("Carga CSV o Excel", type=["csv","xlsx","xls"])
    if uploaded:
        raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith('.csv') else pd.read_excel(uploaded, engine='openpyxl')

if diagnostics:
    with st.expander("Diagnóstico", expanded=True):
        for d in diagnostics: st.write(d)

if not raw.empty:
    df = enriquecer_oportunidades(normalize_columns(raw))
    st.subheader("Dashboard ejecutivo")
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("Registros", len(df))
    c2.metric("Vigentes", int((df.get('estado_comercial','')=='Vigente').sum()) if 'estado_comercial' in df else 0)
    c3.metric("Cerrados", int((df.get('estado_comercial','')=='Cerrado').sum()) if 'estado_comercial' in df else 0)
    c4.metric("Prioridad A", int((df['prioridad']=='A').sum()))
    c5.metric("Prioridad B", int((df['prioridad']=='B').sum()))
    c6.metric("Monto potencial", f"S/ {df['monto'].sum():,.0f}")

    st.subheader("Filtros")
    f1,f2,f3,f4,f5=st.columns(5)
    kw=f1.text_input("Palabra clave", "satelital")
    pri=f2.multiselect("Prioridad", ["A","B","C"], default=["A","B","C"])
    estado=f3.multiselect("Estado comercial", sorted(df['estado_comercial'].dropna().unique().tolist()) if 'estado_comercial' in df else [], default=[])
    sec=f4.multiselect("Sector", sorted(df['sector'].dropna().unique().tolist()), default=[])
    reg=f5.text_input("Región contiene")

    filtered=df.copy()
    if kw: filtered=filtered[filtered.astype(str).apply(lambda s: s.str.lower().str.contains(kw.lower(), na=False)).any(axis=1)]
    if pri: filtered=filtered[filtered['prioridad'].isin(pri)]
    if estado and 'estado_comercial' in filtered: filtered=filtered[filtered['estado_comercial'].isin(estado)]
    if sec: filtered=filtered[filtered['sector'].isin(sec)]
    if reg: filtered=filtered[filtered['region'].astype(str).str.lower().str.contains(reg.lower(), na=False)]

    cols=[c for c in [
        "vigencia","estado_comercial","fecha_presentacion","fecha_buena_pro","ruc","entidad","sector","region",
        "nomenclatura","objeto","descripcion","monto","moneda","version_seace","fecha_publicacion",
        "dias_presentacion","estado","motivos_score","url_detalle","semaforo","prioridad","score"
    ] if c in filtered.columns]

    st.subheader("Oportunidades")
    st.dataframe(filtered[cols], width='stretch')
    st.download_button("Descargar Excel ejecutivo", build_excel(filtered), file_name="SEACE_Radar_v7_Estado_Fechas.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Selecciona una fuente. Para automático usa SEACE Público - navegador automático.")
