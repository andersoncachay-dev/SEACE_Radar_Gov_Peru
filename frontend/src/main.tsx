import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, AccessProfile, Alert, AlertRule, confirmPasswordReset, DocumentRecord, LegalDocumentKey, LegalDocumentRecord, login, Opportunity, RadarKeyword, requestPasswordReset, Run, Stats, UserCreatePayload, UserRecord } from "./api";
import chileRegionsSvg from "./assets_mapa/chile.svg?raw";
import peruRegionsSvg from "./assets_mapa/peru-regions.svg?raw";
import "./styles.css";

type Page = "Inicio Peru" | "Inicio Chile" | "Oportunidades" | "Oportunidades Chile LMP-GC" | "Oportunidades OCDS Peru" | "Alertas" | "Usuarios" | "Sistema";
type Country = "Peru" | "Chile";
type Module = "SEACE Publico" | "Contratos Menores a 8 UIT" | "Oportunidades Chile LMP-GC" | "Ambos modulos";
type CommercialClass = "green" | "amber" | "red";
type HomeStatusFilter = "all" | "priority-a" | "vigentes" | "cerrados";
type SortDirection = "asc" | "desc";
type SearchMode = "append" | "replace";
type OpportunityVariant = "radar" | "ocds";
type MaxResultsMode = "all" | "active";
type ActivePeriodKeywordGroup = {
  year: string;
  months: string[];
  keywords: string[];
  commercialMode: MaxResultsMode;
};
type PendingSearch = { mode: SearchMode; keywords: string[]; runIds: number[]; appliedState: SavedOpportunityViewState };
type SavedOpportunityViewState = {
  keywords: string[];
  runIds: number[];
  keyword: string;
  keyword2: string;
  keyword3: string;
  nomenclatureFilter: string;
  entityFilter: string;
  publicationDateFrom: string;
  publicationDateTo: string;
  years: string[];
  months: string[];
  appliedYears: string[];
  appliedMonths: string[];
  periodKeywordGroups: ActivePeriodKeywordGroup[];
  maxResultsMode: MaxResultsMode;
  searchMode: SearchMode;
};
type NavIconName = "home" | "target" | "globe" | "database" | "money" | "bell" | "users" | "settings";
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

const profilePages: Record<AccessProfile, Page[]> = {
  peru: ["Inicio Peru", "Oportunidades OCDS Peru", "Alertas"],
  chile: ["Inicio Chile", "Oportunidades Chile LMP-GC", "Alertas"],
  both: ["Inicio Peru", "Inicio Chile", "Oportunidades Chile LMP-GC", "Oportunidades OCDS Peru", "Alertas"],
};
const commercialFilters = [
  { label: "Vigente para Consultas y Propuesta", className: "green" },
  { label: "Vigente para Propuesta", className: "amber" },
  { label: "Proceso Culminado", className: "red" },
] as const;
const activeSearchStoragePrefix = "govradar.opportunities.activeSearch";
const unmappedRegionKey = "__sin_region__";
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
const homeKeywordHints = [
  { label: "satelital", terms: ["satelital"] },
  { label: "internet", terms: ["internet"] },
  { label: "conectividad", terms: ["conectividad"] },
  { label: "telecomunicaciones", terms: ["telecomunicaciones"] },
  { label: "radio enlace", terms: ["radio enlace"] },
  { label: "GEO", terms: ["geo"] },
  { label: "LEO", terms: ["leo"] },
  { label: "\u00f3rbita", terms: ["\u00f3rbita", "orbita"] },
];
const navIcons: Record<Page, NavIconName> = {
  "Inicio Peru": "home",
  "Inicio Chile": "home",
  Oportunidades: "money",
  "Oportunidades Chile LMP-GC": "money",
  "Oportunidades OCDS Peru": "money",
  Alertas: "bell",
  Usuarios: "users",
  Sistema: "settings",
};
const launcherNavGroups: Array<{ label: string; pages: Page[] }> = [
  { label: "Perú", pages: ["Inicio Peru", "Oportunidades OCDS Peru", "Oportunidades"] },
  { label: "Chile", pages: ["Inicio Chile", "Oportunidades Chile LMP-GC"] },
  { label: "Operación", pages: ["Alertas"] },
  { label: "Administración", pages: ["Usuarios", "Sistema"] },
];
const launcherDescriptions: Record<Page, string> = {
  "Inicio Peru": "Resumen operativo de procesos SEACE",
  "Inicio Chile": "Resumen comercial de Mercado Público",
  Oportunidades: "Radar de oportunidades de Perú",
  "Oportunidades Chile LMP-GC": "Licitaciones y Grandes Compras",
  "Oportunidades OCDS Peru": "Contrataciones abiertas OECE/OCDS",
  Alertas: "Reglas, canales y notificaciones",
  Usuarios: "Accesos, perfiles y permisos",
  Sistema: "Ejecuciones y configuración",
};

function modulesForCountry(country: Country): Module[] {
  return country === "Chile"
    ? ["Oportunidades Chile LMP-GC"]
    : ["SEACE Publico", "Contratos Menores a 8 UIT", "Ambos modulos"];
}

function defaultModuleForCountry(country: Country): Module {
  return country === "Chile" ? "Oportunidades Chile LMP-GC" : "SEACE Publico";
}

function moduleLabel(module: Module) {
  if (module === "Oportunidades Chile LMP-GC") {
    return "Licitaciones Mercado Público y Grandes Compras";
  }
  return module;
}

function opportunityBandLabel(country: Country, variant: OpportunityVariant, module: Module) {
  if (variant === "ocds") {
    return "Contrataciones Abiertas OECE/OCDS para procesos Peru, incluyendo licitaciones, adjudicaciones, contratos y compras menores publicadas.";
  }
  if (country === "Chile") {
    return "Oportunidades Chile Licitaciones Mercado Publico y Grandes Compras";
  }
  return moduleLabel(module);
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

function formatMoney(value: number, country: Country = "Peru") {
  if (!Number.isFinite(value) || value <= 0) {
    return <span className="reserved-amount">Monto reservado</span>;
  }
  return new Intl.NumberFormat(country === "Chile" ? "es-CL" : "es-PE", {
    style: "currency",
    currency: country === "Chile" ? "CLP" : "PEN",
    maximumFractionDigits: 0,
  }).format(value || 0);
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

function dateFilterBoundary(value: string, endOfDay: boolean) {
  if (!value) return null;
  const timestamp = new Date(`${value}T${endOfDay ? "23:59:59.999" : "00:00:00.000"}`).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function futurePeriodValidationMessage(years: string[], months: string[], now = new Date()) {
  const thisYear = now.getFullYear();
  const thisMonth = now.getMonth() + 1;
  const includesFutureYear = years.some((year) => Number(year) > thisYear);
  const includesFutureMonth = years.includes(String(thisYear))
    && months.some((month) => Number(month) > thisMonth);

  if (!includesFutureYear && !includesFutureMonth) return "";

  const latestValidPeriod = new Intl.DateTimeFormat("es-PE", {
    month: "long",
    year: "numeric",
  }).format(now);
  return `Elige un período válido. No puedes ejecutar búsquedas para fechas posteriores a ${latestValidPeriod}.`;
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
      {name === "money" ? <><circle {...common} cx="12" cy="12" r="9" /><path {...common} d="M15.5 8.5C14.8 7.5 13.6 7 12 7c-2 0-3.5 1-3.5 2.5S10 12 12 12s3.5 1 3.5 2.5S14 17 12 17c-1.6 0-2.8-.5-3.5-1.5M12 5v14" /></> : null}
      {name === "bell" ? <><path {...common} d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path {...common} d="M10 21h4" /></> : null}
      {name === "users" ? <><path {...common} d="M16 21v-2a4 4 0 0 0-8 0v2" /><circle {...common} cx="12" cy="7" r="4" /><path {...common} d="M22 21v-2a4 4 0 0 0-3-3.8M16 3.2a4 4 0 0 1 0 7.6" /></> : null}
      {name === "settings" ? <><path {...common} d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" /><path {...common} d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3.4-.2-.1a1.7 1.7 0 0 0-2 .2 1.7 1.7 0 0 0-.8 1.7V22H9.2v-.2a1.7 1.7 0 0 0-.8-1.7 1.7 1.7 0 0 0-2-.2l-.2.1-2-3.4.1-.1A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.4-1.1H3v-4h.2a1.7 1.7 0 0 0 1.4-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2-3.4.2.1a1.7 1.7 0 0 0 2-.2A1.7 1.7 0 0 0 9.2 2V2h5.6v.2a1.7 1.7 0 0 0 .8 1.7 1.7 1.7 0 0 0 2 .2l.2-.1 2 3.4-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.4 1.1h.2v4h-.2A1.7 1.7 0 0 0 19.4 15Z" /></> : null}
    </svg>
  );
}

function LockIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

function RadarActionIcon() {
  return (
    <svg className="execute-radar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5.5" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <path d="M12 12 18.4 5.6" />
      <path d="M3 12h2.2M18.8 12H21M12 3v2.2M12 18.8V21" />
    </svg>
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

function estimateRunProgress(run: Run) {
  if (["completed", "failed", "cancelled"].includes(run.status)) return 100;
  if (run.status === "queued") return 0;
  return Math.max(0, Math.min(99, Number(run.progress || 0)));
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

function matchesCompletePhrase(text: string, phrase: string) {
  const normalizedText = stripAccents(text).toLowerCase().replace(/\s+/g, " ").trim();
  const normalizedPhrase = stripAccents(phrase).toLowerCase().replace(/\s+/g, " ").trim();
  if (!normalizedPhrase) return true;
  const phrasePattern = normalizedPhrase.split(" ").map(escapeRegex).join("\\s+");
  return new RegExp(`(?:^|[^\\p{L}\\p{N}_])${phrasePattern}(?=$|[^\\p{L}\\p{N}_])`, "iu").test(normalizedText);
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
  const matcher = new RegExp(`(?<![\\p{L}\\p{N}_])(${cleanTerms.map(escapeRegex).join("|")})(?![\\p{L}\\p{N}_])`, "giu");
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

function keywordContextFromHints(
  opportunities: Opportunity[],
  keywordHints: Array<{ label: string; terms: string[] }>,
) {
  const found = new Set<string>();
  for (const item of opportunities) {
    const text = `${item.nomenclature} ${item.description} ${item.entity}`;
    for (const keyword of keywordHints) {
      const matches = keyword.terms.some((term) => matchesCompletePhrase(text, term));
      if (matches) found.add(keyword.label);
    }
  }
  return Array.from(found);
}

function matchesAnyKeywordHint(
  opportunity: Opportunity,
  keywordHints: Array<{ label: string; terms: string[] }>,
) {
  if (!keywordHints.length) return false;
  const text = `${opportunity.nomenclature} ${opportunity.description} ${opportunity.entity}`;
  return keywordHints.some((keyword) => keyword.terms.some((term) => term.trim() && matchesCompletePhrase(text, term)));
}

function matchesHomeStatusFilter(item: Opportunity, filter: HomeStatusFilter) {
  if (filter === "all") return true;
  if (filter === "priority-a") return item.priority === "A";
  const signal = commercialSignal(item).className;
  if (filter === "vigentes") return signal === "green" || signal === "amber";
  return signal === "red";
}

function homeStatusFilterLabel(filter: HomeStatusFilter) {
  if (filter === "priority-a") return "Prioridad A";
  if (filter === "vigentes") return "Vista filtrada: vigentes";
  if (filter === "cerrados") return "Vista filtrada: cerrados";
  return "Vista completa";
}

function opportunityYear(item: Opportunity) {
  const timestamp = parseDate(item.publication_date) ?? parseDate(item.proposal_deadline) ?? parseDate(item.quote_deadline);
  return timestamp === null ? "Sin año" : String(new Date(timestamp).getFullYear());
}

function stripAccents(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function titleCaseRegion(value: string) {
  return value
    .toLowerCase()
    .split(" ")
    .filter(Boolean)
    .map((part) => {
      if (part.length <= 2 && !["de", "la", "el", "y"].includes(part)) return part.toUpperCase();
      return ["de", "la", "el", "y"].includes(part) ? part : `${part.charAt(0).toUpperCase()}${part.slice(1)}`;
    })
    .join(" ");
}

function chileRegionFromOpportunity(item: Opportunity) {
  const suppliedRegion = normalizeRegionName(item.region);
  if (suppliedRegion && suppliedRegion !== "CHILE") return item.region;

  const entity = stripAccents(item.entity || "").toUpperCase().replace(/\s+/g, " ");
  const rules: Array<[string, string[]]> = [
    ["Arica y Parinacota", ["MUNICIPALIDAD DE ARICA", "MUNICIPALIDAD DE GENERAL LAGOS", "EDUCACION DE CHINCHORRO"]],
    ["Tarapacá", ["MUNICIPALIDAD DE IQUIQUE", "MUNICIPALIDAD DE COLCHANE", "MUNICIPALIDAD DE POZO ALMONTE"]],
    ["Antofagasta", ["PROVINCIAL DE EL LOA"]],
    ["Atacama", ["MUNICIPALIDAD DE CALDERA"]],
    ["Coquimbo", ["MUNICIPALIDAD DE RIO HURTADO", "MUNICIPALIDAD DE VICUNA"]],
    ["Valparaíso", ["MUNICIPALIDAD DE NOGALES", "COSTA CENTRAL"]],
    ["Región Metropolitana de Santiago", ["MUNICIPALIDAD DE COLINA", "MUNICIPALIDAD DE PAINE", "MUNICIPALIDAD DE PUENTE ALTO", "MUNICIPALIDAD LO BARNECHEA"]],
    ["Maule", ["MUNICIPALIDAD DE CHANCO", "MUNICIPALIDAD DE SAN CLEMENTE", "REGIONAL DEL MAULE"]],
    ["Bío-Bío", ["MUNICIPALIDAD DE LAJA", "MUNICIPALIDAD DE SANTA BARBARA", "SERVICIO DE SALUD ARAUCO"]],
    ["La Araucanía", ["MUNICIPALIDAD DE CARAHUE", "MUNICIPALIDAD DE CUNCO", "MUNICIPALIDAD DE LONCOCHE", "MUNICIPALIDAD DE GALVARINO"]],
    ["Los Lagos", ["MUNICIPALIDAD DE FRESIA", "MUNICIPALIDAD DE LLANQUIHUE", "MUNICIPALIDAD DE PUERTO MONTT"]],
    ["Magallanes y Antártica Chilena", ["MUNICIPALIDAD DE SAN GREGORIO"]],
  ];
  return rules.find(([, patterns]) => patterns.some((pattern) => entity.includes(pattern)))?.[0] || "";
}

function withChileHomeRegion(item: Opportunity) {
  return { ...item, region: chileRegionFromOpportunity(item) };
}

function regionFill(count: number, max: number) {
  if (count <= 0) return "#dfeaf6";
  const ratio = Math.min(1, count / Math.max(1, max));
  if (ratio >= 0.75) return "#0b2e63";
  if (ratio >= 0.45) return "#1559b7";
  if (ratio >= 0.2) return "#4f94e8";
  return "#a8cff7";
}

function cleanSvgPathAttributes(value: string) {
  return value
    .replace(/\sclass="[^"]*"/gi, "")
    .replace(/\sstyle="[^"]*"/gi, "")
    .replace(/\stabindex="[^"]*"/gi, "")
    .replace(/\srole="[^"]*"/gi, "")
    .replace(/\saria-label="[^"]*"/gi, "")
    .replace(/\sdata-region-key="[^"]*"/gi, "")
    .replace(/\sdata-count="[^"]*"/gi, "")
    .replace(/\s*\/\s*$/g, "");
}

function enrichMapSvg(country: Country, regionCounts: Map<string, number>, selectedRegion: string | null) {
  const raw = country === "Chile" ? chileRegionsSvg : peruRegionsSvg;
  const max = Math.max(1, ...Array.from(regionCounts.values()));
  const rootClass = country === "Chile" ? "interactive-country-map chile" : "interactive-country-map peru";
  let svg = raw
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/\swidth="[^"]*"/i, "")
    .replace(/\sheight="[^"]*"/i, "")
    .replace(/\sviewbox=/i, " viewBox=")
    .replace("<svg", `<svg class="${rootClass}" preserveAspectRatio="xMidYMid meet"`);

  if (country === "Chile") {
    svg = svg.replace(/\sviewBox="[^"]*"/i, ' viewBox="400 0 250 1000"');
  }

  if (country === "Peru") {
    return svg.replace(/<path\b([^>]*?)data-region="([^"]+)"([^>]*)>/gi, (_match, before, region, after) => {
      const key = normalizeRegionName(region);
      if (!key) return `<path${cleanSvgPathAttributes(before)}${cleanSvgPathAttributes(after)} class="map-area-muted" aria-hidden="true" />`;
      if (key === "LAGO TITICACA") return `<path${cleanSvgPathAttributes(before)}${cleanSvgPathAttributes(after)} class="map-water" aria-hidden="true" />`;
      const count = regionCounts.get(key) || 0;
      const selected = selectedRegion === key;
      const cssClass = `country-region${count ? " has-data" : ""}${selected ? " is-selected" : ""}`;
      const attrs = `data-region="${escapeHtml(region)}" data-region-key="${escapeHtml(key)}" data-count="${count}" tabindex="0" role="button" aria-label="${escapeHtml(region)}: ${count} procesos" style="--region-fill:${regionFill(count, max)}"`;
      return `<path${cleanSvgPathAttributes(before)}${cleanSvgPathAttributes(after)} class="${cssClass}" ${attrs} />`;
    });
  }

  return svg.replace(/<path\b([^>]*?)name="([^"]+)"([^>]*)>/gi, (_match, before, region, after) => {
    const key = normalizeRegionName(region);
    const count = regionCounts.get(key) || 0;
    const selected = selectedRegion === key;
    const cssClass = `country-region${count ? " has-data" : ""}${selected ? " is-selected" : ""}`;
    const attrs = `name="${escapeHtml(region)}" data-region="${escapeHtml(region)}" data-region-key="${escapeHtml(key)}" data-count="${count}" tabindex="0" role="button" aria-label="${escapeHtml(region)}: ${count} procesos" style="--region-fill:${regionFill(count, max)}"`;
    return `<path${cleanSvgPathAttributes(before)}${cleanSvgPathAttributes(after)} class="${cssClass}" ${attrs} />`;
  });
}

function InteractiveCountryMap({
  country,
  regions,
  selectedRegion,
  onSelectRegion,
}: {
  country: Country;
  regions: Array<{ key: string; name: string; count: number; percent: number }>;
  selectedRegion: string | null;
  onSelectRegion: (region: string) => void;
}) {
  const regionCounts = useMemo(() => new Map(regions.map((item) => [item.key, item.count])), [regions]);
  const svgMarkup = useMemo(() => enrichMapSvg(country, regionCounts, selectedRegion), [country, regionCounts, selectedRegion]);

  function selectFromTarget(target: EventTarget | null) {
    if (!(target instanceof Element)) return;
    const region = target.closest<SVGElement>("[data-region-key]");
    const key = region?.dataset.regionKey;
    if (key) onSelectRegion(key);
  }

  return (
    <div
      className={`interactive-map-shell ${country === "Chile" ? "chile" : "peru"}`}
      onClick={(event) => selectFromTarget(event.target)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectFromTarget(event.target);
        }
      }}
      dangerouslySetInnerHTML={{ __html: svgMarkup }}
    />
  );
}

function CountryMapOrb({ country }: { country: Country }) {
  return (
    <div className="country-map-orb" aria-hidden="true">
      <img src={countryFlagUrls[country]} alt="" />
    </div>
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

async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
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

function defaultRadarKeywords(country: Country): RadarKeyword[] {
  return homeKeywordHints
    .filter((item) => item.label !== "telecomunicaciones")
    .map((item) => ({
      id: null,
      country: country.toLowerCase() as "peru" | "chile",
      keyword: item.label,
      is_default: true,
    }));
}

function useRadarKeywords(token: string, country: Country) {
  const apiCountry = country.toLowerCase() as "peru" | "chile";
  const [keywords, setKeywords] = useState<RadarKeyword[]>(() => defaultRadarKeywords(country));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      setKeywords(await api.radarKeywords(token, apiCountry));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar las palabras clave");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setKeywords(defaultRadarKeywords(country));
    refresh();
  }, [token, country]);

  async function add(keyword: string) {
    const created = await api.createRadarKeyword(token, apiCountry, keyword);
    setKeywords((current) => [...current, created]);
    return created;
  }

  async function remove(keywordId: number) {
    await api.deleteRadarKeyword(token, apiCountry, keywordId);
    setKeywords((current) => current.filter((item) => item.id !== keywordId));
  }

  return { keywords, loading, error, setError, refresh, add, remove };
}

type LoginMode = "login" | "forgot" | "reset";
type LegalView = LegalDocumentKey;
type LegalDocumentsMap = Partial<Record<LegalView, LegalDocumentRecord>>;

function legalInlineText(text: string) {
  return text.split(/(privacidad@rodar\.pe)/gi).map((part, index) => (
    part.toLowerCase() === "privacidad@rodar.pe"
      ? <a key={`${part}-${index}`} href="mailto:privacidad@rodar.pe">{part}</a>
      : <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>
  ));
}

function LegalTextContent({ content }: { content: string }) {
  const nodes: React.ReactNode[] = [];
  let listItems: string[] = [];
  const flushList = () => {
    if (!listItems.length) return;
    const items = listItems;
    listItems = [];
    nodes.push(<ul key={`list-${nodes.length}`}>{items.map((item, index) => <li key={`${item}-${index}`}>{legalInlineText(item)}</li>)}</ul>);
  };

  content.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }
    if (line.startsWith("- ")) {
      listItems.push(line.slice(2).trim());
      return;
    }
    flushList();
    if (line.startsWith("## ")) {
      nodes.push(<h3 key={`heading-${nodes.length}`}>{line.slice(3)}</h3>);
    } else {
      nodes.push(<p className={line.toLowerCase().startsWith("última actualización:") ? "legal-updated" : undefined} key={`paragraph-${nodes.length}`}>{legalInlineText(line)}</p>);
    }
  });
  flushList();
  return <div className="legal-document">{nodes}</div>;
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

function TermsContent({ content }: { content?: string }) {
  if (content) return <LegalTextContent content={content} />;
  return (
    <div className="legal-document">
      <p className="legal-updated">Última actualización: Julio 2026</p>
      <p>
        Estos Términos de Servicio regulan el acceso y uso de GovRadar, la plataforma SaaS operada por Rodar
        Consulting S.A.C. (en adelante, “la Empresa”). Al ingresar, el usuario confirma que cuenta con autorización
        de su organización y acepta estas condiciones.
      </p>
      <h3>1. Alcance del servicio</h3>
      <p>
        GovRadar facilita el monitoreo de procesos de contratación pública, la priorización de oportunidades y el
        envío de alertas configuradas por el usuario. La plataforma consolida información de fuentes públicas, pero
        no reemplaza la consulta de los portales oficiales ni garantiza la adjudicación, vigencia o integridad de un proceso.
      </p>
      <h3>2. Cuenta y acceso autorizado</h3>
      <p>
        El usuario debe mantener sus credenciales bajo reserva, proporcionar datos de cuenta correctos y notificar
        cualquier acceso no autorizado. Cada cuenta debe utilizarse exclusivamente para los fines comerciales lícitos
        de la organización autorizada.
      </p>
      <h3>3. Configuración y uso responsable</h3>
      <p>
        El usuario es responsable de las palabras clave, reglas de alerta, destinatarios y criterios de seguimiento que
        configure. Antes de tomar decisiones comerciales deberá validar fechas, requisitos y documentos en la fuente oficial.
      </p>
      <h3>4. Disponibilidad y evolución</h3>
      <p>
        La Empresa aplica esfuerzos razonables para mantener el servicio disponible y seguro. Durante la fase de
        validación pueden realizarse mejoras, mantenimientos o ajustes que modifiquen temporalmente alguna funcionalidad.
      </p>
      <h3>5. Privacidad y confidencialidad</h3>
      <p>
        El tratamiento de datos se rige por la Política de Privacidad. Las estrategias, búsquedas y oportunidades del
        cliente se protegen conforme a la Cláusula de Confidencialidad de Datos Comerciales y Gubernamentales.
      </p>
      <h3>6. Propiedad intelectual</h3>
      <p>
        El software, la interfaz, la marca y los componentes propios de GovRadar pertenecen a la Empresa. Los datos
        provenientes de organismos públicos conservan la titularidad y condiciones de sus fuentes de origen.
      </p>
      <h3>7. Suspensión o terminación</h3>
      <p>
        La Empresa podrá restringir el acceso ante usos ilícitos, intentos de vulneración, divulgación de credenciales
        o incumplimientos graves. La terminación no extingue las obligaciones de confidencialidad aplicables.
      </p>
      <h3>8. Actualizaciones y contacto</h3>
      <p>
        Estos términos podrán actualizarse para reflejar cambios funcionales o normativos, indicando siempre su fecha
        de revisión. Las consultas pueden enviarse a <a href="mailto:privacidad@rodar.pe">privacidad@rodar.pe</a>.
      </p>
    </div>
  );
}

function PrivacyContent({ content }: { content?: string }) {
  if (content) return <LegalTextContent content={content} />;
  return (
    <div className="legal-document">
      <p className="legal-updated">Última actualización: Julio 2026</p>
      <p>
        Rodar Consulting S.A.C. (en adelante, “la Empresa”) está comprometida con la seguridad y privacidad de la
        información de sus usuarios. Esta política describe cómo tratamos los datos dentro de nuestra plataforma SaaS.
      </p>
      <h3>A. Datos recopilados</h3>
      <ul>
        <li><strong>Datos de cuenta:</strong> nombres, correos electrónicos, cargos y datos de contacto de los usuarios autorizados.</li>
        <li><strong>Datos de operación:</strong> información sobre procesos, licitaciones, alertas y palabras clave que el usuario configura o gestiona dentro del CRM.</li>
      </ul>
      <h3>B. Finalidad del tratamiento</h3>
      <p>Los datos recopilados se utilizan exclusivamente para:</p>
      <ul>
        <li>Proveer, operar y mantener las funcionalidades de la plataforma.</li>
        <li>Enviar alertas automáticas y notificaciones configuradas por el usuario.</li>
        <li>Brindar soporte técnico y optimizar la experiencia durante esta fase de validación.</li>
      </ul>
      <h3>C. Seguridad de la información</h3>
      <p>
        Implementamos medidas técnicas y organizativas estándar de la industria, como cifrado de datos en tránsito y
        controles de acceso restringido, para proteger la información contra accesos no autorizados, pérdida o alteración.
      </p>
      <h3>D. Derechos ARCO</h3>
      <p>
        Los usuarios pueden ejercer sus derechos de Acceso, Rectificación, Cancelación y Oposición sobre sus datos de
        cuenta mediante una solicitud formal a <a href="mailto:privacidad@rodar.pe">privacidad@rodar.pe</a>.
      </p>
    </div>
  );
}

function ConfidentialityContent({ content }: { content?: string }) {
  if (content) return <LegalTextContent content={content} />;
  return (
    <div className="legal-document confidentiality-document">
      <h3>Reconocimiento de información sensible</h3>
      <p>
        Rodar Consulting S.A.C. reconoce que los criterios de búsqueda, palabras clave, estrategias de seguimiento,
        analítica de mercado y asignación de oportunidades comerciales configuradas por el usuario dentro de la
        plataforma constituyen Información Confidencial y de alto valor estratégico para el negocio del cliente.
      </p>
      <h3>Compromiso de no divulgación</h3>
      <p>La Empresa se compromete estrictamente a:</p>
      <ul>
        <li>No vender, comercializar, transferir ni divulgar a terceros —incluidos otros clientes o competidores— información, reportes o estrategias extraídas de la actividad del usuario.</li>
        <li>Mantener absoluta reserva sobre los procesos específicos del Estado, incluidos SEACE, Mercado Público, OCDS y contratos, que el cliente monitorea activamente o gestiona en su embudo comercial.</li>
        <li>Utilizar datos agregados y completamente anonimizados únicamente con fines estadísticos globales de rendimiento del software, sin permitir la identificación del cliente ni de sus objetivos comerciales.</li>
      </ul>
      <p>
        Esta obligación de confidencialidad permanecerá vigente durante todo el periodo de uso del SaaS y se mantendrá
        de forma indefinida tras la terminación del servicio.
      </p>
    </div>
  );
}

function LegalDialog({ view, documents, onClose }: { view: LegalView; documents: LegalDocumentsMap; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const title = view === "terms"
    ? "Términos de Servicio"
    : view === "privacy"
      ? "Política de Privacidad"
      : "Cláusula de Confidencialidad";

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <div className="legal-dialog-backdrop" onMouseDown={onClose}>
      <section className="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="legal-dialog-header">
          <div>
            <span>GovRadar · Información legal</span>
            <h2 id="legal-dialog-title">{title}</h2>
          </div>
          <button ref={closeButtonRef} className="legal-dialog-close" type="button" onClick={onClose} aria-label={`Cerrar ${title}`}>×</button>
        </header>
        <div className="legal-dialog-body">
          {view === "terms"
            ? <TermsContent content={documents.terms?.content} />
            : view === "privacy"
              ? <PrivacyContent content={documents.privacy?.content} />
              : <ConfidentialityContent content={documents.confidentiality?.content} />}
        </div>
      </section>
    </div>
  );
}

function Login({ onLogin, resetToken = "" }: { onLogin: (token: string, email: string) => void; resetToken?: string }) {
  const [email, setEmail] = useState("admin@seace-radar.local");
  const [password, setPassword] = useState("Admin12345");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState<LoginMode>(resetToken ? "reset" : "login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [legalView, setLegalView] = useState<LegalView | null>(null);
  const legalDocuments = useLegalDocuments();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      if (mode === "forgot") {
        const result = await requestPasswordReset(email);
        setSuccess(result.message);
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
            <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          </label>
        ) : null}
        {mode !== "forgot" ? (
          <label>
            {mode === "reset" ? "Nueva contraseña" : "Contraseña"}
            <input required minLength={mode === "reset" ? 8 : undefined} value={password} onChange={(event) => setPassword(event.target.value)} type={showPassword ? "text" : "password"} autoComplete={mode === "reset" ? "new-password" : "current-password"} />
          </label>
        ) : null}
        {mode === "reset" ? (
          <label>
            Confirmar nueva contraseña
            <input required minLength={8} value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} type={showPassword ? "text" : "password"} autoComplete="new-password" />
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
        <button className="primary" disabled={loading}>{loading ? "Procesando..." : content.action}</button>
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

function AppShell({
  email,
  onLogout,
}: {
  email: string;
  onLogout: () => void;
}) {
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
  const userName = currentUser?.full_name || displayUserName(email);
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
    if (page === "Inicio Chile" || page === "Oportunidades Chile LMP-GC") {
      setCountry("Chile");
    } else if (page === "Inicio Peru" || page === "Oportunidades" || page === "Oportunidades OCDS Peru") {
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
                                <strong>{item}</strong>
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
        {page === "Inicio Peru" ? <Home country="Peru" token={token} isAdmin={currentUser?.role === "admin"} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} onSearchKeyword={(keyword) => openKeywordSearch("Peru", keyword)} onOpenLegal={setLegalView} /> : null}
        {page === "Inicio Chile" ? <Home country="Chile" token={token} isAdmin={currentUser?.role === "admin"} runs={backend.runs} alerts={backend.alerts} opportunities={backend.opportunities} onSearchKeyword={(keyword) => openKeywordSearch("Chile", keyword)} onOpenLegal={setLegalView} /> : null}
        {page === "Oportunidades" ? <Opportunities country="Peru" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} /> : null}
        {page === "Oportunidades Chile LMP-GC" ? <Opportunities country="Chile" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} prefillKeyword={keywordSearchHandoff?.country === "Chile" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} /> : null}
        {page === "Oportunidades OCDS Peru" ? <Opportunities country="Peru" token={token} data={backend.opportunities} runs={backend.runs} refresh={backend.refresh} variant="ocds" prefillKeyword={keywordSearchHandoff?.country === "Peru" ? keywordSearchHandoff.keyword : null} onPrefillConsumed={() => setKeywordSearchHandoff(null)} /> : null}
        {page === "Alertas" ? <Alerts token={token} rules={backend.rules} alerts={backend.alerts} refresh={backend.refresh} /> : null}
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
            versionLabel={versionLabel}
            onVersionUpdated={setVersionLabel}
          />
        ) : null}
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

function Kpis({
  stats,
  country,
  activeFilter = "all",
  onFilterChange,
  yearCounts = [],
  selectedYear,
  yearBreakdownOpen = false,
  onYearChange,
  onToggleYearBreakdown,
  contextLabel,
  contextAction,
}: {
  stats: Stats | null;
  country: Country;
  activeFilter?: HomeStatusFilter;
  onFilterChange?: (filter: HomeStatusFilter) => void;
  yearCounts?: Array<{ year: string; count: number }>;
  selectedYear?: string | null;
  yearBreakdownOpen?: boolean;
  onYearChange?: (year: string | null) => void;
  onToggleYearBreakdown?: () => void;
  contextLabel?: string;
  contextAction?: React.ReactNode;
}) {
  const values: Array<{ label: string; value: React.ReactNode; hint: string; filter?: HomeStatusFilter; tone?: "success" | "danger" }> = [
    { label: "Procesos radar", value: stats?.total ?? 0, hint: yearBreakdownOpen ? "Ocultar desglose anual" : "Ver desglose por año", filter: "all" },
    { label: "Prioridad A", value: stats?.by_priority?.A ?? 0, hint: "Revisar Inmediatamente", filter: "priority-a", tone: "success" },
    { label: "Vigentes", value: stats?.vigentes ?? 0, hint: "Presentar Consultas o Propuestas", filter: "vigentes", tone: "success" },
    { label: "Cerrados", value: stats?.cerrados ?? 0, hint: "Procesos Finalizados", filter: "cerrados", tone: "danger" },
    { label: "Monto detectado", value: formatMoney(stats?.total_amount ?? 0, country), hint: "Valor referencial" },
  ];
  return (
    <>
      <section className="kpi-grid">
        {values.map((item) => {
          const content = (
            <>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.hint}</small>
            </>
          );
          if (item.filter && onFilterChange) {
            const filter = item.filter;
            return (
              <button
                className={`kpi kpi-action ${item.tone ? `kpi-${item.tone}` : ""} ${activeFilter === item.filter ? "active" : ""}`}
                key={item.label}
                type="button"
                aria-pressed={activeFilter === item.filter}
                aria-expanded={filter === "all" ? yearBreakdownOpen : undefined}
                onClick={() => {
                  onFilterChange(filter);
                  if (filter === "all") onToggleYearBreakdown?.();
                }}
              >
                {content}
              </button>
            );
          }
          return <article className="kpi" key={item.label}>{content}</article>;
        })}
      </section>
      {yearBreakdownOpen && onYearChange ? (
        <section className="year-filter-panel" aria-label="Filtrar procesos por año">
          <div>
            <strong>Procesos por año</strong>
            <span>Selecciona un año para actualizar el mapa y sus resultados.</span>
          </div>
          <div className="year-filter-actions">
            <button
              type="button"
              className={selectedYear === null ? "selected" : ""}
              aria-pressed={selectedYear === null}
              onClick={() => onYearChange(null)}
            >
              <b>{stats?.total ?? 0}</b> Todos
            </button>
            {yearCounts.map(({ year, count }) => (
              <button
                type="button"
                className={selectedYear === year ? "selected" : ""}
                aria-pressed={selectedYear === year}
                key={year}
                onClick={() => onYearChange(year)}
              >
                <b>{count}</b> {year}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {contextLabel ? (
        <div className="dashboard-context-row">
          <p className="dashboard-context-line">{contextLabel}</p>
          {contextAction}
        </div>
      ) : null}
    </>
  );
}

function Home({
  country,
  token,
  isAdmin,
  runs,
  alerts,
  opportunities,
  onSearchKeyword,
  onOpenLegal,
}: {
  country: Country;
  token: string;
  isAdmin: boolean;
  runs: Run[];
  alerts: Alert[];
  opportunities: Opportunity[];
  onSearchKeyword: (keyword: string) => void;
  onOpenLegal: (view: LegalView) => void;
}) {
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [homeFilter, setHomeFilter] = useState<HomeStatusFilter>("all");
  const [selectedYear, setSelectedYear] = useState<string | null>(null);
  const [yearBreakdownOpen, setYearBreakdownOpen] = useState(false);
  const [keywordEditorOpen, setKeywordEditorOpen] = useState(false);
  const [newKeyword, setNewKeyword] = useState("");
  const [keywordSaving, setKeywordSaving] = useState(false);
  const [keywordNotice, setKeywordNotice] = useState("");
  const [removedHomeIds, setRemovedHomeIds] = useState<Set<number>>(new Set());
  const [pendingHomeRemoval, setPendingHomeRemoval] = useState<Opportunity | null>(null);
  const [copyNotice, setCopyNotice] = useState("");
  const copyNoticeTimerRef = useRef<number | null>(null);
  const radarKeywordState = useRadarKeywords(token, country);
  const keywordHints = useMemo(
    () => radarKeywordState.keywords.map((item) => ({ label: item.keyword, terms: [item.keyword] })),
    [radarKeywordState.keywords],
  );
  const countryOpportunities = useMemo(
    () => opportunities
      .filter((item) => sourceBelongsToCountry(item.source, country))
      .filter((item) => matchesAnyKeywordHint(item, keywordHints))
      .map((item) => country === "Chile" ? withChileHomeRegion(item) : item),
    [opportunities, country, keywordHints],
  );
  const homeKeywordTerms = useMemo(
    () => keywordContextFromHints(countryOpportunities, keywordHints),
    [countryOpportunities, keywordHints],
  );
  const displayedHomeKeywordTerms = useMemo(
    () => radarKeywordState.keywords.map((item) => item.keyword),
    [radarKeywordState.keywords],
  );
  const yearCounts = useMemo(() => {
    const counts = new Map<string, number>();
    countryOpportunities.forEach((item) => {
      const year = opportunityYear(item);
      counts.set(year, (counts.get(year) || 0) + 1);
    });
    return Array.from(counts, ([year, count]) => ({ year, count })).sort((left, right) => {
      if (left.year === "Sin año") return 1;
      if (right.year === "Sin año") return -1;
      return Number(right.year) - Number(left.year);
    });
  }, [countryOpportunities]);
  const filteredHomeOpportunities = useMemo(
    () => countryOpportunities.filter((item) => matchesHomeStatusFilter(item, homeFilter) && (selectedYear === null || opportunityYear(item) === selectedYear)),
    [countryOpportunities, homeFilter, selectedYear],
  );
  const countryRuns = useMemo(
    () => runs.filter((run) => sourceBelongsToCountry(run.source, country)),
    [runs, country],
  );
  const homeStats = useMemo(() => summarizeOpportunities(countryOpportunities), [countryOpportunities]);
  const filteredHomeStats = useMemo(() => summarizeOpportunities(filteredHomeOpportunities), [filteredHomeOpportunities]);
  const lastRun = countryRuns[0];
  const regionRows = regionSummary(filteredHomeStats, filteredHomeOpportunities);
  const countryLabel = country === "Chile" ? "Chile" : "Peru";
  const homeContextLabel = country === "Chile"
    ? `Palabras detectadas: ${displayedHomeKeywordTerms.join(", ")}. Vigentes + cerrados se calculan con los plazos de consultas y cierre de ofertas.`
    : `Palabras detectadas: ${displayedHomeKeywordTerms.join(", ")}. Vigentes + cerrados se calculan con el semaforo comercial.`;
  const selectedRegionRow = selectedRegion ? regionRows.items.find((item) => item.key === selectedRegion) : null;
  const selectedRegionProcesses = useMemo(() => {
    const filtered = selectedRegion === unmappedRegionKey
      ? filteredHomeOpportunities.filter((item) => !normalizeRegionName(item.region))
      : selectedRegion
        ? filteredHomeOpportunities.filter((item) => normalizeRegionName(item.region) === selectedRegion)
        : filteredHomeOpportunities;
    return filtered
      .filter((item) => !removedHomeIds.has(item.id))
      .slice()
      .sort((left, right) => {
        const rightDate = parseDate(right.publication_date) || parseDate(right.proposal_deadline) || parseDate(right.quote_deadline) || 0;
        const leftDate = parseDate(left.publication_date) || parseDate(left.proposal_deadline) || parseDate(left.quote_deadline) || 0;
        return rightDate - leftDate;
      })
      .slice(0, 8);
  }, [filteredHomeOpportunities, selectedRegion, removedHomeIds]);

  async function copyProcessNomenclature(item: Opportunity) {
    const nomenclature = item.nomenclature.trim();
    if (!nomenclature) return;
    await copyToClipboard(nomenclature);
    setCopyNotice("Nomenclatura Copiada, puedes ver el detalle en el módulo Oportunidades");
    if (copyNoticeTimerRef.current !== null) window.clearTimeout(copyNoticeTimerRef.current);
    copyNoticeTimerRef.current = window.setTimeout(() => setCopyNotice(""), 3200);
  }

  function removeHomeProcess() {
    if (!pendingHomeRemoval) return;
    setRemovedHomeIds((current) => new Set(current).add(pendingHomeRemoval.id));
    setPendingHomeRemoval(null);
  }

  async function addRadarKeyword(event: React.FormEvent) {
    event.preventDefault();
    const cleanKeyword = newKeyword.trim();
    if (!cleanKeyword) return;
    setKeywordSaving(true);
    setKeywordNotice("");
    radarKeywordState.setError("");
    try {
      await radarKeywordState.add(cleanKeyword);
      setNewKeyword("");
      setKeywordNotice(`“${cleanKeyword}” se agregó a ${country}.`);
    } catch (err) {
      radarKeywordState.setError(err instanceof Error ? err.message : "No se pudo agregar la palabra clave");
    } finally {
      setKeywordSaving(false);
    }
  }

  async function removeRadarKeyword(item: RadarKeyword) {
    if (item.id === null) return;
    setKeywordSaving(true);
    setKeywordNotice("");
    radarKeywordState.setError("");
    try {
      await radarKeywordState.remove(item.id);
      setKeywordNotice(`“${item.keyword}” dejó de usarse en nuevas búsquedas.`);
    } catch (err) {
      radarKeywordState.setError(err instanceof Error ? err.message : "No se pudo retirar la palabra clave");
    } finally {
      setKeywordSaving(false);
    }
  }

  useEffect(() => {
    setSelectedRegion(null);
  }, [country, homeFilter, selectedYear]);

  useEffect(() => {
    setHomeFilter("all");
    setSelectedYear(null);
    setYearBreakdownOpen(false);
    setRemovedHomeIds(new Set());
    setPendingHomeRemoval(null);
    setCopyNotice("");
  }, [country]);

  useEffect(() => () => {
    if (copyNoticeTimerRef.current !== null) window.clearTimeout(copyNoticeTimerRef.current);
  }, []);

  const coverage = country === "Chile" ? [
    ["Mercado Público", homeStats?.ocds_total ?? 0, "Licitaciones y Grandes Compras"],
    ["Con RUT", homeStats?.with_ruc ?? 0, "Organismo comprador identificado"],
    ["Con región", homeStats?.with_region ?? 0, "Ubicación regional disponible"],
  ] as const : [
    ["OCDS API", homeStats?.ocds_total ?? 0, "Procesos desde fuente estructurada"],
    ["Con RUC", homeStats?.with_ruc ?? 0, "Comprador identificado"],
    ["Con region", homeStats?.with_region ?? 0, "Listos para mapa"],
  ] as const;
  return (
    <>
      <section className="hero-panel">
        <div>
          <p className="overline">{country === "Peru" ? "Modulo Peru" : "Modulo Chile"}</p>
          <h2>{country === "Peru" ? "SEACE operativo, monitoreo automatico y alertas accionables." : "Mercado Público bajo vigilancia comercial y regional."}</h2>
          <p>
            {country === "Chile"
              ? "La vista prioriza licitaciones y Grandes Compras, sus plazos de oferta, organismos compradores, regiones y documentos disponibles."
              : "La pantalla prioriza procesos con oportunidad comercial, estado de ejecucion, documentos y reglas de alerta sin exponer herramientas tecnicas al usuario final."}
          </p>
        </div>
        <div className="radar-sweep" aria-hidden="true">
          <span />
          <b />
        </div>
      </section>
      <Kpis
        stats={homeStats}
        country={country}
        activeFilter={homeFilter}
        onFilterChange={setHomeFilter}
        yearCounts={yearCounts}
        selectedYear={selectedYear}
        yearBreakdownOpen={yearBreakdownOpen}
        onYearChange={setSelectedYear}
        onToggleYearBreakdown={() => setYearBreakdownOpen((value) => !value)}
        contextLabel={homeContextLabel}
        contextAction={isAdmin ? (
          <button
            className="keyword-manage-button"
            type="button"
            aria-expanded={keywordEditorOpen}
            onClick={() => setKeywordEditorOpen((current) => !current)}
          >
            {keywordEditorOpen ? "Cerrar gestión" : "Gestionar palabras clave"}
          </button>
        ) : undefined}
      />
      {keywordEditorOpen && isAdmin ? (
        <section className="keyword-manager" aria-label={`Palabras clave del radar ${country}`}>
          <div className="keyword-manager-heading">
            <div>
              <strong>Palabras clave de {country}</strong>
              <span>Las palabras base están protegidas. Las personalizadas pueden retirarse sin borrar procesos históricos.</span>
            </div>
            {radarKeywordState.loading ? <span className="keyword-loading">Actualizando…</span> : null}
          </div>
          <div className="keyword-chip-list">
            {radarKeywordState.keywords.map((item) => (
              <span className={`keyword-config-chip ${item.is_default ? "is-default" : ""}`} key={`${item.is_default ? "base" : item.id}-${item.keyword}`}>
                {item.keyword}
                {item.is_default ? <small>Base</small> : (
                  <span className="keyword-chip-actions">
                    <button className="keyword-search-button" type="button" onClick={() => onSearchKeyword(item.keyword)}>Buscar y sumar</button>
                    <button className="keyword-remove-button" type="button" aria-label={`Retirar ${item.keyword}`} disabled={keywordSaving} onClick={() => removeRadarKeyword(item)}>×</button>
                  </span>
                )}
              </span>
            ))}
          </div>
          <form className="keyword-add-form" onSubmit={addRadarKeyword}>
            <label htmlFor={`new-keyword-${country}`}>Nueva palabra o frase</label>
            <div>
              <input
                id={`new-keyword-${country}`}
                value={newKeyword}
                onChange={(event) => setNewKeyword(event.target.value)}
                placeholder="Ej. banda ancha satelital"
                maxLength={80}
              />
              <button className="primary" type="submit" disabled={keywordSaving || newKeyword.trim().length < 2}>
                {keywordSaving ? "Guardando…" : "Agregar"}
              </button>
            </div>
          </form>
          {radarKeywordState.error ? <div className="notice danger">{radarKeywordState.error}</div> : null}
          {keywordNotice ? <div className="notice success">{keywordNotice}</div> : null}
          <div className="keyword-confidentiality-note">
            <LockIcon className="keyword-lock-icon" />
            <p>
              Tus palabras clave y criterios de búsqueda están protegidos bajo nuestra estricta{" "}
              <button type="button" onClick={() => onOpenLegal("confidentiality")}>Cláusula de Confidencialidad</button>.
              Rodar Consulting no comparte tus estrategias comerciales.
            </p>
          </div>
        </section>
      ) : null}
      <section className="home-intelligence-grid">
        <article className="panel map-panel">
          <div className="panel-title">
            <div>
              <h3>Mapa comercial {countryLabel}</h3>
              <span>Distribucion regional de oportunidades detectadas</span>
            </div>
            <div className="panel-title-actions">
              {homeFilter !== "all" || selectedYear ? (
                <span className="data-pill subtle">
                  {[homeFilter !== "all" ? homeStatusFilterLabel(homeFilter) : null, selectedYear ? `Año ${selectedYear}` : null].filter(Boolean).join(" · ")}
                </span>
              ) : null}
              <span className="data-pill">{regionRows.total} procesos</span>
            </div>
          </div>
          <div className={`country-map-layout ${country === "Chile" ? "chile" : "peru"}`}>
            <div className="map-frame interactive">
              <strong className="map-frame-title">Vista de Procesos por Región</strong>
              <InteractiveCountryMap
                country={country}
                regions={regionRows.items}
                selectedRegion={selectedRegion}
                onSelectRegion={setSelectedRegion}
              />
              <CountryMapOrb country={country} />
              {selectedRegionRow && selectedRegion !== unmappedRegionKey ? (
                <strong className="map-selected-region" aria-live="polite">{selectedRegionRow.name}</strong>
              ) : null}
            </div>
            <div className="map-inspector">
              <div className="map-selection-card">
                <div>
                  <strong>{selectedRegionRow?.name || countryLabel}</strong>
                  <span>{selectedRegionRow?.count ?? regionRows.total} procesos visualizados</span>
                </div>
                {selectedRegion ? (
                  <button type="button" onClick={() => setSelectedRegion(null)}>Ver todo</button>
                ) : null}
              </div>
              <div className="region-ranking">
                {regionRows.items.slice(0, 8).map((item) => (
                  <button
                    className={`region-row ${selectedRegion === item.key ? "is-selected" : ""}`}
                    key={item.key}
                    type="button"
                    onClick={() => setSelectedRegion(item.key)}
                  >
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.count} procesos</span>
                    </div>
                    <i style={{ width: `${item.percent}%` }} />
                  </button>
                ))}
                {!regionRows.items.length ? <Empty text={`La region se llenara cuando el conector de ${countryLabel} entregue ubicacion normalizada.`} /> : null}
              </div>
              {selectedRegionProcesses.length ? (
                <div className="region-opportunity-list">
                  {selectedRegionProcesses.map((item) => (
                    <article className="map-opportunity-card" key={item.id}>
                      <button
                        className="map-opportunity-copy"
                        type="button"
                        aria-label={`Copiar nomenclatura ${item.nomenclature || "del proceso"}`}
                        onClick={() => copyProcessNomenclature(item)}
                      >
                        <span className="map-opportunity-heading">
                          <strong>{item.nomenclature || "Proceso sin nomenclatura"}</strong>
                          <span>{item.entity || "Entidad no informada"}</span>
                        </span>
                        <span className="map-opportunity-description"><HighlightedText text={item.description} terms={homeKeywordTerms} /></span>
                      </button>
                      <div className="map-opportunity-actions">
                        <button className="map-opportunity-remove" type="button" onClick={() => setPendingHomeRemoval(item)}>
                          Retirar de la Vista
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </article>
        <article className="panel api-enrichment-panel">
          <div className="panel-title">
            <div>
              <h3>{country === "Chile" ? "Cobertura de datos Chile" : "Cobertura de datos OCDS"}</h3>
              <span>Campos directos del gobierno sin abrir navegador</span>
            </div>
          </div>
          <div className="api-coverage-grid">
            {coverage.map(([label, value, hint]) => (
              <div className="coverage-item" key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
                <small>{hint}</small>
              </div>
            ))}
          </div>
          <div className="ocds-signal-list">
            <span>{country === "Chile" ? "Datos aprovechables: organismo comprador, RUT disponible, región, ID de licitación, moneda CLP, fechas de publicación y cierre, bases, anexos y estado comercial." : "Datos aprovechables: RUC comprador, region, OCID, tender ID, monto, fechas, documentos publicados y estado comercial."}</span>
            <span>{country === "Chile" ? "Mercado Público queda como fuente oficial para validar bases, anexos, aclaraciones y cambios de fecha antes de preparar una oferta." : "Para Inicio conviene cargar primero este resumen API/cache y dejar la web oficial como validacion puntual de fechas/documentos."}</span>
          </div>
        </article>
      </section>
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
      {copyNotice ? (
        <div className="copy-toast" role="status" aria-live="polite">
          <span aria-hidden="true">✓</span>
          {copyNotice}
        </div>
      ) : null}
      {pendingHomeRemoval ? (
        <ConfirmModal
          title="Retirar de la Vista"
          message="¿Está seguro de retirar este detalle de proceso?"
          confirmLabel="Sí"
          cancelLabel="No"
          onConfirm={removeHomeProcess}
          onCancel={() => setPendingHomeRemoval(null)}
        />
      ) : null}
    </>
  );
}

function normalizeRegionName(value: string) {
  const text = stripAccents((value || "").trim());
  if (!text) return "";
  const normalized = text
    .replace(/^departamento\s+de\s+/i, "")
    .replace(/^region\s+de\s+/i, "")
    .replace(/^region\s+/i, "")
    .replace(/\s+/g, " ")
    .toUpperCase();
  const aliases: Record<string, string> = {
    "LIMA METROPOLITANA": "LIMA",
    "BIOBIO": "BIO BIO",
    "BIO-BIO": "BIO BIO",
    "DEL LIBERTADOR GENERAL BERNARDO O HIGGINS": "LIBERTADOR GENERAL BERNARDO O HIGGINS",
    "AYSEN DEL GENERAL CARLOS IBANEZ DEL CAMPO": "AISEN DEL GENERAL CARLOS IBANEZ DEL CAMPO",
  };
  return aliases[normalized] || normalized;
}

function summarizeOpportunities(opportunities: Opportunity[]): Stats {
  const bySource: Record<string, number> = {};
  const byPriority: Record<string, number> = { A: 0, B: 0, C: 0 };
  const byRegion: Record<string, number> = {};
  let totalAmount = 0;
  let vigentes = 0;
  let cerrados = 0;
  let withRuc = 0;
  let withRegion = 0;
  let ocdsTotal = 0;
  let documentsKnown = 0;

  for (const item of opportunities) {
    bySource[item.source] = (bySource[item.source] || 0) + 1;
    byPriority[item.priority] = (byPriority[item.priority] || 0) + 1;
    const region = normalizeRegionName(item.region);
    if (region) {
      byRegion[region] = (byRegion[region] || 0) + 1;
      withRegion += 1;
    }
    if (item.buyer_ruc?.trim()) withRuc += 1;
    if (item.source.toLowerCase().startsWith("oece_ocds") || item.source.toLowerCase().startsWith("mercado_publico")) {
      ocdsTotal += 1;
    }
    if ((item.documents_count || 0) > 0 || item.requirement_pdf_url?.trim()) documentsKnown += 1;
    totalAmount += Number(item.amount || 0);
    const signal = commercialSignal(item).className;
    if (signal === "green" || signal === "amber") vigentes += 1;
    if (signal === "red") cerrados += 1;
  }

  return {
    total: opportunities.length,
    by_source: bySource,
    by_priority: byPriority,
    by_region: byRegion,
    vigentes,
    cerrados,
    total_amount: totalAmount,
    with_ruc: withRuc,
    with_region: withRegion,
    ocds_total: ocdsTotal,
    documents_known: documentsKnown,
  };
}

function regionSummary(stats: Stats | null, opportunities: Opportunity[]) {
  const source = stats?.by_region && Object.keys(stats.by_region).length
    ? stats.by_region
    : opportunities.reduce<Record<string, number>>((acc, item) => {
        const region = normalizeRegionName(item.region);
        if (region) acc[region] = (acc[region] || 0) + 1;
        return acc;
      }, {});
  const entries = Object.entries(source)
    .map(([name, count]) => {
      const key = normalizeRegionName(name);
      return { key, name: titleCaseRegion(key), count };
    })
    .filter((item) => item.key && item.count > 0)
    .sort((left, right) => right.count - left.count);
  const locatedTotal = entries.reduce((sum, item) => sum + item.count, 0);
  const unmappedTotal = Math.max(0, opportunities.length - locatedTotal);
  if (unmappedTotal > 0) {
    entries.push({ key: unmappedRegionKey, name: "Sin región", count: unmappedTotal });
  }
  const max = entries[0]?.count || 1;
  return {
    total: opportunities.length,
    items: entries.map((item) => ({ ...item, percent: Math.max(8, Math.round((item.count / max) * 100)) })),
  };
}

function RunProgress({ run, batchRuns = [], batchKeywords = [] }: { run: Run; batchRuns?: Run[]; batchKeywords?: string[] }) {
  const detail = parseRunDetails(run);
  const runs = batchRuns.length > 1 ? batchRuns : [run];
  const isBatch = runs.length > 1;
  const isLive = runs.some((item) => item.status === "queued" || item.status === "running");
  const terminalCount = runs.filter((item) => ["completed", "failed", "cancelled"].includes(item.status)).length;
  const failedCount = runs.filter((item) => item.status === "failed").length;
  const cancelledCount = runs.filter((item) => item.status === "cancelled").length;
  const progress = isBatch
    ? runs.reduce((total, item) => {
        if (item.status === "queued") return total;
        return total + estimateRunProgress(item);
      }, 0) / runs.length
    : estimateRunProgress(run);
  const currentRun = runs.find((item) => item.status === "running") || runs.find((item) => item.status === "queued");
  const currentKeyword = currentRun ? keywordFromRun(currentRun) : "";
  const heading = isBatch
    ? isLive
      ? `Procesando búsqueda ${Math.min(terminalCount + 1, runs.length)} de ${runs.length}`
      : failedCount
        ? "Búsqueda múltiple finalizada con incidencias"
        : cancelledCount
          ? "Búsqueda múltiple detenida"
          : "Búsqueda múltiple completada"
    : isLive
      ? "Procesando radar"
      : run.status === "completed"
        ? "Ejecución completada"
        : "Estado de ejecución";

  return (
    <div className={`run-progress ${isLive ? "live" : ""}`}>
      <div className="progress-head">
        <strong>{heading}</strong>
        <span>{isBatch ? `${terminalCount}/${runs.length} búsquedas finalizadas` : `Run #${run.id} · ${run.status}`}</span>
      </div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      {isBatch ? (
        <div className="batch-run-statuses" aria-label="Estado por palabra clave">
          {runs.map((item, index) => (
            <span className={`status ${item.status}`} key={item.id}>
              {batchKeywords[index] || keywordFromRun(item) || `Búsqueda ${index + 1}`}: {item.status === "completed" ? "lista" : item.status === "failed" ? "falló" : item.status === "cancelled" ? "detenida" : item.status === "running" ? "procesando" : "en cola"}
            </span>
          ))}
        </div>
      ) : (
        <div className="run-metrics">
          <span><b>{run.rows_found}</b> procesos</span>
          <span><b>{detail.configured ?? "-"}</b> detalles configurados</span>
          <span><b>{detail.reviewed !== null ? `${detail.reviewed}/${detail.requested}` : "-"}</b> revisados</span>
        </div>
      )}
      {isLive ? <div className="progress-current">{currentRun?.progress_message || (currentKeyword ? `Procesando “${currentKeyword}”` : "Procesando búsqueda")}</div> : null}
      {isBatch && failedCount ? <div className="notice danger">{failedCount} de {runs.length} búsquedas no pudieron completarse. Los resultados de las búsquedas terminadas se conservaron.</div> : null}
      {!isBatch && run.error_message ? <div className="notice danger">{run.error_message}</div> : null}
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
  prefillKeyword = null,
  onPrefillConsumed,
}: {
  country: Country;
  token: string;
  data: Opportunity[];
  runs: Run[];
  refresh: () => Promise<void>;
  variant?: OpportunityVariant;
  prefillKeyword?: string | null;
  onPrefillConsumed?: () => void;
}) {
  const storageScope = `${variant}.${country}`;
  const radarKeywordState = useRadarKeywords(token, country);
  const keywordSuggestionListId = `radar-keyword-suggestions-${country}-${variant}`;
  const initialSearchState = useMemo(() => loadActiveSearchState(storageScope), [storageScope]);
  const persistedScopeRef = useRef(storageScope);
  const restoredRunPeriodRef = useRef(false);
  const [module, setModule] = useState<Module>(defaultModuleForCountry(country));
  const [keyword, setKeyword] = useState(initialSearchState.keyword);
  const [keyword2, setKeyword2] = useState(initialSearchState.keyword2);
  const [keyword3, setKeyword3] = useState(initialSearchState.keyword3);
  const [nomenclatureFilter, setNomenclatureFilter] = useState(initialSearchState.nomenclatureFilter);
  const [entityFilter, setEntityFilter] = useState(initialSearchState.entityFilter);
  const [publicationDateFrom, setPublicationDateFrom] = useState(initialSearchState.publicationDateFrom);
  const [publicationDateTo, setPublicationDateTo] = useState(initialSearchState.publicationDateTo);
  const [ocdsYears, setOcdsYears] = useState<string[]>(initialSearchState.years);
  const [ocdsMonths, setOcdsMonths] = useState<string[]>(initialSearchState.months);
  const [appliedPeriodYears, setAppliedPeriodYears] = useState<string[]>(initialSearchState.appliedYears);
  const [appliedPeriodMonths, setAppliedPeriodMonths] = useState<string[]>(initialSearchState.appliedMonths);
  const [appliedPeriodKeywordGroups, setAppliedPeriodKeywordGroups] = useState<ActivePeriodKeywordGroup[]>(initialSearchState.periodKeywordGroups);
  const usesPeriodFilters = variant === "ocds" || country === "Chile";
  const [maxResultsMode, setMaxResultsMode] = useState<MaxResultsMode>(initialSearchState.maxResultsMode);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>(initialSearchState.searchMode);
  const [activeKeywords, setActiveKeywords] = useState<string[]>(initialSearchState.keywords);
  const [activeRunIds, setActiveRunIds] = useState<number[]>(initialSearchState.runIds);
  const [scopedRows, setScopedRows] = useState<Opportunity[] | null>(null);
  const [pinnedRows, setPinnedRows] = useState<Opportunity[]>([]);
  const [pendingSearch, setPendingSearch] = useState<PendingSearch | null>(null);
  const [pendingRunStatuses, setPendingRunStatuses] = useState<Run[]>([]);
  const [batchKeywords, setBatchKeywords] = useState<string[]>([]);
  const [confirmNewSearch, setConfirmNewSearch] = useState(false);
  const [confirmClearFields, setConfirmClearFields] = useState(false);
  const [prefillNotice, setPrefillNotice] = useState("");
  const [periodValidationError, setPeriodValidationError] = useState("");
  const visibleRuns = useMemo(() => runs.filter((run) => sourceBelongsToView(run.source, country, variant)), [runs, country, variant]);
  const invalidPublicationDateRange = Boolean(publicationDateFrom && publicationDateTo && publicationDateFrom > publicationDateTo);
  const activePeriodKeywordGroups = useMemo(
    () => {
      const runGroups = periodKeywordGroupsFromRuns(visibleRuns, activeRunIds);
      const fallbackGroups = [...appliedPeriodYears]
        .sort((left, right) => Number(right) - Number(left))
        .map((year) => ({
          year,
          months: [...appliedPeriodMonths].sort((left, right) => Number(left) - Number(right)),
          keywords: [...activeKeywords],
          commercialMode: maxResultsMode,
        }));
      return mergePeriodKeywordGroups(
        appliedPeriodKeywordGroups.length ? appliedPeriodKeywordGroups : fallbackGroups,
        runGroups,
      );
    },
    [visibleRuns, activeRunIds, appliedPeriodYears, appliedPeriodMonths, appliedPeriodKeywordGroups, activeKeywords, maxResultsMode],
  );

  useEffect(() => {
    const latest = visibleRuns.find((run) => run.id === activeRun?.id) || activeRun;
    setActiveRun(latest || null);
  }, [visibleRuns]);

  useEffect(() => {
    if (!activeRun && visibleRuns[0]) {
      const latestAppliedRun = visibleRuns.find((run) => activeRunIds.includes(run.id));
      setActiveRun(latestAppliedRun || visibleRuns[0]);
    }
  }, [activeRun, activeRunIds, visibleRuns]);

  useEffect(() => {
    if (activeKeywords.length) return;
    const recoverableKeywords = uniqueKeywords([keyword, keyword2, keyword3]);
    if (recoverableKeywords.length) setActiveKeywords(recoverableKeywords);
  }, [activeKeywords, keyword, keyword2, keyword3]);

  useEffect(() => {
    if (persistedScopeRef.current !== storageScope) return;
    saveActiveSearchState(storageScope, {
      keywords: activeKeywords,
      runIds: activeRunIds,
      keyword,
      keyword2,
      keyword3,
      nomenclatureFilter,
      entityFilter,
      publicationDateFrom,
      publicationDateTo,
      years: [...ocdsYears],
      months: [...ocdsMonths],
      appliedYears: [...appliedPeriodYears],
      appliedMonths: [...appliedPeriodMonths],
      periodKeywordGroups: appliedPeriodKeywordGroups,
      maxResultsMode,
      searchMode,
    });
  }, [
    storageScope,
    activeKeywords,
    activeRunIds,
    keyword,
    keyword2,
    keyword3,
    nomenclatureFilter,
    entityFilter,
    publicationDateFrom,
    publicationDateTo,
    ocdsYears,
    ocdsMonths,
    appliedPeriodYears,
    appliedPeriodMonths,
    appliedPeriodKeywordGroups,
    maxResultsMode,
    searchMode,
  ]);

  useEffect(() => {
    if (restoredRunPeriodRef.current || !usesPeriodFilters || !activeRunIds.length || !visibleRuns.length) return;
    const appliedPeriod = periodFiltersFromRuns(visibleRuns, activeRunIds);
    if (!appliedPeriod.years.length && !appliedPeriod.months.length) return;
    restoredRunPeriodRef.current = true;
    if (appliedPeriod.years.length) setAppliedPeriodYears(appliedPeriod.years);
    if (appliedPeriod.months.length) setAppliedPeriodMonths(appliedPeriod.months);
    const restoredGroups = periodKeywordGroupsFromRuns(visibleRuns, activeRunIds);
    if (restoredGroups.length) {
      setAppliedPeriodKeywordGroups((current) => mergePeriodKeywordGroups(current, restoredGroups));
    }
    const savedState = loadActiveSearchState(storageScope);
    saveActiveSearchState(storageScope, {
      ...savedState,
      years: appliedPeriod.years.length ? appliedPeriod.years : savedState.years,
      months: appliedPeriod.months.length ? appliedPeriod.months : savedState.months,
      appliedYears: appliedPeriod.years.length ? appliedPeriod.years : savedState.appliedYears,
      appliedMonths: appliedPeriod.months.length ? appliedPeriod.months : savedState.appliedMonths,
      periodKeywordGroups: mergePeriodKeywordGroups(savedState.periodKeywordGroups, restoredGroups),
    });
  }, [storageScope, usesPeriodFilters, activeRunIds, visibleRuns]);

  async function syncPendingSearch(search: PendingSearch, statuses: Run[]) {
    setPendingRunStatuses(statuses);
    const nextPendingRun = statuses.find((run) => run.status === "queued" || run.status === "running");
    if (nextPendingRun) {
      setActiveRun(nextPendingRun);
      return false;
    }
    const terminal = statuses.every((run) => ["completed", "failed", "cancelled"].includes(run.status));
    if (!terminal) return false;

    await refresh();
    const completedIds = statuses.filter((run) => run.status === "completed").map((run) => run.id);
    const completedKeywords = search.keywords.filter((_, index) => statuses[index]?.status === "completed");
    const nextKeywords = search.mode === "append" ? addKeywords(activeKeywords, completedKeywords) : completedKeywords;
    const nextRunIds = search.mode === "append" ? addRunIds(activeRunIds, completedIds) : completedIds;
    const runRows = nextRunIds.length ? await api.opportunities(token, { runIds: nextRunIds }) : [];
    setActiveKeywords(nextKeywords);
    setActiveRunIds(nextRunIds);
    setScopedRows(search.mode === "append" ? mergeOpportunities(pinnedRows, runRows) : runRows);
    saveActiveSearchState(storageScope, {
      ...search.appliedState,
      keywords: nextKeywords,
      runIds: nextRunIds,
    });
    setPendingSearch(null);
    setActiveRun(statuses[statuses.length - 1] || null);
    return true;
  }

  useEffect(() => {
    const nextInitialState = loadActiveSearchState(storageScope);
    persistedScopeRef.current = storageScope;
    restoredRunPeriodRef.current = false;
    setModule(defaultModuleForCountry(country));
    setKeyword(nextInitialState.keyword);
    setKeyword2(nextInitialState.keyword2);
    setKeyword3(nextInitialState.keyword3);
    setNomenclatureFilter(nextInitialState.nomenclatureFilter);
    setEntityFilter(nextInitialState.entityFilter);
    setPublicationDateFrom(nextInitialState.publicationDateFrom);
    setPublicationDateTo(nextInitialState.publicationDateTo);
    setOcdsYears(nextInitialState.years);
    setOcdsMonths(nextInitialState.months);
    setAppliedPeriodYears(nextInitialState.appliedYears);
    setAppliedPeriodMonths(nextInitialState.appliedMonths);
    setAppliedPeriodKeywordGroups(nextInitialState.periodKeywordGroups);
    setMaxResultsMode(nextInitialState.maxResultsMode);
    setSearchMode(nextInitialState.searchMode);
    setActiveRun(null);
    setActiveKeywords(nextInitialState.keywords);
    setActiveRunIds(nextInitialState.runIds);
    setScopedRows(null);
    setPinnedRows([]);
    setPendingSearch(null);
    setPendingRunStatuses([]);
    setBatchKeywords([]);
    setConfirmNewSearch(false);
    setConfirmClearFields(false);
  }, [country, storageScope]);

  useEffect(() => {
    const cleanKeyword = prefillKeyword?.trim();
    if (!cleanKeyword) return;
    setKeyword(cleanKeyword);
    setKeyword2("");
    setKeyword3("");
    setSearchMode("append");
    setMaxResultsMode("active");
    setConfirmNewSearch(false);
    setPrefillNotice(`“${cleanKeyword}” está lista para buscarse y sumar sus resultados a los procesos activos.`);
    onPrefillConsumed?.();
  }, [prefillKeyword]);

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
        if (pendingSearch?.runIds.includes(activeRun.id)) {
          const statuses = await Promise.all(pendingSearch.runIds.map((runId) => api.run(token, runId)));
          if (cancelled) return;
          setPendingRunStatuses(statuses);
          const nextLiveRun = statuses.find((item) => item.status === "running") || statuses.find((item) => item.status === "queued");
          if (nextLiveRun) setActiveRun(nextLiveRun);
          if (statuses.every((item) => ["completed", "failed", "cancelled"].includes(item.status))) {
            await syncPendingSearch(pendingSearch, statuses);
          }
        } else {
          const nextRun = await api.run(token, activeRun.id);
          if (cancelled) return;
          setActiveRun(nextRun);
          if (["completed", "failed", "cancelled"].includes(nextRun.status)) await refresh();
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

  // En Chile y OCDS Perú, los bloques de períodos activos son la definición
  // del conjunto visible. Los runIds sirven para recuperar la configuración,
  // pero no deben recortar procesos válidos ya presentes en la base acumulada.
  const baseRows = usesPeriodFilters ? data : scopedRows ?? data;
  const filtered = useMemo(() => {
    const normalizedActiveKeywords = activeKeywords.map((item) => item.toLowerCase()).filter(Boolean);
    const normalizedNomenclature = nomenclatureFilter.trim().toLowerCase();
    const normalizedEntity = stripAccents(entityFilter.trim()).toLowerCase();
    const publicationFromTime = dateFilterBoundary(publicationDateFrom, false);
    const publicationToTime = dateFilterBoundary(publicationDateTo, true);
    const activeOnly = maxResultsMode === "active";
    return baseRows.filter((item) => {
      if (!sourceBelongsToView(item.source, country, variant)) return false;
      const haystack = `${item.entity} ${item.nomenclature} ${item.description}`.toLowerCase();
      const keywordMatch = !normalizedActiveKeywords.length || normalizedActiveKeywords.some((item) => matchesCompletePhrase(haystack, item));
      const nomenclatureMatch = !normalizedNomenclature || item.nomenclature.toLowerCase().includes(normalizedNomenclature);
      const entityMatch = !normalizedEntity || stripAccents(item.entity).toLowerCase().includes(normalizedEntity);
      const activeMatch = !activeOnly || commercialSignal(item).className !== "red";
      const publicationTime = parseDate(item.publication_date);
      const publicationDateMatch = publicationFromTime === null && publicationToTime === null
        || publicationTime !== null
          && (publicationFromTime === null || publicationTime >= publicationFromTime)
          && (publicationToTime === null || publicationTime <= publicationToTime);
      const periodCombinationMatch = !usesPeriodFilters || !activePeriodKeywordGroups.length
        ? keywordMatch && activeMatch
        : activePeriodKeywordGroups.some((group) => opportunityMatchesPeriodGroup(item, group));
      return nomenclatureMatch && entityMatch && publicationDateMatch && periodCombinationMatch;
    });
  }, [baseRows, activeKeywords, nomenclatureFilter, entityFilter, publicationDateFrom, publicationDateTo, maxResultsMode, country, variant, usesPeriodFilters, activePeriodKeywordGroups]);

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
    if (invalidPublicationDateRange) return;
    const nextPeriodError = usesPeriodFilters
      ? futurePeriodValidationMessage(ocdsYears, ocdsMonths)
      : "";
    setPeriodValidationError(nextPeriodError);
    if (nextPeriodError) return;
    if (searchMode === "replace" && filtered.length > 0 && !confirmNewSearch) {
      setConfirmNewSearch(true);
      return;
    }
    await executeConfirmed(searchMode);
  }

  async function executeConfirmed(mode: SearchMode) {
    if (invalidPublicationDateRange) return;
    const nextPeriodError = usesPeriodFilters
      ? futurePeriodValidationMessage(ocdsYears, ocdsMonths)
      : "";
    setPeriodValidationError(nextPeriodError);
    if (nextPeriodError) return;
    const cleanNomenclature = nomenclatureFilter.trim();
    const cleanKeywords = cleanNomenclature
      ? [cleanNomenclature]
      : uniqueKeywords([keyword, keyword2, keyword3]).length
        ? uniqueKeywords([keyword, keyword2, keyword3])
        : ["satelital"];
    const forceDetailByNomenclature = Boolean(cleanNomenclature);
    const effectiveMaxDetails = forceDetailByNomenclature ? 1 : 0;
    const nextAppliedYears = mode === "append"
      ? uniqueDefined([...appliedPeriodYears, ...ocdsYears])
      : [...ocdsYears];
    const nextAppliedMonths = mode === "append"
      ? uniqueDefined([...appliedPeriodMonths, ...ocdsMonths])
      : [...ocdsMonths];
    const selectedPeriodGroups = periodKeywordGroupsForSelection(ocdsYears, ocdsMonths, cleanKeywords, maxResultsMode);
    const nextPeriodKeywordGroups = mode === "append"
      ? mergePeriodKeywordGroups(appliedPeriodKeywordGroups, selectedPeriodGroups)
      : selectedPeriodGroups;
    setConfirmNewSearch(false);
    setPrefillNotice("");
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
          max_results: 0,
          max_details: effectiveMaxDetails,
          enrich_details: forceDetailByNomenclature,
          commercial_mode: maxResultsMode,
        });
        startedRuns.push(run);
      }
      const runningRun = startedRuns.find((run) => run.status === "queued" || run.status === "running") || startedRuns[startedRuns.length - 1] || null;
      const startedRunIds = startedRuns.map((run) => run.id);
      const nextKeywords = mode === "append" ? addKeywords(activeKeywords, cleanKeywords) : cleanKeywords;
      const nextRunIds = mode === "append" ? addRunIds(activeRunIds, startedRunIds) : startedRunIds;
      const appliedState: SavedOpportunityViewState = {
        keywords: nextKeywords,
        runIds: nextRunIds,
        keyword,
        keyword2,
        keyword3,
        nomenclatureFilter,
        entityFilter,
        publicationDateFrom,
        publicationDateTo,
        years: [...ocdsYears],
        months: [...ocdsMonths],
        appliedYears: nextAppliedYears,
        appliedMonths: nextAppliedMonths,
        periodKeywordGroups: nextPeriodKeywordGroups,
        maxResultsMode,
        searchMode: mode,
      };
      setAppliedPeriodYears(nextAppliedYears);
      setAppliedPeriodMonths(nextAppliedMonths);
      setAppliedPeriodKeywordGroups(nextPeriodKeywordGroups);
      setActiveRun(runningRun);
      setPendingSearch({ mode, keywords: cleanKeywords, runIds: startedRunIds, appliedState });
      setPendingRunStatuses(startedRuns);
      setBatchKeywords(cleanKeywords);
      saveActiveSearchState(storageScope, appliedState);
      await refresh();
    } finally {
      setStarting(false);
    }
  }

  async function waitForRun(runId: number) {
    for (let index = 0; index < 120; index += 1) {
      const nextRun = await api.run(token, runId);
      setActiveRun(nextRun);
      if (["completed", "failed", "cancelled"].includes(nextRun.status)) return nextRun;
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
        commercial_mode: maxResultsMode,
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

  async function stopSearch() {
    const candidates = pendingRunStatuses.length ? pendingRunStatuses : activeRun ? [activeRun] : [];
    const liveRuns = candidates.filter((item) => (item.status === "queued" || item.status === "running") && !item.cancel_requested);
    if (!liveRuns.length) return;
    setStopping(true);
    try {
      const cancelledRuns = await Promise.all(liveRuns.map((item) => api.cancelRun(token, item.id)));
      setPendingRunStatuses((current) => current.map((item) => cancelledRuns.find((cancelled) => cancelled.id === item.id) || item));
      if (cancelledRuns[0]) setActiveRun(cancelledRuns[0]);
      await refresh();
    } finally {
      setStopping(false);
    }
  }

  function clearRequiredFilters() {
    setOcdsYears([String(currentYear)]);
    setOcdsMonths([String(new Date().getMonth() + 1)]);
    setMaxResultsMode("active");
  }

  function clearOptionalFilters() {
    setNomenclatureFilter("");
    setEntityFilter("");
    setPublicationDateFrom("");
    setPublicationDateTo("");
  }

  function clearFields() {
    setConfirmClearFields(false);
    setPrefillNotice("");
    setKeyword("");
    setKeyword2("");
    setKeyword3("");
    setNomenclatureFilter("");
    setEntityFilter("");
    setPublicationDateFrom("");
    setPublicationDateTo("");
    setSearchMode("append");
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          {country === "Chile" || variant === "ocds" ? null : (
            <h2>Radar de oportunidades Peru</h2>
          )}
          {country === "Chile" || variant === "ocds" ? null : (
            <p>Ejecuta SEACE en backend headless y revisa avance sin abrir Chrome al usuario.</p>
          )}
        </div>
        <button className="ghost" onClick={refresh}>Actualizar</button>
      </div>
      <div className="module-row">
        {variant === "ocds" ? (
          <button className="selected" type="button">{opportunityBandLabel(country, variant, module)}</button>
        ) : (
          modulesForCountry(country).map((item) => (
            <button key={item} className={module === item ? "selected" : ""} onClick={() => setModule(item)}>
              {opportunityBandLabel(country, variant, item)}
            </button>
          ))
        )}
      </div>
      {prefillNotice ? <div className="notice info keyword-search-notice">{prefillNotice}</div> : null}
      {module === "Contratos Menores a 8 UIT" || module === "Ambos modulos" ? <div className="notice info">Menores a 8 UIT queda visible para el flujo, pendiente de estabilizacion del conector.</div> : null}
      <div className="active-search-context">
        <div className="active-keywords">
          <span>Búsqueda activa:</span>
          {activeKeywords.length
            ? activeKeywords.map((item) => <b key={item}>{item}</b>)
            : <b>Todos los procesos</b>}
        </div>
        {usesPeriodFilters ? (
          <div className="active-period-summary">
            <span title="Filtros de período aplicados actualmente a la tabla de procesos">
              Períodos activos:
            </span>
            <div className="active-period-list">
              {activePeriodKeywordGroups.map((group) => (
                <div className="active-period-row" key={`${group.year}-${group.commercialMode}-${group.months.join("-")}-${group.keywords.join("-")}`}>
                  <div className="active-period-box">
                    <strong>{group.year}</strong>
                    <em className={`active-period-mode ${group.commercialMode}`}>
                      {group.commercialMode === "all" ? "Todos" : "Vigentes"}
                    </em>
                    <span>{group.months.length ? monthLabels(group.months).join(", ") : "Todos los meses"}</span>
                  </div>
                  <span className="active-period-arrow" aria-hidden="true">→</span>
                  <div className="active-period-keywords">
                    <span>Keywords aplicadas:</span>
                    {group.keywords.length
                      ? group.keywords.map((item) => <b key={item}>{item}</b>)
                      : <b>Sin palabras clave</b>}
                  </div>
                </div>
              ))}
            </div>
            <p className="active-period-help">
              Cada período activo conserva su semáforo y sus keywords; esta combinación define los datos de la tabla “Detalle de procesos” que podrás ver en la parte inferior.
            </p>
          </div>
        ) : null}
      </div>
      <div className="radar-filter-workspace">
        <section className="radar-filter-section required" aria-labelledby={`${storageScope}-required-title`}>
          <div className="radar-filter-heading">
            <div>
              <h3 id={`${storageScope}-required-title`}>Filtros Obligatorios - Búsqueda de Procesos</h3>
              <p>Define el periodo, las palabras clave y el estado comercial de la búsqueda.</p>
            </div>
            <div className="filter-heading-actions">
              <span className="filter-type-badge">Requeridos</span>
              <button className="clear-section-filters" type="button" onClick={clearRequiredFilters}>Limpiar Filtro</button>
            </div>
          </div>
          {usesPeriodFilters ? (
            <div className="ocds-period-picker" role="group" aria-label="Período de búsqueda" aria-describedby={periodValidationError ? `${storageScope}-period-error` : undefined}>
              <div className="multi-filter">
                <span>Años</span>
                <div>
                  {yearOptions.map((item) => (
                    <button key={item} type="button" className={ocdsYears.includes(item) ? "selected" : ""} onClick={() => {
                      setOcdsYears((current) => toggleSelected(current, item));
                      setPeriodValidationError("");
                    }}>
                      {item}
                    </button>
                  ))}
                </div>
              </div>
              <div className="multi-filter">
                <span>Meses</span>
                <div>
                  {monthOptions.map(([value, label]) => (
                    <button key={value} type="button" className={ocdsMonths.includes(value) ? "selected" : ""} onClick={() => {
                      setOcdsMonths((current) => toggleSelected(current, value));
                      setPeriodValidationError("");
                    }}>
                      {label.slice(0, 3)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
          <div className="keyword-grid">
            <label>Keyword 1<input list={keywordSuggestionListId} value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="satelital" /></label>
            <label>Keyword 2<input list={keywordSuggestionListId} value={keyword2} onChange={(event) => setKeyword2(event.target.value)} placeholder="Ej. internet" /></label>
            <label>Keyword 3<input list={keywordSuggestionListId} value={keyword3} onChange={(event) => setKeyword3(event.target.value)} placeholder="Ej. conectividad" /></label>
            <datalist id={keywordSuggestionListId}>
              {radarKeywordState.keywords.map((item) => <option value={item.keyword} key={`${item.is_default ? "base" : item.id}-${item.keyword}`} />)}
            </datalist>
          </div>
          <div className="required-filter-grid">
            <label>Semáforo Comercial
              <select value={maxResultsMode} onChange={(event) => setMaxResultsMode(event.target.value as MaxResultsMode)}>
                <option value="active">Vigentes</option>
                <option value="all">Todos</option>
              </select>
            </label>
          </div>
          {maxResultsMode === "all" ? (
            <p className="filter-warning">Tu selección incluye procesos cerrados y puede tardar más de lo usual.</p>
          ) : null}

          {periodValidationError ? (
            <div className="notice danger radar-validation-alert" id={`${storageScope}-period-error`} role="alert">
              {periodValidationError}
            </div>
          ) : null}

          <div className="radar-action-row required-action-row">
            <div className="search-mode-row" role="radiogroup" aria-label="Modo de búsqueda">
              <button className={searchMode === "append" ? "selected" : ""} onClick={() => setSearchMode("append")} type="button">
                Agregar a la búsqueda actual
              </button>
              <button className={searchMode === "replace" ? "selected" : ""} onClick={() => setSearchMode("replace")} type="button">
                Iniciar nueva búsqueda
              </button>
              {(((activeRun?.status === "queued" || activeRun?.status === "running") && !activeRun.cancel_requested) || pendingRunStatuses.some((item) => (item.status === "queued" || item.status === "running") && !item.cancel_requested)) ? (
                <button className="stop-search-button" type="button" onClick={stopSearch} disabled={stopping}>
                  {stopping ? "Deteniendo..." : "Detener búsqueda"}
                </button>
              ) : null}
            </div>
            <button className="primary execute-radar-button" type="button" onClick={execute} disabled={invalidPublicationDateRange || starting || (variant === "radar" && (module === "Contratos Menores a 8 UIT" || module === "Ambos modulos"))}>
              <RadarActionIcon />
              <span>{starting ? "Iniciando Radar..." : "Ejecutar Radar"}</span>
            </button>
          </div>
        </section>

        <section className="radar-filter-section optional" aria-labelledby={`${storageScope}-optional-title`}>
          <div className="radar-filter-heading">
            <div>
              <h3 id={`${storageScope}-optional-title`}>Filtros opcionales</h3>
              <p>Acota los resultados cuando conoces datos específicos del proceso.</p>
            </div>
            <div className="filter-heading-actions">
              <span className="filter-type-badge">Opcionales</span>
              <button className="clear-section-filters" type="button" onClick={clearOptionalFilters}>Limpiar Filtro</button>
            </div>
          </div>
          <div className="optional-filter-grid">
            <label>Búsqueda por Nomenclatura del Proceso<input value={nomenclatureFilter} onChange={(event) => setNomenclatureFilter(event.target.value)} placeholder={country === "Chile" ? "Ej. 2422-122-L126" : "Ej. CP-ABR-2-2026-UGEL-A-1"} /></label>
            <label>Búsqueda por Nombre de Entidad<input value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)} placeholder={country === "Chile" ? "Ej. Municipalidad de Santiago" : "Ej. Gobierno Regional de Lima"} /></label>
            <div className="date-range-field" role="group" aria-labelledby={`${storageScope}-publication-date-label`}>
              <span id={`${storageScope}-publication-date-label`}>Búsqueda Fecha de Convocatoria</span>
              <div className="date-range-inputs">
                <label>Inicio<input type="date" value={publicationDateFrom} max={publicationDateTo || undefined} onChange={(event) => setPublicationDateFrom(event.target.value)} /></label>
                <label>Fin<input type="date" value={publicationDateTo} min={publicationDateFrom || undefined} onChange={(event) => setPublicationDateTo(event.target.value)} /></label>
              </div>
              {invalidPublicationDateRange ? <small className="date-range-error" role="alert">La fecha de inicio debe ser anterior o igual a la fecha de fin.</small> : null}
            </div>
          </div>
        </section>

      </div>
      {activeRun ? <RunProgress run={activeRun} batchRuns={pendingRunStatuses} batchKeywords={batchKeywords} /> : visibleRuns[0] ? <RunProgress run={visibleRuns[0]} /> : null}
      <OpportunityTable
        rows={filtered}
        token={token}
        resetKey={`${storageScope}:${activeKeywords.join("|")}:${activeRunIds.join(",")}:${nomenclatureFilter}:${entityFilter}:${publicationDateFrom}:${publicationDateTo}`}
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
          message="Se limpiarán los campos de preparación. La búsqueda activa y los resultados actuales de la tabla se conservarán."
          confirmLabel="Sí, limpiar campos"
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

function defaultOpportunityViewState(): SavedOpportunityViewState {
  return {
    keywords: ["satelital"],
    runIds: [],
    keyword: "satelital",
    keyword2: "",
    keyword3: "",
    nomenclatureFilter: "",
    entityFilter: "",
    publicationDateFrom: "",
    publicationDateTo: "",
    years: [String(currentYear)],
    months: [String(new Date().getMonth() + 1)],
    appliedYears: [String(currentYear)],
    appliedMonths: [String(new Date().getMonth() + 1)],
    periodKeywordGroups: [{
      year: String(currentYear),
      months: [String(new Date().getMonth() + 1)],
      keywords: ["satelital"],
      commercialMode: "active",
    }],
    maxResultsMode: "active",
    searchMode: "append",
  };
}

function loadActiveSearchState(scope: string): SavedOpportunityViewState {
  const defaults = defaultOpportunityViewState();
  try {
    const raw = window.localStorage.getItem(activeSearchStorageKey(scope));
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const hasSavedKeywords = Array.isArray(parsed.keywords);
    const rawKeywords: unknown[] = hasSavedKeywords ? parsed.keywords as unknown[] : [];
    const keywords = rawKeywords.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    const runIds = Array.isArray(parsed.runIds)
      ? parsed.runIds.filter((item): item is number => typeof item === "number" && Number.isFinite(item))
      : [];
    const savedDraftKeywords = uniqueKeywords([
      typeof parsed.keyword === "string" ? parsed.keyword : "",
      typeof parsed.keyword2 === "string" ? parsed.keyword2 : "",
      typeof parsed.keyword3 === "string" ? parsed.keyword3 : "",
    ]);
    const activeKeywords = hasSavedKeywords
      ? keywords.length
        ? keywords
        : savedDraftKeywords.length
          ? savedDraftKeywords
          : defaults.keywords
      : defaults.keywords;
    const hasSavedYears = Array.isArray(parsed.years);
    const hasSavedMonths = Array.isArray(parsed.months);
    const rawYears: unknown[] = hasSavedYears ? parsed.years as unknown[] : [];
    const rawMonths: unknown[] = hasSavedMonths ? parsed.months as unknown[] : [];
    const years = hasSavedYears ? rawYears.filter((item): item is string => typeof item === "string") : defaults.years;
    const months = hasSavedMonths ? rawMonths.filter((item): item is string => typeof item === "string") : defaults.months;
    const appliedYears = Array.isArray(parsed.appliedYears)
      ? parsed.appliedYears.filter((item): item is string => typeof item === "string")
      : years;
    const appliedMonths = Array.isArray(parsed.appliedMonths)
      ? parsed.appliedMonths.filter((item): item is string => typeof item === "string")
      : months;
    const maxResultsMode = ["active", "all"].includes(String(parsed.maxResultsMode))
      ? parsed.maxResultsMode as MaxResultsMode
      : defaults.maxResultsMode;
    const savedPeriodKeywordGroups = Array.isArray(parsed.periodKeywordGroups)
      ? parsed.periodKeywordGroups.flatMap((item) => {
          if (!item || typeof item !== "object") return [];
          const group = item as Record<string, unknown>;
          if (typeof group.year !== "string") return [];
          return [{
            year: group.year,
            months: Array.isArray(group.months)
              ? group.months.filter((value): value is string => typeof value === "string")
              : [],
            keywords: Array.isArray(group.keywords)
              ? group.keywords.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
              : [],
            commercialMode: ["active", "all"].includes(String(group.commercialMode))
              ? group.commercialMode as MaxResultsMode
              : maxResultsMode,
          }];
        })
      : [];
    const periodKeywordGroups = mergePeriodKeywordGroups(
      savedPeriodKeywordGroups.length
        ? savedPeriodKeywordGroups
        : periodKeywordGroupsForSelection(appliedYears, appliedMonths, activeKeywords, maxResultsMode),
    );
    const searchMode = ["append", "replace"].includes(String(parsed.searchMode))
      ? parsed.searchMode as SearchMode
      : defaults.searchMode;
    return {
      keywords: activeKeywords,
      runIds,
      keyword: typeof parsed.keyword === "string" ? parsed.keyword : activeKeywords[0] || defaults.keyword,
      keyword2: typeof parsed.keyword2 === "string" ? parsed.keyword2 : activeKeywords[1] || "",
      keyword3: typeof parsed.keyword3 === "string" ? parsed.keyword3 : activeKeywords[2] || "",
      nomenclatureFilter: typeof parsed.nomenclatureFilter === "string" ? parsed.nomenclatureFilter : "",
      entityFilter: typeof parsed.entityFilter === "string" ? parsed.entityFilter : "",
      publicationDateFrom: typeof parsed.publicationDateFrom === "string" ? parsed.publicationDateFrom : "",
      publicationDateTo: typeof parsed.publicationDateTo === "string" ? parsed.publicationDateTo : "",
      years,
      months,
      appliedYears,
      appliedMonths,
      periodKeywordGroups,
      maxResultsMode,
      searchMode,
    };
  } catch {
    return defaults;
  }
}

function saveActiveSearchState(scope: string, state: SavedOpportunityViewState) {
  try {
    window.localStorage.setItem(activeSearchStorageKey(scope), JSON.stringify(state));
  } catch {
    // Local persistence is a convenience; the backend remains the source of truth.
  }
}

function periodFiltersFromRuns(runs: Run[], runIds: number[]) {
  const selectedIds = new Set(runIds);
  const years = new Set<string>();
  const months = new Set<string>();
  runs.forEach((run) => {
    if (!selectedIds.has(run.id)) return;
    const period = periodPartsFromRun(run);
    period.years.forEach((value) => years.add(value));
    period.months.forEach((value) => months.add(value));
  });
  return {
    years: [...years].sort((left, right) => Number(right) - Number(left)),
    months: [...months].sort((left, right) => Number(left) - Number(right)),
  };
}

function periodPartsFromRun(run: Run) {
  const diagnostics = String(run.diagnostics || "");
  const yearsValue = diagnostics.match(/anos\s*=\s*([^|\r\n]+)/i)?.[1] || "";
  const monthsValue = diagnostics.match(/meses\s*=\s*([^|\r\n]+)/i)?.[1] || "";
  const years = uniqueDefined(yearsValue.match(/\d{4}/g) || [])
    .sort((left, right) => Number(right) - Number(left));
  const months = uniqueDefined((monthsValue.match(/\d{1,2}/g) || [])
    .map((value) => String(Number(value)))
    .filter((value) => Number(value) >= 1 && Number(value) <= 12))
    .sort((left, right) => Number(left) - Number(right));
  return { years, months };
}

function periodKeywordGroupsFromRuns(
  runs: Run[],
  runIds: number[],
  fallbackMode: MaxResultsMode = "active",
): ActivePeriodKeywordGroup[] {
  const selectedIds = new Set(runIds);
  const groups = new Map<string, ActivePeriodKeywordGroup>();
  runs.forEach((run) => {
    if (!selectedIds.has(run.id)) return;
    const period = periodPartsFromRun(run);
    const keyword = keywordFromRun(run);
    const commercialMode = commercialModeFromRun(run, fallbackMode);
    period.years.forEach((year) => {
      const key = `${year}|${period.months.join(",")}|${commercialMode}`;
      const group = groups.get(key) || { year, months: period.months, keywords: [], commercialMode };
      if (keyword) group.keywords = uniqueKeywords([...group.keywords, keyword]);
      groups.set(key, group);
    });
  });
  return mergePeriodKeywordGroups(Array.from(groups.values()));
}

function periodKeywordGroupsForSelection(
  years: string[],
  months: string[],
  keywords: string[],
  commercialMode: MaxResultsMode,
) {
  return uniqueDefined(years)
    .sort((left, right) => Number(right) - Number(left))
    .map((year) => ({
      year,
      months: uniqueDefined(months).sort((left, right) => Number(left) - Number(right)),
      keywords: uniqueKeywords(keywords),
      commercialMode,
    }));
}

function mergePeriodKeywordGroups(...collections: ActivePeriodKeywordGroup[][]) {
  const normalized = collections
    .flat()
    .map((group) => ({
      year: group.year,
      months: uniqueDefined(group.months).sort((left, right) => Number(left) - Number(right)),
      keywords: uniqueKeywords(group.keywords),
      commercialMode: group.commercialMode === "all" ? "all" as const : "active" as const,
    }))
    .filter((group) => group.year && group.months.length && group.keywords.length)
    .sort((left, right) => Number(right.year) - Number(left.year)
      || commercialModeOrder(left.commercialMode) - commercialModeOrder(right.commercialMode)
      || right.keywords.length - left.keywords.length
      || Number(left.months[0] || 0) - Number(right.months[0] || 0));

  const groups: ActivePeriodKeywordGroup[] = [];
  normalized.forEach((group) => {
    const groupKeywords = normalizedKeywordSet(group.keywords);
    const matchIndex = groups.findIndex((current) => {
      if (current.year !== group.year || current.commercialMode !== group.commercialMode) return false;
      const currentKeywords = normalizedKeywordSet(current.keywords);
      return isKeywordSubset(groupKeywords, currentKeywords)
        || isKeywordSubset(currentKeywords, groupKeywords);
    });

    if (matchIndex < 0) {
      groups.push(group);
      return;
    }

    const current = groups[matchIndex];
    groups[matchIndex] = {
      year: current.year,
      months: uniqueDefined([...current.months, ...group.months])
        .sort((left, right) => Number(left) - Number(right)),
      keywords: uniqueKeywords([...current.keywords, ...group.keywords]),
      commercialMode: current.commercialMode,
    };
  });

  const allGroups = groups.filter((group) => group.commercialMode === "all");
  const withoutRedundantActiveMonths = groups.flatMap((group) => {
    if (group.commercialMode === "all") return [group];
    const groupKeywords = normalizedKeywordSet(group.keywords);
    const coveredMonths = new Set(allGroups
      .filter((candidate) => candidate.year === group.year
        && isKeywordSubset(groupKeywords, normalizedKeywordSet(candidate.keywords)))
      .flatMap((candidate) => candidate.months));
    const months = group.months.filter((month) => !coveredMonths.has(month));
    return months.length ? [{ ...group, months }] : [];
  });

  return withoutRedundantActiveMonths.sort((left, right) => Number(right.year) - Number(left.year)
    || commercialModeOrder(left.commercialMode) - commercialModeOrder(right.commercialMode)
    || Number(left.months[0] || 0) - Number(right.months[0] || 0)
    || right.keywords.length - left.keywords.length);
}

function commercialModeOrder(mode: MaxResultsMode) {
  return mode === "all" ? 0 : 1;
}

function commercialModeFromRun(run: Run, fallbackMode: MaxResultsMode) {
  const value = String(run.diagnostics || "").match(/semaforo\s*=\s*(active|all)/i)?.[1]?.toLowerCase();
  return value === "all" || value === "active" ? value as MaxResultsMode : fallbackMode;
}

function opportunityMatchesPeriodGroup(item: Opportunity, group: ActivePeriodKeywordGroup) {
  const timestamp = parseDate(item.publication_date) ?? parseDate(presentationDeadline(item));
  if (timestamp === null) return false;
  const date = new Date(timestamp);
  if (String(date.getFullYear()) !== group.year || !group.months.includes(String(date.getMonth() + 1))) return false;
  const haystack = `${item.entity} ${item.nomenclature} ${item.description}`;
  const keywordMatch = !group.keywords.length || group.keywords.some((keyword) => matchesCompletePhrase(haystack, keyword));
  const commercialMatch = group.commercialMode === "all" || commercialSignal(item).className !== "red";
  return keywordMatch && commercialMatch;
}

function normalizedKeywordSet(keywords: string[]) {
  return new Set(keywords.map((keyword) => keyword.trim().toLocaleLowerCase("es")));
}

function isKeywordSubset(left: Set<string>, right: Set<string>) {
  return Array.from(left).every((keyword) => right.has(keyword));
}

function monthLabels(months: string[]) {
  return months.map((value) => monthOptions.find(([month]) => month === value)?.[1].slice(0, 3) || value);
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
  const ocdsMetadata = [
    ["RUC comprador", opportunity.buyer_ruc],
    ["Region", opportunity.region],
    ["OCID", opportunity.ocid],
    ["Tender ID", opportunity.tender_id],
    ["Release", opportunity.release_id],
    ["Docs OCDS", opportunity.documents_count ? String(opportunity.documents_count) : ""],
  ].filter(([, value]) => String(value || "").trim());

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
              {ocdsMetadata.map(([label, value]) => (
                <React.Fragment key={label}>
                  <span>{label}</span><strong>{value}</strong>
                </React.Fragment>
              ))}
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
              {documents.map((doc) => {
                const isProtectedRoute = doc.title?.toLowerCase().startsWith("ruta protegida");
                const statusMessage = isProtectedRoute
                  ? "Mercado Publico requiere abrir el enlace original."
                  : doc.error_message;

                return (
                  <div className="document-row" key={doc.id}>
                    <div className="document-info">
                      <span className="pdf-badge">PDF</span>
                      <div className="document-copy">
                        <strong>{doc.title || doc.filename || `Documento ${doc.id}`}</strong>
                        <small>
                          <span className="document-status">{isProtectedRoute ? "Ruta protegida" : doc.status}</span>
                          {statusMessage ? <span className="document-message">{statusMessage}</span> : null}
                        </small>
                      </div>
                    </div>
                    <div className="document-actions">
                      {doc.status === "downloaded" ? (
                        <a className="doc-link" href={api.documentDownloadUrl(token, doc.id)} target="_blank" rel="noreferrer">Abrir / descargar</a>
                      ) : doc.source_url ? (
                        <a className="doc-link" href={doc.source_url} target="_blank" rel="noreferrer">
                          {isProtectedRoute ? "Abrir enlace de descarga" : "Abrir fuente"}
                        </a>
                      ) : null}
                    </div>
                  </div>
                );
              })}
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

type AlertChannel = "email" | "whatsapp" | "in_app";
type PhoneCountry = "Peru" | "Chile";

const alertChannelOptions: Array<{ value: AlertChannel; label: string; description: string }> = [
  { value: "email", label: "Correo", description: "Entrega a una dirección de email" },
  { value: "whatsapp", label: "WhatsApp", description: "Envía al celular de Perú o Chile" },
  { value: "in_app", label: "En GovRadar", description: "Notificación dentro de la plataforma" },
];

function alertTypeLabel(value: string) {
  if (value === "priority_match") return "Coincidencia de prioridad";
  if (value === "new_process") return "Nuevo proceso";
  if (value === "deadline") return "Vencimiento próximo";
  return value.replaceAll("_", " ");
}

function alertStatusLabel(value: string) {
  if (value === "sent") return "Enviado";
  if (value === "pending") return "Pendiente";
  if (value === "error") return "Error de envío";
  if (value === "retrying") return "Reintentando";
  if (value === "failed") return "Falló definitivamente";
  if (value === "waiting_channel") return "Esperando habilitación";
  if (value === "skipped") return "Omitido";
  return value;
}

function ruleChannelLabel(value: string) {
  if (value === "whatsapp") return "WhatsApp";
  if (["in_app", "message", "mensaje"].includes(value)) return "GovRadar";
  return "Correo";
}

function formatRuleDestination(rule: AlertRule) {
  if (["in_app", "message", "mensaje"].includes(rule.channel)) return "Notificación interna";
  if (rule.channel !== "whatsapp") return rule.destination;
  const digits = rule.destination.replace(/\D/g, "");
  if (digits.startsWith("51") && digits.length === 11) return `+51 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  if (digits.startsWith("56") && digits.length === 11) return `+56 ${digits.slice(2, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`;
  return rule.destination;
}

function ChannelSymbol({ channel }: { channel: string }) {
  if (channel === "whatsapp") {
    return <span className="channel-symbol whatsapp" aria-hidden="true"><img src="/assets/logowhatsapp.png" alt="" /></span>;
  }
  return <span className={`channel-symbol ${channel}`} aria-hidden="true">{channel === "email" ? "@" : "R"}</span>;
}

function RuleActionIcon({ name }: { name: "edit" | "delete" }) {
  return name === "edit" ? (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-4-3L4 17v3Z" /><path d="m13.5 7.5 3 3" /></svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>
  );
}

function Alerts({ token, rules, alerts, refresh }: { token: string; rules: AlertRule[]; alerts: Alert[]; refresh: () => Promise<void> }) {
  const [channel, setChannel] = useState<AlertChannel>("email");
  const [ruleName, setRuleName] = useState("");
  const [emailDestination, setEmailDestination] = useState("");
  const [phoneCountry, setPhoneCountry] = useState<PhoneCountry>("Peru");
  const [localPhone, setLocalPhone] = useState("");
  const [keywords, setKeywords] = useState("");
  const [minPriority, setMinPriority] = useState("A");
  const [saving, setSaving] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  const phonePrefix = phoneCountry === "Peru" ? "+51" : "+56";
  const phoneDigits = localPhone.replace(/\D/g, "").slice(0, 9);
  const generatedRuleName = channel === "email"
    ? `Correo · prioridad ${minPriority}`
    : channel === "whatsapp"
      ? `WhatsApp ${phoneCountry === "Peru" ? "Perú" : "Chile"} · prioridad ${minPriority}`
      : `GovRadar · prioridad ${minPriority}`;

  function changeChannel(nextChannel: AlertChannel) {
    setChannel(nextChannel);
    setError("");
    setSuccess("");
  }

  function changePhoneCountry(nextCountry: PhoneCountry) {
    setPhoneCountry(nextCountry);
    setLocalPhone("");
    setError("");
  }

  function resetRuleForm() {
    setEditingRuleId(null);
    setChannel("email");
    setRuleName("");
    setEmailDestination("");
    setPhoneCountry("Peru");
    setLocalPhone("");
    setKeywords("");
    setMinPriority("A");
    setError("");
  }

  function startEditingRule(rule: AlertRule) {
    const nextChannel = (["email", "whatsapp", "in_app"].includes(rule.channel) ? rule.channel : "email") as AlertChannel;
    setEditingRuleId(rule.id);
    setChannel(nextChannel);
    setRuleName(rule.name);
    setKeywords(rule.keywords || "");
    setMinPriority(rule.min_priority);
    setEmailDestination(nextChannel === "email" ? rule.destination : "");
    if (nextChannel === "whatsapp") {
      setPhoneCountry(rule.destination.startsWith("+56") ? "Chile" : "Peru");
      setLocalPhone(rule.destination.replace(/^\+(?:51|56)/, "").replace(/\D/g, "").slice(0, 9));
    } else {
      setLocalPhone("");
    }
    setConfirmDeleteId(null);
    setError("");
    setSuccess("");
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function saveRule(event: React.FormEvent) {
    event.preventDefault();
    const destination = channel === "email"
      ? emailDestination.trim()
      : channel === "whatsapp"
        ? `${phonePrefix}${phoneDigits}`
        : "GovRadar";

    if (channel === "whatsapp" && phoneDigits.length !== 9) {
      setError(`Ingresa los 9 dígitos del celular de ${phoneCountry === "Peru" ? "Perú" : "Chile"}.`);
      return;
    }
    if (channel === "email" && !emailDestination.trim()) {
      setError("Ingresa el correo que recibirá las alertas.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = {
        name: ruleName.trim() || generatedRuleName,
        channel,
        destination,
        keywords: keywords.trim(),
        min_priority: minPriority,
        is_active: editingRuleId ? (rules.find((rule) => rule.id === editingRuleId)?.is_active ?? true) : true,
      };
      if (editingRuleId) {
        await api.updateAlertRule(token, editingRuleId, payload);
      } else {
        await api.createAlertRule(token, payload);
      }
      await refresh();
      setSuccess(`Regla “${ruleName.trim() || generatedRuleName}” ${editingRuleId ? "actualizada" : "creada"} correctamente.`);
      resetRuleForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear la regla de alerta");
    } finally {
      setSaving(false);
    }
  }

  async function deleteRule(rule: AlertRule) {
    setDeletingRuleId(rule.id);
    setError("");
    setSuccess("");
    try {
      await api.deleteAlertRule(token, rule.id);
      if (editingRuleId === rule.id) resetRuleForm();
      setConfirmDeleteId(null);
      await refresh();
      setSuccess(`Regla “${rule.name}” eliminada.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo eliminar la regla de alerta");
    } finally {
      setDeletingRuleId(null);
    }
  }

  const errorCount = alerts.filter((alert) => ["error", "retrying", "failed"].includes(alert.status)).length;
  const sentCount = alerts.filter((alert) => alert.status === "sent").length;
  const waitingCount = alerts.filter((alert) => alert.status === "waiting_channel").length;

  return (
    <section className="alerts-layout">
      <article className="panel alert-config-panel">
        <div className="alert-panel-heading">
          <div><h2>{editingRuleId ? "Editar regla de alerta" : "Nueva regla de alerta"}</h2><p>La alerta se envía al detectar un proceso nuevo cuya descripción coincida con la regla.</p></div>
        </div>

        <form className={`alert-rule-form ${editingRuleId ? "editing" : ""}`} onSubmit={saveRule} ref={formRef}>
          <fieldset className="alert-channel-fieldset">
            <legend>¿Cómo quieres recibir la alerta?</legend>
            <div className="alert-channel-grid">
              {alertChannelOptions.map((option) => (
                <button
                  className={`alert-channel-option ${channel === option.value ? "selected" : ""}`}
                  type="button"
                  aria-pressed={channel === option.value}
                  key={option.value}
                  onClick={() => changeChannel(option.value)}
                >
                  <ChannelSymbol channel={option.value} />
                  <span><strong>{option.label}</strong><small>{option.description}</small></span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="alert-destination-block" aria-live="polite">
            {channel === "email" ? (
              <label>Correo de destino <span className="required-label">Obligatorio</span><input required type="email" autoComplete="email" value={emailDestination} onChange={(event) => setEmailDestination(event.target.value)} placeholder="equipo.comercial@empresa.com" /></label>
            ) : null}

            {channel === "whatsapp" ? (
              <>
                <fieldset className="whatsapp-country-fieldset">
                  <legend>País del celular</legend>
                  <div className="whatsapp-country-selector">
                    {(["Peru", "Chile"] as PhoneCountry[]).map((countryOption) => (
                      <button className={phoneCountry === countryOption ? "selected" : ""} type="button" aria-pressed={phoneCountry === countryOption} key={countryOption} onClick={() => changePhoneCountry(countryOption)}>
                        <CountryFlagIcon country={countryOption} />
                        <span>{countryOption === "Peru" ? "Perú" : "Chile"}</span>
                        <small>{countryOption === "Peru" ? "+51" : "+56"}</small>
                      </button>
                    ))}
                  </div>
                </fieldset>
                <label>Celular WhatsApp <span className="required-label">9 dígitos</span>
                  <span className="phone-input-group"><b>{phonePrefix}</b><input required type="tel" inputMode="numeric" autoComplete="tel" value={localPhone} onChange={(event) => setLocalPhone(event.target.value.replace(/\D/g, "").slice(0, 9))} placeholder={phoneCountry === "Peru" ? "999 999 999" : "9 9999 9999"} /></span>
                </label>
                <p className="destination-preview">Se guardará como <strong>{phoneDigits.length ? `${phonePrefix}${phoneDigits}` : `${phonePrefix}•••••••••`}</strong></p>
              </>
            ) : null}

            {channel === "in_app" ? (
              <div className="in-app-destination"><ChannelSymbol channel="in_app" /><div><strong>Centro de alertas GovRadar</strong><p>No necesitas ingresar correo ni celular.</p></div></div>
            ) : null}
          </div>

          <label className="alert-keywords-field">
            Palabras clave de la descripción <span className="field-hint">Opcional</span>
            <input value={keywords} maxLength={1000} onChange={(event) => setKeywords(event.target.value)} placeholder="Ej.: internet satelital, enlace de datos, conectividad" />
            <small>Separa palabras o frases con comas. La alerta se genera si la descripción contiene al menos una; sin palabras clave, acepta cualquier descripción.</small>
          </label>

          <div className="alert-conditions-grid">
            <label>Nombre de la regla <span className="field-hint">Opcional</span><input value={ruleName} maxLength={160} onChange={(event) => setRuleName(event.target.value)} placeholder={generatedRuleName} /></label>
            <label>Prioridad mínima<select value={minPriority} onChange={(event) => setMinPriority(event.target.value)}><option value="A">A · Alta</option><option value="B">B · Media</option><option value="C">C · Todas</option></select></label>
          </div>

          {error ? <div className="notice danger" role="alert">{error}</div> : null}
          {success ? <div className="notice success" role="status">{success}</div> : null}
          <div className="alert-form-actions">
            {editingRuleId ? <button type="button" className="ghost" onClick={resetRuleForm} disabled={saving}>Cancelar</button> : null}
            <button className="primary alert-create-button" type="submit" disabled={saving}>{saving ? "Guardando..." : editingRuleId ? "Guardar cambios" : "Crear regla de alerta"}</button>
          </div>
        </form>

        <div className="configured-rules">
          <div className="configured-rules-heading"><h3>Reglas configuradas</h3><span>{rules.length}</span></div>
          <div className="alert-rule-list">
            {rules.map((rule) => (
              <article className="alert-rule-row" key={rule.id}>
                <ChannelSymbol channel={rule.channel} />
                <div className="alert-rule-copy"><strong>{rule.name}</strong><span>{ruleChannelLabel(rule.channel)} · {formatRuleDestination(rule)} · Prioridad {rule.min_priority}</span><small>Descripción: {rule.keywords || "cualquier descripción"}</small></div>
                <div className="alert-rule-controls">
                  <span className={`account-status ${rule.is_active ? "active" : "blocked"}`}>{rule.is_active ? "Activa" : "Inactiva"}</span>
                  <button type="button" className="rule-action-button" onClick={() => startEditingRule(rule)} aria-label={`Editar regla ${rule.name}`} title="Editar"><RuleActionIcon name="edit" /></button>
                  <button type="button" className="rule-action-button danger" onClick={() => setConfirmDeleteId(rule.id)} aria-label={`Eliminar regla ${rule.name}`} title="Eliminar"><RuleActionIcon name="delete" /></button>
                </div>
                {confirmDeleteId === rule.id ? (
                  <div className="rule-delete-confirmation" role="alert">
                    <span>¿Eliminar esta regla y su historial de alertas?</span>
                    <div><button type="button" className="ghost" onClick={() => setConfirmDeleteId(null)} disabled={deletingRuleId === rule.id}>Cancelar</button><button type="button" className="danger-button" onClick={() => deleteRule(rule)} disabled={deletingRuleId === rule.id}>{deletingRuleId === rule.id ? "Eliminando..." : "Sí, eliminar"}</button></div>
                  </div>
                ) : null}
              </article>
            ))}
            {!rules.length ? <Empty text="Crea tu primera regla para comenzar a recibir alertas." /> : null}
          </div>
        </div>
      </article>

      <article className="panel alert-events-panel">
        <div className="alert-panel-heading events-heading">
          <div><h2>Actividad de alertas</h2><p>Seguimiento de entregas generadas por las reglas.</p></div>
          <div className="event-summary"><span><b>{sentCount}</b> enviados</span><span><b>{waitingCount}</b> por habilitar</span><span className={errorCount ? "has-errors" : ""}><b>{errorCount}</b> errores</span></div>
        </div>
        <div className="alert-event-list">
          {alerts.map((alert) => (
            <article className="alert-event-row" key={alert.id}>
              <span className={`event-status-dot ${alert.status}`} aria-hidden="true" />
              <div><strong>{alertTypeLabel(alert.alert_type)}</strong><small>Regla #{alert.rule_id} · Oportunidad #{alert.opportunity_id}{alert.attempt_count ? ` · Intento ${alert.attempt_count}` : ""}</small></div>
              <span className={`event-status-label ${alert.status}`}>{alertStatusLabel(alert.status)}</span>
            </article>
          ))}
          {!alerts.length ? <Empty text="Las alertas aparecerán cuando una regla coincida con procesos nuevos o vencimientos." /> : null}
        </div>
      </article>
    </section>
  );
}

const emptyUserForm: UserCreatePayload = {
  email: "",
  password: "",
  first_name: "",
  last_name: "",
  position: "",
  address: "",
  phone_peru: "",
  phone_chile: "",
  access_profile: "peru",
  role: "viewer",
};

const accessProfileOptions: Array<{ value: AccessProfile; title: string; description: string; flags: Country[] }> = [
  { value: "peru", title: "Perfil Perú", description: "Inicio Perú, Oportunidades Perú y alertas", flags: ["Peru"] },
  { value: "chile", title: "Perfil Chile", description: "Inicio Chile, Oportunidades Chile y alertas", flags: ["Chile"] },
  { value: "both", title: "Perú y Chile", description: "Acceso operativo a los módulos de ambos países", flags: ["Peru", "Chile"] },
];

function profileName(profile: AccessProfile) {
  return profile === "both" ? "Perú y Chile" : profile === "chile" ? "Chile" : "Perú";
}

function userLocalPhone(value: string, countryCode: "51" | "56") {
  const digits = value.replace(/\D/g, "");
  const localDigits = digits.startsWith(countryCode) && digits.length > 9 ? digits.slice(countryCode.length) : digits;
  return localDigits.slice(0, 9);
}

function userInternationalPhone(value: string, countryCode: "51" | "56") {
  const localDigits = userLocalPhone(value, countryCode);
  return localDigits ? `+${countryCode}${localDigits}` : "";
}

function Users({ token, currentUserId }: { token: string; currentUserId: number }) {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [form, setForm] = useState<UserCreatePayload>(emptyUserForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  async function loadUsers() {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.users(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la lista de usuarios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, [token]);

  function updateField<K extends keyof UserCreatePayload>(field: K, value: UserCreatePayload[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
    setSuccess("");
  }

  function resetForm() {
    setForm(emptyUserForm);
    setEditingId(null);
    setError("");
    setSuccess("");
  }

  function editUser(user: UserRecord) {
    setEditingId(user.id);
    setForm({
      email: user.email,
      password: "",
      first_name: user.first_name,
      last_name: user.last_name,
      position: user.position,
      address: user.address,
      phone_peru: userLocalPhone(user.phone_peru, "51"),
      phone_chile: userLocalPhone(user.phone_chile, "56"),
      access_profile: user.access_profile,
      role: user.role,
    });
    setError("");
    setSuccess("");
    window.requestAnimationFrame(() => {
      formRef.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
      formRef.current?.querySelector<HTMLInputElement>('input[name="first-name"]')?.focus({ preventScroll: true });
    });
  }

  async function submitUser(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const normalizedForm: UserCreatePayload = {
        ...form,
        phone_peru: userInternationalPhone(form.phone_peru, "51"),
        phone_chile: userInternationalPhone(form.phone_chile, "56"),
      };
      if (editingId !== null) {
        const { password, ...editableFields } = normalizedForm;
        const updated = await api.updateUser(token, editingId, password ? { ...editableFields, password } : editableFields);
        setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
        setForm(emptyUserForm);
        setEditingId(null);
        setSuccess(`Los datos de ${updated.full_name} fueron actualizados.`);
        return;
      }
      const created = await api.createUser(token, normalizedForm);
      setUsers((current) => [created, ...current]);
      setForm(emptyUserForm);
      setSuccess(`${created.full_name} fue dado de alta correctamente.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el usuario");
    } finally {
      setSaving(false);
    }
  }

  async function toggleUser(user: UserRecord) {
    setUpdatingId(user.id);
    setError("");
    setSuccess("");
    try {
      const updated = await api.updateUser(token, user.id, { is_active: !user.is_active });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSuccess(`${updated.full_name} ahora esta ${updated.is_active ? "activo" : "bloqueado"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el usuario");
    } finally {
      setUpdatingId(null);
    }
  }

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("es");
    if (!term) return users;
    return users.filter((user) => [user.full_name, user.email, user.position, profileName(user.access_profile)]
      .some((value) => value.toLocaleLowerCase("es").includes(term)));
  }, [search, users]);

  const needsPeruPhone = form.access_profile === "peru" || form.access_profile === "both";
  const needsChilePhone = form.access_profile === "chile" || form.access_profile === "both";

  return (
    <div className="users-module">
      <section className="users-intro">
        <div>
          <h2>Usuarios y permisos</h2>
          <p>Da de alta al equipo y define exactamente qué operación puede visualizar.</p>
        </div>
        <div className="users-summary" aria-label="Resumen de usuarios">
          <span><b>{users.filter((user) => user.is_active).length}</b> activos</span>
          <span><b>{users.filter((user) => !user.is_active).length}</b> bloqueados</span>
        </div>
      </section>

      <section className="user-layout">
        <form className={`panel user-form ${editingId !== null ? "editing" : ""}`} onSubmit={submitUser} ref={formRef}>
          <div className="user-section-heading">
            <span className="section-icon" aria-hidden="true">{editingId !== null ? "\u270E" : "+"}</span>
            <div>
              <h3>{editingId !== null ? "Editar usuario" : "Nuevo usuario"}</h3>
              <p>{editingId !== null ? "Actualiza sus datos, acceso y permisos." : "Completa los datos para habilitar su acceso."}</p>
            </div>
          </div>

          <fieldset className="profile-fieldset">
            <legend>Perfil de visualización</legend>
            <div className="profile-choice-grid">
              {accessProfileOptions.map((option) => (
                <label className={`profile-choice ${form.access_profile === option.value ? "selected" : ""}`} key={option.value}>
                  <input
                    type="radio"
                    name="access-profile"
                    value={option.value}
                    checked={form.access_profile === option.value}
                    onChange={() => updateField("access_profile", option.value)}
                  />
                  <span className="profile-flags">{option.flags.map((flag) => <CountryFlagIcon country={flag} key={flag} />)}</span>
                  <span><strong>{option.title}</strong><small>{option.description}</small></span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="user-fields">
            <label>Nombres<input name="first-name" required minLength={2} autoComplete="given-name" value={form.first_name} onChange={(event) => updateField("first_name", event.target.value)} placeholder="Ej. Andrea" /></label>
            <label>Apellidos<input required minLength={2} autoComplete="family-name" value={form.last_name} onChange={(event) => updateField("last_name", event.target.value)} placeholder="Ej. Valdivia Rojas" /></label>
            <label className="full-field">Correo corporativo <span className="field-hint">Sera su usuario de acceso</span><input required type="email" autoComplete="email" value={form.email} onChange={(event) => updateField("email", event.target.value)} placeholder="nombre@empresa.com" /></label>
            <label>Posición<input required minLength={2} autoComplete="organization-title" value={form.position} onChange={(event) => updateField("position", event.target.value)} placeholder="Ej. Ejecutivo comercial" /></label>
            <label>Permiso de gestión<select value={form.role} onChange={(event) => updateField("role", event.target.value as UserCreatePayload["role"])}><option value="viewer">Usuario</option><option value="admin">Administrador</option></select></label>
            <label className="full-field">Dirección<input required minLength={4} autoComplete="street-address" value={form.address} onChange={(event) => updateField("address", event.target.value)} placeholder="Dirección de oficina o residencia" /></label>
            {needsPeruPhone ? (
              <label>Celular Perú <span className="required-label">9 dígitos</span>
                <span className="phone-input-group user-phone-input"><b>+51</b><input required type="tel" inputMode="numeric" autoComplete="tel-national" minLength={9} maxLength={9} pattern="[0-9]{9}" title="Ingresa los 9 dígitos del celular de Perú" value={form.phone_peru} onChange={(event) => updateField("phone_peru", event.target.value.replace(/\D/g, "").slice(0, 9))} placeholder="999 999 999" /></span>
              </label>
            ) : null}
            {needsChilePhone ? (
              <label>Celular Chile <span className="required-label">9 dígitos</span>
                <span className="phone-input-group user-phone-input"><b>+56</b><input required type="tel" inputMode="numeric" autoComplete="tel-national" minLength={9} maxLength={9} pattern="[0-9]{9}" title="Ingresa los 9 dígitos del celular de Chile" value={form.phone_chile} onChange={(event) => updateField("phone_chile", event.target.value.replace(/\D/g, "").slice(0, 9))} placeholder="9 9999 9999" /></span>
              </label>
            ) : null}
            <label className={form.access_profile === "both" ? "full-field" : ""}>{editingId !== null ? "Nueva contraseña" : "Contraseña temporal"} <span className="field-hint">{editingId !== null ? "Opcional" : "Mínimo 8 caracteres"}</span><input required={editingId === null} minLength={8} type="password" autoComplete="new-password" value={form.password} onChange={(event) => updateField("password", event.target.value)} placeholder={editingId !== null ? "Dejar vacío para conservarla" : "Crea una contraseña segura"} /></label>
          </div>

          {error ? <div className="notice danger" role="alert">{error}</div> : null}
          {success ? <div className="notice success" role="status">{success}</div> : null}
          <div className="user-form-actions">
            <button className="ghost" type="button" onClick={resetForm} disabled={saving}>{editingId !== null ? "Cancelar" : "Limpiar"}</button>
            <button className="primary" type="submit" disabled={saving}>{saving ? editingId !== null ? "Guardando cambios..." : "Creando usuario..." : editingId !== null ? "Guardar cambios" : "Dar de alta"}</button>
          </div>
        </form>

        <section className="panel user-directory">
          <div className="directory-heading">
            <div><h3>Directorio</h3><p>{users.length} usuarios registrados</p></div>
            <label className="user-search"><span className="sr-only">Buscar usuario</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar nombre, correo o posicion" /></label>
          </div>
          {loading ? <div className="user-skeleton" aria-label="Cargando usuarios"><span /><span /><span /></div> : null}
          {!loading ? (
            <div className="user-list">
              {filteredUsers.map((user) => (
                <article className={`user-row ${user.is_active ? "" : "inactive"}`} key={user.id}>
                  <div className="user-avatar">{userInitials(user.full_name)}</div>
                  <div className="user-main">
                    <div className="user-name-line"><strong>{user.full_name}</strong>{user.id === currentUserId ? <span className="self-badge">Tu cuenta</span> : null}</div>
                    <span>{user.email}</span>
                    <small>{user.position || "Posición no registrada"}</small>
                  </div>
                  <div className="user-access">
                    <span className={`profile-badge ${user.access_profile}`}>
                      {user.access_profile !== "chile" ? <CountryFlagIcon country="Peru" /> : null}
                      {user.access_profile !== "peru" ? <CountryFlagIcon country="Chile" /> : null}
                      {profileName(user.access_profile)}
                    </span>
                    <small>{user.role === "admin" ? "Administrador" : "Usuario"}</small>
                  </div>
                  <div className="user-status-area">
                    <span className={`account-status ${user.is_active ? "active" : "blocked"}`}>{user.is_active ? "Activo" : "Bloqueado"}</span>
                    <div className="user-row-actions">
                      <button className="text-action" type="button" disabled={saving || updatingId === user.id} onClick={() => editUser(user)} aria-label={`Editar datos de ${user.full_name}`}>Editar</button>
                      <button className="text-action" type="button" disabled={user.id === currentUserId || updatingId === user.id || saving} onClick={() => toggleUser(user)}>
                        {updatingId === user.id ? "Actualizando..." : user.is_active ? "Bloquear" : "Reactivar"}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
              {!filteredUsers.length ? <Empty text="No encontramos usuarios con ese criterio." /> : null}
            </div>
          ) : null}
        </section>
      </section>
    </div>
  );
}

function System({
  token,
  runs,
  refresh,
  legalDocuments,
  legalLoadError,
  onLegalDocumentUpdated,
  onOpenLegal,
  versionLabel,
  onVersionUpdated,
}: {
  token: string;
  runs: Run[];
  refresh: () => Promise<void>;
  legalDocuments: LegalDocumentsMap;
  legalLoadError: string;
  onLegalDocumentUpdated: (document: LegalDocumentRecord) => void;
  onOpenLegal: (view: LegalView) => void;
  versionLabel: string;
  onVersionUpdated: (versionLabel: string) => void;
}) {
  const [versionDraft, setVersionDraft] = useState(versionLabel);
  const [versionSaving, setVersionSaving] = useState(false);
  const [versionError, setVersionError] = useState("");
  const [versionNotice, setVersionNotice] = useState("");
  const [selectedLegalKey, setSelectedLegalKey] = useState<LegalView>("privacy");
  const [legalDraft, setLegalDraft] = useState("");
  const [legalSaving, setLegalSaving] = useState(false);
  const [legalError, setLegalError] = useState("");
  const [legalNotice, setLegalNotice] = useState("");
  const [legalPreviewOpen, setLegalPreviewOpen] = useState(false);
  const loadedLegalKeyRef = useRef<LegalView | null>(null);
  const selectedLegalDocument = legalDocuments[selectedLegalKey];
  const legalOptions: Array<{ key: LegalView; label: string }> = [
    { key: "privacy", label: "Política de Privacidad" },
    { key: "terms", label: "Términos de Servicio" },
    { key: "confidentiality", label: "Confidencialidad" },
  ];

  useEffect(() => setVersionDraft(versionLabel), [versionLabel]);

  async function saveVersionLabel(event: React.FormEvent) {
    event.preventDefault();
    const nextVersionLabel = versionDraft.trim();
    if (nextVersionLabel.length < 3) return;
    setVersionSaving(true);
    setVersionError("");
    setVersionNotice("");
    try {
      const updated = await api.updateAppSettings(token, nextVersionLabel);
      setVersionDraft(updated.version_label);
      onVersionUpdated(updated.version_label);
      setVersionNotice("La versión visible se actualizó correctamente.");
    } catch (err) {
      setVersionError(err instanceof Error ? err.message : "No se pudo actualizar la versión");
    } finally {
      setVersionSaving(false);
    }
  }

  useEffect(() => {
    if (!selectedLegalDocument || loadedLegalKeyRef.current === selectedLegalKey) return;
    loadedLegalKeyRef.current = selectedLegalKey;
    setLegalDraft(selectedLegalDocument?.content || "");
    setLegalError("");
    setLegalNotice("");
  }, [selectedLegalKey, selectedLegalDocument?.content]);

  async function saveLegalDocument(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedLegalDocument || legalDraft.trim().length < 100) return;
    setLegalSaving(true);
    setLegalError("");
    setLegalNotice("");
    try {
      const updated = await api.updateLegalDocument(token, selectedLegalKey, legalDraft);
      onLegalDocumentUpdated(updated);
      setLegalDraft(updated.content);
      setLegalNotice(`${updated.title} se actualizó correctamente.`);
    } catch (err) {
      setLegalError(err instanceof Error ? err.message : "No se pudo actualizar el documento legal");
    } finally {
      setLegalSaving(false);
    }
  }

  return (
    <div className="system-module">
      <section className="panel version-admin-panel" aria-labelledby="version-admin-title">
        <div className="version-admin-heading">
          <div>
            <p className="overline">Identidad de la aplicación</p>
            <h2 id="version-admin-title">Versión visible</h2>
            <p>Este texto se muestra en el pie del centro de navegación para todos los usuarios.</p>
          </div>
          <span className="version-preview">{versionLabel}</span>
        </div>
        <form className="version-editor-form" onSubmit={saveVersionLabel}>
          <label htmlFor="version-label">Texto de versión</label>
          <div className="version-editor-row">
            <input
              id="version-label"
              value={versionDraft}
              onChange={(event) => {
                setVersionDraft(event.target.value);
                setVersionNotice("");
              }}
              minLength={3}
              maxLength={80}
              required
            />
            <button
              className="primary"
              type="submit"
              disabled={versionSaving || versionDraft.trim().length < 3 || versionDraft.trim() === versionLabel}
            >
              {versionSaving ? "Guardando…" : "Guardar versión"}
            </button>
          </div>
          {versionError ? <div className="notice danger" role="alert">{versionError}</div> : null}
          {versionNotice ? <div className="notice success" role="status">{versionNotice}</div> : null}
        </form>
      </section>
      <section className="panel system-security-panel" aria-labelledby="security-confidentiality-title">
        <div className="security-heading">
          <span className="security-icon"><LockIcon /></span>
          <div>
            <p className="overline">Protección de la cuenta</p>
            <h2 id="security-confidentiality-title">Seguridad y Confidencialidad</h2>
            <p>
              Tus criterios de búsqueda y oportunidades comerciales se consideran información estratégica reservada.
            </p>
          </div>
        </div>
        <ConfidentialityContent content={legalDocuments.confidentiality?.content} />
        <div className="system-legal-actions">
          <button className="ghost" type="button" onClick={() => onOpenLegal("privacy")}>Ver Política de Privacidad</button>
          <button className="ghost" type="button" onClick={() => onOpenLegal("terms")}>Ver Términos de Servicio</button>
        </div>
      </section>
      <section className="panel legal-admin-panel" aria-labelledby="legal-admin-title">
        <div className="legal-admin-heading">
          <div>
            <h2 id="legal-admin-title">Administrar documentos legales</h2>
            <p>Los cambios guardados se publican inmediatamente en el Login, el Footer y las secciones legales.</p>
          </div>
          {selectedLegalDocument ? <span>Actualizado {formatDate(selectedLegalDocument.updated_at)}</span> : null}
        </div>
        <div className="legal-document-tabs" role="tablist" aria-label="Documento legal a modificar">
          {legalOptions.map((option) => (
            <button
              type="button"
              role="tab"
              aria-selected={selectedLegalKey === option.key}
              className={selectedLegalKey === option.key ? "active" : ""}
              onClick={() => setSelectedLegalKey(option.key)}
              key={option.key}
            >
              {option.label}
            </button>
          ))}
        </div>
        {legalLoadError ? <div className="notice danger" role="alert">{legalLoadError}</div> : null}
        {!selectedLegalDocument && !legalLoadError ? <div className="legal-editor-loading">Cargando documentos legales…</div> : null}
        {selectedLegalDocument ? (
          <form className="legal-editor-form" onSubmit={saveLegalDocument}>
            <label htmlFor="legal-document-content">
              Contenido de {selectedLegalDocument.title}
              <span className="legal-format-hint">Usa “##” al inicio de un subtítulo y “-” al inicio de cada punto de una lista.</span>
            </label>
            <textarea
              id="legal-document-content"
              value={legalDraft}
              onChange={(event) => {
                setLegalDraft(event.target.value);
                setLegalNotice("");
              }}
              rows={18}
              minLength={100}
              maxLength={30000}
              spellCheck="true"
            />
            <div className="legal-editor-meta">
              <span>{legalDraft.length.toLocaleString("es-PE")} / 30.000 caracteres</span>
              <button className="text-action" type="button" onClick={() => setLegalPreviewOpen(true)}>Vista previa</button>
            </div>
            {legalError ? <div className="notice danger" role="alert">{legalError}</div> : null}
            {legalNotice ? <div className="notice success" role="status">{legalNotice}</div> : null}
            <div className="legal-editor-actions">
              <button
                className="ghost"
                type="button"
                disabled={legalSaving || legalDraft === selectedLegalDocument.content}
                onClick={() => {
                  setLegalDraft(selectedLegalDocument.content);
                  setLegalError("");
                  setLegalNotice("");
                }}
              >
                Descartar cambios
              </button>
              <button
                className="primary"
                type="submit"
                disabled={legalSaving || legalDraft.trim().length < 100 || legalDraft.trim() === selectedLegalDocument.content}
              >
                {legalSaving ? "Guardando…" : "Guardar y publicar"}
              </button>
            </div>
          </form>
        ) : null}
      </section>
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
          {!runs.length ? <Empty text="Todavía no hay ejecuciones registradas." /> : null}
        </div>
      </section>
      {legalPreviewOpen ? (
        <LegalDialog
          view={selectedLegalKey}
          documents={{
            ...legalDocuments,
            [selectedLegalKey]: { ...selectedLegalDocument!, content: legalDraft },
          }}
          onClose={() => setLegalPreviewOpen(false)}
        />
      ) : null}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function Root() {
  const [token, setToken] = useState(localStorage.getItem("rodar_token") || "");
  const [email, setEmail] = useState(localStorage.getItem("rodar_email") || "");
  const resetToken = new URLSearchParams(window.location.search).get("reset_token") || "";
  if (!token || resetToken) {
    return (
      <Login
        onLogin={(nextToken, nextEmail) => {
          localStorage.setItem("rodar_token", nextToken);
          localStorage.setItem("rodar_email", nextEmail);
          setToken(nextToken);
          setEmail(nextEmail);
        }}
        resetToken={resetToken}
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
