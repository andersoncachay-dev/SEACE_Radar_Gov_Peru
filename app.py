
import streamlit as st
import pandas as pd

from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.oece_massive_connector import download_any_dataset, fetch_massive_by_params, DEFAULT_PORTAL_URL
from src.seace_public_scraper import SEACE_PUBLIC_URL, search_seace_public

st.set_page_config(page_title="SEACE Radar Gov Peru v4", layout="wide")
st.title("SEACE Radar Gov Peru v4 - Public Scraper")
st.caption("Busqueda automatica en SEACE Publico + descargas OECE/OCDS + scoring comercial.")

source = st.sidebar.radio(
    "Fuente de datos",
    [
        "SEACE Publico - busqueda automatica",
        "Auto OECE - descarga construida",
        "URL publica directa",
        "Archivo local CSV/XLSX",
    ],
)
raw = pd.DataFrame()
diagnostics = []

if source == "SEACE Publico - busqueda automatica":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("Descripcion / palabra clave", "satelital")
    objeto = st.sidebar.selectbox("Objeto", ["Servicio", "Bien", "Obra", "Consultoria de Obra", ""], index=0)
    year = st.sidebar.text_input("Año convocatoria", "2026")
    version = st.sidebar.selectbox("Version SEACE", ["Seace 3", "Seace 2", ""], index=0)
    mode = st.sidebar.selectbox("Tipo de consulta", ["procedimientos", "requerimientos", "expresiones_interes"], index=0)
    if st.sidebar.button("Buscar en SEACE Publico"):
        with st.spinner("Consultando Buscador Publico SEACE..."):
            raw, diagnostics = search_seace_public(
                url=url,
                keyword=keyword,
                objeto=objeto,
                year=year,
                version=version,
                mode=mode,
            )

elif source == "Auto OECE - descarga construida":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    source_name = st.sidebar.text_input("source", "ocds")
    file_type = st.sidebar.selectbox("type", ["csv", "excel", "xlsx", "json", "jsonl"], index=0)
    year = st.sidebar.text_input("year", "2026")
    month = st.sidebar.text_input("month", "")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Conectar y descargar automaticamente"):
        with st.spinner("Probando descarga masiva OECE..."):
            raw, diagnostics = fetch_massive_by_params(base_url, source_name, file_type, year, month)
        if not raw.empty and keyword_hint:
            mask = raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)
            raw = raw[mask]

elif source == "URL publica directa":
    url = st.sidebar.text_input("URL directa CSV/XLSX/JSON/JSONL/GZ/ZIP/TAR.GZ")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Descargar URL") and url:
        with st.spinner("Descargando dataset publico..."):
            raw, msg = download_any_dataset(url)
            diagnostics = [msg]
        if not raw.empty and keyword_hint:
            mask = raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)
            raw = raw[mask]

elif source == "Archivo local CSV/XLSX":
    uploaded = st.sidebar.file_uploader("Carga CSV o Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        if uploaded.name.lower().endswith(".csv"):
            raw = pd.read_csv(uploaded)
        else:
            raw = pd.read_excel(uploaded, engine="openpyxl")

if diagnostics:
    with st.expander("Diagnostico", expanded=True):
        for d in diagnostics:
            st.write(d)

if not raw.empty:
    df = normalize_columns(raw)
    df = enriquecer_oportunidades(df)

    st.subheader("Dashboard ejecutivo")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Registros", len(df))
    col2.metric("Prioridad A", int((df["prioridad"] == "A").sum()))
    col3.metric("Prioridad B", int((df["prioridad"] == "B").sum()))
    col4.metric("Monto potencial", f"S/ {df['monto'].sum():,.0f}")
    col5.metric("Cierran <=30 dias", int(((df["dias_presentacion"] <= 30) & (df["dias_presentacion"] >= 0)).sum()))

    st.subheader("Filtros")
    c1, c2, c3, c4 = st.columns(4)
    keyword_filter = c1.text_input("Palabra clave", value="satelital")
    prioridad = c2.multiselect("Prioridad", ["A", "B", "C"], default=["A", "B", "C"])
    sector = c3.multiselect("Sector", sorted(df["sector"].dropna().unique().tolist()), default=[])
    region = c4.text_input("Region contiene")

    filtered = df.copy()
    if keyword_filter:
        mask = filtered.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_filter.lower(), na=False)).any(axis=1)
        filtered = filtered[mask]
    if prioridad:
        filtered = filtered[filtered["prioridad"].isin(prioridad)]
    if sector:
        filtered = filtered[filtered["sector"].isin(sector)]
    if region:
        filtered = filtered[filtered["region"].astype(str).str.lower().str.contains(region.lower(), na=False)]

    st.subheader("Oportunidades")
    cols = [c for c in ["semaforo", "prioridad", "score", "entidad", "sector", "region", "nomenclatura", "objeto", "descripcion", "monto", "fecha_publicacion", "fecha_presentacion", "dias_presentacion", "estado", "motivos_score", "url_detalle"] if c in filtered.columns]
    st.dataframe(filtered[cols], use_container_width=True)

    excel_bytes = build_excel(filtered)
    st.download_button("Descargar Excel ejecutivo", excel_bytes, file_name="SEACE_Radar_v4_Oportunidades.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Selecciona una fuente. Para automatico, prueba SEACE Publico - busqueda automatica con keyword 'satelital'.")
