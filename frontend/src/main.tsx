import React, { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, AccessProfile, Alert, AlertRule, confirmPasswordReset, login, Opportunity, requestPasswordReset, Run, Stats, UserRecord } from "./api";
import "./styles.css";
import { Country, CountryFlagIcon, LegalDialog, LegalDocumentsMap, LegalView, countryFlagUrls, userInitials } from "./shared";

const Home = lazy(() => import("./pages/HomePage"));
const Opportunities = lazy(() => import("./pages/OpportunitiesPage"));
const ArchivedProcesses = lazy(() => import("./pages/OpportunitiesPage").then((module) => ({ default: module.ArchivedProcesses })));
const Alerts = lazy(() => import("./pages/AlertsPage"));
const Users = lazy(() => import("./pages/UsersPage"));
const System = lazy(() => import("./pages/SystemPage"));
const OpportunityTrackingChile = lazy(() => import("./pages/OpportunityTrackingPage"));
const OpportunityTrackingPeru = lazy(() => import("./pages/OpportunityTrackingPage").then((module) => ({ default: module.OpportunityTrackingPeru })));

type Page = "Inicio Peru" | "Inicio Chile" | "Oportunidades" | "Oportunidades Chile LMP-GC" | "Oportunidades OCDS Peru" | "Histórico Procesos Eliminados PE" | "Histórico Procesos Eliminados CL" | "Alertas" | "Seguimiento de Oportunidades Peru" | "Seguimiento de Oportunidades Chile" | "Usuarios" | "Sistema";

type NavIconName = "home" | "target" | "globe" | "database" | "money" | "bell" | "users" | "settings";

const profilePages: Record<AccessProfile, Page[]> = {
  peru: ["Inicio Peru", "Oportunidades OCDS Peru", "Histórico Procesos Eliminados PE", "Alertas", "Seguimiento de Oportunidades Peru"],
  chile: ["Inicio Chile", "Oportunidades Chile LMP-GC", "Histórico Procesos Eliminados CL", "Alertas", "Seguimiento de Oportunidades Chile"],
  both: ["Inicio Peru", "Inicio Chile", "Oportunidades Chile LMP-GC", "Oportunidades OCDS Peru", "Histórico Procesos Eliminados PE", "Histórico Procesos Eliminados CL", "Alertas", "Seguimiento de Oportunidades Peru", "Seguimiento de Oportunidades Chile"],
};

const rodarLogoUrl = "/assets/Rodarfondoblanco.png";

const navIcons: Record<Page, NavIconName> = {
  "Inicio Peru": "home",
  "Inicio Chile": "home",
  Oportunidades: "money",
  "Oportunidades Chile LMP-GC": "money",
  "Oportunidades OCDS Peru": "money",
  "Histórico Procesos Eliminados PE": "database",
  "Histórico Procesos Eliminados CL": "database",
  Alertas: "bell",
  "Seguimiento de Oportunidades Peru": "target",
  "Seguimiento de Oportunidades Chile": "target",
  Usuarios: "users",
  Sistema: "settings",
};

const launcherNavGroups: Array<{ label: string; pages: Page[] }> = [
  { label: "Perú", pages: ["Inicio Peru", "Oportunidades OCDS Peru", "Oportunidades", "Histórico Procesos Eliminados PE", "Seguimiento de Oportunidades Peru"] },
  { label: "Chile", pages: ["Inicio Chile", "Oportunidades Chile LMP-GC", "Histórico Procesos Eliminados CL", "Seguimiento de Oportunidades Chile"] },
  { label: "Operación", pages: ["Alertas"] },
  { label: "Administración", pages: ["Usuarios", "Sistema"] },
];

const launcherLabels: Record<Page, string> = {
  "Inicio Peru": "Inicio Peru",
  "Inicio Chile": "Inicio Chile",
  Oportunidades: "Oportunidades",
  "Oportunidades Chile LMP-GC": "Buscador Oportunidades Chile",
  "Oportunidades OCDS Peru": "Buscador Oportunidades Peru",
  "Histórico Procesos Eliminados PE": "Histórico Procesos Eliminados PE",
  "Histórico Procesos Eliminados CL": "Histórico Procesos Eliminados CL",
  Alertas: "Alertas",
  "Seguimiento de Oportunidades Peru": "Seguimiento de Oportunidades Perú",
  "Seguimiento de Oportunidades Chile": "Seguimiento de Oportunidades Chile",
  Usuarios: "Usuarios",
  Sistema: "Sistema",
};

const launcherDescriptions: Record<Page, string> = {
  "Inicio Peru": "Resumen operativo de procesos SEACE",
  "Inicio Chile": "Resumen comercial de Mercado Público",
  Oportunidades: "Radar de oportunidades de Perú",
  "Oportunidades Chile LMP-GC": "Licitaciones y Grandes Compras",
  "Oportunidades OCDS Peru": "Contrataciones abiertas OECE/OCDS",
  "Histórico Procesos Eliminados PE": "Respaldo de procesos retirados de Perú",
  "Histórico Procesos Eliminados CL": "Respaldo de procesos retirados de Chile",
  Alertas: "Reglas, canales y notificaciones",
  "Seguimiento de Oportunidades Peru": "Fases, etapas y responsables — Perú",
  "Seguimiento de Oportunidades Chile": "Fases, etapas y responsables — Chile",
  Usuarios: "Accesos, perfiles y permisos",
  Sistema: "Ejecuciones y configuración",
};

function NavIcon({ name }: { name: NavIconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
      {name === "home" ? <path {...common} d="M3 11.5 12 4l9 7.5M5 10.5V20h14v-9.5M9 20v-6h6v6" /> : null}
      {name === "target" ? <><circle {...common} cx="12" cy="12" r="8" /><circle {...common} cx="12" cy="12" r="3" /><path {...common} d="M17 7l3-3M17.5 4H20v2.5" /></> : null}
      {name === "globe" ? <><circle {...common} cx="12" cy="12" r="9" /><path {...common} d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></> : null}
      {name === "database" ? <><ellipse {...common} cx="12" cy="5" rx="7" ry="3" /><path {...common} d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></> : null}
      {name === "money" ? <><circle {...common} cx="12" cy="12" r="9" /><path {...common} d="M15.5 8.5C14.8 7.5 13.6 7 12 7c-2 0-3.5 1-3.5 2.5S10 12 12 12s3.5 1 3.5 2.5S14 17 12 17c-1.6 0-2.8-.5-3.5-1.5M12 5v14" /></> : null}
      {name === "bell" ? <><path {...common} d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path {...common} d="M10 21h4" /></> : null}
      {name === "users" ? <><path {...common} d="M16 21v-2a4 4 0 0 0-8 0v2" /><circle {...common} cx="12" cy="7" r="4" /><path {...common} d="M22 21v-2a4 4 0 0 0-3-3.8M16 3.2a4 4 0 0 1 0 7.6" /></> : null}
      {name === "settings" ? <><path {...common} d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" /><path {...common} d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3.4-.2-.1a1.7 1.7 0 0 0-2 .2 1.7 1.7 0 0 0-.8 1.7V22H9.2v-.2a1.7 1.7 0 0 0-.8-1.7 1.7 1.7 0 0 0-2-.2l-.2.1-2-3.4.1-.1A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.4-1.1H3v-4h.2a1.7 1.7 0 0 0 1.4-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2-3.4.2.1a1.7 1.7 0 0 0 2-.2A1.7 1.7 0 0 0 9.2 2V2h5.6v.2a1.7 1.7 0 0 0 .8 1.7 1.7 1.7 0 0 0 2 .2l.2-.1 2 3.4-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.4 1.1h.2v4h-.2A1.7 1.7 0 0 0 19.4 15Z" /></> : null}
    </svg>
  );
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
          Detecta oportunidades de negocio con gobierno en Perú y Chile de forma simple y customizable.
        </p>
        <div className="brand-grid">
          <span>Peru operativo</span>
          <span>Chile operativo</span>
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
        <div className="login-country-flags" aria-label="Operación en Perú y Chile">
          <img src={countryFlagUrls.Peru} alt="Bandera de Perú" />
          <img src={countryFlagUrls.Chile} alt="Bandera de Chile" />
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

function AppShell({ onLogout }: { onLogout: () => void }) {
  const token = localStorage.getItem("rodar_token") || "";
  const [page, setPage] = useState<Page>("Inicio Peru");
  const [country, setCountry] = useState<Country>("Peru");
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [keywordSearchHandoff, setKeywordSearchHandoff] = useState<{ country: Country; keyword: string } | null>(null);
  const [legalView, setLegalView] = useState<LegalView | null>(null);
  const [versionLabel, setVersionLabel] = useState("Versión 1.0 (Beta)");
  const legalDocuments = useLegalDocuments();
  const launcherRef = useRef<HTMLElement | null>(null);
  const launcherButtonRef = useRef<HTMLButtonElement | null>(null);
  const backend = useBackend(token);
  const userName = currentUser?.full_name || "Cargando usuario…";
  const visibleNav = useMemo(() => {
    const allowed = currentUser ? profilePages[currentUser.access_profile] : profilePages.peru;
    return currentUser?.role === "admin" ? [...allowed, "Usuarios", "Sistema"] as Page[] : allowed;
  }, [currentUser]);
  const visibleLauncherGroups = useMemo(() => launcherNavGroups
    .map((group) => ({ ...group, pages: group.pages.filter((item) => visibleNav.includes(item)) }))
    .filter((group) => group.pages.length > 0), [visibleNav]);

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
      setPage(currentUser.access_profile === "chile" ? "Inicio Chile" : "Inicio Peru");
    }
  }, [currentUser, page, visibleNav]);

  useEffect(() => {
    if (page === "Inicio Chile" || page === "Oportunidades Chile LMP-GC" || page === "Histórico Procesos Eliminados CL" || page === "Seguimiento de Oportunidades Chile") {
      setCountry("Chile");
    } else if (page === "Inicio Peru" || page === "Oportunidades" || page === "Oportunidades OCDS Peru" || page === "Histórico Procesos Eliminados PE" || page === "Seguimiento de Oportunidades Peru") {
      setCountry("Peru");
    }
  }, [page]);

  useEffect(() => {
    if (!launcherOpen) return;

    const focusFrame = window.requestAnimationFrame(() => {
      launcherRef.current?.querySelector<HTMLButtonElement>(".launcher-nav-item")?.focus();
    });
    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target as Node;
      if (!launcherRef.current?.contains(target) && !launcherButtonRef.current?.contains(target)) {
        setLauncherOpen(false);
      }
    }
    function closeOnOutsideFocus(event: FocusEvent) {
      const target = event.target as Node;
      if (!launcherRef.current?.contains(target) && !launcherButtonRef.current?.contains(target)) {
        setLauncherOpen(false);
      }
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setLauncherOpen(false);
        launcherButtonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("focusin", closeOnOutsideFocus);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("focusin", closeOnOutsideFocus);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [launcherOpen]);

  function navigateFromLauncher(item: Page) {
    setPage(item);
    setLauncherOpen(false);
    window.requestAnimationFrame(() => launcherButtonRef.current?.focus());
  }

  function openKeywordSearch(targetCountry: Country, keyword: string) {
    setKeywordSearchHandoff({ country: targetCountry, keyword });
    setPage(targetCountry === "Chile" ? "Oportunidades Chile LMP-GC" : "Oportunidades OCDS Peru");
  }

  return (
    <div className="app-shell">
      <div className="workspace">
        <header className="topbar">
          {launcherOpen ? <div className="launcher-backdrop" aria-hidden="true" /> : null}
          <div className="top-title">
            <div className="launcher-anchor">
              <button
                ref={launcherButtonRef}
                className={`menu-toggle ${launcherOpen ? "active" : ""}`}
                type="button"
                onClick={() => setLauncherOpen((value) => !value)}
                aria-label={launcherOpen ? "Cerrar navegación" : "Abrir navegación"}
                aria-expanded={launcherOpen}
                aria-haspopup="true"
                aria-controls="app-launcher"
              >
                <span />
                <span />
                <span />
              </button>
              {launcherOpen ? (
                <section ref={launcherRef} className="launcher-panel" id="app-launcher" aria-label="Navegación principal">
                  <div className="launcher-header">
                    <div className="launcher-brand">
                      <img src={rodarLogoUrl} alt="" />
                      <div>
                        <span>Navegación</span>
                        <strong>CRM Radar Gobierno</strong>
                      </div>
                    </div>
                    <button
                      className="launcher-close"
                      type="button"
                      onClick={() => {
                        setLauncherOpen(false);
                        window.requestAnimationFrame(() => launcherButtonRef.current?.focus());
                      }}
                      aria-label="Cerrar navegación"
                    >×</button>
                  </div>
                  <div className="launcher-intro">
                    <strong>Centro de navegación</strong>
                    <span>Accede a los módulos habilitados para tu perfil.</span>
                  </div>
                  <nav className="launcher-nav" aria-label="Módulos disponibles">
                    {visibleLauncherGroups.map((group) => (
                      <div className="launcher-group" key={group.label}>
                        <h2>{group.label}</h2>
                        <div>
                          {group.pages.map((item) => (
                            <button
                              className={`launcher-nav-item ${item === page ? "active" : ""}`}
                              type="button"
                              key={item}
                              onClick={() => navigateFromLauncher(item)}
                              aria-current={item === page ? "page" : undefined}
                            >
                              <span className="launcher-icon-shell"><NavIcon name={navIcons[item]} /></span>
                              <span className="launcher-item-copy">
                                <strong>{launcherLabels[item]}</strong>
                                <small>{launcherDescriptions[item]}</small>
                              </span>
                              {item === page ? <span className="launcher-current">Actual</span> : null}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </nav>
                  <div className="launcher-footer">
                    <strong className="launcher-version">{versionLabel}</strong>
                    <span className="launcher-api-status">
                      <span><i aria-hidden="true" /> API</span>
                      <b>{backend.loading ? "Sincronizando" : "Conectada"}</b>
                    </span>
                    <div className="launcher-mobile-session">
                      <span className="launcher-mobile-user">
                        <span className="user-pill">{userInitials(userName)}</span>
                        <span>
                          <small>Sesión activa</small>
                          <strong>{userName}</strong>
                        </span>
                      </span>
                      <button className="ghost" type="button" onClick={onLogout}>Salir</button>
                    </div>
                  </div>
                </section>
              ) : null}
            </div>
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
        {sessionError ? <div className="notice danger">{sessionError}</div> : null}
        {backend.error ? <div className="notice danger">{backend.error}</div> : null}
        <Suspense fallback={<div className="panel module-loading" role="status">Cargando módulo…</div>}>
        {!currentUser ? <div className="panel module-loading" role="status">Validando sesión y perfil…</div> : null}
        {currentUser && page === "Inicio Peru" ? <Home country="Peru" token={token} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} refresh={backend.refresh} /> : null}
        {currentUser && page === "Inicio Chile" ? <Home country="Chile" token={token} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} refresh={backend.refresh} /> : null}
        {currentUser && page === "Oportunidades" ? <Opportunities country="Peru" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} /> : null}
        {currentUser && page === "Oportunidades Chile LMP-GC" ? <Opportunities country="Chile" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} prefillKeyword={keywordSearchHandoff?.country === "Chile" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} /> : null}
        {currentUser && page === "Oportunidades OCDS Peru" ? <Opportunities country="Peru" userId={currentUser.id} token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} variant="ocds" prefillKeyword={keywordSearchHandoff?.country === "Peru" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} /> : null}
        {page === "Histórico Procesos Eliminados PE" ? <ArchivedProcesses country="Peru" token={token} onRestored={backend.refresh} /> : null}
        {page === "Histórico Procesos Eliminados CL" ? <ArchivedProcesses country="Chile" token={token} onRestored={backend.refresh} /> : null}
        {page === "Alertas" ? <Alerts token={token} rules={backend.rules} alerts={backend.alerts} refresh={backend.refresh} /> : null}
        {currentUser && page === "Seguimiento de Oportunidades Peru" ? <OpportunityTrackingPeru token={token} isAdmin={currentUser.role === "admin"} currentUserId={currentUser.id} /> : null}
        {currentUser && page === "Seguimiento de Oportunidades Chile" ? <OpportunityTrackingChile token={token} isAdmin={currentUser.role === "admin"} currentUserId={currentUser.id} /> : null}
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
        <footer className="legal-footer">
          <span>© 2026 Rodar Consulting S.A.C.™</span>
          <span aria-hidden="true">|</span>
          <button type="button" onClick={() => setLegalView("terms")}>Términos</button>
          <span aria-hidden="true">|</span>
          <button type="button" onClick={() => setLegalView("privacy")}>Política de Privacidad</button>
        </footer>
      </div>
      {legalView ? <LegalDialog view={legalView} documents={legalDocuments.documents} onClose={() => setLegalView(null)} /> : null}
    </div>
  );
}

function Root() {
  const [token, setToken] = useState(localStorage.getItem("rodar_token") || "");
  const resetToken = new URLSearchParams(window.location.search).get("reset_token") || "";
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

createRoot(document.getElementById("root")!).render(<Root />);
