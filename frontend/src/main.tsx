import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, Alert, AlertRule, DocumentRecord, login, Opportunity, Run, Stats } from "./api";
import "./styles.css";

type Page = "Inicio" | "Oportunidades" | "Alertas" | "Usuarios" | "Sistema";
type Country = "Peru" | "Chile";
type Module = "SEACE Publico" | "Contratos Menores a 8 UIT" | "Licitaciones Mercado Publico" | "Grandes Compras" | "Ambos modulos";
type CommercialClass = "green" | "amber" | "red";
type SortDirection = "asc" | "desc";
type SearchMode = "append" | "replace";
type SortKey =
  | "priority"
  | "commercial"
  | "entity"
  | "nomenclature"
  | "description"
  | "publication_date"
  | "consultation_deadline"
  | "days_consultation"
  | "proposal_deadline"
  | "days_proposal"
  | "amount";

const nav: Page[] = ["Inicio", "Oportunidades", "Alertas", "Usuarios", "Sistema"];
const commercialFilters = [
  { label: "Vigente para Consultas y Propuesta", className: "green" },
  { label: "Vigente para Propuesta", className: "amber" },
  { label: "Proceso Culminado", className: "red" },
] as const;
const activeSearchStorageKey = "govradar.opportunities.activeSearch";

function modulesForCountry(country: Country): Module[] {
  return country === "Chile"
    ? ["Licitaciones Mercado Publico", "Grandes Compras"]
    : ["SEACE Publico", "Contratos Menores a 8 UIT", "Ambos modulos"];
}

function defaultModuleForCountry(country: Country): Module {
  return country === "Chile" ? "Licitaciones Mercado Publico" : "SEACE Publico";
}

function sourceForModule(module: Module) {
  if (module === "Licitaciones Mercado Publico") return "mercado_publico_browser";
  if (module === "Grandes Compras") return "mercado_publico_grandes_compras";
  if (module === "Contratos Menores a 8 UIT") return "menor8_browser";
  return "seace_public_browser";
}

function sourceBelongsToCountry(source: string, country: Country) {
  const normalized = source.toLowerCase();
  if (country === "Chile") return normalized.startsWith("mercado_publico");
  return normalized.startsWith("seace") || normalized.includes("menor8");
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN", maximumFractionDigits: 0 }).format(value || 0);
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-PE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function parseDate(value: string | null) {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function dateOnly(value: number) {
  const date = new Date(value);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function daysUntil(value: string | null) {
  const timestamp = parseDate(value);
  if (timestamp === null) return null;
  const dayMs = 24 * 60 * 60 * 1000;
  return Math.round((dateOnly(timestamp) - dateOnly(Date.now())) / dayMs);
}

function presentationDeadline(item: Opportunity) {
  return item.proposal_deadline || item.quote_deadline;
}

function parseRunDetails(run?: Run | null) {
  const diagnostics = run?.diagnostics || "";
  const reviewed = diagnostics.match(/Cronogramas revisados:\s*(\d+)\/(\d+);\s*aplicados correctamente:\s*(\d+)/);
  const configured = diagnostics.match(/max_detalles=(\d+)/);
  return {
    configured: configured ? Number(configured[1]) : null,
    reviewed: reviewed ? Number(reviewed[1]) : null,
    requested: reviewed ? Number(reviewed[2]) : null,
    applied: reviewed ? Number(reviewed[3]) : null,
  };
}

function estimateRunProgress(run: Run, detail: ReturnType<typeof parseRunDetails>, now: number) {
  if (run.status === "completed") return 100;
  if (run.status === "failed") return 100;
  if (run.status === "queued") return 8;

  if (run.status === "running") {
    if (detail.reviewed !== null && detail.requested && detail.requested > 0) {
      return Math.min(94, 28 + (detail.reviewed / detail.requested) * 58);
    }
    const startedAt = run.started_at ? new Date(run.started_at).getTime() : now;
    const elapsedSeconds = Math.max(0, (now - startedAt) / 1000);
    return Math.min(92, 14 + elapsedSeconds * 1.9);
  }

  return 12;
}

function commercialSignal(item: Opportunity): { label: string; hint: string; className: CommercialClass } {
  const now = Date.now();
  const consultationDeadline = parseDate(item.consultation_deadline);
  const presentationDeadline = parseDate(item.proposal_deadline) ?? parseDate(item.quote_deadline);
  const status = (item.status || "").toLowerCase();

  if (consultationDeadline !== null && now <= consultationDeadline) {
    return {
      label: "Vigente para Consultas y Propuesta",
      hint: "Consultas abiertas",
      className: "green",
    };
  }

  if (presentationDeadline !== null && now <= presentationDeadline) {
    return {
      label: "Vigente para Propuesta",
      hint: "Presentacion Cotizacion abierta",
      className: "amber",
    };
  }

  if (
    (presentationDeadline !== null && now > presentationDeadline) ||
    status.includes("cerrado") ||
    status.includes("culmin") ||
    status.includes("evaluaci")
  ) {
    return {
      label: "Proceso Culminado",
      hint: "Plazo vencido",
      className: "red",
    };
  }

  if (status.includes("consulta")) {
    return {
      label: "Vigente para Consultas y Propuesta",
      hint: "Consultas abiertas",
      className: "green",
    };
  }

  if (status.includes("propuesta") || status.includes("cotiz")) {
    return {
      label: "Vigente para Propuesta",
      hint: "Presentacion Cotizacion abierta",
      className: "amber",
    };
  }

  if (item.priority === "A" || item.score >= 70) {
    return {
      label: "Vigente para Consultas y Propuesta",
      hint: "Revisar cronograma",
      className: "green",
    };
  }

  return {
    label: "Proceso Culminado",
    hint: "Sin ventana activa",
    className: "red",
  };
}

function useBackend(token: string) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [nextStats, nextOpps, nextRuns, nextRules, nextAlerts] = await Promise.all([
        api.stats(token),
        api.opportunities(token),
        api.runs(token),
        api.alertRules(token),
        api.alerts(token),
      ]);
      setStats(nextStats);
      setOpportunities(nextOpps);
      setRuns(nextRuns);
      setRules(nextRules);
      setAlerts(nextAlerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo conectar con el backend");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [token]);

  return { stats, opportunities, runs, rules, alerts, loading, error, refresh, setRuns, setRules };
}

function Login({ onLogin }: { onLogin: (token: string, email: string) => void }) {
  const [email, setEmail] = useState("admin@seace-radar.local");
  const [password, setPassword] = useState("Admin12345");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await login(email, password);
      onLogin(result.access_token, email);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesion");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-brand">
        <div className="brand-mark">R</div>
        <p className="overline">RODAR Consulting</p>
        <h1>Radar comercial para procesos de gobierno.</h1>
        <p>
          Detecta convocatorias de conectividad, internet satelital y telecomunicaciones, prioriza oportunidades
          accionables y activa alertas automaticas para el equipo comercial.
        </p>
        <div className="brand-grid">
          <span>Peru operativo</span>
          <span>Chile preparado</span>
          <span>Email y WhatsApp</span>
          <span>Documentos trazables</span>
        </div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <div>
          <p className="overline">Acceso CRM</p>
          <h2>Iniciar sesion</h2>
          <p className="muted">Ingresa al panel productivo sin la capa tecnica de Streamlit.</p>
        </div>
        <label>
          Correo corporativo
          <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
        </label>
        <label>
          Password
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" />
        </label>
        {error ? <div className="notice danger">{error}</div> : null}
        <button className="primary" disabled={loading}>{loading ? "Validando..." : "Acceder"}</button>
      </form>
    </main>
  );
}

function AppShell({
  email,
  onLogout,
}: {
  email: string;
  onLogout: () => void;
}) {
  const token = localStorage.getItem("rodar_token") || "";
  const [page, setPage] = useState<Page>("Inicio");
  const [country, setCountry] = useState<Country>("Peru");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const backend = useBackend(token);

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <aside className="side">
        <div className="side-brand">
          <div className="brand-mark compact">R</div>
          <div>
            <strong>GovRadar CRM</strong>
            <span>RODAR Consulting</span>
          </div>
        </div>
        <nav>
          {nav.map((item) => (
            <button key={item} className={item === page ? "active" : ""} onClick={() => setPage(item)}>
              {item}
            </button>
          ))}
        </nav>
        <div className="side-footer">
          <span>API</span>
          <strong>{backend.loading ? "Sincronizando" : "Conectada"}</strong>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="top-title">
            <button className="menu-toggle" onClick={() => setSidebarOpen((value) => !value)} aria-label={sidebarOpen ? "Ocultar menu" : "Mostrar menu"}>
              <span />
              <span />
              <span />
            </button>
            <div>
              <p className="overline">Sala de control comercial</p>
              <h1>{page}</h1>
            </div>
          </div>
          <div className="top-actions">
            <div className="segmented" aria-label="Pais">
              <button className={country === "Peru" ? "selected" : ""} onClick={() => setCountry("Peru")}>Peru</button>
              <button className={country === "Chile" ? "selected" : ""} onClick={() => setCountry("Chile")}>Chile</button>
            </div>
            <div className="user-pill">{email.slice(0, 1).toUpperCase()}</div>
            <button className="ghost" onClick={onLogout}>Salir</button>
          </div>
        </header>
        {backend.error ? <div className="notice danger">{backend.error}</div> : null}
        {page === "Inicio" ? <Home country={country} stats={backend.stats} runs={backend.runs} alerts={backend.alerts} /> : null}
        {page === "Oportunidades" ? <Opportunities country={country} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} /> : null}
        {page === "Alertas" ? <Alerts token={token} rules={backend.rules} alerts={backend.alerts} refresh={backend.refresh} /> : null}
        {page === "Usuarios" ? <Users /> : null}
        {page === "Sistema" ? <System runs={backend.runs} refresh={backend.refresh} /> : null}
      </div>
    </div>
  );
}

function Kpis({ stats }: { stats: Stats | null }) {
  const values = [
    ["Procesos radar", stats?.total ?? 0, "Total persistido"],
    ["Prioridad A", stats?.by_priority?.A ?? 0, "Requiere accion"],
    ["Vigentes", stats?.vigentes ?? 0, "Ventana activa"],
    ["Cerrados", stats?.cerrados ?? 0, "Historico"],
    ["Monto detectado", formatMoney(stats?.total_amount ?? 0), "Valor referencial"],
  ];
  return (
    <section className="kpi-grid">
      {values.map(([label, value, hint]) => (
        <article className="kpi" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{hint}</small>
        </article>
      ))}
    </section>
  );
}

function Home({ country, stats, runs, alerts }: { country: Country; stats: Stats | null; runs: Run[]; alerts: Alert[] }) {
  const lastRun = runs[0];
  return (
    <>
      <section className="hero-panel">
        <div>
          <p className="overline">{country === "Peru" ? "Modulo Peru" : "Modulo Chile"}</p>
          <h2>{country === "Peru" ? "SEACE operativo, monitoreo automatico y alertas accionables." : "Radar Chile preparado para conectores Mercado Publico."}</h2>
          <p>
            La pantalla prioriza procesos con oportunidad comercial, estado de ejecucion, documentos y reglas de alerta
            sin exponer herramientas tecnicas al usuario final.
          </p>
        </div>
        <div className="radar-sweep" aria-hidden="true">
          <span />
          <b />
        </div>
      </section>
      <Kpis stats={stats} />
      <section className="two-col">
        <article className="panel">
          <div className="panel-title">
            <h3>Ultima ejecucion</h3>
            <span className={`status ${lastRun?.status || "queued"}`}>{lastRun?.status || "Sin datos"}</span>
          </div>
          {lastRun ? <RunProgress run={lastRun} /> : <Empty text="Aun no hay ejecuciones registradas." />}
        </article>
        <article className="panel">
          <div className="panel-title">
            <h3>Alertas recientes</h3>
            <span>{alerts.length}</span>
          </div>
          <div className="list">
            {alerts.slice(0, 5).map((alert) => (
              <div className="list-row" key={alert.id}>
                <strong>{alert.alert_type}</strong>
                <span>{alert.status}</span>
              </div>
            ))}
            {!alerts.length ? <Empty text="Crea reglas para activar alertas por email, WhatsApp o mensaje interno." /> : null}
          </div>
        </article>
      </section>
    </>
  );
}

function RunProgress({ run }: { run: Run }) {
  const [now, setNow] = useState(Date.now());
  const detail = parseRunDetails(run);
  const isLive = run.status === "queued" || run.status === "running";
  const progress = estimateRunProgress(run, detail, now);

  useEffect(() => {
    if (!isLive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isLive]);

  return (
    <div className={`run-progress ${isLive ? "live" : ""}`}>
      <div className="progress-head">
        <strong>{isLive ? "Procesando radar" : run.status === "completed" ? "Ejecucion completada" : "Estado de ejecucion"}</strong>
        <span>Run #{run.id} · {run.status}</span>
      </div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      <div className="run-metrics">
        <span><b>{run.rows_found}</b> procesos</span>
        <span><b>{detail.configured ?? "-"}</b> detalles configurados</span>
        <span><b>{detail.reviewed !== null ? `${detail.reviewed}/${detail.requested}` : "-"}</b> revisados</span>
      </div>
      {run.error_message ? <div className="notice danger">{run.error_message}</div> : null}
    </div>
  );
}

function Opportunities({
  country,
  token,
  data,
  runs,
  refresh,
}: {
  country: Country;
  token: string;
  data: Opportunity[];
  runs: Run[];
  refresh: () => Promise<void>;
}) {
  const initialSearchState = useMemo(() => loadActiveSearchState(), []);
  const [module, setModule] = useState<Module>(defaultModuleForCountry(country));
  const [keyword, setKeyword] = useState("satelital");
  const [priority, setPriority] = useState("Todas");
  const [maxResults, setMaxResults] = useState(25);
  const [readDetails, setReadDetails] = useState(false);
  const [maxDetails, setMaxDetails] = useState(10);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>("append");
  const [activeKeywords, setActiveKeywords] = useState<string[]>(initialSearchState.keywords);
  const [activeRunIds, setActiveRunIds] = useState<number[]>(initialSearchState.runIds);
  const [scopedRows, setScopedRows] = useState<Opportunity[] | null>(null);
  const [pinnedRows, setPinnedRows] = useState<Opportunity[]>([]);
  const [pendingSearch, setPendingSearch] = useState<{ mode: SearchMode; keyword: string; runId: number } | null>(null);
  const [confirmNewSearch, setConfirmNewSearch] = useState(false);
  const visibleRuns = useMemo(() => runs.filter((run) => sourceBelongsToCountry(run.source, country)), [runs, country]);

  useEffect(() => {
    const latest = visibleRuns.find((run) => run.id === activeRun?.id) || activeRun;
    setActiveRun(latest || null);
  }, [visibleRuns]);

  useEffect(() => {
    if (!activeRun && visibleRuns[0]) {
      setActiveRun(visibleRuns[0]);
    }
  }, [activeRun, visibleRuns]);

  useEffect(() => {
    saveActiveSearchState(activeKeywords, activeRunIds);
  }, [activeKeywords, activeRunIds]);

  useEffect(() => {
    setModule(defaultModuleForCountry(country));
    setActiveRun(null);
    setActiveKeywords(["satelital"]);
    setActiveRunIds([]);
    setScopedRows(null);
    setPinnedRows([]);
    setPendingSearch(null);
    setConfirmNewSearch(false);
    setSearchMode("append");
  }, [country]);

  useEffect(() => {
    if (!activeRunIds.length) return;
    let cancelled = false;
    api.opportunities(token, { runIds: activeRunIds })
      .then((rows) => {
        if (!cancelled) setScopedRows((current) => mergeOpportunities(pinnedRows, current ? mergeOpportunities(current, rows) : rows));
      })
      .catch(() => {
        // Manual refresh remains available if the scoped reload fails.
      });
    return () => {
      cancelled = true;
    };
  }, [token, activeRunIds, pinnedRows]);

  useEffect(() => {
    if (!activeRun || (activeRun.status !== "queued" && activeRun.status !== "running")) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await api.run(token, activeRun.id);
        if (cancelled) return;
        setActiveRun(nextRun);
        if (nextRun.status === "completed" || nextRun.status === "failed") {
          await refresh();
          if (nextRun.status === "completed" && pendingSearch?.runId === nextRun.id) {
            const nextKeywords = pendingSearch.mode === "append" ? addKeyword(activeKeywords, pendingSearch.keyword) : [pendingSearch.keyword];
            const nextRunIds = pendingSearch.mode === "append" ? addRunId(activeRunIds, nextRun.id) : [nextRun.id];
            const runRows = await api.opportunities(token, { runIds: nextRunIds });
            setActiveKeywords(nextKeywords);
            setActiveRunIds(nextRunIds);
            setScopedRows(pendingSearch.mode === "append" ? mergeOpportunities(pinnedRows, runRows) : runRows);
            setPendingSearch(null);
          }
        }
      } catch {
        // The manual refresh button remains available if polling is interrupted.
      }
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeRun, token, refresh, pendingSearch, activeKeywords, activeRunIds, pinnedRows]);

  const baseRows = scopedRows ?? data;
  const filtered = useMemo(() => {
    const normalizedActiveKeywords = activeKeywords.map((item) => item.toLowerCase()).filter(Boolean);
    return baseRows.filter((item) => {
      if (!sourceBelongsToCountry(item.source, country)) return false;
      const haystack = `${item.entity} ${item.nomenclature} ${item.description}`.toLowerCase();
      const keywordMatch = !normalizedActiveKeywords.length || normalizedActiveKeywords.some((item) => haystack.includes(item));
      const priorityMatch = priority === "Todas" || item.priority === priority;
      return keywordMatch && priorityMatch;
    });
  }, [baseRows, activeKeywords, priority, country]);

  useEffect(() => {
    if (!activeRun || activeRun.status !== "completed" || pendingSearch?.runId !== activeRun.id) return;
    let cancelled = false;
    const nextKeywords = pendingSearch.mode === "append" ? addKeyword(activeKeywords, pendingSearch.keyword) : [pendingSearch.keyword];
    const nextRunIds = pendingSearch.mode === "append" ? addRunId(activeRunIds, activeRun.id) : [activeRun.id];
    api.opportunities(token, { runIds: nextRunIds })
      .then((rows) => {
        if (cancelled) return;
        setActiveKeywords(nextKeywords);
        setActiveRunIds(nextRunIds);
        setScopedRows(pendingSearch.mode === "append" ? mergeOpportunities(pinnedRows, rows) : rows);
        setPendingSearch(null);
      })
      .catch(() => {
        // The polling loop or manual refresh can retry the visible state.
      });
    return () => {
      cancelled = true;
    };
  }, [activeRun, pendingSearch, activeKeywords, activeRunIds, pinnedRows, token]);

  useEffect(() => {
    if (!activeRun || activeRun.status !== "completed" || activeRun.rows_found <= 0 || activeRunIds.length || pendingSearch) return;
    const recoveredKeyword = keywordFromRun(activeRun);
    if (!recoveredKeyword || activeKeywords.some((item) => item.toLowerCase() === recoveredKeyword.toLowerCase())) return;
    let cancelled = false;
    api.opportunities(token, { runIds: [activeRun.id] })
      .then((rows) => {
        if (cancelled) return;
        const nextKeywords = addKeyword(activeKeywords, recoveredKeyword);
        setActiveKeywords(nextKeywords);
        setActiveRunIds([activeRun.id]);
        setPinnedRows(filtered);
        setScopedRows(mergeOpportunities(filtered, rows));
      })
      .catch(() => {
        // The user can rerun or refresh if recovery is interrupted.
      });
    return () => {
      cancelled = true;
    };
  }, [activeRun, activeRunIds.length, pendingSearch, token, activeKeywords, filtered]);

  async function execute() {
    if (searchMode === "replace" && filtered.length > 0 && !confirmNewSearch) {
      setConfirmNewSearch(true);
      return;
    }
    await executeConfirmed(searchMode);
  }

  async function executeConfirmed(mode: SearchMode) {
    const cleanKeyword = keyword.trim() || "satelital";
    setConfirmNewSearch(false);
    setStarting(true);
    try {
      if (mode === "replace") {
        setActiveKeywords([cleanKeyword]);
        setActiveRunIds([]);
        setPinnedRows([]);
        setScopedRows([]);
      } else {
        setActiveKeywords((current) => addKeyword(current, cleanKeyword));
        if (!activeRunIds.length && scopedRows === null) {
          setPinnedRows(filtered);
        }
      }
      const run = await api.startRun(token, {
        source: sourceForModule(module),
        keyword: cleanKeyword,
        year: country === "Peru" ? "2026" : "",
        version: country === "Peru" ? "Seace 3" : "Mercado Publico",
        max_results: maxResults,
        max_details: readDetails ? maxDetails : 0,
        enrich_details: readDetails,
      });
      setActiveRun(run);
      setPendingSearch({ mode, keyword: cleanKeyword, runId: run.id });
      await refresh();
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>Radar de oportunidades {country}</h2>
          <p>{country === "Peru" ? "Ejecuta SEACE en backend headless y revisa avance sin abrir Chrome al usuario." : "Ejecuta Mercado Publico en backend headless, con licitaciones y grandes compras en la misma bandeja comercial."}</p>
        </div>
        <button className="ghost" onClick={refresh}>Actualizar</button>
      </div>
      <div className="module-row">
        {modulesForCountry(country).map((item) => (
          <button key={item} className={module === item ? "selected" : ""} onClick={() => setModule(item)}>
            {item}
          </button>
        ))}
      </div>
      {module === "Contratos Menores a 8 UIT" || module === "Ambos modulos" ? <div className="notice info">Menores a 8 UIT queda visible para el flujo, pendiente de estabilizacion del conector.</div> : null}
      {module === "Grandes Compras" ? <div className="notice info">Grandes Compras queda visible para Chile, pendiente de estabilizar el formulario de busqueda de Mercado Publico.</div> : null}
      <div className="active-keywords">
        <span>Vista activa:</span>
        {activeKeywords.map((item) => <b key={item}>{item}</b>)}
      </div>
      <div className="form-grid">
        <label>Keyword<input value={keyword} onChange={(event) => setKeyword(event.target.value)} /></label>
        <label>Prioridad<select value={priority} onChange={(event) => setPriority(event.target.value)}><option>Todas</option><option>A</option><option>B</option><option>C</option></select></label>
        <label>Max resultados<input type="number" min={1} max={150} value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))} /></label>
        <label className="check"><input type="checkbox" checked={readDetails} onChange={(event) => setReadDetails(event.target.checked)} /> Leer detalle</label>
        <label>Procesos a revisar detalle<input type="number" min={0} max={maxResults} value={readDetails ? maxDetails : 0} disabled={!readDetails} onChange={(event) => setMaxDetails(Number(event.target.value))} /></label>
        <button className="primary" onClick={execute} disabled={starting || module === "Contratos Menores a 8 UIT" || module === "Ambos modulos" || module === "Grandes Compras"}>
          {starting ? "Iniciando..." : "Ejecutar radar"}
        </button>
      </div>
      <div className="search-mode-row" role="radiogroup" aria-label="Modo de busqueda">
        <button className={searchMode === "append" ? "selected" : ""} onClick={() => setSearchMode("append")} type="button">
          Agregar a la busqueda actual
        </button>
        <button className={searchMode === "replace" ? "selected" : ""} onClick={() => setSearchMode("replace")} type="button">
          Iniciar nueva busqueda
        </button>
      </div>
      {activeRun ? <RunProgress run={activeRun} /> : visibleRuns[0] ? <RunProgress run={visibleRuns[0]} /> : null}
      <OpportunityTable rows={filtered} token={token} />
      {confirmNewSearch ? (
        <ConfirmModal
          title="Iniciar nueva busqueda"
          message="Esta seguro de iniciar una nueva busqueda? Los resultados actuales se quitaran de esta vista, pero quedaran guardados en el historico."
          confirmLabel="Si, iniciar"
          cancelLabel="No"
          onConfirm={() => executeConfirmed("replace")}
          onCancel={() => setConfirmNewSearch(false)}
        />
      ) : null}
    </section>
  );
}

function addKeyword(current: string[], keyword: string) {
  const normalized = keyword.trim();
  if (!normalized) return current;
  const exists = current.some((item) => item.toLowerCase() === normalized.toLowerCase());
  return exists ? current : [...current, normalized];
}

function addRunId(current: number[], runId: number) {
  return current.includes(runId) ? current : [...current, runId];
}

function mergeOpportunities(left: Opportunity[], right: Opportunity[]) {
  const byId = new Map<number, Opportunity>();
  [...left, ...right].forEach((item) => byId.set(item.id, item));
  return [...byId.values()];
}

function loadActiveSearchState(): { keywords: string[]; runIds: number[] } {
  try {
    const raw = window.localStorage.getItem(activeSearchStorageKey);
    if (!raw) return { keywords: ["satelital"], runIds: [] };
    const parsed = JSON.parse(raw) as { keywords?: unknown; runIds?: unknown };
    const keywords = Array.isArray(parsed.keywords)
      ? parsed.keywords.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
    const runIds = Array.isArray(parsed.runIds)
      ? parsed.runIds.filter((item): item is number => typeof item === "number" && Number.isFinite(item))
      : [];
    return { keywords: keywords.length ? keywords : ["satelital"], runIds };
  } catch {
    return { keywords: ["satelital"], runIds: [] };
  }
}

function saveActiveSearchState(keywords: string[], runIds: number[]) {
  try {
    window.localStorage.setItem(activeSearchStorageKey, JSON.stringify({ keywords, runIds }));
  } catch {
    // Local persistence is a convenience; the backend remains the source of truth.
  }
}

function keywordFromRun(run: Run) {
  const match = String(run.diagnostics || "").match(/keyword=([^|]+)/i);
  return match?.[1]?.trim() || "";
}

function ConfirmModal({
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="confirm-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="confirm-card">
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="confirm-actions">
          <button className="ghost" onClick={onCancel}>{cancelLabel}</button>
          <button className="primary" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

function OpportunityTable({ rows, token }: { rows: Opportunity[]; token: string }) {
  const [commercialFilter, setCommercialFilter] = useState<CommercialClass | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "publication_date",
    direction: "desc",
  });
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const topScrollRef = useRef<HTMLDivElement | null>(null);
  const tableScrollRef = useRef<HTMLDivElement | null>(null);

  const rowsWithSignals = useMemo(
    () => rows.map((item) => ({ item, signal: commercialSignal(item) })),
    [rows],
  );

  const filteredRows = useMemo(() => {
    return rowsWithSignals.filter(({ signal }) => !commercialFilter || signal.className === commercialFilter);
  }, [rowsWithSignals, commercialFilter]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((left, right) => {
      const commercialResult = commercialOrder(left.signal.className) - commercialOrder(right.signal.className);
      if (commercialResult !== 0) return commercialResult;
      const dateResult = compareValues(parseDate(left.item.publication_date), parseDate(right.item.publication_date));
      if (dateResult !== 0) return -dateResult;
      const leftValue = sortValue(left.item, left.signal, sort.key);
      const rightValue = sortValue(right.item, right.signal, sort.key);
      const result = compareValues(leftValue, rightValue);
      return sort.direction === "asc" ? result : -result;
    });
  }, [filteredRows, sort]);

  function updateSort(key: SortKey) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  }

  function syncTableScroll(source: "top" | "table") {
    const top = topScrollRef.current;
    const table = tableScrollRef.current;
    if (!top || !table) return;
    if (source === "top") table.scrollLeft = top.scrollLeft;
    if (source === "table") top.scrollLeft = table.scrollLeft;
  }

  const counts = commercialFilters.reduce<Record<CommercialClass, number>>(
    (acc, filter) => {
      acc[filter.className] = rowsWithSignals.filter(({ signal }) => signal.className === filter.className).length;
      return acc;
    },
    { green: 0, amber: 0, red: 0 },
  );

  return (
    <>
      <div className="commercial-filter-row">
        {commercialFilters.map((filter) => (
          <button
            className={`commercial-filter ${filter.className} ${commercialFilter === filter.className ? "active" : ""}`}
            key={filter.className}
            onClick={() => setCommercialFilter((current) => current === filter.className ? null : filter.className)}
          >
            <span>{filter.label}</span>
            <b>{counts[filter.className]}</b>
          </button>
        ))}
      </div>
      <div className="table-scroll-top" ref={topScrollRef} onScroll={() => syncTableScroll("top")} aria-label="Desplazamiento horizontal de oportunidades">
        <div />
      </div>
      <div className="table-wrap" ref={tableScrollRef} onScroll={() => syncTableScroll("table")}>
        <table>
          <thead>
            <tr>
              <SortableTh label="Prioridad" sortKey="priority" sort={sort} onSort={updateSort} />
              <SortableTh label="Semáforo\ncomercial" sortKey="commercial" sort={sort} onSort={updateSort} />
              <SortableTh label="Entidad" sortKey="entity" sort={sort} onSort={updateSort} />
              <SortableTh label="Proceso" sortKey="nomenclature" sort={sort} onSort={updateSort} />
              <th><span className="plain-header">Documentos</span></th>
              <SortableTh label="Descripción" sortKey="description" sort={sort} onSort={updateSort} />
              <SortableTh label="Fecha de\nconvocatoria" sortKey="publication_date" sort={sort} onSort={updateSort} />
              <SortableTh label="Fin\nConsultas" sortKey="consultation_deadline" sort={sort} onSort={updateSort} />
              <SortableTh label="Días\nConsultas" sortKey="days_consultation" sort={sort} onSort={updateSort} />
              <SortableTh label="Fin\nPropuesta" sortKey="proposal_deadline" sort={sort} onSort={updateSort} />
              <SortableTh label="Días\nPropuesta" sortKey="days_proposal" sort={sort} onSort={updateSort} />
              <SortableTh label="Monto" sortKey="amount" sort={sort} onSort={updateSort} />
            </tr>
          </thead>
          <tbody>
            {sortedRows.slice(0, 100).map(({ item, signal }) => (
              <OpportunityRow item={item} signal={signal} key={item.id} onOpenDocuments={setSelectedOpportunity} />
            ))}
          </tbody>
        </table>
        {!sortedRows.length ? <Empty text="No hay oportunidades con los filtros actuales." /> : null}
      </div>
      {selectedOpportunity ? (
        <OpportunityDetailModal
          opportunity={selectedOpportunity}
          token={token}
          onClose={() => setSelectedOpportunity(null)}
        />
      ) : null}
    </>
  );
}

function SortableTh({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sort: { key: SortKey; direction: SortDirection };
  onSort: (key: SortKey) => void;
}) {
  const active = sort.key === sortKey;
  const labelParts = label.split(/\\n|\n/);
  return (
    <th>
      <button className={`sort-header ${active ? "active" : ""}`} onClick={() => onSort(sortKey)}>
        <span>
          {labelParts.map((part, index) => (
            <React.Fragment key={`${part}-${index}`}>
              {part}
              {index < labelParts.length - 1 ? <br /> : null}
            </React.Fragment>
          ))}
        </span>
        <b>{active ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}</b>
      </button>
    </th>
  );
}

function OpportunityRow({
  item,
  signal,
  onOpenDocuments,
}: {
  item: Opportunity;
  signal: ReturnType<typeof commercialSignal>;
  onOpenDocuments: (item: Opportunity) => void;
}) {
  const proposalDeadline = presentationDeadline(item);
  return (
    <tr>
      <td><span className={`priority p${item.priority}`}>{item.priority}</span></td>
      <td>
        <span className={`commercial-signal ${signal.className}`}>
          <i aria-hidden="true" />
          <span>
            <b>{signal.label}</b>
            <small>{signal.hint}</small>
          </span>
        </span>
      </td>
      <td>{item.entity}</td>
      <td>{item.nomenclature}</td>
      <td>
        <button className="pdf-button" onClick={() => onOpenDocuments(item)} title="Ver detalle y documentos">
          <span>PDF</span>
        </button>
      </td>
      <td>{item.description}</td>
      <td>{formatDate(item.publication_date)}</td>
      <td>{formatDate(item.consultation_deadline)}</td>
      <td>{formatDays(daysUntil(item.consultation_deadline))}</td>
      <td>{formatDate(proposalDeadline)}</td>
      <td>{formatDays(daysUntil(proposalDeadline))}</td>
      <td>{formatMoney(item.amount)}</td>
    </tr>
  );
}

function OpportunityDetailModal({
  opportunity,
  token,
  onClose,
}: {
  opportunity: Opportunity;
  token: string;
  onClose: () => void;
}) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDocuments() {
    setLoading(true);
    setError("");
    try {
      setDocuments(await api.opportunityDocuments(token, opportunity.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar documentos");
    } finally {
      setLoading(false);
    }
  }

  async function discoverDocuments() {
    setLoading(true);
    setError("");
    try {
      setDocuments(await api.discoverDocuments(token, opportunity.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo buscar documentos en SEACE");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, [opportunity.id]);

  const proposalDeadline = presentationDeadline(opportunity);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Detalle del proceso">
      <section className="process-modal">
        <header className="modal-header">
          <h2>Informacion detallada del proceso</h2>
          <button className="modal-close" onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className="modal-body">
          <article className="detail-card">
            <div className="detail-card-title">Informacion general</div>
            <div className="detail-grid">
              <span>Proceso</span><strong>{opportunity.nomenclature || "-"}</strong>
              <span>Fecha</span><strong>{formatDate(opportunity.publication_date)}</strong>
              <span>Entidad</span><strong>{opportunity.entity || "-"}</strong>
              <span>Monto</span><strong>{formatMoney(opportunity.amount)}</strong>
              <span>Consultas</span><strong>{formatDate(opportunity.consultation_deadline)}</strong>
              <span>Propuesta</span><strong>{formatDate(proposalDeadline)}</strong>
              <span>Descripcion</span><p>{opportunity.description || "-"}</p>
            </div>
          </article>
          <article className="detail-card">
            <div className="detail-card-title">
              <span>Documentos del proceso</span>
              <button className={`ghost document-search-button ${loading ? "is-loading" : ""}`} onClick={discoverDocuments} disabled={loading}>
                {loading ? (
                  <>
                    <span className="button-spinner" aria-hidden="true" />
                    <span>Buscando documentos</span>
                  </>
                ) : (
                  "Buscar documentos"
                )}
              </button>
            </div>
            {error ? <div className="notice danger">{error}</div> : null}
            <div className="document-list">
              {documents.map((doc) => (
                <div className="document-row" key={doc.id}>
                  <div>
                    <span className="pdf-badge">PDF</span>
                    <strong>{doc.title || doc.filename || `Documento ${doc.id}`}</strong>
                    <small>{doc.status}{doc.error_message ? ` · ${doc.error_message}` : ""}</small>
                  </div>
                  <div className="document-actions">
                    {doc.status === "downloaded" ? (
                      <a className="doc-link" href={api.documentDownloadUrl(token, doc.id)} target="_blank" rel="noreferrer">Abrir / descargar</a>
                    ) : doc.source_url ? (
                      <a className="doc-link" href={doc.source_url} target="_blank" rel="noreferrer">Abrir fuente</a>
                    ) : null}
                  </div>
                </div>
              ))}
              {!documents.length && !loading ? (
                <Empty text="Aun no hay documentos registrados. Usa Buscar documentos para consultar SEACE desde backend." />
              ) : null}
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}

function formatDays(value: number | null) {
  if (value === null) return "-";
  return `${value}`;
}

function sortValue(item: Opportunity, signal: ReturnType<typeof commercialSignal>, key: SortKey) {
  switch (key) {
    case "priority":
      return item.priority || "";
    case "commercial":
      return commercialOrder(signal.className);
    case "entity":
      return item.entity || "";
    case "nomenclature":
      return item.nomenclature || "";
    case "description":
      return item.description || "";
    case "publication_date":
      return parseDate(item.publication_date);
    case "consultation_deadline":
      return parseDate(item.consultation_deadline);
    case "days_consultation":
      return daysUntil(item.consultation_deadline);
    case "proposal_deadline":
      return parseDate(presentationDeadline(item));
    case "days_proposal":
      return daysUntil(presentationDeadline(item));
    case "amount":
      return item.amount || 0;
    default:
      return "";
  }
}

function commercialOrder(value: CommercialClass) {
  return value === "green" ? 1 : value === "amber" ? 2 : 3;
}

function compareValues(left: string | number | null, right: string | number | null) {
  if (left === null && right === null) return 0;
  if (left === null) return -1;
  if (right === null) return 1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), "es", { numeric: true, sensitivity: "base" });
}

function Alerts({ token, rules, alerts, refresh }: { token: string; rules: AlertRule[]; alerts: Alert[]; refresh: () => Promise<void> }) {
  const [channel, setChannel] = useState("email");
  const [destination, setDestination] = useState("equipo.comercial@empresa.com");
  async function createRule() {
    await api.createAlertRule(token, {
      name: `Radar ${channel} prioridad A`,
      channel,
      destination,
      min_priority: "A",
      hours_before_deadline: 48,
      is_active: true,
    });
    await refresh();
  }
  return (
    <section className="two-col">
      <article className="panel">
        <div className="panel-title"><h2>Reglas de alerta</h2></div>
        <div className="form-stack">
          <label>Canal<select value={channel} onChange={(event) => setChannel(event.target.value)}><option>email</option><option>whatsapp</option><option>message</option></select></label>
          <label>Destino<input value={destination} onChange={(event) => setDestination(event.target.value)} /></label>
          <button className="primary" onClick={createRule}>Crear regla</button>
        </div>
        <div className="list">
          {rules.map((rule) => <div className="list-row" key={rule.id}><strong>{rule.name}</strong><span>{rule.channel} · {rule.destination}</span></div>)}
        </div>
      </article>
      <article className="panel">
        <div className="panel-title"><h2>Eventos generados</h2><span>{alerts.length}</span></div>
        <div className="list">
          {alerts.map((alert) => <div className="list-row" key={alert.id}><strong>{alert.alert_type}</strong><span>{alert.status}</span></div>)}
          {!alerts.length ? <Empty text="Las alertas apareceran cuando una regla coincida con procesos nuevos o vencimientos." /> : null}
        </div>
      </article>
    </section>
  );
}

function Users() {
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>Usuarios y permisos</h2>
          <p>Administracion conectable al modulo actual de usuarios del backend.</p>
        </div>
      </div>
      <div className="notice info">Siguiente paso: formulario de alta, roles operador/visor/admin y bloqueo de usuarios.</div>
    </section>
  );
}

function System({ runs, refresh }: { runs: Run[]; refresh: () => Promise<void> }) {
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>Ejecuciones backend</h2>
        <button className="ghost" onClick={refresh}>Actualizar</button>
      </div>
      <div className="list">
        {runs.slice(0, 20).map((run) => (
          <div className="list-row" key={run.id}>
            <strong>Run #{run.id} · {run.source}</strong>
            <span>{run.status} · {run.rows_found} procesos · {formatDate(run.finished_at || run.started_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function Root() {
  const [token, setToken] = useState(localStorage.getItem("rodar_token") || "");
  const [email, setEmail] = useState(localStorage.getItem("rodar_email") || "");
  if (!token) {
    return (
      <Login
        onLogin={(nextToken, nextEmail) => {
          localStorage.setItem("rodar_token", nextToken);
          localStorage.setItem("rodar_email", nextEmail);
          setToken(nextToken);
          setEmail(nextEmail);
        }}
      />
    );
  }
  return (
    <AppShell
      email={email}
      onLogout={() => {
        localStorage.removeItem("rodar_token");
        localStorage.removeItem("rodar_email");
        setToken("");
      }}
    />
  );
}

createRoot(document.getElementById("root")!).render(<Root />);
