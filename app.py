
import streamlit as st
import pandas as pd

from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.oece_massive_connector import (
    DEFAULT_PORTAL_URL,
    list_massive_files,
    fetch_massive_by_params,
    download_any_dataset,
)

st.set_page_config(page_title="SEACE Radar Gov Peru v3", layout="wide")
st.title("SEACE Radar Gov Peru v3 - Automatico Masivo OECE")
st.caption("Conexion automatica a descargas masivas OECE/OCDS + scoring comercial para oportunidades publicas de conectividad.")

source = st.sidebar.radio(
    "Fuente de datos",
    [
        "Auto OECE - buscar archivos",
        "Auto OECE - descarga construida",
        "URL publica directa",
        "Archivo local CSV/XLSX",
    ],
)

raw = pd.DataFrame()
diagnostics = []

if source == "Auto OECE - buscar archivos":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    if st.sidebar.button("Buscar archivos masivos"):
        with st.spinner("Consultando listado de archivos masivos..."):
            files, diagnostics = list_massive_files(base_url)
            st.session_state["oece_files"] = files

    files = st.session_state.get("oece_files", pd.DataFrame())
    if not files.empty:
        st.sidebar.success(f"Archivos encontrados: {len(files)}")
        st.subheader("Archivos masivos detectados")
        st.dataframe(files, use_container_width=True)

        keyword_file = st.sidebar.text_input("Filtrar lista de archivos", "2026")
        filtered_files = files.copy()
        if keyword_file:
            mask = filtered_files.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_file.lower(), na=False)).any(axis=1)
            filtered_files = filtered_files[mask]

        if not filtered_files.empty:
            options = filtered_files.index.astype(str).tolist()
            selected = st.sidebar.selectbox("Indice de archivo a descargar", options)
            if st.sidebar.button("Descargar archivo seleccionado"):
                row = filtered_files.loc[int(selected)].to_dict()
                url = row.get("url") or row.get("download_url") or row.get("href") or row.get("link")
                if url:
                    with st.spinner("Descargando archivo seleccionado..."):
                        raw, msg = download_any_dataset(url)
                        diagnostics.append(msg)
                else:
                    st.warning("No encontré una columna URL en el listado. Usa descarga construida.")

elif source == "Auto OECE - descarga construida":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    source_name = st.sidebar.text_input("source", "ocds")
    file_type = st.sidebar.selectbox("type", ["csv", "excel", "xlsx", "json", "jsonl"], index=0)
    year = st.sidebar.text_input("year", "2026")
    month = st.sidebar.text_input("month", "")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Conectar y descargar automaticamente"):
        with st.spinner("Probando endpoint /file/{source}/{type}/{year}/{month}..."):
            raw, diagnostics = fetch_massive_by_params(
                base_url=base_url,
                source=source_name,
                file_type=file_type,
                year=year,
                month=month,
            )
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
    with st.expander("Diagnostico de conexion / procesamiento", expanded=True):
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
    keyword = c1.text_input("Palabra clave", value="satelital")
    prioridad = c2.multiselect("Prioridad", ["A", "B", "C"], default=["A", "B", "C"])
    sector = c3.multiselect("Sector", sorted(df["sector"].dropna().unique().tolist()), default=[])
    region = c4.text_input("Region contiene")

    filtered = df.copy()
    if keyword:
        mask = filtered.astype(str).apply(lambda s: s.str.lower().str.contains(keyword.lower(), na=False)).any(axis=1)
        filtered = filtered[mask]
    if prioridad:
        filtered = filtered[filtered["prioridad"].isin(prioridad)]
    if sector:
        filtered = filtered[filtered["sector"].isin(sector)]
    if region:
        filtered = filtered[filtered["region"].astype(str).str.lower().str.contains(region.lower(), na=False)]

    st.subheader("Oportunidades")
    show_cols = [
        c for c in [
            "semaforo", "prioridad", "score", "entidad", "sector", "region", "nomenclatura", "objeto",
            "descripcion", "monto", "fecha_publicacion", "fecha_presentacion", "dias_presentacion", "estado", "motivos_score", "url_detalle",
        ] if c in filtered.columns
    ]
    st.dataframe(filtered[show_cols], use_container_width=True)

    excel_bytes = build_excel(filtered)
    st.download_button(
        "Descargar Excel ejecutivo",
        excel_bytes,
        file_name="SEACE_Radar_v3_Oportunidades.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Selecciona una fuente en el panel izquierdo. Para pruebas automaticas usa Auto OECE - descarga construida o Auto OECE - buscar archivos.")
