import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, Alert, AlertRule, DocumentRecord, login, Opportunity, Run, Stats } from "./api";
import "./styles.css";

type Page = "Inicio" | "Oportunidades" | "Oportunidades Chile LMP-GC" | "Oportunidades OCDS Peru" | "Alertas" | "Usuarios" | "Sistema";
type Country = "Peru" | "Chile";
type Module = "SEACE Publico" | "Contratos Menores a 8 UIT" | "Oportunidades Chile LMP-GC" | "Ambos modulos";
type CommercialClass = "green" | "amber" | "red";
type SortDirection = "asc" | "desc";
type SearchMode = "append" | "replace";
type OpportunityVariant = "radar" | "ocds";
type MaxResultsMode = "custom" | "all" | "active";
type PendingSearch = { mode: SearchMode; keywords: string[]; runIds: number[] };
type NavIconName = "home" | "target" | "globe" | "database" | "bell" | "users" | "settings";
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

const nav: Page[] = ["Inicio", "Oportunidades", "Oportunidades Chile LMP-GC", "Oportunidades OCDS Peru", "Alertas", "Usuarios", "Sistema"];
const commercialFilters = [
  { label: "Vigente para Consultas y Propuesta", className: "green" },
  { label: "Vigente para Propuesta", className: "amber" },
  { label: "Proceso Culminado", className: "red" },
] as const;
const activeSearchStoragePrefix = "govradar.opportunities.activeSearch";
const monthOptions = [
  ["1", "Enero"],
  ["2", "Febrero"],
  ["3", "Marzo"],
  ["4", "Abril"],
  ["5", "Mayo"],
  ["6", "Junio"],
  ["7", "Julio"],
  ["8", "Agosto"],
  ["9", "Setiembre"],
  ["10", "Octubre"],
  ["11", "Noviembre"],
  ["12", "Diciembre"],
] as const;
const currentYear = new Date().getFullYear();
const yearOptions = Array.from({ length: 6 }, (_, index) => String(currentYear - index));
const rodarLogoUrl = "/assets/Rodarfondoblanco.png";
const countryFlagUrls: Record<Country, string> = {
  Peru: "/assets/flag-peru.svg",
  Chile: "/assets/flag-chile.svg",
};
const excelLogoUrl = "/assets/logoexcel.png";
const navIcons: Record<Page, NavIconName> = {
  Inicio: "home",
  Oportunidades: "target",
  "Oportunidades Chile LMP-GC": "globe",
  "Oportunidades OCDS Peru": "database",
  Alertas: "bell",
  Usuarios: "users",
  Sistema: "settings",
};

function modulesForCountry(country: Country): Module[] {
  return country === "Chile"
    ? ["Oportunidades Chile LMP-GC"]
    : ["SEACE Publico", "Contratos Menores a 8 UIT", "Ambos modulos"];
}

function defaultModuleForCountry(country: Country): Module {
  return country === "Chile" ? "Oportunidades Chile LMP-GC" : "SEACE Publico";
}

function sourceForModule(module: Module) {
  if (module === "Oportunidades Chile LMP-GC") return "mercado_publico_lmp_gc";
  if (module === "Contratos Menores a 8 UIT") return "menor8_browser";
  return "seace_public_browser";
}

function sourceBelongsToCountry(source: string, country: Country) {
  const normalized = source.toLowerCase();
  if (country === "Chile") return normalized.startsWith("mercado_publico");
  return normalized.startsWith("seace") || normalized.includes("menor8") || normalized.startsWith("oece_ocds");
}

function sourceBelongsToView(source: string, country: Country, variant: OpportunityVariant) {
  const normalized = source.toLowerCase();
  if (variant === "ocds") return country === "Peru" && normalized.startsWith("oece_ocds");
  if (country === "Peru") return (normalized.startsWith("seace") || normalized.includes("menor8")) && !normalized.startsWith("oece_ocds");
  return sourceBelongsToCountry(source, country);
}

function formatMoney(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return <span className="reserved-amount">Monto reservado</span>;
  }
  return new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN", maximumFractionDigits: 0 }).format(value || 0);
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-PE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatManualTimestamp(value: string) {
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
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

function toggleSelected(values: string[], value: string) {
  if (values.includes(value)) {
    return values.length > 1 ? values.filter((item) => item !== value) : values;
  }
  return [...values, value];
}

function CountryFlagIcon({ country, className = "" }: { country: Country; className?: string }) {
  return (
    <img
      className={className}
      src={countryFlagUrls[country]}
      alt={country === "Chile" ? "Chile" : "Peru"}
      loading="eager"
    />
  );
}

function NavIcon({ name }: { name: NavIconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
      {name === "home" ? <path {...common} d="M3 11.5 12 4l9 7.5M5 10.5V20h14v-9.5M9 20v-6h6v6" /> : null}
      {name === "target" ? <><circle {...common} cx="12" cy="12" r="8" /><circle {...common} cx="12" cy="12" r="3" /><path {...common} d="M17 7l3-3M17.5 4H20v2.5" /></> : null}
      {name === "globe" ? <><circle {...common} cx="12" cy="12" r="9" /><path {...common} d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></> : null}
      {name === "database" ? <><ellipse {...common} cx="12" cy="5" rx="7" ry="3" /><path {...common} d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></> : null}
      {name === "bell" ? <><path {...common} d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path {...common} d="M10 21h4" /></> : null}
      {name === "users" ? <><path {...common} d="M16 21v-2a4 4 0 0 0-8 0v2" /><circle {...common} cx="12" cy="7" r="4" /><path {...common} d="M22 21v-2a4 4 0 0 0-3-3.8M16 3.2a4 4 0 0 1 0 7.6" /></> : null}
      {name === "settings" ? <><path {...common} d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" /><path {...common} d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3.4-.2-.1a1.7 1.7 0 0 0-2 .2 1.7 1.7 0 0 0-.8 1.7V22H9.2v-.2a1.7 1.7 0 0 0-.8-1.7 1.7 1.7 0 0 0-2-.2l-.2.1-2-3.4.1-.1A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.4-1.1H3v-4h.2a1.7 1.7 0 0 0 1.4-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2-3.4.2.1a1.7 1.7 0 0 0 2-.2A1.7 1.7 0 0 0 9.2 2V2h5.6v.2a1.7 1.7 0 0 0 .8 1.7 1.7 1.7 0 0 0 2 .2l.2-.1 2 3.4-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.4 1.1h.2v4h-.2A1.7 1.7 0 0 0 19.4 15Z" /></> : null}
    </svg>
  );
}

function pageLabel(item: Page) {
  return (
    <span className="nav-label">
      <NavIcon name={navIcons[item]} />
      <span>{item}</span>
    </span>
  );
}

function displayUserName(email: string) {
  if (email.toLowerCase().startsWith("admin@")) return "Admin Hughes";
  return email;
}

function userInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

function datePart(value: string | null, part: "year" | "month") {
  const timestamp = parseDate(value);
  if (timestamp === null) return null;
  const date = new Date(timestamp);
  return part === "year" ? String(date.getFullYear()) : String(date.getMonth() + 1);
}

function uniqueDefined(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((item): item is string => Boolean(item))));
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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
  const startedAt = run.started_at ? new Date(run.started_at).getTime() : now;
  const elapsedSeconds = Math.max(0, (now - startedAt) / 1000);
  if (run.status === "queued") return Math.min(18, 4 + elapsedSeconds * 1.4);

  if (run.status === "running") {
    if (detail.reviewed !== null && detail.requested && detail.requested > 0) {
      return Math.min(94, 12 + (detail.reviewed / detail.requested) * 72);
    }
    return Math.min(92, 8 + elapsedSeconds * 2.6);
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

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function highlightTermsFromKeywords(keywords: string[]) {
  const terms = new Set<string>();
  keywords.forEach((keyword) => {
    const clean = keyword.trim();
    if (clean.length >= 3 && !/^\d+$/.test(clean)) terms.add(clean);
    clean.split(/[,\s;]+/).forEach((part) => {
      const normalized = part.trim();
      if (normalized.length >= 3 && !/^\d+$/.test(normalized)) terms.add(normalized);
    });
  });
  return Array.from(terms).sort((left, right) => right.length - left.length).slice(0, 40);
}

function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
  const cleanText = text || "-";
  const cleanTerms = useMemo(() => highlightTermsFromKeywords(terms), [terms]);
  if (!cleanTerms.length) return <>{cleanText}</>;
  const matcher = new RegExp(`(${cleanTerms.map(escapeRegex).join("|")})`, "gi");
  const lowerTerms = cleanTerms.map((term) => term.toLowerCase());
  return (
    <>
      {cleanText.split(matcher).map((part, index) => {
        const isMatch = lowerTerms.includes(part.toLowerCase());
        return isMatch ? <mark className="keyword-mark" key={`${part}-${index}`}>{part}</mark> : <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
      })}
    </>
  );
}

function moneyText(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "Monto reservado";
  return new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN", maximumFractionDigits: 0 }).format(value || 0);
}

function daysText(value: number | null) {
  if (value === null) return "-";
  if (value < 0) return `Vencido hace ${Math.abs(value)} dias`;
  return String(value);
}

function exportOpportunitiesToExcel(rows: Array<{ item: Opportunity; signal: ReturnType<typeof commercialSignal> }>, title: string) {
  const headers = [
    "Prioridad",
    "Semaforo comercial",
    "Entidad",
    "Proceso",
    "Descripcion",
    "Fecha de convocatoria",
    "Fin Consultas",
    "Dias Consultas",
    "Fin Propuesta",
    "Dias Propuesta",
    "Monto",
  ];
  const body = rows.map(({ item, signal }) => {
    const proposalDeadline = presentationDeadline(item);
    return [
      item.priority,
      `${signal.label} - ${signal.hint}`,
      item.entity,
      item.nomenclature,
      item.description,
      formatDate(item.publication_date),
      formatDate(item.consultation_deadline),
      daysText(daysUntil(item.consultation_deadline)),
      formatDate(proposalDeadline),
      daysText(daysUntil(proposalDeadline)),
      moneyText(item.amount),
    ];
  });
  const html = `<!doctype html><html><head><meta charset="utf-8" /></head><body><table><caption>${escapeHtml(title)}</caption><thead><tr>${headers
    .map((header) => `<th>${escapeHtml(header)}</th>`)
    .join("")}</tr></thead><tbody>${body
    .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table></body></html>`;
  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `oportunidades-${new Date().toISOString().slice(0, 10)}.xls`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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
        <img className="brand-logo" src={rodarLogoUrl} alt="RODAR Consulting" />
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
  const userName = displayUserName(email);

  useEffect(() => {
    if (page === "Oportunidades Chile LMP-GC") {
      setCountry("Chile");
    } else if (page === "Oportunidades" || page === "Oportunidades OCDS Peru") {
      setCountry("Peru");
    }
  }, [page]);

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <aside className="side">
        <div className="side-brand">
          <img className="brand-logo compact" src={rodarLogoUrl} alt="RODAR Consulting" />
          <div>
            <strong>GovRadar CRM</strong>
            <span>RODAR Consulting</span>
          </div>
        </div>
        <nav>
          {nav.map((item) => (
            <button key={item} className={item === page ? "active" : ""} onClick={() => setPage(item)}>
              {pageLabel(item)}
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
            <div className="country-flag-pill" title={country} aria-label={`Modulo ${country}`}>
              <CountryFlagIcon country={country} className="country-flag-image" />
            </div>
            <div className="user-identity" title={userName}>
              <div className="user-pill">{userInitials(userName)}</div>
              <span>{userName}</span>
            </div>
            <button className="ghost" onClick={onLogout}>Salir</button>
          </div>
        </header>
        {backend.error ? <div className="notice danger">{backend.error}</div> : null}
        {page === "Inicio" ? <Home country={country} stats={backend.stats} runs={backend.runs} alerts={backend.alerts} /> : null}
        {page === "Oportunidades" ? <Opportunities country="Peru" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} /> : null}
        {page === "Oportunidades Chile LMP-GC" ? <Opportunities country="Chile" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} /> : null}
        {page === "Oportunidades OCDS Peru" ? <Opportunities country="Peru" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} variant="ocds" /> : null}
        {page === "Alertas" ? <Alerts token={token} rules={backend.rules} alerts={backend.alerts} refresh={backend.refresh} /> : null}
        {page === "Usuarios" ? <Users /> : null}
        {page === "Sistema" ? <System runs={backend.runs} refresh={backend.refresh} /> : null}
      </div>
    </div>
  );
}

function Kpis({ stats }: { stats: Stats | null }) {
  const values: Array<[string, React.ReactNode, string]> = [
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
  variant = "radar",
}: {
  country: Country;
  token: string;
  data: Opportunity[];
  runs: Run[];
  refresh: () => Promise<void>;
  variant?: OpportunityVariant;
}) {
  const storageScope = `${variant}.${country}`;
  const initialSearchState = useMemo(() => loadActiveSearchState(storageScope), [storageScope]);
  const [module, setModule] = useState<Module>(defaultModuleForCountry(country));
  const [keyword, setKeyword] = useState("satelital");
  const [keyword2, setKeyword2] = useState("");
  const [keyword3, setKeyword3] = useState("");
  const [nomenclatureFilter, setNomenclatureFilter] = useState("");
  const [priority, setPriority] = useState("Todas");
  const [ocdsYears, setOcdsYears] = useState<string[]>([String(currentYear)]);
  const [ocdsMonths, setOcdsMonths] = useState<string[]>([String(new Date().getMonth() + 1)]);
  const ocdsYear = ocdsYears[0] || String(currentYear);
  const ocdsMonth = ocdsMonths[0] || String(new Date().getMonth() + 1);
  const setOcdsYear = (value: string) => setOcdsYears([value]);
  const setOcdsMonth = (value: string) => setOcdsMonths([value]);
  const usesPeriodFilters = variant === "ocds" || country === "Chile";
  const [maxResultsMode, setMaxResultsMode] = useState<MaxResultsMode>("active");
  const [maxResults, setMaxResults] = useState(25);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>("append");
  const [activeKeywords, setActiveKeywords] = useState<string[]>(initialSearchState.keywords);
  const [activeRunIds, setActiveRunIds] = useState<number[]>(initialSearchState.runIds);
  const [scopedRows, setScopedRows] = useState<Opportunity[] | null>(null);
  const [pinnedRows, setPinnedRows] = useState<Opportunity[]>([]);
  const [pendingSearch, setPendingSearch] = useState<PendingSearch | null>(null);
  const [confirmNewSearch, setConfirmNewSearch] = useState(false);
  const [confirmClearFields, setConfirmClearFields] = useState(false);
  const visibleRuns = useMemo(() => runs.filter((run) => sourceBelongsToView(run.source, country, variant)), [runs, country, variant]);

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
    saveActiveSearchState(storageScope, activeKeywords, activeRunIds);
  }, [storageScope, activeKeywords, activeRunIds]);

  async function syncPendingSearch(search: PendingSearch, statuses: Run[]) {
    const nextPendingRun = statuses.find((run) => run.status === "queued" || run.status === "running");
    if (nextPendingRun) {
      setActiveRun(nextPendingRun);
      return false;
    }
    const terminal = statuses.every((run) => run.status === "completed" || run.status === "failed");
    if (!terminal) return false;

    await refresh();
    const completedIds = statuses.filter((run) => run.status === "completed").map((run) => run.id);
    const nextKeywords = search.mode === "append" ? addKeywords(activeKeywords, search.keywords) : search.keywords;
    const nextRunIds = search.mode === "append" ? addRunIds(activeRunIds, completedIds) : completedIds;
    const runRows = nextRunIds.length ? await api.opportunities(token, { runIds: nextRunIds }) : [];
    setActiveKeywords(nextKeywords);
    setActiveRunIds(nextRunIds);
    setScopedRows(search.mode === "append" ? mergeOpportunities(pinnedRows, runRows) : runRows);
    setPendingSearch(null);
    setActiveRun(statuses[statuses.length - 1] || null);
    return true;
  }

  useEffect(() => {
    const nextInitialState = loadActiveSearchState(storageScope);
    setModule(defaultModuleForCountry(country));
    setActiveRun(null);
    setActiveKeywords(nextInitialState.keywords);
    setActiveRunIds(nextInitialState.runIds);
    setScopedRows(null);
    setPinnedRows([]);
    setPendingSearch(null);
    setConfirmNewSearch(false);
    setConfirmClearFields(false);
    setSearchMode("append");
  }, [country, storageScope]);

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
          if (pendingSearch?.runIds.includes(nextRun.id)) {
            const statuses = await Promise.all(pendingSearch.runIds.map((runId) => api.run(token, runId)));
            if (cancelled) return;
            await syncPendingSearch(pendingSearch, statuses);
          } else {
            await refresh();
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
    const normalizedNomenclature = nomenclatureFilter.trim().toLowerCase();
    const activeOnly = maxResultsMode === "active";
    return baseRows.filter((item) => {
      if (!sourceBelongsToView(item.source, country, variant)) return false;
      const haystack = `${item.entity} ${item.nomenclature} ${item.description}`.toLowerCase();
      const keywordMatch = !normalizedActiveKeywords.length || normalizedActiveKeywords.some((item) => haystack.includes(item));
      const nomenclatureMatch = !normalizedNomenclature || item.nomenclature.toLowerCase().includes(normalizedNomenclature);
      const priorityMatch = priority === "Todas" || item.priority === priority;
      const activeMatch = !activeOnly || commercialSignal(item).className !== "red";
      const timestamp = parseDate(item.publication_date) ?? parseDate(presentationDeadline(item));
      const date = timestamp !== null ? new Date(timestamp) : null;
      const yearMatch = !usesPeriodFilters || !ocdsYears.length || (date !== null && ocdsYears.includes(String(date.getFullYear())));
      const monthMatch = !usesPeriodFilters || !ocdsMonths.length || (date !== null && ocdsMonths.includes(String(date.getMonth() + 1)));
      return keywordMatch && nomenclatureMatch && priorityMatch && activeMatch && yearMatch && monthMatch;
    });
  }, [baseRows, activeKeywords, nomenclatureFilter, priority, maxResultsMode, country, variant, usesPeriodFilters, ocdsYears, ocdsMonths]);

  useEffect(() => {
    if (!activeRun || activeRun.status !== "completed" || !pendingSearch?.runIds.includes(activeRun.id)) return;
    let cancelled = false;
    Promise.all(pendingSearch.runIds.map((runId) => api.run(token, runId)))
      .then(async (statuses) => {
        if (cancelled) return;
        await syncPendingSearch(pendingSearch, statuses);
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
    const cleanNomenclature = nomenclatureFilter.trim();
    const cleanKeywords = cleanNomenclature
      ? [cleanNomenclature]
      : uniqueKeywords([keyword, keyword2, keyword3]).length
        ? uniqueKeywords([keyword, keyword2, keyword3])
        : ["satelital"];
    const effectiveMaxResults = maxResultsMode === "all" || maxResultsMode === "active" ? 0 : maxResults;
    const forceDetailByNomenclature = Boolean(cleanNomenclature);
    const effectiveMaxDetails = forceDetailByNomenclature ? 1 : 0;
    setConfirmNewSearch(false);
    setStarting(true);
    try {
      if (mode === "replace") {
        setActiveKeywords(cleanKeywords);
        setActiveRunIds([]);
        setPinnedRows([]);
        setScopedRows([]);
      } else {
        setActiveKeywords((current) => addKeywords(current, cleanKeywords));
        if (!activeRunIds.length && scopedRows === null) {
          setPinnedRows(filtered);
        }
      }
      const startedRuns: Run[] = [];
      for (const searchKeyword of cleanKeywords) {
        const run = await api.startRun(token, {
          source: variant === "ocds" ? "oece_ocds_api" : sourceForModule(module),
          keyword: searchKeyword,
          nomenclature: cleanNomenclature || undefined,
          year: usesPeriodFilters ? ocdsYears.join(",") : country === "Peru" ? "2026" : "",
          month: usesPeriodFilters ? ocdsMonths.join(",") : "",
          years: usesPeriodFilters ? ocdsYears : undefined,
          months: usesPeriodFilters ? ocdsMonths : undefined,
          version: variant === "ocds" ? "OCDS OECE" : country === "Peru" ? "Seace 3" : "Mercado Publico",
          max_results: effectiveMaxResults,
          max_details: effectiveMaxDetails,
          enrich_details: forceDetailByNomenclature,
        });
        startedRuns.push(run);
      }
      const runningRun = startedRuns.find((run) => run.status === "queued" || run.status === "running") || startedRuns[startedRuns.length - 1] || null;
      setActiveRun(runningRun);
      setPendingSearch({ mode, keywords: cleanKeywords, runIds: startedRuns.map((run) => run.id) });
      await refresh();
    } finally {
      setStarting(false);
    }
  }

  async function waitForRun(runId: number) {
    for (let index = 0; index < 120; index += 1) {
      const nextRun = await api.run(token, runId);
      setActiveRun(nextRun);
      if (nextRun.status === "completed" || nextRun.status === "failed") return nextRun;
      await delay(1800);
    }
    return api.run(token, runId);
  }

  async function revalidateProposalDate(item: Opportunity) {
    const cleanNomenclature = item.nomenclature.trim();
    if (!cleanNomenclature) return false;
    const detailKeyword = item.description.trim() || cleanNomenclature;
    setStarting(true);
    try {
      const revalidateYears = uniqueDefined([
        ...ocdsYears,
        datePart(item.publication_date, "year"),
        datePart(item.consultation_deadline, "year"),
        datePart(item.proposal_deadline, "year"),
      ]);
      const revalidateMonths = uniqueDefined([
        ...ocdsMonths,
        datePart(item.publication_date, "month"),
        datePart(item.consultation_deadline, "month"),
        datePart(item.proposal_deadline, "month"),
      ]);
      const run = await api.startRun(token, {
        source: variant === "ocds" ? "oece_ocds_api" : sourceForModule(module),
        keyword: detailKeyword,
        nomenclature: cleanNomenclature,
        year: usesPeriodFilters ? revalidateYears.join(",") : country === "Peru" ? "2026" : "",
        month: usesPeriodFilters ? revalidateMonths.join(",") : "",
        years: usesPeriodFilters ? revalidateYears : undefined,
        months: usesPeriodFilters ? revalidateMonths : undefined,
        version: variant === "ocds" ? "OCDS OECE" : country === "Peru" ? "Seace 3" : "Mercado Publico",
        max_results: 1,
        max_details: 12,
        enrich_details: true,
      });
      setActiveRun(run);
      await refresh();
      const finishedRun = await waitForRun(run.id);
      await refresh();
      if (finishedRun.status !== "completed") return false;
      const runRows = await api.opportunities(token, { runIds: [run.id] });
      const updatedRow = runRows.find((row) => row.nomenclature.toLowerCase() === cleanNomenclature.toLowerCase())
        || runRows.find((row) => row.nomenclature.toLowerCase().includes(cleanNomenclature.toLowerCase()) || cleanNomenclature.toLowerCase().includes(row.nomenclature.toLowerCase()));
      const nextRunIds = addRunId(activeRunIds, run.id);
      setActiveRunIds(nextRunIds);
      setActiveKeywords((current) => addKeyword(current, cleanNomenclature));
      setScopedRows((current) => mergeOpportunities(current ?? filtered, runRows));
      return Boolean(updatedRow && presentationDeadline(updatedRow));
    } finally {
      setStarting(false);
    }
  }

  function clearFields() {
    setConfirmClearFields(false);
    setKeyword("");
    setKeyword2("");
    setKeyword3("");
    setNomenclatureFilter("");
    setPriority("Todas");
    setMaxResultsMode("active");
    setMaxResults(25);
    setSearchMode("append");
    setActiveKeywords([]);
    setActiveRunIds([]);
    setScopedRows([]);
    setPinnedRows([]);
    setPendingSearch(null);
    setActiveRun(null);
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>{variant === "ocds" ? "Oportunidades OCDS Peru" : country === "Chile" ? "Oportunidades Chile LMP-GC" : "Radar de oportunidades Peru"}</h2>
          <p>
            {variant === "ocds"
              ? "Consulta la API de Contrataciones Abiertas OECE/OCDS para procesos Peru, incluyendo licitaciones, adjudicaciones, contratos y compras menores publicadas."
              : country === "Peru"
                ? "Ejecuta SEACE en backend headless y revisa avance sin abrir Chrome al usuario."
                : "Ejecuta Mercado Publico en backend headless, separando Chile en una bandeja LMP-GC independiente."}
          </p>
        </div>
        <button className="ghost" onClick={refresh}>Actualizar</button>
      </div>
      {variant !== "ocds" ? (
        <>
          <div className="module-row">
            {modulesForCountry(country).map((item) => (
              <button key={item} className={module === item ? "selected" : ""} onClick={() => setModule(item)}>
                {item}
              </button>
            ))}
          </div>
          {module === "Contratos Menores a 8 UIT" || module === "Ambos modulos" ? <div className="notice info">Menores a 8 UIT queda visible para el flujo, pendiente de estabilizacion del conector.</div> : null}
        </>
      ) : null}
      <div className="active-keywords">
        <span>Vista activa:</span>
        {activeKeywords.map((item) => <b key={item}>{item}</b>)}
      </div>
      {usesPeriodFilters ? (
        <div className="ocds-period-picker">
          <div className="multi-filter">
            <span>Anios</span>
            <div>
              {yearOptions.map((item) => (
                <button key={item} type="button" className={ocdsYears.includes(item) ? "selected" : ""} onClick={() => setOcdsYears((current) => toggleSelected(current, item))}>
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="multi-filter">
            <span>Meses</span>
            <div>
              {monthOptions.map(([value, label]) => (
                <button key={value} type="button" className={ocdsMonths.includes(value) ? "selected" : ""} onClick={() => setOcdsMonths((current) => toggleSelected(current, value))}>
                  {label.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
      <div className="keyword-grid">
        <label>Keyword 1<input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="satelital" /></label>
        <label>Keyword 2<input value={keyword2} onChange={(event) => setKeyword2(event.target.value)} placeholder="internet" /></label>
        <label>Keyword 3<input value={keyword3} onChange={(event) => setKeyword3(event.target.value)} placeholder="conectividad" /></label>
      </div>
      <div className="form-grid">
        <label className="nomenclature-filter">Busqueda por Nomenclatura del Proceso<input value={nomenclatureFilter} onChange={(event) => setNomenclatureFilter(event.target.value)} placeholder="Ej. CP-ABR-2-2026-UGEL-A-1" /></label>
        {false && variant === "ocds" ? (
          <>
            <label>Año<select value={ocdsYear} onChange={(event) => setOcdsYear(event.target.value)}>
              {Array.from({ length: 5 }, (_, index) => String(new Date().getFullYear() - index)).map((item) => <option key={item}>{item}</option>)}
            </select></label>
            <label>Mes<select value={ocdsMonth} onChange={(event) => setOcdsMonth(event.target.value)}>
              {monthOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          </>
        ) : null}
        <label>Prioridad<select value={priority} onChange={(event) => setPriority(event.target.value)}><option>Todas</option><option>A</option><option>B</option><option>C</option></select></label>
        <label>Max resultados
          <div className="max-results-control">
            <select value={maxResultsMode} onChange={(event) => setMaxResultsMode(event.target.value as MaxResultsMode)}>
              <option value="active">Vigentes</option>
              <option value="custom">Cantidad</option>
              <option value="all">Todos</option>
            </select>
            <input type="number" min={1} max={500} value={maxResults} disabled={maxResultsMode !== "custom"} onChange={(event) => setMaxResults(Number(event.target.value))} />
          </div>
        </label>
        <button className="primary" onClick={execute} disabled={starting || (variant === "radar" && (module === "Contratos Menores a 8 UIT" || module === "Ambos modulos"))}>
          {starting ? "Iniciando..." : "Ejecutar radar"}
        </button>
      </div>
      {maxResultsMode === "all" ? (
        <p className="filter-warning">*Tu seleccion incluye procesos ya cerrados y puede tardar mas de lo usual.</p>
      ) : null}
      <div className="search-mode-row" role="radiogroup" aria-label="Modo de busqueda">
        <button className={searchMode === "append" ? "selected" : ""} onClick={() => setSearchMode("append")} type="button">
          Agregar a la busqueda actual
        </button>
        <button className={searchMode === "replace" ? "selected" : ""} onClick={() => setSearchMode("replace")} type="button">
          Iniciar nueva busqueda
        </button>
      </div>
      {activeRun ? <RunProgress run={activeRun} /> : visibleRuns[0] ? <RunProgress run={visibleRuns[0]} /> : null}
      <OpportunityTable
        rows={filtered}
        token={token}
        resetKey={`${storageScope}:${activeKeywords.join("|")}:${activeRunIds.join(",")}:${nomenclatureFilter}`}
        onRevalidateProposal={revalidateProposalDate}
        highlightTerms={activeKeywords}
        onRequestClearFields={() => setConfirmClearFields(true)}
      />
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
      {confirmClearFields ? (
        <ConfirmModal
          title="Limpiar campos"
          message="Esta seguro de limpiar? Para obtener los datos tendras que aplicar filtros y busquedas nuevamente."
          confirmLabel="Si, limpiar"
          cancelLabel="No"
          onConfirm={clearFields}
          onCancel={() => setConfirmClearFields(false)}
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

function uniqueKeywords(values: string[]) {
  return values.reduce<string[]>((items, value) => addKeyword(items, value), []);
}

function addKeywords(current: string[], keywords: string[]) {
  return keywords.reduce((items, keyword) => addKeyword(items, keyword), current);
}

function addRunId(current: number[], runId: number) {
  return current.includes(runId) ? current : [...current, runId];
}

function addRunIds(current: number[], runIds: number[]) {
  return runIds.reduce((items, runId) => addRunId(items, runId), current);
}

function mergeOpportunities(left: Opportunity[], right: Opportunity[]) {
  const byId = new Map<number, Opportunity>();
  [...left, ...right].forEach((item) => byId.set(item.id, item));
  return [...byId.values()];
}

function activeSearchStorageKey(scope: string) {
  return `${activeSearchStoragePrefix}.${scope}`;
}

function loadActiveSearchState(scope: string): { keywords: string[]; runIds: number[] } {
  try {
    const raw = window.localStorage.getItem(activeSearchStorageKey(scope));
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

function saveActiveSearchState(scope: string, keywords: string[], runIds: number[]) {
  try {
    window.localStorage.setItem(activeSearchStorageKey(scope), JSON.stringify({ keywords, runIds }));
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

function OpportunityTable({
  rows,
  token,
  resetKey,
  onRevalidateProposal,
  highlightTerms,
  onRequestClearFields,
}: {
  rows: Opportunity[];
  token: string;
  resetKey: string;
  onRevalidateProposal: (item: Opportunity) => Promise<boolean>;
  highlightTerms: string[];
  onRequestClearFields: () => void;
}) {
  const [commercialFilter, setCommercialFilter] = useState<CommercialClass | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "publication_date",
    direction: "desc",
  });
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());
  const [pendingRemoval, setPendingRemoval] = useState<Opportunity | null>(null);
  const [revalidatingIds, setRevalidatingIds] = useState<Set<number>>(new Set());
  const [unavailableProposalIds, setUnavailableProposalIds] = useState<Set<number>>(new Set());
  const [manualProposalUpdates, setManualProposalUpdates] = useState<Map<number, string>>(new Map());
  const topScrollRef = useRef<HTMLDivElement | null>(null);
  const tableScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setRemovedIds(new Set());
    setPendingRemoval(null);
    setUnavailableProposalIds(new Set());
    setManualProposalUpdates(new Map());
  }, [resetKey]);

  const rowsWithSignals = useMemo(
    () => rows.map((item) => ({ item, signal: commercialSignal(item) })),
    [rows],
  );

  const filteredRows = useMemo(() => {
    return rowsWithSignals.filter(({ item, signal }) => !removedIds.has(item.id) && (!commercialFilter || signal.className === commercialFilter));
  }, [rowsWithSignals, commercialFilter, removedIds]);

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

  function confirmRemove(item: Opportunity) {
    setPendingRemoval(item);
  }

  function removePendingRow() {
    if (!pendingRemoval) return;
    setRemovedIds((current) => new Set(current).add(pendingRemoval.id));
    setPendingRemoval(null);
  }

  async function revalidateRow(item: Opportunity) {
    setRevalidatingIds((current) => new Set(current).add(item.id));
    setUnavailableProposalIds((current) => {
      const next = new Set(current);
      next.delete(item.id);
      return next;
    });
    try {
      const found = await onRevalidateProposal(item);
      if (!found) {
        setUnavailableProposalIds((current) => new Set(current).add(item.id));
      } else {
        setManualProposalUpdates((current) => new Map(current).set(item.id, new Date().toISOString()));
      }
    } finally {
      setRevalidatingIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  }

  return (
    <>
      <div className="table-toolbar">
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
        <div className="table-action-buttons">
          <button className="clear-fields-button" type="button" onClick={onRequestClearFields}>
            Limpiar Campos
          </button>
          <button className="export-excel-button" type="button" onClick={() => exportOpportunitiesToExcel(sortedRows, "Oportunidades GovRadar")}>
            <img src={excelLogoUrl} alt="" aria-hidden="true" />
            <span>Exportar a Excel</span>
          </button>
        </div>
      </div>
      <div className="table-scroll-top" ref={topScrollRef} onScroll={() => syncTableScroll("top")} aria-label="Desplazamiento horizontal de oportunidades">
        <div />
      </div>
      <div className="table-wrap" ref={tableScrollRef} onScroll={() => syncTableScroll("table")}>
        <table>
          <thead>
            <tr>
              <SortableTh label="Prioridad" sortKey="priority" sort={sort} onSort={updateSort} />
              <SortableTh label="Semaforo\ncomercial" sortKey="commercial" sort={sort} onSort={updateSort} />
              <SortableTh label="Entidad" sortKey="entity" sort={sort} onSort={updateSort} />
              <SortableTh label="Proceso" sortKey="nomenclature" sort={sort} onSort={updateSort} />
              <th><span className="plain-header">Documentos</span></th>
              <SortableTh label="Descripcion" sortKey="description" sort={sort} onSort={updateSort} />
              <SortableTh label="Fecha de\nconvocatoria" sortKey="publication_date" sort={sort} onSort={updateSort} />
              <SortableTh label="Fin\nConsultas" sortKey="consultation_deadline" sort={sort} onSort={updateSort} />
              <SortableTh label="Dias\nConsultas" sortKey="days_consultation" sort={sort} onSort={updateSort} />
              <SortableTh label="Fin\nPropuesta" sortKey="proposal_deadline" sort={sort} onSort={updateSort} />
              <SortableTh label="Dias\nPropuesta" sortKey="days_proposal" sort={sort} onSort={updateSort} />
              <SortableTh label="Monto" sortKey="amount" sort={sort} onSort={updateSort} />
            </tr>
          </thead>
          <tbody>
            {sortedRows.slice(0, 100).map(({ item, signal }) => (
              <OpportunityRow
                item={item}
                signal={signal}
                key={item.id}
                onOpenDocuments={setSelectedOpportunity}
                onRemove={confirmRemove}
                onRevalidateProposal={revalidateRow}
                isRevalidating={revalidatingIds.has(item.id)}
                proposalUnavailable={unavailableProposalIds.has(item.id)}
                highlightTerms={highlightTerms}
                manualProposalUpdatedAt={manualProposalUpdates.get(item.id) || null}
              />
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
      {pendingRemoval ? (
        <ConfirmModal
          title="Retirar de esta vista"
          message="Estas seguro de retirar? Para recuperar tendras que filtrar nuevamente o ingresar la nomenclatura."
          confirmLabel="Si, retirar"
          cancelLabel="No"
          onConfirm={removePendingRow}
          onCancel={() => setPendingRemoval(null)}
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
  onRemove,
  onRevalidateProposal,
  isRevalidating,
  proposalUnavailable,
  highlightTerms,
  manualProposalUpdatedAt,
}: {
  item: Opportunity;
  signal: ReturnType<typeof commercialSignal>;
  onOpenDocuments: (item: Opportunity) => void;
  onRemove: (item: Opportunity) => void;
  onRevalidateProposal: (item: Opportunity) => Promise<void>;
  isRevalidating: boolean;
  proposalUnavailable: boolean;
  highlightTerms: string[];
  manualProposalUpdatedAt: string | null;
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
      <td>
        <div className="process-cell">
          <span>{item.nomenclature}</span>
          <button className="remove-view-button" type="button" onClick={() => onRemove(item)}>Retirar de esta vista</button>
        </div>
      </td>
      <td>
        <button className="pdf-button" onClick={() => onOpenDocuments(item)} title="Ver detalle y documentos">
          <span>PDF</span>
        </button>
      </td>
      <td><HighlightedText text={item.description} terms={highlightTerms} /></td>
      <td>{formatDate(item.publication_date)}</td>
      <td>{formatDate(item.consultation_deadline)}</td>
      <td>{formatDays(daysUntil(item.consultation_deadline))}</td>
      <td>
        {proposalDeadline ? (
          manualProposalUpdatedAt ? (
            <span className="manual-proposal-date">
              <b>{formatDate(proposalDeadline)}</b>
              <small>*Actualizado manual desde Seace ({formatManualTimestamp(manualProposalUpdatedAt)})</small>
            </span>
          ) : (
            formatDate(proposalDeadline)
          )
        ) : proposalUnavailable ? (
          <span className="proposal-unavailable">Fecha no Disponible en Seace</span>
        ) : (
          <button className="revalidate-button" type="button" disabled={isRevalidating} onClick={() => onRevalidateProposal(item)}>
            {isRevalidating ? (
              <>
                <span className="button-spinner compact" aria-hidden="true" />
                <span>Procesando en SV3</span>
              </>
            ) : (
              "Revalidar fecha de fin propuesta en SV3"
            )}
          </button>
        )}
      </td>
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
  if (value < 0) {
    return (
      <span className="overdue-days">
        <span>Vencido hace</span>
        <b>{Math.abs(value)} dias</b>
      </span>
    );
  }
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
