import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, historicoApi, Alert, AlertRule, APP_MODULES, AppModule, confirmPasswordReset, CountryCode, login, Opportunity, parseAccessProfile, parseModuleAccess, requestPasswordReset, Run, setUnauthorizedHandler, Stats, UserRecord } from "./api";
import "./ui/tokens.css";
import "./styles.css";
import "./ui/ui.css";
import "./ui/legacy-bridge.css";
import { applyTenantBrand, DEFAULT_BRAND } from "./ui/brand";
import { Country, LegalDialog, LegalDocumentsMap, LegalView, countryFlagUrls, userInitials } from "./shared";
import { AppShell as UiAppShell, CountryOption, CountrySelector, IconName, NavSection, PageHeader } from "./ui";

const Home = lazy(() => import("./pages/HomePage"));
const Opportunities = lazy(() => import("./pages/OpportunitiesPage"));
const ArchivedProcesses = lazy(() => import("./pages/OpportunitiesPage").then((module) => ({ default: module.ArchivedProcesses })));
const Alerts = lazy(() => import("./pages/AlertsPage"));
const Users = lazy(() => import("./pages/UsersPage"));
const System = lazy(() => import("./pages/SystemPage"));
const OpportunityTrackingChile = lazy(() => import("./pages/OpportunityTrackingPage"));
const OpportunityTrackingPeru = lazy(() => import("./pages/OpportunityTrackingPage").then((module) => ({ default: module.OpportunityTrackingPeru })));
const HistoricoResumen = lazy(() => import("./pages/historico/HistoricoPages").then((module) => ({ default: module.HistoricoResumen })));
const HistoricoContrataciones = lazy(() => import("./pages/historico/HistoricoPages").then((module) => ({ default: module.HistoricoContrataciones })));
const HistoricoVencimientos = lazy(() => import("./pages/historico/HistoricoPages").then((module) => ({ default: module.HistoricoVencimientos })));
const HistoricoPac = lazy(() => import("./pages/historico/HistoricoPages").then((module) => ({ default: module.HistoricoPac })));
const HistoricoAlertas = lazy(() => import("./pages/historico/HistoricoPages").then((module) => ({ default: module.HistoricoAlertas })));
const UiPreview = lazy(() => import("./ui/UiPreview"));
const OpportunityTrackingArgentina = lazy(() => import("./pages/OpportunityTrackingPage").then((module) => ({ default: module.OpportunityTrackingArgentina })));

type Page = "Inicio Peru" | "Inicio Chile" | "Inicio Argentina" | "Oportunidades" | "Oportunidades Chile LMP-GC" | "Procesos COMPR.AR Argentina" | "Publicaciones COMPR.AR Argentina" | "Oportunidades OCDS Peru" | "Histórico Procesos Eliminados PE" | "Histórico Procesos Eliminados CL" | "Histórico Procesos Eliminados AR" | "Alertas" | "Seguimiento de Oportunidades Peru" | "Seguimiento de Oportunidades Chile" | "Seguimiento de Oportunidades Argentina" | "Usuarios" | "Sistema" | HistoricoPage;

type HistoricoPage = "Resumen Histórico Perú" | "Historial de Contrataciones" | "Contratos por Vencer" | "PAC Perú" | "Alertas Histórico Perú";


// Histórico Perú is a separate product module (monthly CONOSCE open data),
// gated by User.module_access rather than by the per-country access_profile.
const historicoPages: HistoricoPage[] = ["Resumen Histórico Perú", "Historial de Contrataciones", "Contratos por Vencer", "PAC Perú", "Alertas Histórico Perú"];
const adminPages: Page[] = ["Usuarios", "Sistema"];

function isHistoricoPage(page: Page): page is HistoricoPage {
  return (historicoPages as Page[]).includes(page);
}

const rodarLogoUrl = "/assets/Rodarfondoblanco.png";

const pagesByCountry: Record<CountryCode, Page[]> = {
  peru: ["Inicio Peru", "Oportunidades OCDS Peru", "Histórico Procesos Eliminados PE", "Alertas", "Seguimiento de Oportunidades Peru"],
  chile: ["Inicio Chile", "Oportunidades Chile LMP-GC", "Histórico Procesos Eliminados CL", "Alertas", "Seguimiento de Oportunidades Chile"],
  argentina: ["Inicio Argentina", "Procesos COMPR.AR Argentina", "Publicaciones COMPR.AR Argentina", "Histórico Procesos Eliminados AR", "Alertas", "Seguimiento de Oportunidades Argentina"],
};





const launcherDescriptions: Record<Page, string> = {
  "Inicio Peru": "Resumen operativo de procesos SEACE",
  "Inicio Chile": "Resumen comercial de Mercado Público",
  "Inicio Argentina": "Resumen comercial de COMPR.AR",
  Oportunidades: "Radar de oportunidades de Perú",
  "Oportunidades Chile LMP-GC": "Licitaciones y Grandes Compras",
  "Oportunidades OCDS Peru": "Contrataciones abiertas OECE/OCDS",
  "Procesos COMPR.AR Argentina": "Procesos y publicaciones de COMPR.AR",
  "Publicaciones COMPR.AR Argentina": "Contrataciones difundidas en el portal",
  "Histórico Procesos Eliminados PE": "Respaldo de procesos retirados de Perú",
  "Histórico Procesos Eliminados CL": "Respaldo de procesos retirados de Chile",
  "Histórico Procesos Eliminados AR": "Respaldo de procesos retirados de Argentina",
  Alertas: "Reglas, canales y notificaciones",
  "Seguimiento de Oportunidades Peru": "Fases, etapas y responsables — Perú",
  "Seguimiento de Oportunidades Chile": "Fases, etapas y responsables — Chile",
  "Seguimiento de Oportunidades Argentina": "Fases, etapas y responsables — Argentina",
  Usuarios: "Accesos, perfiles y permisos",
  Sistema: "Ejecuciones y configuración",
  "Resumen Histórico Perú": "Cuánto, quién y dónde compra el Estado",
  "Historial de Contrataciones": "Órdenes ≤ 8 UIT y adjudicaciones desde 2023",
  "Contratos por Vencer": "Vencimientos > 8 UIT y compras recurrentes",
  "PAC Perú": "Procesos programados en el Plan Anual",
  "Alertas Histórico Perú": "Prioridades comerciales del mes",
};


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

  useEffect(() => {
    if (!token) return;
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const timer = window.setInterval(refreshWhenVisible, 60_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [token]);

  return { stats, opportunities, runs, rules, alerts, loading, error, refresh, setRuns, setRules };
}

type LoginMode = "login" | "forgot" | "reset";

const PASSWORD_RESET_COOLDOWN_MS = 5 * 60 * 1000;
const PASSWORD_RESET_COOLDOWN_KEY = "password_reset_cooldown_until";

function formatCooldownRemaining(ms: number) {
  const totalSeconds = Math.ceil(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} m ${String(seconds).padStart(2, "0")} s`;
}

function useLegalDocuments() {
  const [documents, setDocuments] = useState<LegalDocumentsMap>({});
  const [error, setError] = useState("");

  useEffect(() => {
    api.legalDocuments()
      .then((items) => {
        setDocuments(Object.fromEntries(items.map((item) => [item.key, item])) as LegalDocumentsMap);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "No se pudo cargar la información legal"));
  }, []);

  return { documents, setDocuments, error };
}

function Login({ onLogin, resetToken = "" }: { onLogin: (token: string, email: string) => void; resetToken?: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState<LoginMode>(resetToken ? "reset" : "login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [legalView, setLegalView] = useState<LegalView | null>(null);
  const [resetCooldownEndsAt, setResetCooldownEndsAt] = useState<number | null>(() => {
    const stored = Number(localStorage.getItem(PASSWORD_RESET_COOLDOWN_KEY) || 0);
    return stored > Date.now() ? stored : null;
  });
  const [now, setNow] = useState(() => Date.now());
  const legalDocuments = useLegalDocuments();

  const resetCooldownRemainingMs = resetCooldownEndsAt ? Math.max(0, resetCooldownEndsAt - now) : 0;
  const resetCooldownActive = resetCooldownRemainingMs > 0;

  useEffect(() => {
    if (!resetCooldownEndsAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [resetCooldownEndsAt]);

  useEffect(() => {
    if (resetCooldownEndsAt && resetCooldownRemainingMs <= 0) {
      setResetCooldownEndsAt(null);
      localStorage.removeItem(PASSWORD_RESET_COOLDOWN_KEY);
    }
  }, [resetCooldownRemainingMs, resetCooldownEndsAt]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      if (mode === "forgot") {
        if (resetCooldownActive) return;
        const result = await requestPasswordReset(email);
        setSuccess(result.message);
        const endsAt = Date.now() + PASSWORD_RESET_COOLDOWN_MS;
        setResetCooldownEndsAt(endsAt);
        setNow(Date.now());
        localStorage.setItem(PASSWORD_RESET_COOLDOWN_KEY, String(endsAt));
      } else if (mode === "reset") {
        if (password !== passwordConfirmation) {
          throw new Error("Las contraseñas no coinciden.");
        }
        const result = await confirmPasswordReset(resetToken, password);
        window.history.replaceState({}, "", window.location.pathname);
        setSuccess(result.message);
        setPassword("");
        setPasswordConfirmation("");
        setMode("login");
      } else {
        const result = await login(email, password);
        onLogin(result.access_token, email);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo completar la solicitud");
    } finally {
      setLoading(false);
    }
  }

  function changeMode(nextMode: LoginMode) {
    setMode(nextMode);
    setError("");
    setSuccess("");
  }

  const content = mode === "forgot"
    ? { title: "Recuperar acceso", description: "Ingresa tu correo corporativo y te enviaremos un enlace seguro.", action: "Enviar enlace" }
    : mode === "reset"
      ? { title: "Nueva contraseña", description: "Crea una contraseña segura para recuperar el acceso a GovRadar.", action: "Guardar contraseña" }
      : { title: "Iniciar sesión", description: "Ingresa al panel productivo sin la capa técnica de Streamlit.", action: "Acceder" };

  return (
    <main className="login-shell">
      <section className="login-brand">
        <img className="brand-logo login-brand-logo" src={rodarLogoUrl} alt="RODAR Consulting" />
        <h1>Radar comercial para procesos de gobierno.</h1>
        <p>
          Detecta oportunidades de negocio con gobierno en Perú, Chile y Argentina de forma simple y personalizable.
        </p>
        <div className="brand-grid">
          <span>Peru operativo</span>
          <span>Chile operativo</span>
          <span>Argentina operativa</span>
          <span>Email y WhatsApp</span>
          <span>Documentos trazables</span>
        </div>
        <p className="login-brand-legal">© 2026 Rodar Consulting S.A.C.™ Todos los derechos reservados.</p>
        <div className="login-live-radar" aria-hidden="true">
          <span className="login-radar-ring login-radar-ring-middle" />
          <span className="login-radar-ring login-radar-ring-inner" />
          <span className="login-radar-crosshair login-radar-crosshair-horizontal" />
          <span className="login-radar-crosshair login-radar-crosshair-vertical" />
          <span className="login-radar-sweep" />
          <span className="login-radar-contact login-radar-contact-one" />
          <span className="login-radar-contact login-radar-contact-two" />
          <span className="login-radar-core" />
        </div>
        <div className="login-country-flags" aria-label="Operación en Perú, Chile y Argentina">
          <img src={countryFlagUrls.Peru} alt="Bandera de Perú" />
          <img src={countryFlagUrls.Chile} alt="Bandera de Chile" />
          <img src={countryFlagUrls.Argentina} alt="Bandera de Argentina" />
        </div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <div>
          <p className="overline">Acceso CRM</p>
          <h2>{content.title}</h2>
          <p className="muted">{content.description}</p>
        </div>
        {mode !== "reset" ? (
          <label>
            Correo corporativo
            <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" placeholder="Ej. nombre@empresa.com" />
          </label>
        ) : null}
        {mode !== "forgot" ? (
          <label>
            {mode === "reset" ? "Nueva contraseña" : "Contraseña"}
            <input required minLength={mode === "reset" ? 8 : undefined} value={password} onChange={(event) => setPassword(event.target.value)} type={showPassword ? "text" : "password"} autoComplete={mode === "reset" ? "new-password" : "current-password"} placeholder={mode === "reset" ? "Mínimo 8 caracteres" : "Ingresa tu contraseña"} />
          </label>
        ) : null}
        {mode === "reset" ? (
          <label>
            Confirmar nueva contraseña
            <input required minLength={8} value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} type={showPassword ? "text" : "password"} autoComplete="new-password" placeholder="Repite tu nueva contraseña" />
          </label>
        ) : null}
        {mode !== "forgot" ? (
          <label className="password-visibility-toggle">
            <input
              type="checkbox"
              role="switch"
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
            />
            <span className="password-switch-track" aria-hidden="true"><span /></span>
            <span>Mostrar contraseña</span>
          </label>
        ) : null}
        {error ? <div className="notice danger" role="alert">{error}</div> : null}
        {success ? <div className="notice success" role="status">{success}</div> : null}
        {mode === "forgot" && resetCooldownActive ? (
          <p className="reset-cooldown-notice">Link de restauración enviado, si no lo ubicas vuelve a intentarlo en:</p>
        ) : null}
        <button className="primary" disabled={loading || (mode === "forgot" && resetCooldownActive)}>{loading ? "Procesando..." : content.action}</button>
        {mode === "forgot" && resetCooldownActive ? (
          <p className="reset-cooldown-timer" role="status" aria-live="polite">{formatCooldownRemaining(resetCooldownRemainingMs)}</p>
        ) : null}
        {mode === "login" ? (
          <p className="login-acceptance">
            Al ingresar, aceptas nuestros{" "}
            <button type="button" onClick={() => setLegalView("terms")}>Términos de Servicio</button> y{" "}
            <button type="button" onClick={() => setLegalView("privacy")}>Política de Privacidad</button>.
          </p>
        ) : null}
        {mode === "login" ? <button className="login-link" type="button" onClick={() => changeMode("forgot")}>¿Olvidaste tu contraseña?</button> : null}
        {mode === "forgot" ? <button className="login-link" type="button" onClick={() => changeMode("login")}>Volver a iniciar sesión</button> : null}
      </form>
      {legalView ? <LegalDialog view={legalView} documents={legalDocuments.documents} onClose={() => setLegalView(null)} /> : null}
    </main>
  );
}

type RadarRole = "inicio" | "oportunidades" | "publicaciones" | "seguimiento" | "eliminados";

// Radar navigation per country; the CountrySelector swaps the country and
// keeps the same section (Oportunidades Perú -> Oportunidades Chile).
const radarNav: Record<CountryCode, Array<{ role: RadarRole; page: Page; label: string; shortLabel: string; icon: IconName }>> = {
  peru: [
    { role: "inicio", page: "Inicio Peru", label: "Inicio", shortLabel: "Inicio", icon: "home" },
    { role: "oportunidades", page: "Oportunidades OCDS Peru", label: "Oportunidades", shortLabel: "Oport.", icon: "target" },
    { role: "seguimiento", page: "Seguimiento de Oportunidades Peru", label: "Seguimiento", shortLabel: "Seguim.", icon: "tracking" },
    { role: "eliminados", page: "Histórico Procesos Eliminados PE", label: "Procesos eliminados", shortLabel: "Elimin.", icon: "database" },
  ],
  chile: [
    { role: "inicio", page: "Inicio Chile", label: "Inicio", shortLabel: "Inicio", icon: "home" },
    { role: "oportunidades", page: "Oportunidades Chile LMP-GC", label: "Oportunidades", shortLabel: "Oport.", icon: "target" },
    { role: "seguimiento", page: "Seguimiento de Oportunidades Chile", label: "Seguimiento", shortLabel: "Seguim.", icon: "tracking" },
    { role: "eliminados", page: "Histórico Procesos Eliminados CL", label: "Procesos eliminados", shortLabel: "Elimin.", icon: "database" },
  ],
  argentina: [
    { role: "inicio", page: "Inicio Argentina", label: "Inicio", shortLabel: "Inicio", icon: "home" },
    { role: "oportunidades", page: "Procesos COMPR.AR Argentina", label: "Oportunidades", shortLabel: "Oport.", icon: "target" },
    { role: "publicaciones", page: "Publicaciones COMPR.AR Argentina", label: "Publicaciones", shortLabel: "Public.", icon: "file" },
    { role: "seguimiento", page: "Seguimiento de Oportunidades Argentina", label: "Seguimiento", shortLabel: "Seguim.", icon: "tracking" },
    { role: "eliminados", page: "Histórico Procesos Eliminados AR", label: "Procesos eliminados", shortLabel: "Elimin.", icon: "database" },
  ],
};

const historicoNav: Array<{ page: HistoricoPage; label: string; shortLabel: string; icon: IconName }> = [
  { page: "Resumen Histórico Perú", label: "Resumen", shortLabel: "Resumen", icon: "chart" },
  { page: "Historial de Contrataciones", label: "Historial de contrataciones", shortLabel: "Historial", icon: "database" },
  { page: "Contratos por Vencer", label: "Contratos por vencer", shortLabel: "Por vencer", icon: "clock" },
  { page: "PAC Perú", label: "PAC Perú", shortLabel: "PAC", icon: "file" },
  { page: "Alertas Histórico Perú", label: "Alertas", shortLabel: "Alertas", icon: "bell" },
];

const countryCodeOf: Record<Country, CountryCode> = { Peru: "peru", Chile: "chile", Argentina: "argentina" };
const countryOfCode: Record<CountryCode, Country> = { peru: "Peru", chile: "Chile", argentina: "Argentina" };
const countryOptions: Record<CountryCode, CountryOption<Country>> = {
  peru: { value: "Peru", label: "Perú", code: "PE", flagUrl: countryFlagUrls.Peru },
  chile: { value: "Chile", label: "Chile", code: "CL", flagUrl: countryFlagUrls.Chile },
  argentina: { value: "Argentina", label: "Argentina", code: "AR", flagUrl: countryFlagUrls.Argentina },
};

function countryOfPage(page: Page): Country | null {
  for (const code of Object.keys(radarNav) as CountryCode[]) {
    if (radarNav[code].some((item) => item.page === page)) return countryOfCode[code];
  }
  if (page === "Oportunidades" || isHistoricoPage(page)) return "Peru";
  return null;
}

function pageTitle(page: Page): string {
  const radar = Object.values(radarNav).flat().find((item) => item.page === page);
  if (radar) return radar.label;
  const historico = historicoNav.find((item) => item.page === page);
  if (historico) return historico.label;
  if (page === "Sistema") return "Configuración";
  return page;
}

function AppShell({ onLogout }: { onLogout: () => void }) {
  const token = localStorage.getItem("rodar_token") || "";
  const [page, setPage] = useState<Page>("Inicio Peru");
  const [country, setCountry] = useState<Country>("Peru");
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [keywordSearchHandoff, setKeywordSearchHandoff] = useState<{ country: Country; keyword: string } | null>(null);
  const [opportunityHandoff, setOpportunityHandoff] = useState<{ country: Country; opportunityId: number } | null>(null);
  const [homeScrollSignal, setHomeScrollSignal] = useState(0);
  const [legalView, setLegalView] = useState<LegalView | null>(null);
  const [versionLabel, setVersionLabel] = useState("Versión 1.0 (Beta)");
  const [historicoUrgent, setHistoricoUrgent] = useState(0);
  const brand = DEFAULT_BRAND;
  const legalDocuments = useLegalDocuments();
  const backend = useBackend(token);
  const userName = currentUser?.full_name || "Cargando usuario…";
  const allowedModules = useMemo<AppModule[]>(() => {
    if (!currentUser) return ["radar"];
    if (currentUser.role === "admin") return [...APP_MODULES];
    const modules = parseModuleAccess(currentUser.module_access);
    return modules.length ? modules : ["radar"];
  }, [currentUser]);
  const allowedCountries = useMemo<CountryCode[]>(
    () => (currentUser ? parseAccessProfile(currentUser.access_profile) : ["peru"]),
    [currentUser],
  );
  const visibleNav = useMemo(() => {
    const radarPages = allowedModules.includes("radar") ? allowedCountries.flatMap((code) => [...pagesByCountry[code], ...radarNav[code].map((item) => item.page)]) : [];
    const moduleHistorico = allowedModules.includes("historico_peru") ? historicoPages : [];
    const allowed = Array.from(new Set<Page>([...radarPages, ...moduleHistorico]));
    return currentUser?.role === "admin" ? [...allowed, ...adminPages] : allowed;
  }, [currentUser, allowedModules, allowedCountries]);
  const activeModule: AppModule = isHistoricoPage(page) ? "historico_peru" : "radar";
  const isAdmin = currentUser?.role === "admin";

  useEffect(() => {
    api.appSettings()
      .then((settings) => setVersionLabel(settings.version_label))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    api.me(token)
      .then((user) => {
        setCurrentUser(user);
        setSessionError("");
      })
      .catch((error) => setSessionError(error instanceof Error ? error.message : "No se pudo cargar el perfil del usuario"));
  }, [token]);

  useEffect(() => {
    if (currentUser && !visibleNav.includes(page)) {
      if (!allowedModules.includes("radar")) {
        setPage("Resumen Histórico Perú");
        return;
      }
      const firstCountry = parseAccessProfile(currentUser.access_profile)[0];
      setPage(firstCountry === "chile" ? "Inicio Chile" : firstCountry === "argentina" ? "Inicio Argentina" : "Inicio Peru");
    }
  }, [currentUser, page, visibleNav, allowedModules]);

  useEffect(() => {
    const pageCountry = countryOfPage(page);
    if (pageCountry) setCountry(pageCountry);
  }, [page]);

  useEffect(() => {
    // Badge for the Histórico alerts tab: open critical alerts.
    if (!currentUser || !allowedModules.includes("historico_peru")) return;
    historicoApi.alerts(token, { page_size: 1 })
      .then((result) => setHistoricoUrgent(result.counts?.P1 ?? 0))
      .catch(() => setHistoricoUrgent(0));
  }, [currentUser, allowedModules, token, page === "Alertas Histórico Perú"]);

  function changeModule(next: AppModule) {
    if (next === activeModule) return;
    if (next === "historico_peru") setPage("Resumen Histórico Perú");
    else setPage(radarNav[countryCodeOf[country]][0].page);
  }

  function changeCountry(next: Country) {
    const role = radarNav[countryCodeOf[country]].find((item) => item.page === page)?.role ?? "inicio";
    const target = radarNav[countryCodeOf[next]].find((item) => item.role === role) ?? radarNav[countryCodeOf[next]][0];
    setCountry(next);
    if (activeModule === "radar" && (countryOfPage(page) || page === "Alertas")) setPage(target.page);
  }

  function openKeywordSearch(targetCountry: Country, keyword: string) {
    setKeywordSearchHandoff({ country: targetCountry, keyword });
    setPage(targetCountry === "Chile" ? "Oportunidades Chile LMP-GC" : targetCountry === "Argentina" ? "Procesos COMPR.AR Argentina" : "Oportunidades OCDS Peru");
  }

  function openOpportunityDetail(targetCountry: Country, opportunityId: number, recordType?: string) {
    setOpportunityHandoff({ country: targetCountry, opportunityId });
    setPage(
      targetCountry === "Chile"
        ? "Oportunidades Chile LMP-GC"
        : targetCountry === "Argentina"
          ? recordType === "publicacion"
            ? "Publicaciones COMPR.AR Argentina"
            : "Procesos COMPR.AR Argentina"
          : "Oportunidades OCDS Peru",
    );
  }

  function goToHomeAndScrollToMap(targetCountry: Country) {
    setPage(targetCountry === "Chile" ? "Inicio Chile" : targetCountry === "Argentina" ? "Inicio Argentina" : "Inicio Peru");
    setHomeScrollSignal((current) => current + 1);
  }

  const countryCode = countryCodeOf[country];
  const adminSection: NavSection | null = isAdmin
    ? { label: "Administración", items: [
      { id: "Usuarios", label: "Usuarios", icon: "users" },
      { id: "Sistema", label: "Configuración", shortLabel: "Config.", icon: "settings" },
    ] }
    : null;
  const sections: NavSection[] = activeModule === "historico_peru"
    ? [
      { label: "Histórico Perú", items: historicoNav.map((item) => ({ id: item.page, label: item.label, shortLabel: item.shortLabel, icon: item.icon, badge: item.page === "Alertas Histórico Perú" ? historicoUrgent : undefined })) },
      ...(adminSection ? [{ ...adminSection, items: adminSection.items.filter((item) => item.id === "Sistema") }] : []),
    ]
    : [
      { label: countryOptions[countryCode].label, items: [
        ...radarNav[countryCode].filter((item) => item.role !== "eliminados").map((item) => ({ id: item.page, label: item.label, shortLabel: item.shortLabel, icon: item.icon })),
        { id: "Alertas", label: "Alertas", icon: "bell" as IconName },
        ...radarNav[countryCode].filter((item) => item.role === "eliminados").map((item) => ({ id: item.page, label: item.label, shortLabel: item.shortLabel, icon: item.icon })),
      ] },
      ...(adminSection ? [adminSection] : []),
    ];
  const phoneTabs = activeModule === "historico_peru"
    ? ["Resumen Histórico Perú", "Historial de Contrataciones", "Contratos por Vencer", "Alertas Histórico Perú"]
    : [radarNav[countryCode][0].page, radarNav[countryCode][1].page, radarNav[countryCode].find((item) => item.role === "seguimiento")!.page, "Alertas"];
  const selectableCountries = activeModule === "radar" ? allowedCountries.map((code) => countryOptions[code]) : [countryOptions.peru];
  const countrySelector = (compact: boolean) => (
    <CountrySelector
      value={activeModule === "radar" ? country : "Peru"}
      options={selectableCountries}
      onChange={activeModule === "radar" && selectableCountries.length > 1 ? changeCountry : undefined}
      compact={compact}
      onDark={compact}
    />
  );
  const pageMeta = activeModule === "historico_peru"
    ? "Datos abiertos OECE · CONOSCE"
    : countryOfPage(page)
      ? `${countryOptions[countryCode].label} · ${launcherDescriptions[page]}`
      : launcherDescriptions[page];

  return (
    <UiAppShell
      brand={brand}
      module={activeModule}
      modules={allowedModules}
      onModuleChange={changeModule}
      sections={sections}
      phoneTabs={phoneTabs}
      currentId={page}
      onNavigate={(id) => setPage(id as Page)}
      pageLabel={pageTitle(page)}
      topbarEnd={countrySelector(false)}
      phoneEnd={countrySelector(true)}
      user={{ name: userName, roleLabel: isAdmin ? "Administrador" : "Usuario", initials: userInitials(userName) }}
      onLogout={onLogout}
      footer={
        <footer className="legal-footer ui-legal-footer">
          <span>© 2026 {brand.name}™ · {versionLabel}</span>
          <span aria-hidden="true">|</span>
          <button type="button" onClick={() => setLegalView("terms")}>Términos</button>
          <span aria-hidden="true">|</span>
          <button type="button" onClick={() => setLegalView("privacy")}>Política de Privacidad</button>
        </footer>
      }
    >
      <PageHeader title={pageTitle(page)} meta={pageMeta} />
        {sessionError ? <div className="notice danger">{sessionError}</div> : null}
        {backend.error ? <div className="notice danger">{backend.error}</div> : null}
        <Suspense fallback={<div className="panel module-loading" role="status">Cargando módulo…</div>}>
        {!currentUser ? <div className="panel module-loading" role="status">Validando sesión y perfil…</div> : null}
        {currentUser && page === "Inicio Peru" ? <Home country="Peru" token={token} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} refresh={backend.refresh} onGoToDetail={openOpportunityDetail} scrollToMapSignal={homeScrollSignal} /> : null}
        {currentUser && page === "Inicio Chile" ? <Home country="Chile" token={token} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} refresh={backend.refresh} onGoToDetail={openOpportunityDetail} scrollToMapSignal={homeScrollSignal} /> : null}
        {currentUser && page === "Inicio Argentina" ? <Home country="Argentina" token={token} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} refresh={backend.refresh} onGoToDetail={openOpportunityDetail} scrollToMapSignal={homeScrollSignal} /> : null}
        {currentUser && page === "Oportunidades" ? <Opportunities country="Peru" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} onGoHome={goToHomeAndScrollToMap} /> : null}
        {currentUser && page === "Oportunidades Chile LMP-GC" ? <Opportunities country="Chile" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} prefillKeyword={keywordSearchHandoff?.country === "Chile" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} targetOpportunityId={opportunityHandoff?.country === "Chile" ? opportunityHandoff.opportunityId : null} onTargetConsumed={() => setOpportunityHandoff(null)} onGoHome={goToHomeAndScrollToMap} /> : null}
        {currentUser && page === "Procesos COMPR.AR Argentina" ? <Opportunities country="Argentina" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} argentinaRecordType="procesos" prefillKeyword={keywordSearchHandoff?.country === "Argentina" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} targetOpportunityId={opportunityHandoff?.country === "Argentina" ? opportunityHandoff.opportunityId : null} onTargetConsumed={() => setOpportunityHandoff(null)} onGoHome={goToHomeAndScrollToMap} /> : null}
        {currentUser && page === "Publicaciones COMPR.AR Argentina" ? <Opportunities country="Argentina" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} argentinaRecordType="publicaciones" targetOpportunityId={opportunityHandoff?.country === "Argentina" ? opportunityHandoff.opportunityId : null} onTargetConsumed={() => setOpportunityHandoff(null)} onGoHome={goToHomeAndScrollToMap} /> : null}
        {currentUser && page === "Oportunidades OCDS Peru" ? <Opportunities country="Peru" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} variant="ocds" prefillKeyword={keywordSearchHandoff?.country === "Peru" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} targetOpportunityId={opportunityHandoff?.country === "Peru" ? opportunityHandoff.opportunityId : null} onTargetConsumed={() => setOpportunityHandoff(null)} onGoHome={goToHomeAndScrollToMap} /> : null}
        {page === "Histórico Procesos Eliminados PE" ? <ArchivedProcesses country="Peru" token={token} onRestored={backend.refresh} /> : null}
        {page === "Histórico Procesos Eliminados CL" ? <ArchivedProcesses country="Chile" token={token} onRestored={backend.refresh} /> : null}
        {page === "Histórico Procesos Eliminados AR" ? <ArchivedProcesses country="Argentina" token={token} onRestored={backend.refresh} /> : null}
        {page === "Alertas" ? <Alerts token={token} rules={backend.rules} alerts={backend.alerts} refresh={backend.refresh} /> : null}
        {currentUser && page === "Seguimiento de Oportunidades Peru" ? <OpportunityTrackingPeru token={token} isAdmin={currentUser.role === "admin"} currentUserId={currentUser.id} /> : null}
        {currentUser && page === "Seguimiento de Oportunidades Chile" ? <OpportunityTrackingChile token={token} isAdmin={currentUser.role === "admin"} currentUserId={currentUser.id} /> : null}
        {currentUser && page === "Seguimiento de Oportunidades Argentina" ? <OpportunityTrackingArgentina token={token} isAdmin={currentUser.role === "admin"} currentUserId={currentUser.id} /> : null}
        {currentUser && page === "Resumen Histórico Perú" ? <HistoricoResumen token={token} onGo={setPage} /> : null}
        {currentUser && page === "Historial de Contrataciones" ? <HistoricoContrataciones token={token} /> : null}
        {currentUser && page === "Contratos por Vencer" ? <HistoricoVencimientos token={token} /> : null}
        {currentUser && page === "PAC Perú" ? <HistoricoPac token={token} /> : null}
        {currentUser && page === "Alertas Histórico Perú" ? <HistoricoAlertas token={token} /> : null}
        {page === "Usuarios" && currentUser?.role === "admin" ? <Users token={token} currentUserId={currentUser.id} /> : null}
        {page === "Sistema" ? (
          <System
            token={token}
            runs={backend.runs}
            refresh={backend.refresh}
            legalDocuments={legalDocuments.documents}
            legalLoadError={legalDocuments.error}
            onLegalDocumentUpdated={(document) => legalDocuments.setDocuments((current) => ({ ...current, [document.key]: document }))}
            onOpenLegal={setLegalView}
            onSearchKeyword={openKeywordSearch}
            versionLabel={versionLabel}
            onVersionUpdated={setVersionLabel}
          />
        ) : null}
        </Suspense>
      {legalView ? <LegalDialog view={legalView} documents={legalDocuments.documents} onClose={() => setLegalView(null)} /> : null}
    </UiAppShell>
  );
}

// Internal component sheet (docs/design/mockups/Componentes.dc.html). Dev
// server only, or builds made with VITE_UI_PREVIEW=true; never in production.
const UI_PREVIEW_ENABLED = import.meta.env.DEV || import.meta.env.VITE_UI_PREVIEW === "true";

function Root() {
  const [token, setToken] = useState(localStorage.getItem("rodar_token") || "");
  if (UI_PREVIEW_ENABLED && window.location.pathname.replace(/\/$/, "") === "/ui-preview") {
    return <Suspense fallback={null}><UiPreview /></Suspense>;
  }
  const resetToken = new URLSearchParams(window.location.search).get("reset_token") || "";
  useEffect(() => {
    setUnauthorizedHandler(() => {
      localStorage.removeItem("rodar_token");
      localStorage.removeItem("rodar_email");
      setToken("");
    });
    return () => setUnauthorizedHandler(null);
  }, []);
  if (!token || resetToken) {
    return (
      <Login
        onLogin={(nextToken, nextEmail) => {
          localStorage.setItem("rodar_token", nextToken);
          localStorage.setItem("rodar_email", nextEmail);
          setToken(nextToken);
        }}
        resetToken={resetToken}
      />
    );
  }
  return (
    <AppShell
      onLogout={() => {
        localStorage.removeItem("rodar_token");
        localStorage.removeItem("rodar_email");
        setToken("");
      }}
    />
  );
}

// Default brand until the tenant brand is loaded from app_settings.
applyTenantBrand(DEFAULT_BRAND);

createRoot(document.getElementById("root")!).render(<Root />);
