import streamlit as st
import pandas as pd
import os
import re
import requests
from pathlib import Path
from urllib.parse import quote

from src.normalizer import normalize_columns
from src.scoring import enriquecer_oportunidades
from src.exporter import build_excel
from src.seace_browser_scraper import search_seace_public_browser, SEACE_PUBLIC_URL
from src.seace_public_scraper import search_seace_public
from src.oece_massive_connector import download_any_dataset, fetch_massive_by_params, DEFAULT_PORTAL_URL
from src.seace_menor8_scraper import search_menor8_browser, MENOR8_SEARCH_URL, MENOR8_AUTH_URL

st.set_page_config(page_title="SEACE Radar Gov Peru v10.6", layout="wide")

MENOR8_MODULE_ENABLED = os.getenv("ENABLE_MENOR8_MODULE", "false").lower() == "true"
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")

for key, default in {
    "raw_publico": None,
    "raw_menor8": None,
    "diagnostics_publico": [],
    "diagnostics_menor8": [],
    "df_final": None,
    "excel_bytes": None,
    "last_filter_key": None,
    "backend_token": "",
    "backend_last_error": "",
    "crm_authenticated": False,
    "crm_user_email": "",
    "crm_page": "Inicio",
    "crm_country": "Peru",
    "crm_peru_module": "SEACE Publico",
    "crm_active_run_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

@st.cache_data(show_spinner=False)
def generar_excel(df: pd.DataFrame) -> bytes:
    return build_excel(df)

def reset_resultados():
    for k in ["raw_publico", "raw_menor8", "diagnostics_publico", "diagnostics_menor8", "df_final", "excel_bytes", "last_filter_key"]:
        st.session_state[k] = None if k not in ["diagnostics_publico", "diagnostics_menor8"] else []

def backend_headers():
    token = st.session_state.get("backend_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}

def backend_request(method, path, **kwargs):
    try:
        response = requests.request(method, f"{BACKEND_API_URL}{path}", timeout=60, **kwargs)
        response.raise_for_status()
        st.session_state.backend_last_error = ""
        return response.json() if response.content else None
    except requests.RequestException as exc:
        detail = ""
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                detail = str(response.json())
            except Exception:
                detail = response.text[:500]
        st.session_state.backend_last_error = f"{type(exc).__name__}: {exc} {detail}".strip()
        return None

def backend_login(email, password):
    data = backend_request(
        "POST",
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if data and data.get("access_token"):
        st.session_state.backend_token = data["access_token"]
        st.session_state.backend_last_error = ""
        return True
    return False

def inject_corporate_css():
    st.markdown(
        """
        <style>
        :root {
            --gov-bg: #edf4fc;
            --gov-ink: #031225;
            --gov-muted: #405675;
            --gov-panel: #ffffff;
            --gov-line: #c9d9ee;
            --gov-navy: #031225;
            --gov-blue: #1559c7;
            --gov-cyan: #2d7df0;
            --gov-steel: #6f8db7;
            --gov-ice: #e8f2ff;
            --gov-sky: #cfe2ff;
            --gov-shadow: 0 8px 24px rgba(3, 18, 37, .10);
        }
        .stApp {
            background:
                radial-gradient(circle at 14% 0%, rgba(21, 89, 199, .16), transparent 30%),
                linear-gradient(180deg, #f8fbff 0%, var(--gov-bg) 44%, #f7faff 100%);
            color: var(--gov-ink);
        }
        .block-container {
            padding-top: 1.25rem;
            max-width: 1560px;
        }
        .corp-login-shell {
            min-height: calc(100vh - 80px);
            display: grid;
            grid-template-columns: minmax(320px, 1fr) minmax(360px, 520px);
            gap: 28px;
            align-items: center;
        }
        .corp-brand-panel {
            background: linear-gradient(135deg, #031225 0%, #082852 48%, #1559c7 110%);
            border-radius: 18px;
            padding: 44px;
            color: white;
            min-height: 520px;
            box-shadow: var(--gov-shadow);
            position: relative;
            overflow: hidden;
        }
        .corp-brand-panel:after {
            content: "";
            position: absolute;
            right: -90px;
            top: -90px;
            width: 320px;
            height: 320px;
            border: 42px solid rgba(255,255,255,.12);
            border-radius: 50%;
        }
        .corp-logo-mark {
            display: inline-flex;
            width: 46px;
            height: 46px;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            background: rgba(45,125,240,.22);
            border: 1px solid rgba(255,255,255,.22);
            font-weight: 800;
            margin-bottom: 28px;
        }
        .corp-brand-panel h1 {
            font-size: 52px;
            line-height: 1.02;
            letter-spacing: -0.03em;
            margin: 0 0 18px;
            text-wrap: balance;
        }
        .corp-brand-panel p {
            max-width: 64ch;
            color: rgba(255,255,255,.84);
            font-size: 17px;
            line-height: 1.65;
        }
        .corp-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 32px;
        }
        .corp-tag {
            border: 1px solid rgba(255,255,255,.24);
            background: rgba(255,255,255,.12);
            border-radius: 999px;
            padding: 9px 13px;
            font-weight: 700;
            font-size: 13px;
        }
        .corp-login-card, .corp-card, .corp-module, .corp-panel {
            background: var(--gov-panel);
            border: 1px solid var(--gov-line);
            border-radius: 14px;
            box-shadow: var(--gov-shadow);
        }
        .corp-login-card {
            padding: 34px;
        }
        .corp-login-card h2 {
            margin: 0 0 8px;
            font-size: 28px;
            letter-spacing: -0.02em;
        }
        .corp-login-card p {
            color: var(--gov-muted);
            margin-bottom: 24px;
        }
        .corp-shell-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 14px 18px;
            background: rgba(255,255,255,.92);
            border: 1px solid var(--gov-line);
            border-radius: 16px;
            box-shadow: var(--gov-shadow);
            margin-bottom: 18px;
        }
        .corp-brand-row {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .corp-mark {
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 10px;
            color: white;
            background: linear-gradient(135deg, #031225, #1559c7 72%, #2d7df0);
            font-weight: 900;
        }
        .corp-brand-title {
            font-weight: 850;
            font-size: 18px;
        }
        .corp-brand-sub {
            color: var(--gov-muted);
            font-size: 12px;
            margin-top: 2px;
        }
        .corp-user {
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--gov-muted);
            font-size: 13px;
        }
        .corp-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: grid;
            place-items: center;
            background: var(--gov-ice);
            color: var(--gov-blue);
            font-weight: 800;
        }
        .corp-hero {
            background: linear-gradient(135deg, #031225 0%, #082852 58%, #1559c7 118%);
            border-radius: 18px;
            color: white;
            padding: 30px;
            margin: 12px 0 18px;
            box-shadow: var(--gov-shadow);
        }
        .corp-hero h1 {
            font-size: 34px;
            line-height: 1.15;
            letter-spacing: -0.03em;
            margin: 0 0 10px;
            text-wrap: balance;
        }
        .corp-hero p {
            color: rgba(255,255,255,.82);
            margin: 0;
            max-width: 78ch;
            line-height: 1.55;
        }
        .corp-kpi-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(160px, 1fr));
            gap: 12px;
            margin: 14px 0 18px;
        }
        .corp-kpi {
            background: white;
            border: 1px solid var(--gov-line);
            border-radius: 12px;
            padding: 16px;
        }
        .corp-kpi label {
            display: block;
            color: var(--gov-muted);
            font-size: 12px;
            margin-bottom: 8px;
            font-weight: 700;
        }
        .corp-kpi strong {
            font-size: 28px;
            letter-spacing: -0.03em;
        }
        .corp-kpi span {
            display: block;
            color: var(--gov-muted);
            font-size: 12px;
            margin-top: 6px;
        }
        .corp-module-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(280px, 1fr));
            gap: 14px;
            margin: 16px 0;
        }
        .corp-module {
            padding: 18px;
            min-height: 160px;
        }
        .corp-module h3 {
            margin: 0 0 8px;
            font-size: 20px;
        }
        .corp-module p {
            color: var(--gov-muted);
            line-height: 1.5;
            margin: 0 0 14px;
        }
        .corp-status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border-radius: 999px;
            padding: 7px 10px;
            background: var(--gov-ice);
            color: #0b3f8f;
            font-size: 12px;
            font-weight: 800;
        }
        .corp-status.pending {
            background: #edf3ff;
            color: #4b6388;
        }
        .corp-panel {
            padding: 18px;
            margin-top: 14px;
        }
        .corp-panel-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
        }
        .corp-panel-title h2, .corp-panel-title h3 {
            margin: 0;
            letter-spacing: -0.02em;
        }
        .corp-alert-row {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .corp-callout {
            border: 1px solid #b7cdf0;
            background: #eef6ff;
            color: #0a3978;
            border-radius: 12px;
            padding: 14px 16px;
            margin: 12px 0;
            font-weight: 650;
        }
        div[data-testid="stButton"] > button {
            border-radius: 10px;
            border: 1px solid #c7d5e8;
            background: #ffffff;
            color: #0c1f3d;
            font-weight: 750;
            min-height: 42px;
            transition: background .16s ease, border-color .16s ease, transform .16s ease;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: var(--gov-blue);
            background: #f3f8ff;
            transform: translateY(-1px);
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: var(--gov-blue);
            color: white;
            border-color: var(--gov-blue);
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid var(--gov-line);
            border-radius: 12px;
            padding: 12px 14px;
        }
        div[data-testid="stAlert"] {
            border-radius: 12px;
            border-color: #b7cdf0;
            background: #eef6ff !important;
        }
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
            color: #07346f;
        }
        div[data-testid="stRadio"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stTextInput"] label {
            color: #0c1f3d;
            font-weight: 700;
        }
        @media (max-width: 900px) {
            .corp-login-shell, .corp-module-grid, .corp-alert-row {
                grid-template-columns: 1fr;
            }
            .corp-brand-panel {
                min-height: auto;
                padding: 28px;
            }
            .corp-brand-panel h1 {
                font-size: 36px;
            }
            .corp-kpi-grid {
                grid-template-columns: repeat(2, minmax(140px, 1fr));
            }
            .corp-shell-header {
                align-items: flex-start;
                flex-direction: column;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            * {
                transition: none !important;
                animation: none !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_login_page():
    st.markdown(
        """
        <div class="corp-login-shell">
          <section class="corp-brand-panel">
            <div class="corp-logo-mark">R</div>
            <h1>RODAR GovRadar CRM para procesos de gobierno</h1>
            <p>Radar comercial para detectar oportunidades de conectividad, internet satelital y telecomunicaciones en portales publicos de Peru y Chile.</p>
            <div class="corp-tags">
              <span class="corp-tag">Peru operativo</span>
              <span class="corp-tag">Chile en desarrollo</span>
              <span class="corp-tag">Alertas email y WhatsApp</span>
              <span class="corp-tag">Documentos y trazabilidad</span>
            </div>
          </section>
          <section class="corp-login-card">
            <h2>Iniciar sesion</h2>
            <p>Accede al tablero corporativo, perfiles de busqueda y reglas de alerta.</p>
        """,
        unsafe_allow_html=True,
    )
    email = st.text_input("Correo corporativo", "admin@seace-radar.local", key="crm_login_email")
    password = st.text_input("Password", "Admin12345", type="password", key="crm_login_password")
    c1, c2 = st.columns([1, 1])
    remember = c1.checkbox("Recordarme", value=True)
    if c2.button("Acceder", type="primary", width="stretch"):
        if backend_login(email, password):
            st.session_state.crm_authenticated = True
            st.session_state.crm_user_email = email
            st.session_state.crm_page = "Inicio"
            st.rerun()
        else:
            st.error("No se pudo iniciar sesion. Verifica que el backend este activo y las credenciales sean correctas.")
    st.caption("Admin local: admin@seace-radar.local / Admin12345")
    st.markdown("</section></div>", unsafe_allow_html=True)

def _set_crm_page(page: str):
    st.session_state.crm_page = page

def _set_crm_country(country: str):
    st.session_state.crm_country = country

def render_crm_header():
    initials = "".join([part[:1] for part in (st.session_state.crm_user_email or "Admin").split("@")[0].split(".")])[:2].upper()
    st.markdown(
        f"""
        <div class="corp-shell-header">
          <div class="corp-brand-row">
            <div class="corp-mark">R</div>
            <div>
              <div class="corp-brand-title">RODAR GovRadar CRM</div>
              <div class="corp-brand-sub">Radar de procesos publicos para Peru y Chile</div>
            </div>
          </div>
          <div class="corp-user">
            <span>{st.session_state.crm_country}</span>
            <div class="corp-avatar">{initials}</div>
            <span>{st.session_state.crm_user_email or "admin"}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    nav = st.columns([1, 1, 1, 1, 1, 1, 1, 1])
    pages = ["Inicio", "Oportunidades", "Alertas", "Documentos", "Usuarios", "Perfiles", "Vista tecnica"]
    for col, page in zip(nav, pages):
        if col.button(page, key=f"crm_nav_{page}", width="stretch"):
            _set_crm_page(page)
            st.rerun()
    if nav[-1].button("Salir", key="crm_logout", width="stretch"):
        st.session_state.crm_authenticated = False
        st.session_state.backend_token = ""
        st.rerun()
    c1, c2 = st.columns([1, 1])
    if c1.button("Modulo Peru", key="crm_country_peru", type="primary" if st.session_state.crm_country == "Peru" else "secondary", width="stretch"):
        _set_crm_country("Peru")
        st.rerun()
    if c2.button("Modulo Chile", key="crm_country_chile", type="primary" if st.session_state.crm_country == "Chile" else "secondary", width="stretch"):
        _set_crm_country("Chile")
        st.rerun()

def render_kpi_cards(stats: dict):
    total = int(stats.get("total") or 0)
    priority_a = int((stats.get("by_priority") or {}).get("A", 0))
    vigentes = int(stats.get("vigentes") or 0)
    cerrados = int(stats.get("cerrados") or 0)
    amount = float(stats.get("total_amount") or 0)
    st.markdown(
        f"""
        <div class="corp-kpi-grid">
          <div class="corp-kpi"><label>Procesos radar</label><strong>{total:,}</strong><span>Total persistido</span></div>
          <div class="corp-kpi"><label>Prioridad A</label><strong>{priority_a:,}</strong><span>Requiere revision comercial</span></div>
          <div class="corp-kpi"><label>Vigentes</label><strong>{vigentes:,}</strong><span>Con ventana activa</span></div>
          <div class="corp-kpi"><label>Cerrados</label><strong>{cerrados:,}</strong><span>Seguimiento historico</span></div>
          <div class="corp-kpi"><label>Monto detectado</label><strong>S/ {amount:,.0f}</strong><span>Valor referencial acumulado</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def get_backend_opportunities():
    rows = backend_request("GET", "/opportunities", headers=backend_headers()) or []
    return opportunities_to_dataframe(rows)

def parse_run_diagnostics(run: dict) -> dict:
    diagnostics = str((run or {}).get("diagnostics") or "")
    reviewed = applied = requested = None
    match = re.search(r"Cronogramas revisados:\s*(\d+)/(\d+);\s*aplicados correctamente:\s*(\d+)", diagnostics)
    if match:
        reviewed = int(match.group(1))
        requested = int(match.group(2))
        applied = int(match.group(3))
    config_match = re.search(r"max_detalles=(\d+)", diagnostics)
    configured = int(config_match.group(1)) if config_match else None
    return {"reviewed": reviewed, "requested": requested, "applied": applied, "configured": configured}


def render_run_progress(run_id: int | None = None):
    run = None
    if run_id:
        run = backend_request("GET", f"/runs/{int(run_id)}", headers=backend_headers())
    if not run:
        runs = backend_request("GET", "/runs", headers=backend_headers()) or []
        run = runs[0] if runs else None
    if not run:
        return

    status = str(run.get("status") or "queued")
    status_map = {
        "queued": (0.15, "En cola"),
        "running": (0.55, "Ejecutando"),
        "completed": (1.0, "Completado"),
        "failed": (1.0, "Fallido"),
    }
    progress, label = status_map.get(status, (0.25, status))
    details = parse_run_diagnostics(run)

    st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h3>Estado de ejecucion</h3></div>', unsafe_allow_html=True)
    st.progress(progress, text=f"{label} | Run #{run.get('id')} | Fuente: {run.get('source')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado", status)
    c2.metric("Procesos guardados", int(run.get("rows_found") or 0))
    c3.metric("Detalles configurados", details.get("configured") if details.get("configured") is not None else "-")
    if details.get("reviewed") is not None:
        c4.metric("Detalles revisados", f"{details['reviewed']}/{details['requested']}", f"{details['applied']} aplicados")
    else:
        c4.metric("Detalles revisados", "Pendiente" if status in ["queued", "running"] else "-")
    if run.get("error_message"):
        st.error(run.get("error_message"))
    if st.button("Actualizar estado de ejecucion", key=f"refresh_run_{run.get('id')}"):
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def render_country_modules():
    st.markdown(
        """
        <div class="corp-module-grid">
          <div class="corp-module">
            <h3>Peru | SEACE Radar</h3>
            <p>Modulo Peru con selector para SEACE Publico, Contratos Menores a 8 UIT y ejecucion combinada cuando ambos conectores esten estables.</p>
            <span class="corp-status">Operativo</span>
          </div>
          <div class="corp-module">
            <h3>Chile | Mercado Publico Radar</h3>
            <p>Modulo preparado para integrar busquedas de procesos chilenos por conectividad, satelital, internet y telecomunicaciones.</p>
            <span class="corp-status pending">Por desarrollar</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_crm_home(stats: dict):
    st.markdown(
        """
        <section class="corp-hero">
          <h1>Centro de control comercial para procesos con gobierno</h1>
          <p>Monitorea oportunidades, prioriza procesos accionables y configura alertas automaticas para que el equipo llegue antes a cada convocatoria relevante.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    render_kpi_cards(stats)
    render_country_modules()
    st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Flujo operativo</h2></div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("1. Captura", "SEACE", "Peru activo")
    f2.metric("2. Calificacion", "A/B/C", "Score comercial")
    f3.metric("3. Alerta", "Email/WA", "Reglas configurables")
    f4.metric("4. Accion", "PDF/Excel", "Documentos y exportacion")
    st.markdown("</div>", unsafe_allow_html=True)

def render_crm_opportunities():
    if st.session_state.crm_country == "Chile":
        st.markdown('<div class="corp-callout">Chile esta preparado como modulo CRM, pendiente de desarrollar conectores para Mercado Publico y fuentes chilenas.</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([
            {"pais": "Chile", "keyword": "internet satelital", "estado": "Conector pendiente", "fuente": "Mercado Publico"},
            {"pais": "Chile", "keyword": "conectividad", "estado": "Conector pendiente", "fuente": "ChileCompra"},
        ]), width="stretch", hide_index=True)
        return
    df = get_backend_opportunities()
    st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Radar de oportunidades Peru</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="corp-callout">Elige que fuente quieres ejecutar para Peru. SEACE Publico esta operativo; Contratos Menores a 8 UIT esta visible para el flujo, pero queda pendiente de estabilizacion.</div>', unsafe_allow_html=True)
    module_options = ["SEACE Publico", "Contratos Menores a 8 UIT", "Ambos modulos"]
    selected_module = st.radio(
        "Modulo a ejecutar",
        module_options,
        index=module_options.index(st.session_state.get("crm_peru_module", "SEACE Publico")),
        horizontal=True,
        key="crm_peru_module_radio",
    )
    st.session_state.crm_peru_module = selected_module
    a1, a2, a3 = st.columns([1.2, 1, 1])
    kw = a1.text_input("Keyword", "satelital")
    priority = a2.selectbox("Prioridad", ["Todas", "A", "B", "C"])
    status = a3.text_input("Estado contiene", "")

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
    max_results = b1.number_input("Max resultados", min_value=1, max_value=150, value=25, step=5)
    enrich_details = b2.checkbox("Leer detalle", value=False, help="Abre la ficha de cada proceso para validar cronograma, estado y datos adicionales.")
    max_details = b3.number_input("Procesos a revisar detalle", min_value=0, max_value=int(max_results), value=min(10, int(max_results)), step=1, disabled=not enrich_details)
    run_label = {
        "SEACE Publico": "Ejecutar SEACE Publico",
        "Contratos Menores a 8 UIT": "Ejecutar Menores 8 UIT",
        "Ambos modulos": "Ejecutar ambos modulos",
    }[selected_module]
    menores_selected = selected_module in ["Contratos Menores a 8 UIT", "Ambos modulos"]
    disabled_run = selected_module == "Contratos Menores a 8 UIT" and not MENOR8_MODULE_ENABLED
    if b4.button(run_label, type="primary", width="stretch", disabled=disabled_run):
        if selected_module in ["SEACE Publico", "Ambos modulos"]:
            run = backend_request(
                "POST",
                "/runs/start",
                headers=backend_headers(),
                json={
                    "source": "seace_public_browser",
                    "keyword": kw,
                    "year": "2026",
                    "version": "Seace 3",
                    "max_results": int(max_results),
                    "max_details": int(max_details),
                    "enrich_details": bool(enrich_details),
                },
            )
            if run:
                st.session_state.crm_active_run_id = run.get("id")
                st.success(f"SEACE Publico iniciado: #{run.get('id')}. Revisa la barra de ejecucion abajo.")
        if menores_selected:
            st.warning("Contratos Menores a 8 UIT aun no esta habilitado en backend productivo. Lo dejamos como seleccion visible para el siguiente sprint.")
    if disabled_run:
        st.info("Seleccionaste Contratos Menores a 8 UIT. El modulo esta deshabilitado temporalmente mientras corregimos el scraper.")

    render_run_progress(st.session_state.get("crm_active_run_id"))
    if not df.empty:
        filtered = df.copy()
        if kw:
            filtered = filtered[filtered.astype(str).apply(lambda s: s.str.lower().str.contains(kw.lower(), na=False)).any(axis=1)]
        if priority != "Todas" and "priority" in filtered:
            filtered = filtered[filtered["priority"] == priority]
        if status and "estado_operativo" in filtered:
            filtered = filtered[filtered["estado_operativo"].astype(str).str.lower().str.contains(status.lower(), na=False)]
        visible = [c for c in ["priority", "score", "estado_operativo", "fecha_publicacion", "propuesta_fin", "entidad", "nomenclatura", "descripcion", "monto", "url_detalle"] if c in filtered.columns]
        st.caption(f"Mostrando {len(filtered)} oportunidades filtradas")
        st.dataframe(filtered[visible], width="stretch", hide_index=True)
        st.download_button("Descargar Excel filtrado", data=generar_excel(filtered), file_name="GovRadar_Peru_Oportunidades.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Aun no hay oportunidades en backend. Ejecuta el radar Peru para poblar la base.")
    st.markdown("</div>", unsafe_allow_html=True)

def render_crm_alerts():
    st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Alertas automaticas</h2></div>', unsafe_allow_html=True)
    st.markdown('<div class="corp-callout">Palabras objetivo iniciales: satelital, conectividad, internet satelital, telecomunicaciones.</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    name = c1.text_input("Nombre regla", f"{st.session_state.crm_country} prioridad A")
    channel = c2.selectbox("Canal", ["email", "whatsapp", "message"])
    destination = c3.text_input("Destino", "equipo.comercial@empresa.com" if channel == "email" else "+51")
    min_priority = c4.selectbox("Prioridad minima", ["A", "B", "C"])
    if st.button("Crear regla de alerta", type="primary"):
        rule = backend_request(
            "POST",
            "/alerts/rules",
            headers=backend_headers(),
            json={"name": name, "channel": channel, "destination": destination, "min_priority": min_priority, "hours_before_deadline": 48, "is_active": True},
        )
        if rule:
            st.success(f"Regla creada: {rule.get('name')}")
    a1, a2 = st.columns(2)
    if a1.button("Evaluar oportunidades", width="stretch"):
        created = backend_request("POST", "/alerts/evaluate", headers=backend_headers())
        st.success(f"Alertas generadas: {len(created or [])}")
    if a2.button("Enviar pendientes", width="stretch"):
        sent = backend_request("POST", "/alerts/send-pending", headers=backend_headers())
        st.success(f"Alertas procesadas: {len(sent or [])}")
    rules = backend_request("GET", "/alerts/rules", headers=backend_headers()) or []
    alerts = backend_request("GET", "/alerts", headers=backend_headers()) or []
    if rules:
        st.write("Reglas activas")
        st.dataframe(pd.DataFrame(rules), width="stretch", hide_index=True)
    if alerts:
        st.write("Historial de alertas")
        st.dataframe(pd.DataFrame(alerts), width="stretch", hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_crm_documents():
    st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Documentos de procesos</h2></div>', unsafe_allow_html=True)
    if st.session_state.crm_country == "Chile":
        st.info("La descarga de documentos Chile se habilitara junto con el conector de fuentes chilenas.")
        st.markdown("</div>", unsafe_allow_html=True)
        return
    opportunities = backend_request("GET", "/opportunities", headers=backend_headers()) or []
    labels = {f"{o.get('id')} | {o.get('nomenclature')} | {str(o.get('entity') or '')[:70]}": o for o in opportunities}
    if labels:
        selected = st.selectbox("Proceso", list(labels.keys()))
        opp = labels[selected]
        c1, c2 = st.columns(2)
        if c1.button("Buscar documentos en SEACE", type="primary", width="stretch"):
            docs = backend_request("POST", f"/documents/opportunity/{int(opp['id'])}/discover", headers=backend_headers())
            if docs is not None:
                st.success(f"Documentos procesados: {len(docs)}")
        if c2.button("Actualizar listado", width="stretch"):
            st.rerun()
        docs = backend_request("GET", f"/documents/opportunity/{int(opp['id'])}", headers=backend_headers()) or []
        if docs:
            st.dataframe(pd.DataFrame(docs), width="stretch", hide_index=True)
            for doc in docs:
                if doc.get("status") == "downloaded":
                    st.link_button(
                        f"Descargar {doc.get('filename') or doc.get('title')}",
                        f"{BACKEND_API_URL}/documents/{doc.get('id')}/download?token={quote(st.session_state.backend_token, safe='')}",
                    )
        else:
            st.info("No hay documentos registrados para este proceso.")
    else:
        st.info("No hay oportunidades disponibles.")
    st.markdown("</div>", unsafe_allow_html=True)

def render_crm_users_profiles(kind: str):
    if kind == "Usuarios":
        st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Usuarios y permisos</h2></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        email = c1.text_input("Email", key="crm_new_user_email")
        name = c2.text_input("Nombre", key="crm_new_user_name")
        role = c3.selectbox("Rol", ["viewer", "operator", "admin"], key="crm_new_user_role")
        password = c4.text_input("Password inicial", "Usuario12345", type="password", key="crm_new_user_password")
        if st.button("Crear usuario", type="primary", disabled=not email or not name):
            created = backend_request("POST", "/users", headers=backend_headers(), json={"email": email, "full_name": name, "role": role, "password": password})
            if created:
                st.success(f"Usuario creado: {created.get('email')}")
        users = backend_request("GET", "/users", headers=backend_headers()) or []
        if users:
            st.dataframe(pd.DataFrame(users), width="stretch", hide_index=True)
    else:
        st.markdown('<div class="corp-panel"><div class="corp-panel-title"><h2>Perfiles de busqueda</h2></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        profile_name = c1.text_input("Nombre perfil", f"{st.session_state.crm_country} satelital 2026")
        keyword = c2.text_input("Keywords", "satelital conectividad internet")
        year = c3.text_input("Anio", "2026")
        max_results = c4.number_input("Max resultados", min_value=1, max_value=100, value=25)
        if st.button("Crear perfil", type="primary"):
            source_name = "seace_public_browser" if st.session_state.crm_country == "Peru" else "chile_marketplace_pending"
            created = backend_request("POST", "/search-profiles", headers=backend_headers(), json={"name": profile_name, "keyword": keyword, "source": source_name, "year": year, "version": "Seace 3" if st.session_state.crm_country == "Peru" else "Chile", "max_results": int(max_results), "is_active": True})
            if created:
                st.success(f"Perfil creado: {created.get('name')}")
        profiles = backend_request("GET", "/search-profiles", headers=backend_headers()) or []
        if profiles:
            st.dataframe(pd.DataFrame(profiles), width="stretch", hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_corporate_crm():
    render_crm_header()
    if st.session_state.backend_last_error:
        st.error(st.session_state.backend_last_error)
    if not st.session_state.backend_token:
        st.warning("Sesion backend no disponible. Vuelve a iniciar sesion.")
        return
    stats = backend_request("GET", "/opportunities/stats", headers=backend_headers()) or {}
    page = st.session_state.crm_page
    if page == "Inicio":
        render_crm_home(stats)
    elif page == "Oportunidades":
        render_kpi_cards(stats)
        render_crm_opportunities()
    elif page == "Alertas":
        render_crm_alerts()
    elif page == "Documentos":
        render_crm_documents()
    elif page in ["Usuarios", "Perfiles"]:
        render_crm_users_profiles(page)
    elif page == "Vista tecnica":
        st.info("Vista tecnica activada. Usa el panel lateral para acceder al MVP anterior.")

def opportunities_to_dataframe(rows):
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df
    rename = {
        "source": "origen",
        "entity": "entidad",
        "nomenclature": "nomenclatura",
        "object_type": "objeto",
        "description": "descripcion",
        "amount": "monto",
        "currency": "moneda",
        "status": "estado_operativo",
        "reasons": "motivos_score",
        "detail_url": "url_detalle",
        "requirement_pdf_url": "requerimiento_pdf",
        "requirement_pdf_local": "requerimiento_pdf_local",
        "publication_date": "fecha_publicacion",
        "consultation_deadline": "consulta_fin",
        "quote_deadline": "cotizacion_fin",
        "proposal_deadline": "propuesta_fin",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ["fecha_publicacion", "consulta_fin", "cotizacion_fin", "propuesta_fin"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    now = pd.Timestamp.now()
    if "cotizacion_fin" in df.columns:
        df["dias_para_cotizacion"] = (df["cotizacion_fin"].dt.normalize() - now.normalize()).dt.days
    if "propuesta_fin" in df.columns:
        df["dias_para_propuesta"] = (df["propuesta_fin"].dt.normalize() - now.normalize()).dt.days
    if "priority" in df.columns:
        order = {"A": 0, "B": 1, "C": 2}
        df["_priority_order"] = df["priority"].map(order).fillna(9)
        sort_cols = [c for c in ["_priority_order", "score", "fecha_publicacion"] if c in df.columns]
        ascending = [True if c != "score" and c != "fecha_publicacion" else False for c in sort_cols]
        df = df.sort_values(sort_cols, ascending=ascending, na_position="last").drop(columns=["_priority_order"])
    return df

def dataframe_to_backend_records(df: pd.DataFrame) -> list[dict]:
    export_df = df.copy()
    export_df = export_df.where(pd.notna(export_df), None)
    records = []
    for row in export_df.to_dict(orient="records"):
        clean = {}
        for key, value in row.items():
            if isinstance(value, (list, tuple, set)):
                clean[key] = ", ".join(map(str, value))
            elif pd.isna(value):
                clean[key] = None
            elif isinstance(value, pd.Timestamp):
                clean[key] = value.isoformat()
            elif hasattr(value, "isoformat"):
                clean[key] = value.isoformat()
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        records.append(clean)
    return records

def render_backend_api_view():
    st.subheader("Backend productivo")
    st.caption("Consulta oportunidades persistidas, dispara ejecuciones y administra alertas desde la API.")

    with st.sidebar:
        st.subheader("Backend API")
        st.text_input("URL API", BACKEND_API_URL, disabled=True)
        email = st.text_input("Usuario API", "admin@seace-radar.local")
        password = st.text_input("Password API", "Admin12345", type="password")
        if st.button("Iniciar sesion API"):
            if backend_login(email, password):
                st.success("Sesion API iniciada.")
            else:
                st.error("No se pudo iniciar sesion API.")
        if st.button("Cerrar sesion API"):
            st.session_state.backend_token = ""
            st.rerun()

    if st.session_state.backend_last_error:
        st.error(st.session_state.backend_last_error)

    if not st.session_state.backend_token:
        st.info("Inicia sesion contra el backend para usar este modulo.")
        return

    stats = backend_request("GET", "/opportunities/stats", headers=backend_headers()) or {}
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total backend", stats.get("total", 0))
    s2.metric("Prioridad A", (stats.get("by_priority") or {}).get("A", 0))
    s3.metric("Vigentes", stats.get("vigentes", 0))
    s4.metric("Cerrados", stats.get("cerrados", 0))
    s5.metric("Monto total", f"S/ {float(stats.get('total_amount') or 0):,.0f}")

    tab_oportunidades, tab_runs, tab_alertas, tab_usuarios, tab_perfiles, tab_documentos = st.tabs(["Oportunidades", "Ejecuciones", "Alertas", "Usuarios", "Perfiles", "Documentos"])

    with tab_oportunidades:
        c1, c2, c3 = st.columns(3)
        source_filter = c1.text_input("Fuente", "")
        priority_filter = c2.selectbox("Prioridad", ["", "A", "B", "C"], index=0)
        status_filter = c3.text_input("Estado contiene", "")
        params = {}
        if source_filter:
            params["source"] = source_filter
        if priority_filter:
            params["priority"] = priority_filter
        if st.button("Actualizar oportunidades", key="refresh_backend_opportunities"):
            st.rerun()
        rows = backend_request("GET", "/opportunities", headers=backend_headers(), params=params)
        df = opportunities_to_dataframe(rows)
        if status_filter and not df.empty and "estado_operativo" in df.columns:
            df = df[df["estado_operativo"].astype(str).str.lower().str.contains(status_filter.lower(), na=False)]
        if df.empty:
            st.info("Aun no hay oportunidades persistidas en el backend.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total", len(df))
            m2.metric("Prioridad A", int((df.get("priority", pd.Series(dtype=str)) == "A").sum()) if "priority" in df else 0)
            m3.metric("Vigentes", int(df.get("estado_operativo", pd.Series(dtype=str)).astype(str).str.contains("Vigente", na=False).sum()) if "estado_operativo" in df else 0)
            m4.metric("Monto", f"S/ {pd.to_numeric(df.get('monto', 0), errors='coerce').fillna(0).sum():,.0f}")
            visible_cols = [c for c in [
                "origen", "estado_operativo", "priority", "score", "fecha_publicacion",
                "consulta_fin", "cotizacion_fin", "propuesta_fin", "entidad", "nomenclatura",
                "dias_para_cotizacion", "dias_para_propuesta", "objeto", "descripcion", "monto", "moneda", "motivos_score", "url_detalle",
            ] if c in df.columns]
            st.dataframe(df[visible_cols], width="stretch")
            excel_bytes = generar_excel(df)
            st.download_button("Descargar Excel desde backend", data=excel_bytes, file_name="SEACE_Radar_Backend.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab_runs:
        r1, r2, r3, r4 = st.columns(4)
        run_keyword = r1.text_input("Keyword run", "satelital")
        run_year = r2.text_input("Anio run", "2026")
        run_max = r3.number_input("Max resultados", min_value=1, max_value=100, value=25)
        enrich = r4.checkbox("Leer detalles", value=False)
        if st.button("Iniciar radar backend"):
            payload = {
                "source": "seace_public_browser",
                "keyword": run_keyword,
                "year": run_year,
                "version": "Seace 3",
                "max_results": int(run_max),
                "enrich_details": bool(enrich),
            }
            run = backend_request("POST", "/runs/start", headers=backend_headers(), json=payload)
            if run:
                st.success(f"Run encolado: #{run.get('id')} estado {run.get('status')}")
                st.info("Usa Actualizar ejecuciones en unos segundos para ver el resultado.")
        if st.button("Actualizar ejecuciones", key="refresh_backend_runs"):
            st.rerun()
        runs = backend_request("GET", "/runs", headers=backend_headers())
        if runs:
            st.dataframe(pd.DataFrame(runs), width="stretch")

    with tab_alertas:
        a1, a2, a3 = st.columns(3)
        rule_name = a1.text_input("Nombre regla", "Prioridad A comercial")
        channel = a2.selectbox("Canal", ["email", "whatsapp", "message"])
        destination = a3.text_input("Destino", "")
        if st.button("Crear regla de alerta", disabled=not destination):
            payload = {
                "name": rule_name,
                "channel": channel,
                "destination": destination,
                "min_priority": "A",
                "hours_before_deadline": 48,
                "is_active": True,
            }
            rule = backend_request("POST", "/alerts/rules", headers=backend_headers(), json=payload)
            if rule:
                st.success(f"Regla creada: #{rule.get('id')}")
        b1, b2 = st.columns(2)
        if b1.button("Evaluar alertas"):
            created = backend_request("POST", "/alerts/evaluate", headers=backend_headers())
            st.success(f"Alertas generadas: {len(created or [])}")
        if b2.button("Enviar pendientes"):
            sent = backend_request("POST", "/alerts/send-pending", headers=backend_headers())
            st.success(f"Alertas procesadas: {len(sent or [])}")
        rules = backend_request("GET", "/alerts/rules", headers=backend_headers())
        alerts = backend_request("GET", "/alerts", headers=backend_headers())
        if rules:
            st.write("Reglas")
            st.dataframe(pd.DataFrame(rules), width="stretch")
        if alerts:
            st.write("Alertas")
            st.dataframe(pd.DataFrame(alerts), width="stretch")

    with tab_usuarios:
        st.write("Usuarios del sistema")
        u1, u2, u3, u4 = st.columns(4)
        new_email = u1.text_input("Email", key="new_user_email")
        new_name = u2.text_input("Nombre", key="new_user_name")
        new_role = u3.selectbox("Rol", ["viewer", "operator", "admin"], key="new_user_role")
        new_password = u4.text_input("Password", "Usuario12345", type="password", key="new_user_password")
        if st.button("Crear usuario", disabled=not new_email or not new_name, key="create_user_button"):
            user = backend_request(
                "POST",
                "/users",
                headers=backend_headers(),
                json={
                    "email": new_email,
                    "full_name": new_name,
                    "password": new_password,
                    "role": new_role,
                },
            )
            if user:
                st.success(f"Usuario creado: {user.get('email')}")
        users = backend_request("GET", "/users", headers=backend_headers())
        if users:
            st.dataframe(pd.DataFrame(users), width="stretch")

    with tab_perfiles:
        st.write("Perfiles de busqueda")
        p1, p2, p3, p4 = st.columns(4)
        profile_name = p1.text_input("Nombre perfil", "Satelital 2026", key="profile_name")
        profile_keyword = p2.text_input("Keyword", "satelital", key="profile_keyword")
        profile_year = p3.text_input("Anio", "2026", key="profile_year")
        profile_max = p4.number_input("Max", min_value=1, max_value=100, value=25, key="profile_max")
        if st.button("Crear perfil", key="create_profile_button"):
            profile = backend_request(
                "POST",
                "/search-profiles",
                headers=backend_headers(),
                json={
                    "name": profile_name,
                    "keyword": profile_keyword,
                    "source": "seace_public_browser",
                    "year": profile_year,
                    "version": "Seace 3",
                    "max_results": int(profile_max),
                    "is_active": True,
                },
            )
            if profile:
                st.success(f"Perfil creado: {profile.get('name')}")
        profiles = backend_request("GET", "/search-profiles", headers=backend_headers())
        if profiles:
            profile_df = pd.DataFrame(profiles)
            st.dataframe(profile_df, width="stretch")
            labels = {f"{p.get('id')} | {p.get('name')} | {p.get('keyword')} | {'activo' if p.get('is_active') else 'inactivo'}": p for p in profiles}
            selected_label = st.selectbox("Perfil seleccionado", list(labels.keys()), key="selected_profile_label")
            selected_profile = labels[selected_label]
            c_run, c_toggle = st.columns(2)
            if c_run.button("Ejecutar perfil seleccionado", key="run_selected_profile"):
                run = backend_request(
                    "POST",
                    "/runs/start",
                    headers=backend_headers(),
                    json={"search_profile_id": int(selected_profile["id"])},
                )
                if run:
                    st.success(f"Run de perfil encolado: #{run.get('id')}")
            toggle_label = "Desactivar perfil" if selected_profile.get("is_active") else "Activar perfil"
            if c_toggle.button(toggle_label, key="toggle_selected_profile"):
                updated = backend_request(
                    "PATCH",
                    f"/search-profiles/{int(selected_profile['id'])}/active",
                    headers=backend_headers(),
                    params={"is_active": not bool(selected_profile.get("is_active"))},
                )
                if updated:
                    st.success(f"Perfil actualizado: {updated.get('name')}")
                    st.rerun()

    with tab_documentos:
        st.write("Documentos descargables")
        opportunities = backend_request("GET", "/opportunities", headers=backend_headers()) or []
        labels = {
            f"{o.get('id')} | {o.get('nomenclature')} | {str(o.get('entity') or '')[:60]}": o
            for o in opportunities
        }
        if not labels:
            st.info("No hay oportunidades para buscar documentos.")
        else:
            selected_doc_label = st.selectbox("Oportunidad", list(labels.keys()), key="doc_opportunity")
            selected_opp = labels[selected_doc_label]
            d1, d2 = st.columns(2)
            if d1.button("Buscar/descargar documentos SEACE", key="discover_docs"):
                docs = backend_request(
                    "POST",
                    f"/documents/opportunity/{int(selected_opp['id'])}/discover",
                    headers=backend_headers(),
                )
                if docs is not None:
                    st.success(f"Documentos procesados: {len(docs)}")
            if d2.button("Actualizar documentos", key="refresh_docs"):
                st.rerun()
            docs = backend_request(
                "GET",
                f"/documents/opportunity/{int(selected_opp['id'])}",
                headers=backend_headers(),
            )
            if docs:
                st.dataframe(pd.DataFrame(docs), width="stretch")
                for doc in docs:
                    if doc.get("status") == "downloaded":
                        st.link_button(
                            f"Descargar {doc.get('filename') or doc.get('title') or doc.get('id')}",
                            f"{BACKEND_API_URL}/documents/{doc.get('id')}/download?token={quote(st.session_state.backend_token, safe='')}",
                        )
            else:
                st.info("Aun no hay documentos registrados para esta oportunidad.")

def estado_orden(valor: str) -> int:
    orden = {
        "Vence Hoy": 0,
        "Vigente": 1,
        "Vigente para Consultas y Propuesta": 1,
        "Vigente para Consulta y CotizaciÃ³n": 1,
        "Vigente sÃ³lo para Propuesta": 2,
        "Vigente solo para Propuesta": 2,
        "Vigente sÃ³lo para CotizaciÃ³n": 2,
        "Vigente solo para CotizaciÃ³n": 2,
        "En EvaluaciÃ³n": 3,
        "En Evaluacion": 3,
        "Revisar": 4,
        "Cerrado": 5,
    }
    return orden.get(str(valor), 99)

def preparar_publico(raw: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(raw)
    df["origen"] = "SEACE_PUBLICO"
    if "fecha_publicacion" in df.columns:
        df = df.sort_values(by="fecha_publicacion", ascending=False, na_position="last")
    return df

def preparar_menor8(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["origen"] = "MENOR_8_UIT"
    rename = {
        "codigo": "nomenclatura",
        "entidad_contratante": "entidad",
        "tipo_objeto": "objeto",
        "descripcion": "descripcion",
        "monto_estimado": "monto",
        "moneda": "moneda",
        "detalle_url": "url_detalle",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "monto" not in df.columns:
        df["monto"] = 0
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    for c in [
        "fecha_publicacion", "consulta_inicio", "consulta_fin", "cotizacion_inicio", "cotizacion_fin",
        "propuesta_inicio", "propuesta_fin", "buena_pro_inicio", "buena_pro_fin",
    ]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    if "cotizacion_inicio" in df.columns:
        df["propuesta_inicio"] = df["cotizacion_inicio"]
    if "cotizacion_fin" in df.columns:
        df["propuesta_fin"] = df["cotizacion_fin"]
    return df

inject_corporate_css()
if not st.session_state.crm_authenticated:
    render_login_page()
    st.stop()
if st.session_state.crm_page != "Vista tecnica":
    render_corporate_crm()
    st.stop()

st.title("SEACE Radar Gov Peru v10.6 - PÃºblico + Menores a 8 UIT")
st.caption("Radar comercial Hughes/Starlink para SEACE PÃºblico y Contratos Menores a 8 UIT, con cronograma robusto y descarga de requerimientos PDF.")

with st.sidebar:
    st.success("Vista tecnica del MVP")
    if st.button("Volver al CRM corporativo"):
        st.session_state.crm_page = "Inicio"
        st.rerun()

source = st.sidebar.radio("Fuente de datos", [
    "Backend API",
    "SEACE PÃºblico", "Menores a 8 UIT", "Ambos mÃ³dulos",
    "SEACE PÃºblico - requests experimental", "Auto OECE - descarga construida",
    "URL pÃºblica directa", "Archivo local CSV/XLSX",
])

with st.sidebar:
    st.divider()
    if st.button("Limpiar resultados guardados"):
        reset_resultados()
        st.rerun()

if source == "Backend API":
    render_backend_api_view()
    st.stop()

if source in ["SEACE PÃºblico", "Ambos mÃ³dulos"]:
    st.sidebar.subheader("SEACE PÃºblico")
    url_publico = st.sidebar.text_input("URL Buscador SEACE PÃºblico", SEACE_PUBLIC_URL)
    keyword_publico = st.sidebar.text_input("Palabra clave pÃºblico", "satelital")
    year_publico = st.sidebar.text_input("AÃ±o convocatoria", "2026")
    version_publico = st.sidebar.selectbox("VersiÃ³n SEACE", ["Seace 3", "Seace 2", ""], index=0)
    headless_publico = not st.sidebar.checkbox("Navegador visible pÃºblico", value=False)
    max_wait_publico = st.sidebar.slider("Espera pÃºblico (segundos)", 5, 120, 45)
    enrich_publico = st.sidebar.checkbox("Enriquecer pÃºblico con detalle", value=True)
    max_details_publico = st.sidebar.slider("MÃ¡ximo detalles pÃºblico", 1, 30, 15)
    if st.sidebar.button("Buscar SEACE PÃºblico"):
        with st.spinner("Consultando SEACE PÃºblico..."):
            raw, diag = search_seace_public_browser(
                url=url_publico, keyword=keyword_publico, year=year_publico,
                version=version_publico, headless=headless_publico,
                max_wait=max_wait_publico, enrich_details=enrich_publico,
                max_details=max_details_publico,
            )
            st.session_state.raw_publico = raw
            st.session_state.diagnostics_publico = diag
            st.session_state.excel_bytes = None
            st.session_state.df_final = None
            st.session_state.last_filter_key = None

if source in ["Menores a 8 UIT", "Ambos mÃ³dulos"]:
    st.sidebar.subheader("Menores a 8 UIT")
    if not MENOR8_MODULE_ENABLED:
        st.sidebar.warning("MÃ³dulo Menores a 8 UIT deshabilitado temporalmente hasta estabilizar el scraper.")
    auth_url = st.sidebar.text_input("URL Login Menores", MENOR8_AUTH_URL)
    search_url = st.sidebar.text_input("URL Buscador Menores", MENOR8_SEARCH_URL)
    keyword_menor8 = st.sidebar.text_input("Palabra clave menores", "satelital")
    headless_menor8 = not st.sidebar.checkbox("Navegador visible menores", value=True)
    max_wait_menor8 = st.sidebar.slider("Espera menores (segundos)", 5, 180, 60)
    login_wait_seconds = st.sidebar.slider("Espera login manual (segundos)", 60, 600, 300, step=30)
    max_results_menor8 = st.sidebar.slider("MÃ¡ximo contratos menores", 5, 100, 50)
    enrich_menor8 = st.sidebar.checkbox("Leer detalle menores", value=True)
    download_requirements = st.sidebar.checkbox("Descargar PDFs/TDR automÃ¡ticamente", value=True)
    st.sidebar.info("Para Menores a 8 UIT, abre navegador visible. Si aparece login, inicia sesiÃ³n manualmente; el scraper continÃºa desde la sesiÃ³n abierta, acepta tÃ©rminos si aparecen y descarga PDFs si estÃ¡ activado.")
    if st.sidebar.button("Buscar Menores a 8 UIT", disabled=not MENOR8_MODULE_ENABLED):
        with st.spinner("Consultando Contratos Menores a 8 UIT..."):
            raw, diag = search_menor8_browser(
                auth_url=auth_url, search_url=search_url, keyword=keyword_menor8,
                headless=headless_menor8, max_wait=max_wait_menor8,
                login_wait_seconds=login_wait_seconds, max_results=max_results_menor8,
                enrich_details=enrich_menor8, download_requirements=download_requirements,
            )
            st.session_state.raw_menor8 = raw
            st.session_state.diagnostics_menor8 = diag
            st.session_state.excel_bytes = None
            st.session_state.df_final = None
            st.session_state.last_filter_key = None

if source == "SEACE PÃºblico - requests experimental":
    url = st.sidebar.text_input("URL Buscador SEACE", SEACE_PUBLIC_URL)
    keyword = st.sidebar.text_input("DescripciÃ³n / palabra clave", "satelital")
    year = st.sidebar.text_input("AÃ±o convocatoria", "2026")
    version = st.sidebar.selectbox("VersiÃ³n SEACE", ["Seace 3", "Seace 2", ""], index=0)
    if st.sidebar.button("Buscar con requests"):
        raw, diagnostics = search_seace_public(url=url, keyword=keyword, objeto="", year=year, version=version)
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "Auto OECE - descarga construida":
    base_url = st.sidebar.text_input("Portal API OECE", DEFAULT_PORTAL_URL)
    source_name = st.sidebar.text_input("source", "ocds")
    file_type = st.sidebar.selectbox("type", ["csv", "excel", "xlsx", "json", "jsonl"], index=0)
    year = st.sidebar.text_input("year", "2026")
    month = st.sidebar.text_input("month", "")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Conectar y descargar automÃ¡ticamente"):
        raw, diagnostics = fetch_massive_by_params(base_url, source_name, file_type, year, month)
        if raw is not None and not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "URL pÃºblica directa":
    url = st.sidebar.text_input("URL directa CSV/XLSX/JSON/JSONL/GZ/ZIP/TAR.GZ")
    keyword_hint = st.sidebar.text_input("Keyword posterior", "satelital")
    if st.sidebar.button("Descargar URL") and url:
        raw, msg = download_any_dataset(url)
        diagnostics = [msg]
        if raw is not None and not raw.empty and keyword_hint:
            raw = raw[raw.astype(str).apply(lambda s: s.str.lower().str.contains(keyword_hint.lower(), na=False)).any(axis=1)]
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = diagnostics
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None
elif source == "Archivo local CSV/XLSX":
    uploaded = st.sidebar.file_uploader("Carga CSV o Excel", type=["csv", "xlsx", "xls"])
    if uploaded:
        raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded, engine="openpyxl")
        st.session_state.raw_publico = raw
        st.session_state.diagnostics_publico = [f"Archivo cargado: {uploaded.name}"]
        st.session_state.excel_bytes = None
        st.session_state.last_filter_key = None

if st.session_state.diagnostics_publico or st.session_state.diagnostics_menor8:
    with st.expander("DiagnÃ³stico", expanded=False):
        if st.session_state.diagnostics_publico:
            st.write("### SEACE PÃºblico")
            for d in st.session_state.diagnostics_publico:
                st.write(d)
        if st.session_state.diagnostics_menor8:
            st.write("### Menores a 8 UIT")
            for d in st.session_state.diagnostics_menor8:
                st.write(d)

frames = []
if st.session_state.raw_publico is not None and not st.session_state.raw_publico.empty:
    try:
        frames.append(preparar_publico(st.session_state.raw_publico))
    except Exception as e:
        st.warning(f"No se pudo preparar SEACE PÃºblico: {e}")
if st.session_state.raw_menor8 is not None and not st.session_state.raw_menor8.empty:
    try:
        frames.append(preparar_menor8(st.session_state.raw_menor8))
    except Exception as e:
        st.warning(f"No se pudo preparar Menores a 8 UIT: {e}")

if frames:
    df = pd.concat(frames, ignore_index=True, sort=False)
    df = enriquecer_oportunidades(df)
    if "estado_operativo" in df.columns:
        df["orden_estado"] = df["estado_operativo"].apply(estado_orden)
    elif "estado_comercial" in df.columns:
        df["orden_estado"] = df["estado_comercial"].apply(estado_orden)
    else:
        df["orden_estado"] = 99

    st.subheader("Dashboard ejecutivo")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total", len(df))
    c2.metric("SEACE PÃºblico", int((df.get("origen", "") == "SEACE_PUBLICO").sum()) if "origen" in df else 0)
    c3.metric("Menores 8 UIT", int((df.get("origen", "") == "MENOR_8_UIT").sum()) if "origen" in df else 0)
    accionables_count = (int(df["estado_operativo"].astype(str).isin(["Vence Hoy", "Vigente"]).sum()) if "estado_operativo" in df else int(df.get("estado_comercial", pd.Series(dtype=str)).astype(str).str.contains("Vigente", na=False).sum()) if "estado_comercial" in df else 0)
    c4.metric("Accionables", accionables_count)
    cerrados_count = int((df["estado_operativo"].astype(str) == "Cerrado").sum()) if "estado_operativo" in df else int((df.get("estado_comercial", "") == "Cerrado").sum()) if "estado_comercial" in df else 0
    c5.metric("Cerrados", cerrados_count)
    c6.metric("Monto", f"S/ {pd.to_numeric(df.get('monto', 0), errors='coerce').fillna(0).sum():,.0f}")

    st.subheader("Filtros")
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    kw = f1.text_input("Palabra clave", "satelital")
    origen_options = sorted(df["origen"].dropna().unique().tolist()) if "origen" in df else []
    origen = f2.multiselect("Origen", origen_options, default=origen_options)
    pri_options = ["A", "B", "C"]
    pri = f3.multiselect("Prioridad", pri_options, default=pri_options)
    estado_options = sorted(df["estado_operativo"].dropna().unique().tolist()) if "estado_operativo" in df else sorted(df["estado_comercial"].dropna().unique().tolist()) if "estado_comercial" in df else []
    estado = f4.multiselect("Estado", estado_options, default=[])
    sec_options = sorted(df["sector"].dropna().unique().tolist()) if "sector" in df else []
    sec = f5.multiselect("Sector", sec_options, default=[])
    reg = f6.text_input("RegiÃ³n contiene")

    filtered = df.copy()
    if kw:
        filtered = filtered[filtered.astype(str).apply(lambda s: s.str.lower().str.contains(kw.lower(), na=False)).any(axis=1)]
    if origen and "origen" in filtered:
        filtered = filtered[filtered["origen"].isin(origen)]
    if pri and "prioridad" in filtered:
        filtered = filtered[filtered["prioridad"].isin(pri)]
    if estado:
        if "estado_operativo" in filtered:
            filtered = filtered[filtered["estado_operativo"].isin(estado)]
        elif "estado_comercial" in filtered:
            filtered = filtered[filtered["estado_comercial"].isin(estado)]
    if sec and "sector" in filtered:
        filtered = filtered[filtered["sector"].isin(sec)]
    if reg and "region" in filtered:
        filtered = filtered[filtered["region"].astype(str).str.lower().str.contains(reg.lower(), na=False)]

    sort_cols = [c for c in ["orden_estado", "dias_para_cotizacion", "dias_para_propuesta", "propuesta_fin", "fecha_publicacion"] if c in filtered.columns]
    if sort_cols:
        ascending = [True if c != "fecha_publicacion" else False for c in sort_cols]
        filtered = filtered.sort_values(by=sort_cols, ascending=ascending, na_position="last")

    st.session_state.df_final = filtered
    cols = [c for c in [
        "origen", "estado_operativo", "vigencia", "estado_comercial", "estado_portal",
        "fecha_publicacion", "consulta_inicio", "consulta_fin", "cotizacion_inicio", "cotizacion_fin", "propuesta_fin",
        "dias_para_consulta", "dias_para_cotizacion", "dias_para_propuesta",
        "horas_para_consulta", "horas_para_cotizacion", "situacion_consulta", "situacion_cotizacion",
        "ruc", "entidad", "sector", "region", "nomenclatura", "objeto", "descripcion", "area_usuaria",
        "monto", "moneda", "version_seace", "requerimiento_pdf", "requerimiento_pdf_nombre",
        "requerimiento_pdf_local", "requerimiento_pdf_archivo", "motivos_score", "semaforo", "prioridad", "score", "url_detalle",
    ] if c in filtered.columns]

    st.subheader("Oportunidades")

    # Eliminar columnas duplicadas del dataframe
    filtered = filtered.loc[:, ~filtered.columns.duplicated()].copy()

    # Eliminar nombres repetidos de la lista cols
    cols = list(dict.fromkeys(cols))

    # Mantener solo columnas existentes
    cols = [c for c in cols if c in filtered.columns]
    #st.dataframe(filtered[cols], width="stretch")

    filtered = filtered.loc[:, ~filtered.columns.duplicated()].copy()
    try:
        cols = list(cols)
    except Exception:
        cols = list(filtered.columns)
    cols = [c for c in cols if isinstance(c, str)]
    cols = list(dict.fromkeys(cols))
    cols = [c for c in cols if c in filtered.columns]
    if not cols:
        cols = list(filtered.columns)

    for _c in filtered.columns:
        filtered[_c] = filtered[_c].apply(
            lambda x: '' if x is None else (', '.join(map(str, x)) if isinstance(x, (list, tuple, set)) else x)
        )

    st.dataframe(filtered[cols], width="stretch")

    if st.session_state.backend_token:
        if st.button("Guardar resultados actuales en Backend API", key="import_manual_results"):
            payload = {
                "source": "seace_public_browser",
                "rows": dataframe_to_backend_records(filtered),
            }
            imported = backend_request("POST", "/opportunities/import", headers=backend_headers(), json=payload)
            if imported:
                st.success(f"Backend actualizado: {imported.get('imported', 0)} oportunidades procesadas.")
    else:
        st.caption("Para guardar esta busqueda en Backend API, inicia sesion en el modulo Backend API primero.")

    if "requerimiento_pdf_local" in filtered.columns:
        pdf_df = filtered[filtered["requerimiento_pdf_local"].notna() & (filtered["requerimiento_pdf_local"].astype(str) != "")].copy()
        if not pdf_df.empty:
            st.subheader("Descarga de requerimientos PDF")
            labels = []
            lookup = {}
            for _, r in pdf_df.iterrows():
                label = f"{r.get('nomenclatura','')} | {str(r.get('entidad',''))[:60]} | {r.get('requerimiento_pdf_archivo','requerimiento.pdf')}"
                labels.append(label)
                lookup[label] = r
            selected_label = st.selectbox("Selecciona el requerimiento a descargar", labels, key="pdf_req_selector")
            selected_row = lookup[selected_label]
            pdf_path = Path(str(selected_row.get("requerimiento_pdf_local", "")))
            if pdf_path.exists():
                st.download_button("Descargar PDF del requerimiento", data=pdf_path.read_bytes(), file_name=str(selected_row.get("requerimiento_pdf_archivo", pdf_path.name)), mime="application/pdf")
            else:
                st.warning("El PDF figura en la tabla, pero no se encuentra el archivo local. Ejecuta nuevamente con 'Leer detalle menores' y 'Descargar PDFs/TDR automÃ¡ticamente' activados.")

    filter_key = str(filtered.shape) + "|" + str(filtered.index.tolist()) + "|" + str(filtered.columns.tolist())
    if st.session_state.last_filter_key != filter_key:
        st.session_state.excel_bytes = generar_excel(filtered)
        st.session_state.last_filter_key = filter_key

    st.download_button("Descargar Excel ejecutivo", data=st.session_state.excel_bytes, file_name="SEACE_Radar_v10_5_Publico_Menores8UIT.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Ejecuta una bÃºsqueda en SEACE PÃºblico, Menores a 8 UIT o Ambos mÃ³dulos.")
