import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, chileStatusSlug, Alert, Opportunity, RadarKeyword, Run, SchedulerStatus, Stats } from "../api";
import { ConfirmModal, Country, CountryFlagIcon, Empty, HighlightedText, LegalView, LockIcon, RunProgress, commercialSignal, countryFlagUrls, formatDate, formatMoney, keywordFromRun, matchesCompletePhrase, parseDate, sourceBelongsToCountry, stripAccents, updateIntervalLabel, useRadarKeywords } from "../shared";
import { alertStatusLabel, ChannelSymbol } from "./AlertsPage";
import { excelLogoUrl, exportOpportunitiesToExcel, isOpportunityNew } from "./OpportunitiesPage";

export type HomeStatusFilter = "all" | "priority-a" | "vigentes" | "cerrados";
export type YearBreakdownMode = "processes";
export type ProcessSortMode = "date-desc" | "date-asc" | "amount-desc" | "amount-asc";

export const PROCESS_SORT_OPTIONS: Array<{ value: ProcessSortMode; label: string }> = [
  { value: "date-desc", label: "Fecha: recientes primero" },
  { value: "date-asc", label: "Fecha: antiguos primero" },
  { value: "amount-desc", label: "Monto: mayor a menor" },
  { value: "amount-asc", label: "Monto: menor a mayor" },
];

export const unmappedRegionKey = "__sin_region__";

export function sourceBelongsToCountryRadar(source: string, country: Country) {
  const normalized = source.trim().toLowerCase();
  return country === "Chile"
    ? normalized.startsWith("mercado_publico")
    : normalized === "oece_ocds_api";
}

export function backendRunDate(value: string | null) {
  if (!value) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function limaDateKey(date: Date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Lima",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function formatRunTime(value: string | null) {
  const date = backendRunDate(value);
  if (!date) return "--:--";
  return new Intl.DateTimeFormat("es-PE", {
    timeZone: "America/Lima",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

export function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function keywordContextFromHints(
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

export function matchesAnyKeywordHint(
  opportunity: Opportunity,
  keywordHints: Array<{ label: string; terms: string[] }>,
) {
  if (!keywordHints.length) return false;
  const text = `${opportunity.nomenclature} ${opportunity.description} ${opportunity.entity}`;
  return keywordHints.some((keyword) => keyword.terms.some((term) => term.trim() && matchesCompletePhrase(text, term)));
}

export function homeCommercialStatusLabel(item: Opportunity) {
  const signal = commercialSignal(item);
  if (signal.className === "green") return "Vigente para Consultas y Propuesta";
  if (signal.className === "amber") return "Vigente sólo para Propuesta";
  return "Proceso Culminado";
}

export function matchesHomeStatusFilter(item: Opportunity, filter: HomeStatusFilter) {
  if (filter === "all") return true;
  if (filter === "priority-a") return item.priority === "A";
  const signal = commercialSignal(item).className;
  if (filter === "vigentes") return signal === "green" || signal === "amber";
  return signal === "red";
}

export function homeStatusFilterLabel(filter: HomeStatusFilter) {
  if (filter === "priority-a") return "Prioridad A";
  if (filter === "vigentes") return "Vista filtrada: vigentes";
  if (filter === "cerrados") return "Vista filtrada: cerrados";
  return "Vista completa";
}

export function opportunityYear(item: Opportunity) {
  const timestamp = parseDate(item.publication_date) ?? parseDate(item.proposal_deadline) ?? parseDate(item.quote_deadline);
  return timestamp === null ? "Sin año" : String(new Date(timestamp).getFullYear());
}

export function currentAnalysisYear() {
  return String(new Date().getFullYear());
}

export function summarizeByYear(items: Opportunity[]) {
  const summaries = new Map<string, { count: number; amount: number }>();
  items.forEach((item) => {
    const year = opportunityYear(item);
    const current = summaries.get(year) || { count: 0, amount: 0 };
    summaries.set(year, {
      count: current.count + 1,
      amount: current.amount + Number(item.amount || 0),
    });
  });
  return Array.from(summaries, ([year, summary]) => ({ year, ...summary })).sort((left, right) => {
    if (left.year === "Sin año") return 1;
    if (right.year === "Sin año") return -1;
    return Number(right.year) - Number(left.year);
  });
}

// Groups by the same region/department key shown in the map's region-ranking
// boxes, so the amount pie's slices always match what's visible there. Top 7
// regions by amount get their own slice; the rest fold into "Otros" so the
// pie/callouts stay legible even for Peru's ~20 departments.
export function summarizeByRegion(items: Opportunity[], country: Country) {
  const summaries = new Map<string, { name: string; count: number; amount: number }>();
  items.forEach((item) => {
    const key = normalizeRegionName(item.region) || unmappedRegionKey;
    const name = key === unmappedRegionKey
      ? (country === "Chile" ? "Sin Región" : "Sin Departamento")
      : titleCaseRegion(key);
    const current = summaries.get(key) || { name, count: 0, amount: 0 };
    summaries.set(key, { name, count: current.count + 1, amount: current.amount + Number(item.amount || 0) });
  });
  const all = Array.from(summaries, ([key, summary]) => ({ key, ...summary })).sort((left, right) => right.amount - left.amount);
  const top = all.slice(0, 7);
  const rest = all.slice(7);
  if (rest.length) {
    top.push({
      key: "__otros__",
      name: "Otros",
      count: rest.reduce((sum, item) => sum + item.count, 0),
      amount: rest.reduce((sum, item) => sum + item.amount, 0),
    });
  }
  return top;
}

const AMOUNT_PIE_COLORS = [
  "#6b8e23",
  "#7b2ff7",
  "#2b3ee8",
  "#12b8c4",
  "#ff8a3d",
  "#f4c400",
  "#e0457b",
  "#3fae6a",
];

// Callouts for slices assigned to a column are stacked top-to-bottom in the
// order they're given (largest amount first), not by their geometric
// position on the pie, so the box reading order stays largest -> smallest.
function layoutCalloutColumn<T>(items: T[], side: "left" | "right") {
  const anchorLeft = side === "left" ? 6 : 94;
  const count = items.length;
  return items.map((item, index) => ({
    ...item,
    side,
    slot: {
      left: anchorLeft,
      top: count > 1 ? 16 + (index * (84 - 16)) / (count - 1) : 50,
    },
  }));
}

// Compact "CL 6.744.162.052" / "S/ 182.845.995" form for the callout's second
// line - formatMoney's "PESO CL ..." prefix reads fine elsewhere but doesn't
// fit a two-line label.
function formatCompactAmount(value: number, country: Country) {
  const formatted = new Intl.NumberFormat(country === "Chile" ? "es-CL" : "es-PE", { maximumFractionDigits: 0 }).format(value);
  return country === "Chile" ? `CL ${formatted}` : `S/ ${formatted}`;
}

export function AmountByRegionPie3D({
  rows,
  country,
}: {
  rows: Array<{ key: string; name: string; count: number; amount: number }>;
  totalAmount: number;
  country: Country;
}) {
  // rows arrives sorted largest amount -> smallest, with "Otros" always last
  // regardless of its own amount (see summarizeByRegion). That order is the
  // source of truth for both the box ranks below and each slice's color.
  const ranked = rows
    .filter((row) => row.amount > 0)
    .map((row, index) => ({ ...row, color: AMOUNT_PIE_COLORS[index % AMOUNT_PIE_COLORS.length] }));
  const total = ranked.reduce((sum, row) => sum + row.amount, 0);

  // The largest slice starts at the 12 o'clock point (0deg in CSS's
  // clockwise-from-12 convention - rotated 90deg clockwise from the 9
  // o'clock start this used to have) and sweeps counter-clockwise through
  // largest -> ... -> Otros. conic-gradient only sweeps clockwise from its
  // start angle, so instead we draw the same start point with the stops in
  // reverse (Otros first, largest last): sweeping clockwise through a
  // reversed list traces the identical arcs as sweeping counter-clockwise
  // through the forward list, since reversing both the direction and the
  // order cancels out.
  // conic-gradient requires its stop angles to be listed in non-decreasing
  // order (browsers clamp any stop smaller than the previous one), so the
  // gradient string is built from this reversed, ascending-angle sequence -
  // not from `ranked`, whose rank order runs the opposite direction.
  const START_DEG = 0;
  let cumulativeDeg = START_DEG;
  const drawnOrder = [...ranked].reverse().map((row) => {
    const fraction = total > 0 ? row.amount / total : 0;
    const sweepDeg = fraction * 360;
    const startDeg = cumulativeDeg;
    cumulativeDeg += sweepDeg;
    const midDeg = startDeg + sweepDeg / 2;
    const angleRad = (midDeg * Math.PI) / 180;
    const rimX = 50 + 20 * Math.sin(angleRad);
    const rimY = 50 + 20 * -Math.cos(angleRad) * 0.58;
    return { ...row, startDeg, sweepDeg, rimX, rimY };
  });

  const gradient = drawnOrder.length
    ? `conic-gradient(${drawnOrder.map((slice) => `${slice.color} ${slice.startDeg}deg ${slice.startDeg + slice.sweepDeg}deg`).join(", ")})`
    : "#0d3a6b";

  const geometryByKey = new Map(drawnOrder.map((slice) => [slice.key, slice]));
  const slices = ranked.map((row) => ({ ...row, ...geometryByKey.get(row.key)! }));

  // Boxes read largest -> smallest -> Otros-last, top-left down to
  // bottom-right: the first half of `ranked` fills the left column
  // (top to bottom), the rest fills the right column.
  const leftCount = Math.ceil(slices.length / 2);
  const placedSlices = [
    ...layoutCalloutColumn(slices.slice(0, leftCount), "left"),
    ...layoutCalloutColumn(slices.slice(leftCount), "right"),
  ];

  return (
    <div className="amount-pie-block">
      <div className="amount-pie-scene">
        <div className="amount-pie-3d">
          <div className="amount-pie-3d-side" style={{ background: gradient }} />
          <div className="amount-pie-3d-top" style={{ background: gradient }} />
        </div>
        {placedSlices.map((slice) => (
          <div
            key={slice.key}
            className={`amount-pie-callout ${slice.side}`}
            style={{ left: `${slice.slot.left}%`, top: `${slice.slot.top}%`, borderColor: slice.color }}
          >
            <span className="amount-pie-callout-dot" style={{ background: slice.color }} aria-hidden="true" />
            <span className="amount-pie-callout-copy">
              <span className="amount-pie-callout-name">{slice.name}</span>
              <span className="amount-pie-callout-amount">{slice.count} {slice.count === 1 ? "Opp" : "Opps"} · {formatCompactAmount(slice.amount, country)}</span>
            </span>
          </div>
        ))}
      </div>
      {!slices.length ? <Empty text="El monto por región aparecerá cuando el radar detecte procesos con monto informado." /> : null}
    </div>
  );
}

export function titleCaseRegion(value: string) {
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

export function chileRegionFromOpportunity(item: Opportunity) {
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

export function withChileHomeRegion(item: Opportunity) {
  return { ...item, region: chileRegionFromOpportunity(item) };
}

export function regionFill(count: number, max: number) {
  if (count <= 0) return "#dfeaf6";
  const ratio = Math.min(1, count / Math.max(1, max));
  if (ratio >= 0.75) return "#0b2e63";
  if (ratio >= 0.45) return "#1559b7";
  if (ratio >= 0.2) return "#4f94e8";
  return "#a8cff7";
}

export function cleanSvgPathAttributes(value: string) {
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

export function enrichMapSvg(country: Country, raw: string, regionCounts: Map<string, number>, selectedRegion: string | null) {
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

export function InteractiveCountryMap({
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
  const [rawSvg, setRawSvg] = useState("");
  const regionCounts = useMemo(() => new Map(regions.map((item) => [item.key, item.count])), [regions]);
  const svgMarkup = useMemo(
    () => rawSvg ? enrichMapSvg(country, rawSvg, regionCounts, selectedRegion) : "",
    [country, rawSvg, regionCounts, selectedRegion],
  );

  useEffect(() => {
    let active = true;
    const loader = country === "Chile"
      ? import("../assets_mapa/chile.svg?raw")
      : import("../assets_mapa/peru-regions.svg?raw");
    setRawSvg("");
    loader.then((module) => {
      if (active) setRawSvg(module.default);
    });
    return () => { active = false; };
  }, [country]);

  function selectFromTarget(target: EventTarget | null) {
    if (!(target instanceof Element)) return;
    const region = target.closest<SVGElement>("[data-region-key]");
    const key = region?.dataset.regionKey;
    if (key) onSelectRegion(key);
  }

  return (
    <div
      className={`interactive-map-shell ${country === "Chile" ? "chile" : "peru"}`}
      aria-busy={!rawSvg}
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

export function CountryMapOrb({ country }: { country: Country }) {
  return (
    <div className="country-map-orb" aria-hidden="true">
      <img src={countryFlagUrls[country]} alt="" />
    </div>
  );
}

export function SortIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 4v16M7 4 4 7M7 4l3 3M17 20V4M17 20l-3-3M17 20l3-3" />
    </svg>
  );
}

export function SearchIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export async function copyToClipboard(value: string) {
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

export function Kpis({
  stats,
  country,
  activeFilter = "all",
  onFilterChange,
  yearSummaries = [],
  selectedYear,
  yearBreakdownMode = null,
  onYearChange,
  onToggleYearBreakdown,
  contextLabel,
  contextAction,
  filteredAmount,
  yearScopedStats,
}: {
  stats: Stats | null;
  country: Country;
  activeFilter?: HomeStatusFilter;
  onFilterChange?: (filter: HomeStatusFilter) => void;
  yearSummaries?: Array<{ year: string; count: number; amount: number }>;
  selectedYear?: string | null;
  yearBreakdownMode?: YearBreakdownMode | null;
  onYearChange?: (year: string | null) => void;
  onToggleYearBreakdown?: (mode: YearBreakdownMode) => void;
  contextLabel?: React.ReactNode;
  contextAction?: React.ReactNode;
  filteredAmount?: number;
  yearScopedStats?: Stats | null;
}) {
  const amountHint = activeFilter && activeFilter !== "all"
    ? "Monto de la selección"
    : selectedYear
      ? `Año ${selectedYear}`
      : "Monto total detectado";
  const countStats = yearScopedStats ?? stats;
  const values: Array<{ label: string; value: React.ReactNode; hint: string; filter?: HomeStatusFilter; breakdown?: YearBreakdownMode; tone?: "success" | "danger" }> = [
    { label: "Procesos radar", value: countStats?.total ?? 0, hint: yearBreakdownMode === "processes" ? "Ocultar desglose anual" : "Ver desglose por año", filter: "all", breakdown: "processes" },
    { label: "Prioridad A", value: countStats?.by_priority?.A ?? 0, hint: "Revisar Inmediatamente", filter: "priority-a", tone: "success" },
    { label: "Vigentes", value: countStats?.vigentes ?? 0, hint: "Presentar Consultas o Propuestas", filter: "vigentes", tone: "success" },
    { label: "Cerrados", value: countStats?.cerrados ?? 0, hint: "Procesos Finalizados", filter: "cerrados", tone: "danger" },
    { label: "Monto detectado", value: formatMoney(filteredAmount ?? stats?.total_amount ?? 0, country), hint: amountHint },
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
          if ((item.filter && onFilterChange) || item.breakdown) {
            const isActive = item.breakdown
              ? yearBreakdownMode === item.breakdown
              : activeFilter === item.filter;
            return (
              <button
                className={`kpi kpi-action ${item.tone ? `kpi-${item.tone}` : ""} ${isActive ? "active" : ""}`}
                key={item.label}
                type="button"
                aria-pressed={isActive}
                aria-expanded={item.breakdown ? yearBreakdownMode === item.breakdown : undefined}
                onClick={() => {
                  if (item.breakdown) {
                    onFilterChange?.("all");
                    onToggleYearBreakdown?.(item.breakdown);
                  } else if (item.filter) {
                    onFilterChange?.(item.filter);
                  }
                }}
              >
                {content}
              </button>
            );
          }
          return <article className="kpi" key={item.label}>{content}</article>;
        })}
      </section>
      {yearBreakdownMode && onYearChange ? (
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
            {yearSummaries.map(({ year, count }) => (
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

export function Home({
  country,
  token,
  isAdmin,
  runs,
  alerts,
  opportunities,
  refresh,
  onSearchKeyword,
  onOpenLegal,
}: {
  country: Country;
  token: string;
  isAdmin: boolean;
  runs: Run[];
  alerts: Alert[];
  opportunities: Opportunity[];
  refresh: () => Promise<void>;
  onSearchKeyword: (keyword: string) => void;
  onOpenLegal: (view: LegalView) => void;
}) {
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [processSort, setProcessSort] = useState<ProcessSortMode>("date-desc");
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const [nomenclatureSearchOpen, setNomenclatureSearchOpen] = useState(false);
  const [nomenclatureSearch, setNomenclatureSearch] = useState("");
  const sortMenuRef = useRef<HTMLDivElement | null>(null);
  const [homeFilter, setHomeFilter] = useState<HomeStatusFilter>("all");
  const [selectedYear, setSelectedYear] = useState<string | null>(() => currentAnalysisYear());
  const [yearBreakdownMode, setYearBreakdownMode] = useState<YearBreakdownMode | null>(null);
  const [keywordEditorOpen, setKeywordEditorOpen] = useState(false);
  const [newKeyword, setNewKeyword] = useState("");
  const [keywordSaving, setKeywordSaving] = useState(false);
  const [keywordNotice, setKeywordNotice] = useState("");
  const [pendingHomeRemoval, setPendingHomeRemoval] = useState<Opportunity | null>(null);
  const [archiveError, setArchiveError] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [countdownNow, setCountdownNow] = useState(() => Date.now());
  const copyNoticeTimerRef = useRef<number | null>(null);
  const refreshRef = useRef(refresh);
  const schedulerWasRunningRef = useRef(false);
  refreshRef.current = refresh;
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
  const recentCountryAlerts = useMemo(
    () => alerts.filter((alert) => alert.country === (country === "Chile" ? "chile" : "peru") && alert.rule_is_active),
    [alerts, country],
  );
  const yearSummaries = useMemo(() => summarizeByYear(countryOpportunities), [countryOpportunities]);
  const filteredHomeOpportunities = useMemo(
    () => countryOpportunities.filter((item) => matchesHomeStatusFilter(item, homeFilter) && (selectedYear === null || opportunityYear(item) === selectedYear)),
    [countryOpportunities, homeFilter, selectedYear],
  );
  const countryRuns = useMemo(
    () => runs.filter((run) => sourceBelongsToCountryRadar(run.source, country)),
    [runs, country],
  );
  const homeStats = useMemo(() => summarizeOpportunities(countryOpportunities), [countryOpportunities]);
  const filteredHomeStats = useMemo(() => summarizeOpportunities(filteredHomeOpportunities), [filteredHomeOpportunities]);
  const yearScopedOpportunities = useMemo(
    () => countryOpportunities.filter((item) => selectedYear === null || opportunityYear(item) === selectedYear),
    [countryOpportunities, selectedYear],
  );
  const yearScopedStats = useMemo(() => summarizeOpportunities(yearScopedOpportunities), [yearScopedOpportunities]);
  const lastRun = countryRuns[0];
  const todayKey = limaDateKey(new Date(countdownNow));
  const todayRuns = countryRuns
    .filter((run) => {
      const date = backendRunDate(run.started_at || run.finished_at);
      return date ? limaDateKey(date) === todayKey : false;
    })
    .sort((left, right) => {
      const leftTime = backendRunDate(left.started_at || left.finished_at)?.getTime() || 0;
      const rightTime = backendRunDate(right.started_at || right.finished_at)?.getTime() || 0;
      return rightTime - leftTime;
    });
  const nextUpdateSeconds = schedulerStatus?.next_update_at
    ? Math.max(0, Math.ceil((new Date(schedulerStatus.next_update_at).getTime() - countdownNow) / 1000))
    : null;
  const regionRows = regionSummary(filteredHomeStats, filteredHomeOpportunities, country);
  const countryLabel = country === "Chile" ? "Chile" : "Peru";
  const homeContextLabel = (
    <>
      <strong className="dashboard-context-title">Palabras Clave para el update automático</strong>
      <span className="dashboard-keyword-list" aria-label={displayedHomeKeywordTerms.join(", ")}>
        {displayedHomeKeywordTerms.map((term) => (
          <span className="dashboard-keyword" key={term}>{term}</span>
        ))}
      </span>
    </>
  );
  const selectedRegionRow = selectedRegion ? regionRows.items.find((item) => item.key === selectedRegion) : null;

  useEffect(() => {
    let active = true;
    async function loadSchedulerStatus() {
      try {
        const status = await api.schedulerStatus(token, country === "Chile" ? "chile" : "peru");
        if (active) {
          setSchedulerStatus(status);
          if (status.is_running || schedulerWasRunningRef.current) {
            void refreshRef.current();
          }
          schedulerWasRunningRef.current = status.is_running;
        }
      } catch {
        if (active) setSchedulerStatus(null);
      }
    }
    void loadSchedulerStatus();
    const syncTimer = window.setInterval(loadSchedulerStatus, 5_000);
    const countdownTimer = window.setInterval(() => setCountdownNow(Date.now()), 1_000);
    return () => {
      active = false;
      window.clearInterval(syncTimer);
      window.clearInterval(countdownTimer);
    };
  }, [token, country]);
  const selectedRegionProcesses = useMemo(() => {
    const filtered = selectedRegion === unmappedRegionKey
      ? filteredHomeOpportunities.filter((item) => !normalizeRegionName(item.region))
      : selectedRegion
        ? filteredHomeOpportunities.filter((item) => normalizeRegionName(item.region) === selectedRegion)
        : filteredHomeOpportunities;
    const nomenclatureNeedle = nomenclatureSearch.trim().toLowerCase();
    const searched = nomenclatureNeedle
      ? filtered.filter((item) => item.nomenclature.toLowerCase().includes(nomenclatureNeedle))
      : filtered;
    return searched
      .slice()
      .sort((left, right) => {
        if (processSort === "amount-desc" || processSort === "amount-asc") {
          const delta = (left.amount || 0) - (right.amount || 0);
          return processSort === "amount-desc" ? -delta : delta;
        }
        if (processSort === "date-desc") {
          const newDelta = Number(isOpportunityNew(right)) - Number(isOpportunityNew(left));
          if (newDelta !== 0) return newDelta;
        }
        const rightDate = parseDate(right.publication_date) || parseDate(right.proposal_deadline) || parseDate(right.quote_deadline) || 0;
        const leftDate = parseDate(left.publication_date) || parseDate(left.proposal_deadline) || parseDate(left.quote_deadline) || 0;
        return processSort === "date-asc" ? leftDate - rightDate : rightDate - leftDate;
      });
  }, [filteredHomeOpportunities, selectedRegion, processSort, nomenclatureSearch]);
  const regionAmountBreakdown = useMemo(() => summarizeByRegion(filteredHomeOpportunities, country), [filteredHomeOpportunities, country]);

  async function copyProcessNomenclature(item: Opportunity) {
    const nomenclature = item.nomenclature.trim();
    if (!nomenclature) return;
    await copyToClipboard(nomenclature);
    setCopyNotice("Nomenclatura Copiada, puedes ver el detalle en el módulo Oportunidades");
    if (copyNoticeTimerRef.current !== null) window.clearTimeout(copyNoticeTimerRef.current);
    copyNoticeTimerRef.current = window.setTimeout(() => setCopyNotice(""), 3200);
  }

  async function removeHomeProcess() {
    if (!pendingHomeRemoval) return;
    setArchiveError("");
    try {
      await api.archiveOpportunity(token, pendingHomeRemoval.id);
      setPendingHomeRemoval(null);
      await refresh();
    } catch (error) {
      setArchiveError(error instanceof Error ? error.message : "No se pudo retirar el proceso");
    }
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
    if (!sortMenuOpen) return;
    function closeOnOutsidePointer(event: PointerEvent) {
      if (!sortMenuRef.current?.contains(event.target as Node)) setSortMenuOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setSortMenuOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [sortMenuOpen]);

  useEffect(() => {
    setHomeFilter("all");
    setSelectedYear(currentAnalysisYear());
    setYearBreakdownMode(null);
    setPendingHomeRemoval(null);
    setArchiveError("");
    setCopyNotice("");
  }, [country]);

  useEffect(() => () => {
    if (copyNoticeTimerRef.current !== null) window.clearTimeout(copyNoticeTimerRef.current);
  }, []);

  return (
    <>
      <section className="hero-panel">
        <div>
          <div className="hero-update-banner" role="note">
            <span>Update Automático del sistema cada {updateIntervalLabel(schedulerStatus?.interval_seconds)} para detectar nuevas oportunidades.</span>
          </div>
          <p className="overline">{country === "Peru" ? "Modulo Peru" : "Modulo Chile"}</p>
          <h2>{country === "Peru" ? "SEACE operativo, monitoreo automatico y alertas accionables." : "Mercado Público bajo vigilancia comercial y regional."}</h2>
        </div>
        <div className="radar-sweep" aria-hidden="true">
          <span />
          <b />
        </div>
      </section>
      <section className="year-analysis-row" aria-label="Selector de año de análisis">
        <span className="year-analysis-label">Seleccionar año para análisis:</span>
        <div className="year-analysis-actions">
          <button
            type="button"
            className={selectedYear === null ? "selected" : ""}
            aria-pressed={selectedYear === null}
            onClick={() => setSelectedYear(null)}
          >
            Todos
          </button>
          {yearSummaries.map(({ year }) => (
            <button
              type="button"
              key={year}
              className={selectedYear === year ? "selected" : ""}
              aria-pressed={selectedYear === year}
              onClick={() => setSelectedYear(year)}
            >
              {year}
            </button>
          ))}
        </div>
      </section>
      <Kpis
        stats={homeStats}
        yearScopedStats={yearScopedStats}
        filteredAmount={filteredHomeStats.total_amount}
        country={country}
        activeFilter={homeFilter}
        onFilterChange={setHomeFilter}
        yearSummaries={yearSummaries}
        selectedYear={selectedYear}
        yearBreakdownMode={yearBreakdownMode}
        onYearChange={setSelectedYear}
        onToggleYearBreakdown={(mode) => setYearBreakdownMode((current) => current === mode ? null : mode)}
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
              {homeFilter !== "all" ? (
                <span className="data-pill subtle">{homeStatusFilterLabel(homeFilter)}</span>
              ) : null}
              {selectedYear ? (
                <span className="data-pill year-pill">Año {selectedYear}</span>
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
                {regionRows.items.map((item) => (
                  <button
                    className={`region-row ${selectedRegion === item.key ? "is-selected" : ""}`}
                    key={item.key}
                    type="button"
                    title={`${item.name}: ${item.count} procesos`}
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
              <div className="map-inspector-donut">
                <div className="map-inspector-donut-heading">
                  <strong>Monto detectado</strong>
                  <span>{formatMoney(filteredHomeStats.total_amount, country)}</span>
                </div>
                <AmountByRegionPie3D rows={regionAmountBreakdown} totalAmount={filteredHomeStats.total_amount} country={country} />
              </div>
            </div>
          </div>
        </article>
        <article className={`panel map-process-list-panel ${country === "Chile" ? "chile" : "peru"}`}>
          <div className="panel-title">
            <div>
              <h3>Procesos {selectedRegionRow?.name || countryLabel}</h3>
              <span>{selectedRegionProcesses.length} procesos visualizados</span>
            </div>
            <div className="panel-title-actions">
              <div className={`process-nomenclature-search ${nomenclatureSearchOpen ? "is-open" : ""}`}>
                {nomenclatureSearchOpen ? (
                  <input
                    autoFocus
                    type="text"
                    value={nomenclatureSearch}
                    onChange={(event) => setNomenclatureSearch(event.target.value)}
                    onBlur={() => {
                      if (!nomenclatureSearch.trim()) setNomenclatureSearchOpen(false);
                    }}
                    placeholder="Buscar por nomenclatura"
                    aria-label="Buscar proceso por nomenclatura"
                  />
                ) : null}
                <button
                  type="button"
                  className="process-search-icon-button"
                  title="Buscar por nomenclatura"
                  aria-label="Buscar por nomenclatura"
                  onClick={() => {
                    if (nomenclatureSearchOpen) {
                      setNomenclatureSearch("");
                      setNomenclatureSearchOpen(false);
                    } else {
                      setNomenclatureSearchOpen(true);
                    }
                  }}
                >
                  <SearchIcon />
                </button>
              </div>
              <button
                className="export-excel-icon-button"
                type="button"
                title="Descargar procesos filtrados en Excel"
                aria-label="Descargar procesos filtrados en Excel"
                onClick={() => void exportOpportunitiesToExcel(
                  token,
                  selectedRegionProcesses.map((item) => ({ item, signal: commercialSignal(item) })),
                  `Procesos ${selectedRegionRow?.name || countryLabel}`,
                  country,
                  "dashboard",
                )}
              >
                <img src={excelLogoUrl} alt="" aria-hidden="true" loading="lazy" decoding="async" />
              </button>
              <div className="process-sort-control" ref={sortMenuRef}>
                <button
                  type="button"
                  className="process-sort-trigger"
                  aria-haspopup="listbox"
                  aria-expanded={sortMenuOpen}
                  onClick={() => setSortMenuOpen((value) => !value)}
                >
                  <SortIcon />
                  <span>{PROCESS_SORT_OPTIONS.find((option) => option.value === processSort)?.label}</span>
                </button>
                {sortMenuOpen ? (
                  <ul className="process-sort-menu" role="listbox" aria-label="Ordenar procesos">
                    {PROCESS_SORT_OPTIONS.map((option) => (
                      <li key={option.value}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={processSort === option.value}
                          className={processSort === option.value ? "selected" : ""}
                          onClick={() => {
                            setProcessSort(option.value);
                            setSortMenuOpen(false);
                          }}
                        >
                          {option.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
              {selectedRegion ? (
                <button className="ghost" type="button" onClick={() => setSelectedRegion(null)}>Ver todo</button>
              ) : null}
            </div>
          </div>
          {selectedRegionProcesses.length ? (
            <div className="region-opportunity-list">
              {selectedRegionProcesses.map((item, index) => (
                <article className="map-opportunity-card" key={item.id}>
                  <button
                    className="map-opportunity-copy"
                    type="button"
                    aria-label={`Copiar nomenclatura ${item.nomenclature || "del proceso"}`}
                    onClick={() => copyProcessNomenclature(item)}
                  />
                  <div className="map-opportunity-top">
                    <span className="map-opportunity-order" aria-label={`Proceso ${index + 1}`}>{index + 1}</span>
                    <span className="map-opportunity-heading">
                      <strong>{item.nomenclature || "Proceso sin nomenclatura"}</strong>
                      <span>{item.entity || "Entidad no informada"}</span>
                    </span>
                    <div className="map-opportunity-action">
                      <button className="map-opportunity-remove" type="button" onClick={() => setPendingHomeRemoval(item)}>
                        Retirar de la Sección
                      </button>
                      {isOpportunityNew(item) ? (
                        <span className="new-opportunity-badge" title="Proceso incorporado a GovRadar durante los últimos 7 días" aria-label="Proceso nuevo">
                          NEW
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <span className="map-opportunity-description"><HighlightedText text={item.description} terms={homeKeywordTerms} /></span>
                  <span className={`home-status-badge ${commercialSignal(item).className}`}>{homeCommercialStatusLabel(item)}</span>
                  {country === "Chile" && (item.source_status || item.contract_duration) ? (
                    <span className="map-opportunity-chile-meta">
                      {item.source_status ? <span className={`chile-ml-status ${chileStatusSlug(item.source_status)}`}>{item.source_status}</span> : null}
                      {item.contract_duration ? <span className="chile-ml-contract">Duración de contrato: {item.contract_duration}</span> : null}
                    </span>
                  ) : null}
                  <span className="map-opportunity-amount">
                    <small className={item.amount > 0 ? "" : "amount-unpublished"}>
                      {item.amount > 0 ? "Monto detectado" : "Monto no publicado"}
                    </small>
                    <strong>{formatMoney(item.amount, country)}</strong>
                  </span>
                </article>
              ))}
            </div>
          ) : (
            <Empty text={`La lista de procesos aparecerá cuando el radar de ${countryLabel} detecte coincidencias.`} />
          )}
        </article>
      </section>
      <section className="two-col">
        <article className="panel execution-panel">
          <div className="panel-title execution-panel-title">
            <h3>Updates Automáticos</h3>
            <div className="execution-title-actions">
              <UpdateCountdown status={schedulerStatus} seconds={nextUpdateSeconds} />
              <span className={`status ${lastRun?.status || "queued"}`}>{lastRun?.status || "Sin datos"}</span>
            </div>
          </div>
          {lastRun ? <RunProgress run={lastRun} /> : <Empty text="Aun no hay ejecuciones registradas." />}
          <RunHistoryToday runs={todayRuns} />
        </article>
        <article className="panel">
          <div className="panel-title">
            <h3>Alertas recientes</h3>
            <span>{recentCountryAlerts.length}</span>
          </div>
          <div className="list recent-alerts-list">
            {recentCountryAlerts.slice(0, 20).map((alert) => {
              const alertKeywordTerms = alert.keywords.split(",").map((term) => term.trim()).filter(Boolean);
              return (
                <div className="list-row recent-alert-row" key={alert.id}>
                  <span className="recent-alert-icons">
                    <CountryFlagIcon country={alert.country === "chile" ? "Chile" : "Peru"} className="rule-country-flag-image" />
                    <ChannelSymbol channel={alert.channel} />
                  </span>
                  <div className="recent-alert-copy">
                    <strong>{alert.entity || "Sin entidad"}</strong>
                    <small>
                      {alert.description ? <HighlightedText text={alert.description} terms={alertKeywordTerms} /> : "Sin descripción"}
                    </small>
                    <small className="recent-alert-destination">{alert.destination || "Sin destino"}</small>
                  </div>
                  <div className="recent-alert-status">
                    <span className={`event-status-label ${alert.status}`}>{alertStatusLabel(alert.status)}</span>
                    {alert.run_id ? <small>Run #{alert.run_id} · 1 proceso</small> : null}
                    <small>{formatDate(alert.created_at)}</small>
                  </div>
                </div>
              );
            })}
            {!recentCountryAlerts.length ? <Empty text="Crea reglas para activar alertas por email, WhatsApp o mensaje interno." /> : null}
          </div>
        </article>
      </section>
      {copyNotice ? (
        <div className="copy-toast" role="status" aria-live="polite">
          <span aria-hidden="true">✓</span>
          {copyNotice}
        </div>
      ) : null}
      {archiveError ? <div className="notice danger archive-action-notice" role="alert">{archiveError}</div> : null}
      {pendingHomeRemoval ? (
        <ConfirmModal
          title="Retirar de la Vista"
          message="¿Está seguro de retirar este detalle de proceso? Se moverá al histórico y no será reincorporado por las actualizaciones automáticas."
          confirmLabel="Sí, retirar"
          cancelLabel="No"
          onConfirm={removeHomeProcess}
          onCancel={() => setPendingHomeRemoval(null)}
        />
      ) : null}
    </>
  );
}

export function UpdateCountdown({ status, seconds }: { status: SchedulerStatus | null; seconds: number | null }) {
  let message = "Consultando próximo update...";
  if (status && !status.enabled) {
    message = "Update automático pausado";
  } else if (status?.is_running) {
    message = "Update en ejecución...";
  } else if (seconds !== null) {
    const days = Math.floor(seconds / 86_400);
    const hours = Math.floor((seconds % 86_400) / 3_600);
    const minutes = Math.floor((seconds % 3_600) / 60);
    const remainingSeconds = seconds % 60;
    const parts = [days ? `${days} d` : "", hours ? `${hours} h` : "", `${minutes} m`, `${String(remainingSeconds).padStart(2, "0")} s`].filter(Boolean);
    message = seconds === 0
      ? "Update iniciando..."
      : `Update se ejecutará en ${parts.join(" ")}`;
  }
  return <span className={`update-countdown ${status?.is_running ? "running" : ""}`} role="timer" aria-live="off">{message}</span>;
}

export function RunHistoryToday({ runs }: { runs: Run[] }) {
  return (
    <section className="run-history" aria-labelledby="run-history-title">
      <div className="run-history-heading">
        <h4 id="run-history-title">Historial de updates de hoy</h4>
        <span>{runs.length}</span>
      </div>
      <div className="run-history-scroll" tabIndex={0} aria-label="Historial desplazable de actualizaciones de hoy">
        {runs.map((run) => {
          const keyword = keywordFromRun(run) || "Actualización automática";
          return (
            <article className="run-history-row" key={run.id}>
              <time dateTime={run.started_at || run.finished_at || undefined}>{formatRunTime(run.started_at || run.finished_at)}</time>
              <div>
                <strong>{keyword}</strong>
                <small>Run #{run.id} · {run.rows_found} {run.rows_found === 1 ? "proceso" : "procesos"}</small>
              </div>
              <span className={`status ${run.status}`}>{run.status}</span>
            </article>
          );
        })}
        {!runs.length ? <Empty text="Aún no hay updates registrados hoy." /> : null}
      </div>
    </section>
  );
}

export function normalizeRegionName(value: string) {
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

export function summarizeOpportunities(opportunities: Opportunity[]): Stats {
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

export function regionSummary(stats: Stats | null, opportunities: Opportunity[], country: Country = "Peru") {
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
    entries.push({
      key: unmappedRegionKey,
      name: country === "Chile" ? "Sin Región" : "Sin Departamento",
      count: unmappedTotal,
    });
  }
  const max = entries[0]?.count || 1;
  return {
    total: opportunities.length,
    items: entries.map((item) => ({ ...item, percent: Math.max(8, Math.round((item.count / max) * 100)) })),
  };
}

export default Home;
