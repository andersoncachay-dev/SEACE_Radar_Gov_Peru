import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, DocumentRecord, Opportunity, Run } from "../api";
import { CommercialClass, ConfirmModal, Country, Empty, HighlightedText, RunProgress, addKeyword, commercialSignal, formatDate, formatMoney, keywordFromRun, matchesCompletePhrase, normalizedSearchTerm, parseDate, presentationDeadline, sourceBelongsToCountry, uniqueKeywords, useRadarKeywords } from "../shared";

export type Module = "SEACE Publico" | "Contratos Menores a 8 UIT" | "Oportunidades Chile LMP-GC" | "Ambos modulos";

export type SearchMode = "append" | "replace";

export type OpportunityVariant = "radar" | "ocds";

export type TableColumnFilters = {
  priority: string; entity: string; process: string; description: string;
  publicationFrom: string; publicationTo: string;
  consultationFrom: string; consultationTo: string;
  consultationDaysMin: string; consultationDaysMax: string;
  proposalFrom: string; proposalTo: string;
  proposalDaysMin: string; proposalDaysMax: string;
  amountMin: string; amountMax: string; amountReserved: boolean;
};

export const emptyTableColumnFilters: TableColumnFilters = {
  priority: "", entity: "", process: "", description: "",
  publicationFrom: "", publicationTo: "",
  consultationFrom: "", consultationTo: "",
  consultationDaysMin: "", consultationDaysMax: "",
  proposalFrom: "", proposalTo: "",
  proposalDaysMin: "", proposalDaysMax: "",
  amountMin: "", amountMax: "", amountReserved: false,
};

export type MaxResultsMode = "all" | "active";

export type ActivePeriodKeywordGroup = {
  year: string;
  months: string[];
  keywords: string[];
  commercialMode: MaxResultsMode;
  processCount?: number;
  opportunityIds?: number[];
};

export type PendingSearch = { mode: SearchMode; keywords: string[]; runIds: number[]; appliedState: SavedOpportunityViewState; kind?: "required" | "additional" };

export type SavedOpportunityViewState = {
  keywords: string[];
  runIds: number[];
  keyword: string;
  keyword2: string;
  keyword3: string;
  nomenclatureFilter: string;
  entityFilter: string;
  entityKeyword: string;
  entityKeyword2: string;
  entityKeyword3: string;
  publicationDateFrom: string;
  publicationDateTo: string;
  years: string[];
  months: string[];
  appliedYears: string[];
  appliedMonths: string[];
  periodKeywordGroups: ActivePeriodKeywordGroup[];
  additionalPeriodKeywordGroups: ActivePeriodKeywordGroup[];
  maxResultsMode: MaxResultsMode;
  searchMode: SearchMode;
};

export const commercialFilters = [
  { label: "Vigente para Consultas y Propuesta", className: "green" },
  { label: "Vigente para Propuesta", className: "amber" },
  { label: "Proceso Culminado", className: "red" },
] as const;

export const activeSearchStoragePrefix = "govradar.opportunities.activeSearch";

export const monthOptions = [
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

export const currentYear = new Date().getFullYear();

export const yearOptions = Array.from({ length: 6 }, (_, index) => String(currentYear - index));

export const excelLogoUrl = "/assets/logoexcel.png";

export function modulesForCountry(country: Country): Module[] {
  return country === "Chile"
    ? ["Oportunidades Chile LMP-GC"]
    : ["SEACE Publico", "Contratos Menores a 8 UIT", "Ambos modulos"];
}

export function defaultModuleForCountry(country: Country): Module {
  return country === "Chile" ? "Oportunidades Chile LMP-GC" : "SEACE Publico";
}

export function moduleLabel(module: Module) {
  if (module === "Oportunidades Chile LMP-GC") {
    return "Licitaciones Mercado Público y Grandes Compras";
  }
  return module;
}

export function opportunityBandLabel(country: Country, variant: OpportunityVariant, module: Module) {
  if (variant === "ocds") {
    return "Contrataciones Abiertas OECE/OCDS para procesos Peru, incluyendo licitaciones, adjudicaciones, contratos y compras menores publicadas.";
  }
  if (country === "Chile") {
    return "Oportunidades Chile Licitaciones Mercado Publico y Grandes Compras";
  }
  return moduleLabel(module);
}

export function sourceForModule(module: Module) {
  if (module === "Oportunidades Chile LMP-GC") return "mercado_publico_lmp_gc";
  if (module === "Contratos Menores a 8 UIT") return "menor8_browser";
  return "seace_public_browser";
}

export function sourceBelongsToView(source: string, country: Country, variant: OpportunityVariant) {
  const normalized = source.toLowerCase();
  if (variant === "ocds") return country === "Peru" && normalized.startsWith("oece_ocds");
  if (country === "Peru") return (normalized.startsWith("seace") || normalized.includes("menor8")) && !normalized.startsWith("oece_ocds");
  return sourceBelongsToCountry(source, country);
}

export function formatManualTimestamp(value: string) {
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function futurePeriodValidationMessage(years: string[], months: string[], now = new Date()) {
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

export function dateOnly(value: number) {
  const date = new Date(value);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function daysUntil(value: string | null) {
  const timestamp = parseDate(value);
  if (timestamp === null) return null;
  const dayMs = 24 * 60 * 60 * 1000;
  return Math.round((dateOnly(timestamp) - dateOnly(Date.now())) / dayMs);
}

export function toggleSelected(values: string[], value: string) {
  if (values.includes(value)) {
    return values.length > 1 ? values.filter((item) => item !== value) : values;
  }
  return [...values, value];
}

export function RadarActionIcon() {
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

export function datePart(value: string | null, part: "year" | "month") {
  const timestamp = parseDate(value);
  if (timestamp === null) return null;
  const date = new Date(timestamp);
  return part === "year" ? String(date.getFullYear()) : String(date.getMonth() + 1);
}

export function uniqueDefined(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((item): item is string => Boolean(item))));
}

export function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function moneyText(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "Monto reservado";
  return new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN", maximumFractionDigits: 0 }).format(value || 0);
}

export function daysText(value: number | null) {
  if (value === null) return "-";
  if (value < 0) return `Vencido hace ${Math.abs(value)} dias`;
  return String(value);
}

export async function exportOpportunitiesToExcel(token: string, rows: Array<{ item: Opportunity; signal: ReturnType<typeof commercialSignal> }>, title: string, country: Country) {
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
  const blob = await api.exportOpportunitiesXlsx(token, { title, country: country.toLowerCase() as "peru" | "chile", headers, rows: body });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `oportunidades-${new Date().toISOString().slice(0, 10)}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function Opportunities({
  country,
  userId,
  token,
  data,
  runs,
  refresh,
  variant = "radar",
  prefillKeyword = null,
  onPrefillConsumed,
}: {
  country: Country;
  userId: number;
  token: string;
  data: Opportunity[];
  runs: Run[];
  refresh: () => Promise<void>;
  variant?: OpportunityVariant;
  prefillKeyword?: string | null;
  onPrefillConsumed?: () => void;
}) {
  const serverScope = `${variant}.${country}`;
  const storageScope = `${userId}.${serverScope}`;
  const radarKeywordState = useRadarKeywords(token, country);
  const keywordSuggestionListId = `radar-keyword-suggestions-${country}-${variant}`;
  const initialSearchState = useMemo(() => loadActiveSearchState(storageScope, serverScope), [storageScope, serverScope]);
  const persistedScopeRef = useRef(storageScope);
  const restoredRunPeriodRef = useRef(false);
  const lastServerStateRef = useRef("");
  const [viewStateHydrated, setViewStateHydrated] = useState(false);
  const [module, setModule] = useState<Module>(defaultModuleForCountry(country));
  const [keyword, setKeyword] = useState(initialSearchState.keyword);
  const [keyword2, setKeyword2] = useState(initialSearchState.keyword2);
  const [keyword3, setKeyword3] = useState(initialSearchState.keyword3);
  const [nomenclatureFilter, setNomenclatureFilter] = useState(initialSearchState.nomenclatureFilter);
  const [entityFilter, setEntityFilter] = useState(initialSearchState.entityFilter);
  const [entityKeyword, setEntityKeyword] = useState(initialSearchState.entityKeyword);
  const [entityKeyword2, setEntityKeyword2] = useState(initialSearchState.entityKeyword2);
  const [entityKeyword3, setEntityKeyword3] = useState(initialSearchState.entityKeyword3);
  const [publicationDateFrom, setPublicationDateFrom] = useState(initialSearchState.publicationDateFrom);
  const [publicationDateTo, setPublicationDateTo] = useState(initialSearchState.publicationDateTo);
  const [ocdsYears, setOcdsYears] = useState<string[]>(initialSearchState.years);
  const [ocdsMonths, setOcdsMonths] = useState<string[]>(initialSearchState.months);
  const [appliedPeriodYears, setAppliedPeriodYears] = useState<string[]>(initialSearchState.appliedYears);
  const [appliedPeriodMonths, setAppliedPeriodMonths] = useState<string[]>(initialSearchState.appliedMonths);
  const [appliedPeriodKeywordGroups, setAppliedPeriodKeywordGroups] = useState<ActivePeriodKeywordGroup[]>(initialSearchState.periodKeywordGroups);
  const [additionalPeriodKeywordGroups, setAdditionalPeriodKeywordGroups] = useState<ActivePeriodKeywordGroup[]>(initialSearchState.additionalPeriodKeywordGroups);
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
  const [pendingKeywordRemoval, setPendingKeywordRemoval] = useState<string | null>(null);
  const [removingKeyword, setRemovingKeyword] = useState(false);
  const [keywordRemovalNotice, setKeywordRemovalNotice] = useState("");
  const [keywordRemovalError, setKeywordRemovalError] = useState("");
  const [prefillNotice, setPrefillNotice] = useState("");
  const [periodValidationError, setPeriodValidationError] = useState("");
  const [opportunitySummaryOpen, setOpportunitySummaryOpen] = useState(() => !window.matchMedia("(max-width: 720px)").matches);
  const [requiredFiltersOpen, setRequiredFiltersOpen] = useState(() => !window.matchMedia("(max-width: 720px)").matches);
  const [optionalFiltersOpen, setOptionalFiltersOpen] = useState(() => !window.matchMedia("(max-width: 720px)").matches);
  const [runResultRows, setRunResultRows] = useState<Opportunity[]>([]);
  const [focusedRunResultIds, setFocusedRunResultIds] = useState<Set<number> | null>(null);
  const visibleRuns = useMemo(() => runs.filter((run) => sourceBelongsToView(run.source, country, variant)), [runs, country, variant]);
  const invalidPublicationDateRange = Boolean(publicationDateFrom && publicationDateTo && publicationDateFrom > publicationDateTo);
  const entitySearchKeywords = uniqueKeywords([entityKeyword, entityKeyword2, entityKeyword3]);
  const additionalSearchReady = Boolean(
    publicationDateFrom
    && publicationDateTo
    && !invalidPublicationDateRange
    && (nomenclatureFilter.trim() || (entityFilter.trim() && entitySearchKeywords.length)),
  );
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
  const visibleRequiredPeriodGroups = useMemo(() => {
    const optionalTerms = [nomenclatureFilter, entityFilter].map((item) => item.trim().toLowerCase()).filter(Boolean);
    const additionalTerms = new Set(additionalPeriodKeywordGroups.flatMap((group) => group.keywords).map(normalizedSearchTerm));
    const processTerms = new Set(
      data
        .filter((item) => sourceBelongsToView(item.source, country, variant))
        .flatMap((item) => [item.nomenclature, item.description])
        .map(normalizedSearchTerm)
        .filter(Boolean),
    );
    const cleanedGroups = activePeriodKeywordGroups.flatMap((group) => {
      const keywords = group.keywords.filter((item) => {
        const normalized = normalizedSearchTerm(item);
        return normalized
          && !optionalTerms.includes(normalized)
          && !additionalTerms.has(normalized)
          && !processTerms.has(normalized)
          && item.trim().length <= 80;
      });
      return keywords.length ? [{ ...group, keywords }] : [];
    });
    return mergePeriodKeywordGroups(cleanedGroups);
  }, [activePeriodKeywordGroups, additionalPeriodKeywordGroups, nomenclatureFilter, entityFilter, data, country, variant]);
  const displayedSearchKeywords = useMemo(
    () => uniqueKeywords(visibleRequiredPeriodGroups.flatMap((group) => group.keywords)),
    [visibleRequiredPeriodGroups],
  );
  const periodProcessCounts = useMemo(() => {
    const viewRows = data.filter((item) => sourceBelongsToView(item.source, country, variant));
    const requiredCounts = visibleRequiredPeriodGroups.map((group) => [
      periodGroupKey(group),
      new Set(viewRows.filter((item) => opportunityMatchesPeriodGroup(item, group)).map((item) => item.id)).size,
    ] as const);
    const additionalCounts = additionalPeriodKeywordGroups.map((group) => [
      periodGroupKey(group),
      group.processCount ?? inferAdditionalRunCount(group, visibleRuns),
    ] as const);
    return new Map([...requiredCounts, ...additionalCounts]);
  }, [data, country, variant, visibleRuns, visibleRequiredPeriodGroups, additionalPeriodKeywordGroups]);

  useEffect(() => {
    // A newly-created run may not be present in `visibleRuns` until the next
    // global refresh. Do not replace it with an older run while its dedicated
    // polling loop is active.
    if (pendingSearch) return;
    const currentVisibleRun = visibleRuns.find((run) => run.id === activeRun?.id);
    if (currentVisibleRun) return;
    const latestAppliedRun = visibleRuns.find((run) => activeRunIds.includes(run.id));
    setActiveRun(latestAppliedRun || visibleRuns[0] || null);
  }, [activeRun, activeRunIds, visibleRuns, pendingSearch]);

  const visiblePendingRunStatuses = useMemo(
    () => pendingRunStatuses.filter((run) => sourceBelongsToView(run.source, country, variant)),
    [pendingRunStatuses, country, variant],
  );
  const isRadarProcessing = starting
    || visiblePendingRunStatuses.some((run) => run.status === "queued" || run.status === "running")
    || Boolean(activeRun && (activeRun.status === "queued" || activeRun.status === "running"));
  const displayedRunIds = useMemo(() => {
    const candidates = visiblePendingRunStatuses.length > 1 ? visiblePendingRunStatuses : activeRun ? [activeRun] : [];
    return candidates.filter((run) => run.status === "completed").map((run) => run.id);
  }, [visiblePendingRunStatuses, activeRun]);

  useEffect(() => {
    if (!displayedRunIds.length) {
      setRunResultRows([]);
      setFocusedRunResultIds(null);
      return;
    }
    let cancelled = false;
    api.opportunities(token, { runIds: displayedRunIds }).then((rows) => {
      if (cancelled) return;
      setRunResultRows(rows.filter((item) => sourceBelongsToView(item.source, country, variant)));
      setFocusedRunResultIds(null);
    }).catch(() => { if (!cancelled) setRunResultRows([]); });
    return () => { cancelled = true; };
  }, [token, country, variant, displayedRunIds.join(",")]);

  useEffect(() => {
    if (activeKeywords.length) return;
    const recoverableKeywords = uniqueKeywords(variant === "ocds" ? [keyword] : [keyword, keyword2, keyword3]);
    if (recoverableKeywords.length) setActiveKeywords(recoverableKeywords);
  }, [activeKeywords, keyword, keyword2, keyword3, variant]);

  useEffect(() => {
    if (persistedScopeRef.current !== storageScope || !viewStateHydrated) return;
    const nextState: SavedOpportunityViewState = {
      keywords: activeKeywords,
      runIds: activeRunIds,
      keyword,
      keyword2,
      keyword3,
      nomenclatureFilter,
      entityFilter,
      entityKeyword,
      entityKeyword2,
      entityKeyword3,
      publicationDateFrom,
      publicationDateTo,
      years: [...ocdsYears],
      months: [...ocdsMonths],
      appliedYears: [...appliedPeriodYears],
      appliedMonths: [...appliedPeriodMonths],
      periodKeywordGroups: appliedPeriodKeywordGroups,
      additionalPeriodKeywordGroups,
      maxResultsMode,
      searchMode,
    };
    const serialized = JSON.stringify(nextState);
    saveActiveSearchState(storageScope, nextState);
    if (serialized === lastServerStateRef.current) return;
    const timer = window.setTimeout(() => {
      api.saveOpportunityViewState(token, serverScope, nextState)
        .then((saved) => {
          const normalized = normalizeActiveSearchState(saved.state);
          lastServerStateRef.current = JSON.stringify(normalized);
          window.localStorage.setItem(`${activeSearchStorageKey(storageScope)}.serverSynced`, "1");
        })
        .catch(() => {
          // Keep the local copy and retry after the next state change.
        });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    storageScope,
    serverScope,
    token,
    viewStateHydrated,
    activeKeywords,
    activeRunIds,
    keyword,
    keyword2,
    keyword3,
    nomenclatureFilter,
    entityFilter,
    entityKeyword,
    entityKeyword2,
    entityKeyword3,
    publicationDateFrom,
    publicationDateTo,
    ocdsYears,
    ocdsMonths,
    appliedPeriodYears,
    appliedPeriodMonths,
    appliedPeriodKeywordGroups,
    additionalPeriodKeywordGroups,
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
    if (search.kind === "additional") {
      const runRows = completedIds.length ? await api.opportunities(token, { runIds: completedIds }) : [];
      const displayedTerms = uniqueKeywords(runRows.map((item) => item.nomenclature).filter(Boolean));
      const additionalGroups = search.appliedState.additionalPeriodKeywordGroups.map((group) => ({
        ...group,
        keywords: displayedTerms.length ? displayedTerms : group.keywords,
        processCount: runRows.length,
        opportunityIds: runRows.map((item) => item.id),
      }));
      const nextRunIds = addRunIds(activeRunIds, completedIds);
      setActiveRunIds(nextRunIds);
      setAdditionalPeriodKeywordGroups(additionalGroups);
      setScopedRows((current) => mergeOpportunities(current ?? filtered, runRows));
      saveActiveSearchState(storageScope, {
        ...search.appliedState,
        keywords: activeKeywords,
        runIds: nextRunIds,
        additionalPeriodKeywordGroups: additionalGroups,
      });
      setPendingSearch(null);
      setActiveRun(statuses[statuses.length - 1] || null);
      return true;
    }
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
    const localState = loadActiveSearchState(storageScope, serverScope);
    let cancelled = false;

    const applyState = (nextState: SavedOpportunityViewState) => {
      setModule(defaultModuleForCountry(country));
      setKeyword(nextState.keyword);
      setKeyword2(nextState.keyword2);
      setKeyword3(nextState.keyword3);
      setNomenclatureFilter(nextState.nomenclatureFilter);
      setEntityFilter(nextState.entityFilter);
      setEntityKeyword(nextState.entityKeyword);
      setEntityKeyword2(nextState.entityKeyword2);
      setEntityKeyword3(nextState.entityKeyword3);
      setPublicationDateFrom(nextState.publicationDateFrom);
      setPublicationDateTo(nextState.publicationDateTo);
      setOcdsYears(nextState.years);
      setOcdsMonths(nextState.months);
      setAppliedPeriodYears(nextState.appliedYears);
      setAppliedPeriodMonths(nextState.appliedMonths);
      setAppliedPeriodKeywordGroups(nextState.periodKeywordGroups);
      setAdditionalPeriodKeywordGroups(nextState.additionalPeriodKeywordGroups);
      setMaxResultsMode(nextState.maxResultsMode);
      setSearchMode(nextState.searchMode);
      setActiveKeywords(nextState.keywords);
      setActiveRunIds(nextState.runIds);
    };

    setViewStateHydrated(false);
    lastServerStateRef.current = "";
    persistedScopeRef.current = storageScope;
    restoredRunPeriodRef.current = false;
    applyState(localState);
    setActiveRun(null);
    setScopedRows(null);
    setPinnedRows([]);
    setPendingSearch(null);
    setPendingRunStatuses([]);
    setBatchKeywords([]);
    setRunResultRows([]);
    setFocusedRunResultIds(null);
    setConfirmNewSearch(false);

    const hydrateFromServer = async () => {
      let selectedState = localState;
      let serverConfirmed = false;
      try {
        const remoteRecord = await api.opportunityViewState(token, serverScope);
        serverConfirmed = true;
        const remoteState = normalizeActiveSearchState(remoteRecord.state);
        const wasAlreadySynced = window.localStorage.getItem(`${activeSearchStorageKey(storageScope)}.serverSynced`) === "1";
        if (!wasAlreadySynced && opportunityViewStateRichness(localState) > opportunityViewStateRichness(remoteState)) {
          const saved = await api.saveOpportunityViewState(token, serverScope, localState);
          selectedState = normalizeActiveSearchState(saved.state);
          serverConfirmed = true;
        } else {
          selectedState = remoteState;
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          try {
            const saved = await api.saveOpportunityViewState(token, serverScope, localState);
            selectedState = normalizeActiveSearchState(saved.state);
            serverConfirmed = true;
          } catch {
            selectedState = localState;
          }
        }
      }
      if (cancelled) return;
      applyState(selectedState);
      saveActiveSearchState(storageScope, selectedState);
      lastServerStateRef.current = serverConfirmed ? JSON.stringify(selectedState) : "";
      if (serverConfirmed) window.localStorage.setItem(`${activeSearchStorageKey(storageScope)}.serverSynced`, "1");
      setViewStateHydrated(true);
    };

    void hydrateFromServer();
    return () => {
      cancelled = true;
    };
  }, [country, storageScope, serverScope, token]);

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
    const pendingRunIds = pendingSearch?.runIds || [];
    const liveRunId = !pendingRunIds.length && activeRun && ["queued", "running"].includes(activeRun.status)
      ? activeRun.id
      : null;
    if (!pendingRunIds.length && liveRunId === null) return;

    let cancelled = false;
    let polling = false;

    const pollRunProgress = async () => {
      if (polling || cancelled) return;
      polling = true;
      try {
        if (pendingSearch && pendingRunIds.length) {
          const statuses = await Promise.all(pendingRunIds.map((runId) => api.run(token, runId)));
          if (cancelled) return;
          setPendingRunStatuses(statuses);
          const nextLiveRun = statuses.find((item) => item.status === "running") || statuses.find((item) => item.status === "queued");
          if (nextLiveRun) setActiveRun(nextLiveRun);
          if (statuses.every((item) => ["completed", "failed", "cancelled"].includes(item.status))) {
            await syncPendingSearch(pendingSearch, statuses);
          }
        } else if (liveRunId !== null) {
          const nextRun = await api.run(token, liveRunId);
          if (cancelled) return;
          setActiveRun(nextRun);
          if (["completed", "failed", "cancelled"].includes(nextRun.status)) await refresh();
        }
      } catch {
        // The manual refresh button remains available if polling is interrupted.
      } finally {
        polling = false;
      }
    };

    // Fetch immediately so the UI does not stay at the POST response's
    // initial `queued` state for the first polling interval.
    void pollRunProgress();
    const timer = window.setInterval(pollRunProgress, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeRun?.id, activeRun?.status, token, refresh, pendingSearch, activeKeywords, activeRunIds, pinnedRows]);

  // En Chile y OCDS Perú, los bloques de períodos activos son la definición
  // del conjunto visible. Los runIds sirven para recuperar la configuración,
  // pero no deben recortar procesos válidos ya presentes en la base acumulada.
  const baseRows = usesPeriodFilters ? data : scopedRows ?? data;
  const filtered = useMemo(() => {
    const normalizedActiveKeywords = activeKeywords.map((item) => item.toLowerCase()).filter(Boolean);
    const activeOnly = maxResultsMode === "active";
    return baseRows.filter((item) => {
      if (!sourceBelongsToView(item.source, country, variant)) return false;
      if (focusedRunResultIds && !focusedRunResultIds.has(item.id)) return false;
      // En Perú, "Ver en la tabla" representa un proceso que ya fue
      // identificado (y, en la revalidación, enriquecido en SEACE). No debe
      // volver a excluirse por el período de convocatoria de la búsqueda
      // general: la selección exacta se sostiene por el ID del proceso.
      // Chile conserva su filtrado vigente por fecha de cierre/presentación.
      if (country === "Peru" && focusedRunResultIds) return true;
      const haystack = `${item.entity} ${item.nomenclature} ${item.description}`.toLowerCase();
      const keywordMatch = !normalizedActiveKeywords.length || normalizedActiveKeywords.some((item) => matchesCompletePhrase(haystack, item));
      const activeMatch = !activeOnly || commercialSignal(item).className !== "red";
      const periodCombinationMatch = !usesPeriodFilters || (!activePeriodKeywordGroups.length && !additionalPeriodKeywordGroups.length)
        ? keywordMatch && activeMatch
        : activePeriodKeywordGroups.some((group) => opportunityMatchesPeriodGroup(item, group))
          || additionalPeriodKeywordGroups.some((group) => opportunityMatchesAdditionalGroup(item, group, visibleRuns));
      return periodCombinationMatch;
    });
  }, [baseRows, activeKeywords, maxResultsMode, country, variant, usesPeriodFilters, visibleRuns, activePeriodKeywordGroups, additionalPeriodKeywordGroups, focusedRunResultIds]);

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

  async function execute() {
    setPeriodValidationError("");
    if (searchMode === "replace" && filtered.length > 0 && !confirmNewSearch) {
      setConfirmNewSearch(true);
      return;
    }
    await executeConfirmed(searchMode);
  }

  async function executeConfirmed(mode: SearchMode) {
    setPeriodValidationError("");
    const rawKeywords = variant === "ocds" ? [keyword] : [keyword, keyword2, keyword3];
    const cleanKeywords = uniqueKeywords(rawKeywords).length
      ? uniqueKeywords(rawKeywords)
      : ["satelital"];
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
          year: usesPeriodFilters ? ocdsYears.join(",") : country === "Peru" ? "2026" : "",
          month: usesPeriodFilters ? ocdsMonths.join(",") : "",
          years: usesPeriodFilters ? ocdsYears : undefined,
          months: usesPeriodFilters ? ocdsMonths : undefined,
          version: variant === "ocds" ? "OCDS OECE" : country === "Peru" ? "Seace 3" : "Mercado Publico",
          max_results: 0,
          max_details: 0,
          // Mercado Publico only exposes convocatoria and consultation dates
          // inside each tender sheet. Enrich every active Chile result; the
          // scraper deliberately skips expired processes in this normal flow.
          enrich_details: country === "Chile",
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
        entityKeyword,
        entityKeyword2,
        entityKeyword3,
        publicationDateFrom,
        publicationDateTo,
        years: [...ocdsYears],
        months: [...ocdsMonths],
        appliedYears: nextAppliedYears,
        appliedMonths: nextAppliedMonths,
        periodKeywordGroups: nextPeriodKeywordGroups,
        additionalPeriodKeywordGroups,
        maxResultsMode,
        searchMode: mode,
      };
      setAppliedPeriodYears(nextAppliedYears);
      setAppliedPeriodMonths(nextAppliedMonths);
      setAppliedPeriodKeywordGroups(nextPeriodKeywordGroups);
      setActiveRun(runningRun);
      setPendingSearch({ mode, keywords: cleanKeywords, runIds: startedRunIds, appliedState, kind: "required" });
      setPendingRunStatuses(startedRuns);
      setBatchKeywords(cleanKeywords);
      saveActiveSearchState(storageScope, appliedState);
      await refresh();
    } finally {
      setStarting(false);
    }
  }

  async function executeAdditionalSearch() {
    if (!additionalSearchReady) return;
    const cleanNomenclature = nomenclatureFilter.trim();
    const cleanEntity = entityFilter.trim();
    const searchTerms = cleanNomenclature ? [cleanNomenclature] : entitySearchKeywords;
    const start = new Date(`${publicationDateFrom}T00:00:00`);
    const end = new Date(`${publicationDateTo}T00:00:00`);
    const years: string[] = [];
    const months: string[] = [];
    const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
    while (cursor <= end) {
      const year = String(cursor.getFullYear());
      const month = String(cursor.getMonth() + 1);
      if (!years.includes(year)) years.push(year);
      if (!months.includes(month)) months.push(month);
      cursor.setMonth(cursor.getMonth() + 1);
    }
    const groups = years.map((year) => ({ year, months: [...months], keywords: [...searchTerms], commercialMode: "all" as MaxResultsMode }));
    setStarting(true);
    try {
      const startedRuns = await Promise.all(searchTerms.map((searchTerm) => api.startRun(token, {
        source: variant === "ocds" ? "oece_ocds_api" : sourceForModule(module),
        keyword: searchTerm,
        nomenclature: cleanNomenclature || undefined,
        entity_filter: cleanNomenclature ? undefined : cleanEntity,
        year: years.join(","),
        month: months.join(","),
        years,
        months,
        publication_date_from: publicationDateFrom,
        publication_date_to: publicationDateTo,
        version: variant === "ocds" ? "OCDS OECE" : country === "Peru" ? "Seace 3" : "Mercado Publico",
        max_results: 0,
        max_details: cleanNomenclature ? 1 : 0,
        // Every manual Chile search needs the Mercado Publico tender sheet to
        // obtain publication and consultation dates. The scraper itself skips
        // expired processes unless the user explicitly requests revalidation.
        enrich_details: country === "Chile" || Boolean(cleanNomenclature),
        commercial_mode: "all",
      })));
      const run = startedRuns[0];
      const startedRunIds = startedRuns.map((item) => item.id);
      const appliedState: SavedOpportunityViewState = {
        ...loadActiveSearchState(storageScope),
        keywords: activeKeywords,
        runIds: addRunIds(activeRunIds, startedRunIds),
        nomenclatureFilter,
        entityFilter,
        entityKeyword,
        entityKeyword2,
        entityKeyword3,
        publicationDateFrom,
        publicationDateTo,
        additionalPeriodKeywordGroups: groups,
      };
      setAdditionalPeriodKeywordGroups(groups);
      setActiveRun(run);
      setPendingRunStatuses(startedRuns);
      setBatchKeywords(searchTerms);
      setPendingSearch({ mode: "append", keywords: searchTerms, runIds: startedRunIds, appliedState, kind: "additional" });
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
    const detailKeyword = country === "Chile" ? cleanNomenclature : item.description.trim() || cleanNomenclature;
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
        max_details: country === "Chile" ? 1 : 12,
        enrich_details: true,
        revalidate_closed_detail: country === "Chile" && commercialSignal(item).className === "red",
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
      setScopedRows((current) => mergeOpportunities(current ?? filtered, runRows));
      return country === "Chile"
        ? Boolean(updatedRow?.consultation_deadline)
        : Boolean(updatedRow && presentationDeadline(updatedRow));
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
    setKeyword("");
    setKeyword2("");
    setKeyword3("");
    setMaxResultsMode("active");
    setPeriodValidationError("");
    setConfirmNewSearch(false);
  }

  function clearOptionalFilters() {
    setNomenclatureFilter("");
    setEntityFilter("");
    setEntityKeyword("");
    setEntityKeyword2("");
    setEntityKeyword3("");
    setPublicationDateFrom("");
    setPublicationDateTo("");
  }

  async function archiveProcess(item: Opportunity) {
    await api.archiveOpportunity(token, item.id);
    setScopedRows((current) => current ? current.filter((row) => row.id !== item.id) : current);
    setPinnedRows((current) => current.filter((row) => row.id !== item.id));
    await refresh();
  }

  async function removeActiveKeyword() {
    if (!pendingKeywordRemoval || removingKeyword) return;
    const removedKeyword = pendingKeywordRemoval;
    const normalizedRemovedKeyword = normalizedSearchTerm(removedKeyword);
    setRemovingKeyword(true);
    setKeywordRemovalError("");
    setKeywordRemovalNotice("");
    try {
      const remainingKeywords = displayedSearchKeywords.filter(
        (item) => normalizedSearchTerm(item) !== normalizedRemovedKeyword,
      );
      const result = await api.archiveOpportunitiesByKeyword(
        token,
        country.toLowerCase() as "peru" | "chile",
        removedKeyword,
        remainingKeywords,
      );
      const archivedIds = new Set(result.opportunity_ids);
      const withoutKeyword = (groups: ActivePeriodKeywordGroup[]) => groups.flatMap((group) => {
        const keywords = group.keywords.filter((item) => normalizedSearchTerm(item) !== normalizedRemovedKeyword);
        return keywords.length ? [{ ...group, keywords }] : [];
      });
      setActiveKeywords((current) => current.filter((item) => normalizedSearchTerm(item) !== normalizedRemovedKeyword));
      setActiveRunIds((current) => current.filter((runId) => {
        const run = visibleRuns.find((item) => item.id === runId);
        return !run || normalizedSearchTerm(keywordFromRun(run)) !== normalizedRemovedKeyword;
      }));
      setAppliedPeriodKeywordGroups((current) => withoutKeyword(current));
      setAdditionalPeriodKeywordGroups((current) => withoutKeyword(current));
      if (normalizedSearchTerm(keyword) === normalizedRemovedKeyword) setKeyword("");
      if (normalizedSearchTerm(keyword2) === normalizedRemovedKeyword) setKeyword2("");
      if (normalizedSearchTerm(keyword3) === normalizedRemovedKeyword) setKeyword3("");
      setScopedRows((current) => current ? current.filter((item) => !archivedIds.has(item.id)) : current);
      setPinnedRows((current) => current.filter((item) => !archivedIds.has(item.id)));
      setPendingKeywordRemoval(null);
      setKeywordRemovalNotice(result.archived
        ? `${result.archived} ${result.archived === 1 ? "proceso fue enviado" : "procesos fueron enviados"} al histórico al eliminar “${removedKeyword}”.`
        : `Se eliminó “${removedKeyword}” de la búsqueda activa. No había procesos asociados para archivar.`);
      await refresh();
    } catch (error) {
      setKeywordRemovalError(error instanceof Error ? error.message : "No se pudo eliminar la palabra clave");
    } finally {
      setRemovingKeyword(false);
    }
  }

  return (
    <section className="panel opportunities-panel">
      <div className="panel-title">
        <div>
          {country === "Chile" || variant === "ocds" ? null : (
            <h2>Radar de oportunidades Peru</h2>
          )}
          {country === "Chile" || variant === "ocds" ? null : (
            <p>Ejecuta SEACE en backend headless y revisa avance sin abrir Chrome al usuario.</p>
          )}
        </div>
      </div>
      <div className="module-row">
        {variant === "ocds" || country === "Chile" ? (
          <button
            className="selected opportunity-summary-toggle"
            type="button"
            aria-expanded={opportunitySummaryOpen}
            aria-controls={`${storageScope}-summary-content`}
            onClick={() => setOpportunitySummaryOpen((current) => !current)}
          >
            <span>{opportunityBandLabel(country, variant, module)}</span>
            <i className="filter-section-chevron" aria-hidden="true" />
          </button>
        ) : (
          modulesForCountry(country).map((item) => (
            <button key={item} className={module === item ? "selected" : ""} onClick={() => setModule(item)}>
              {opportunityBandLabel(country, variant, item)}
            </button>
          ))
        )}
      </div>
      <div id={`${storageScope}-summary-content`} hidden={(variant === "ocds" || country === "Chile") && !opportunitySummaryOpen}>
      {prefillNotice ? <div className="notice info keyword-search-notice">{prefillNotice}</div> : null}
      {module === "Contratos Menores a 8 UIT" || module === "Ambos modulos" ? <div className="notice info">Menores a 8 UIT queda visible para el flujo, pendiente de estabilizacion del conector.</div> : null}
      <div className="active-search-context">
        <div className="active-keywords">
          <span>Búsqueda activa:</span>
          {displayedSearchKeywords.length
            ? displayedSearchKeywords.map((item) => (
                <b className="active-keyword-chip" key={item}>
                  <span>{item}</span>
                  <button
                    type="button"
                    aria-label={`Eliminar ${item} de la búsqueda activa`}
                    title={`Eliminar ${item}`}
                    onClick={() => setPendingKeywordRemoval(item)}
                  >×</button>
                </b>
              ))
            : <b>Todos los procesos</b>}
        </div>
        {keywordRemovalNotice ? <div className="notice success keyword-removal-notice" role="status">{keywordRemovalNotice}</div> : null}
        {keywordRemovalError ? <div className="notice danger keyword-removal-notice" role="alert">{keywordRemovalError}</div> : null}
        {usesPeriodFilters ? (
          <div className="active-period-summary">
            <span title="Filtros de período aplicados actualmente a la tabla de procesos">
              Períodos activos:
            </span>
            <div className="active-period-list">
              {visibleRequiredPeriodGroups.map((group) => (
                <div className="active-period-row" key={`${group.year}-${group.commercialMode}-${group.months.join("-")}-${group.keywords.join("-")}`}>
                  <div className="active-period-box">
                    <strong>{group.year}</strong>
                    <em className={`active-period-mode ${group.commercialMode}`}>
                      {group.commercialMode === "all" ? "Todos" : "Vigentes"}
                    </em>
                    <span>{group.months.length ? monthLabels(group.months).join(", ") : "Todos los meses"}</span>
                    <span className={`active-period-count ${(periodProcessCounts.get(periodGroupKey(group)) || 0) === 0 ? "zero" : ""}`}>
                      {processCountLabel(periodProcessCounts.get(periodGroupKey(group)) || 0)}
                    </span>
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
            {additionalPeriodKeywordGroups.length ? (
              <div className="additional-search-summary">
                <span>Búsquedas adicionales:</span>
                <div className="active-period-list">
                  {additionalPeriodKeywordGroups.map((group) => (
                    <div className="active-period-row" key={`additional-${group.year}-${group.months.join("-")}-${group.keywords.join("-")}`}>
                      <div className="active-period-box">
                        <strong>{group.year}</strong>
                        <em className="active-period-mode all">Todos</em>
                        <span>{group.months.length ? monthLabels(group.months).join(", ") : "Todos los meses"}</span>
                        <span className={`active-period-count ${(periodProcessCounts.get(periodGroupKey(group)) || 0) === 0 ? "zero" : ""}`}>
                          {processCountLabel(periodProcessCounts.get(periodGroupKey(group)) || 0)}
                        </span>
                      </div>
                      <span className="active-period-arrow" aria-hidden="true">→</span>
                      <div className="active-period-keywords">
                        <span>Keywords aplicadas:</span>
                        {group.keywords.map((item) => <b key={item}>{item}</b>)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      </div>
      <div className="radar-filter-workspace">
        <section className={`radar-filter-section required ${requiredFiltersOpen ? "is-open" : "is-collapsed"}`} aria-labelledby={`${storageScope}-required-title`}>
          <div className="radar-filter-heading">
            <div>
              <h3 id={`${storageScope}-required-title`}>
                <button
                  className="filter-section-toggle"
                  type="button"
                  aria-expanded={requiredFiltersOpen}
                  aria-controls={`${storageScope}-required-content`}
                  onClick={() => setRequiredFiltersOpen((current) => !current)}
                >
                  <span>Búsqueda de Procesos - Filtros generales</span>
                  <i className="filter-section-chevron" aria-hidden="true" />
                </button>
              </h3>
              <p>Define el periodo, las palabras clave y el estado comercial de la búsqueda.</p>
            </div>
            <div className="filter-heading-actions">
              <span className="filter-type-badge">Requeridos</span>
              <button className="clear-section-filters" type="button" onClick={clearRequiredFilters}>Limpiar Filtro</button>
            </div>
          </div>
          <div className="radar-filter-content" id={`${storageScope}-required-content`} hidden={!requiredFiltersOpen}>
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
                <div className="multi-filter-heading">
                  <span>Meses</span>
                  <label className="all-months-switch">
                    <span>Todos los meses</span>
                    <input
                      type="checkbox"
                      checked={ocdsMonths.length === monthOptions.length}
                      onChange={(event) => {
                        setOcdsMonths(event.target.checked ? monthOptions.map(([value]) => value) : []);
                        setPeriodValidationError("");
                      }}
                    />
                    <span className="all-months-switch-track" aria-hidden="true"><span /></span>
                  </label>
                </div>
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
            {variant !== "ocds" ? (
              <>
                <label>Keyword 2<input list={keywordSuggestionListId} value={keyword2} onChange={(event) => setKeyword2(event.target.value)} placeholder="Ej. internet" /></label>
                <label>Keyword 3<input list={keywordSuggestionListId} value={keyword3} onChange={(event) => setKeyword3(event.target.value)} placeholder="Ej. conectividad" /></label>
              </>
            ) : null}
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
            <button
              className="primary execute-radar-button"
              type="button"
              onClick={execute}
              disabled={isRadarProcessing || (variant === "radar" && (module === "Contratos Menores a 8 UIT" || module === "Ambos modulos"))}
              aria-busy={isRadarProcessing}
            >
              <RadarActionIcon />
              <span>{isRadarProcessing ? "Procesando" : "Ejecutar Radar"}</span>
            </button>
          </div>
          </div>
        </section>

        <section className={`radar-filter-section optional ${optionalFiltersOpen ? "is-open" : "is-collapsed"}`} aria-labelledby={`${storageScope}-optional-title`}>
          <div className="radar-filter-heading">
            <div>
              <h3 id={`${storageScope}-optional-title`}>
                <button
                  className="filter-section-toggle"
                  type="button"
                  aria-expanded={optionalFiltersOpen}
                  aria-controls={`${storageScope}-optional-content`}
                  onClick={() => setOptionalFiltersOpen((current) => !current)}
                >
                  <span>Búsqueda Específica</span>
                  <i className="filter-section-chevron" aria-hidden="true" />
                </button>
              </h3>
              <p>Devuelve los resultados cuando conoces datos específicos del proceso. Si no se logra visualizar el proceso en la tabla inferior, puedes generar una búsqueda adicional.</p>
            </div>
            <div className="filter-heading-actions">
              <span className="filter-type-badge">Opcionales</span>
              <button className="clear-section-filters" type="button" onClick={clearOptionalFilters}>Limpiar Filtro</button>
            </div>
          </div>
          <div className="radar-filter-content" id={`${storageScope}-optional-content`} hidden={!optionalFiltersOpen}>
          <div className="optional-filter-grid">
            <label>Búsqueda por Nomenclatura del Proceso <small className="exact-match-hint">Coincidencia exacta</small><input value={nomenclatureFilter} onChange={(event) => setNomenclatureFilter(event.target.value)} placeholder={country === "Chile" ? "Ej. 2422-122-L126" : "Ej. CP-ABR-2-2026-UGEL-A-1"} /></label>
            <div className="entity-search-field">
              <label>Búsqueda por Nombre de Entidad <small className="exact-match-hint">Coincidencia exacta</small><input value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)} placeholder={country === "Chile" ? "Ej. Municipalidad de Santiago" : "Ej. Gobierno Regional de Lima"} /></label>
              {entityFilter.trim() && !nomenclatureFilter.trim() ? (
                <div className="entity-keyword-fields" role="group" aria-label="Keywords obligatorias para la búsqueda por entidad">
                  <span>Keywords de negocio <small>Ingresa de 1 a 3</small></span>
                  <div>
                    <label>Keyword 1<input list={keywordSuggestionListId} value={entityKeyword} onChange={(event) => setEntityKeyword(event.target.value)} placeholder="Ej. conectividad" /></label>
                    <label>Keyword 2<input list={keywordSuggestionListId} value={entityKeyword2} onChange={(event) => setEntityKeyword2(event.target.value)} placeholder="Ej. internet" /></label>
                    <label>Keyword 3<input list={keywordSuggestionListId} value={entityKeyword3} onChange={(event) => setEntityKeyword3(event.target.value)} placeholder="Ej. satelital" /></label>
                  </div>
                  {!entitySearchKeywords.length ? <small className="entity-keyword-error" role="status">Debes ingresar al menos una keyword para buscar por entidad.</small> : null}
                </div>
              ) : null}
            </div>
            <div className="date-range-field" role="group" aria-labelledby={`${storageScope}-publication-date-label`}>
              <span id={`${storageScope}-publication-date-label`}>Búsqueda Fecha de Convocatoria</span>
              <div className="date-range-inputs">
                <label>Inicio<input type="date" value={publicationDateFrom} max={publicationDateTo || undefined} onChange={(event) => setPublicationDateFrom(event.target.value)} /></label>
                <label>Fin<input type="date" value={publicationDateTo} min={publicationDateFrom || undefined} onChange={(event) => setPublicationDateTo(event.target.value)} /></label>
              </div>
              {invalidPublicationDateRange ? <small className="date-range-error" role="alert">La fecha de inicio debe ser anterior o igual a la fecha de fin.</small> : null}
            </div>
          </div>
          <p className="additional-search-requirements">Completa la fecha de convocatoria y, además, la nomenclatura, el nombre de la entidad o ambos. Si ingresas nomenclatura, tendrá prioridad. Una búsqueda solo por entidad requiere entre una y tres keywords de negocio.</p>
          <div className="radar-action-row optional-action-row">
            <button className="primary additional-search-button" type="button" onClick={executeAdditionalSearch} disabled={!additionalSearchReady || isRadarProcessing}>
              {isRadarProcessing ? "Procesando..." : "Ejecutar búsqueda adicional"}
            </button>
          </div>
          </div>
        </section>

      </div>
      {activeRun ? <RunProgress run={activeRun} batchRuns={visiblePendingRunStatuses} batchKeywords={batchKeywords} resultRows={runResultRows} resultsFocused={Boolean(focusedRunResultIds)} country={country} onToggleResults={runResultRows.length ? () => setFocusedRunResultIds((current) => current ? null : new Set(runResultRows.map((item) => item.id))) : undefined} /> : visibleRuns[0] ? <RunProgress run={visibleRuns[0]} resultRows={runResultRows} resultsFocused={Boolean(focusedRunResultIds)} country={country} onToggleResults={runResultRows.length ? () => setFocusedRunResultIds((current) => current ? null : new Set(runResultRows.map((item) => item.id))) : undefined} /> : null}
      <OpportunityTable
        rows={filtered}
        country={country}
        token={token}
        resetKey={`${storageScope}:${activeKeywords.join("|")}:${activeRunIds.join(",")}`}
        onRevalidateProposal={revalidateProposalDate}
        highlightTerms={activeKeywords}
        onProcessAction={archiveProcess}
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
      {pendingKeywordRemoval ? (
        <ConfirmModal
          title="Eliminar palabra clave"
          message="¿Está seguro de eliminar la palabra clave? Se enviarán todos los procesos asociados al módulo Histórico de Procesos Eliminados."
          confirmLabel={removingKeyword ? "Eliminando..." : "Sí"}
          cancelLabel="No"
          onConfirm={removeActiveKeyword}
          onCancel={() => { if (!removingKeyword) setPendingKeywordRemoval(null); }}
        />
      ) : null}
    </section>
  );
}

export function addKeywords(current: string[], keywords: string[]) {
  return keywords.reduce((items, keyword) => addKeyword(items, keyword), current);
}

export function addRunId(current: number[], runId: number) {
  return current.includes(runId) ? current : [...current, runId];
}

export function addRunIds(current: number[], runIds: number[]) {
  return runIds.reduce((items, runId) => addRunId(items, runId), current);
}

export function mergeOpportunities(left: Opportunity[], right: Opportunity[]) {
  const byId = new Map<number, Opportunity>();
  [...left, ...right].forEach((item) => byId.set(item.id, item));
  return [...byId.values()];
}

export function activeSearchStorageKey(scope: string) {
  return `${activeSearchStoragePrefix}.${scope}`;
}

export function defaultOpportunityViewState(): SavedOpportunityViewState {
  return {
    keywords: ["satelital"],
    runIds: [],
    keyword: "satelital",
    keyword2: "",
    keyword3: "",
    nomenclatureFilter: "",
    entityFilter: "",
    entityKeyword: "",
    entityKeyword2: "",
    entityKeyword3: "",
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
    additionalPeriodKeywordGroups: [],
    maxResultsMode: "active",
    searchMode: "append",
  };
}

export function publishedOpportunityViewState(scope: string): SavedOpportunityViewState | null {
  const shared = {
    runIds: [],
    keyword: "satelital",
    keyword2: "internet",
    keyword3: "conectividad",
    nomenclatureFilter: "",
    entityFilter: "",
    entityKeyword: "",
    entityKeyword2: "",
    entityKeyword3: "",
    publicationDateFrom: "",
    publicationDateTo: "",
    years: ["2026"],
    months: ["7"],
    appliedYears: ["2026"],
    maxResultsMode: "active" as MaxResultsMode,
    searchMode: "append" as SearchMode,
  };

  if (scope === "radar.Chile") {
    return {
      ...shared,
      keywords: ["satelital", "internet", "conectividad", "LEO", "GEO", "firewall", "Starlink"],
      appliedMonths: ["8", "9", "10", "7", "6"],
      periodKeywordGroups: [
        { year: "2026", months: ["1", "2", "3", "4", "5", "6", "7"], keywords: ["satelital", "internet", "conectividad"], commercialMode: "all" },
        { year: "2026", months: ["6", "7"], keywords: ["Starlink"], commercialMode: "all" },
        { year: "2026", months: ["8", "9", "10"], keywords: ["LEO", "GEO"], commercialMode: "all" },
        { year: "2026", months: ["7"], keywords: ["firewall"], commercialMode: "active" },
      ],
      additionalPeriodKeywordGroups: [],
    };
  }

  if (scope === "ocds.Peru") {
    return {
      ...shared,
      keywords: [
        "satelital",
        "internet",
        "conectividad",
        "LEO",
        "CP-ABR-5-2026-MDL/DEC-1",
        "LP-SM-6-2026-GRA-SEDECENTRAL-1",
        "Starlink",
        "GEO",
      ],
      appliedMonths: ["7", "1", "2", "3", "4", "5", "6"],
      periodKeywordGroups: [
        { year: "2026", months: ["6", "7"], keywords: ["satelital", "internet", "conectividad", "LEO"], commercialMode: "all" },
        { year: "2026", months: ["6", "7"], keywords: ["Starlink"], commercialMode: "all" },
        { year: "2026", months: ["7"], keywords: ["capacidad"], commercialMode: "all" },
        { year: "2026", months: ["1", "2", "3", "4", "5", "6", "7"], keywords: ["GEO"], commercialMode: "active" },
        {
          year: "2026",
          months: ["6", "7"],
          keywords: [
            "ADQUISICIÓN E INSTALACIÓN A TODO COSTO DEL SISTEMA DE CONECTIVIDAD INFORMÁTICA Y SERVIDORES (TERCERA HABILITACIÓN), META 115: MEJORAMIENTO DEL SERVICIO DE FORMACIÓN PROFESIONAL EN LA ESCUELA DE MEDICINA HUMANA DE LA FACULTAD DE CIENCIAS DE LA SALUD DE LA UNSCH, DISTRITO DE AYACUCHO, PROVINCIA DE HUA",
            "SERVICIO DE CONECTIVIDAD DE DATOS (INTERNET Y L2L) Y TELEFONIA IP EN 17 MÓDULOS DESCENTRALIZADOS Y CIRCUITO DE FIBRA OPTICA (234 P2P) PARA TRANSPORTE DE CONTENIDO",
            "LEO",
          ],
          commercialMode: "active",
        },
      ],
      additionalPeriodKeywordGroups: [
        { year: "2026", months: ["7"], keywords: ["capacidad"], commercialMode: "all", processCount: 0 },
      ],
    };
  }

  return null;
}

export function shouldSeedPublishedOpportunityState(scope: string) {
  void scope;
  return false;
}

export function normalizeActiveSearchState(value: unknown): SavedOpportunityViewState {
  const defaults = defaultOpportunityViewState();
  try {
    if (!value) return defaults;
    const parsed = (typeof value === "string" ? JSON.parse(value) : value) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object") return defaults;
    const hasSavedKeywords = Array.isArray(parsed.keywords);
    const rawKeywords: unknown[] = hasSavedKeywords ? parsed.keywords as unknown[] : [];
    const keywords = uniqueKeywords(rawKeywords.filter((item): item is string => typeof item === "string" && item.trim().length > 0));
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
              ? uniqueKeywords(group.keywords.filter((value): value is string => typeof value === "string" && value.trim().length > 0))
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
    const savedAdditionalPeriodKeywordGroups = Array.isArray(parsed.additionalPeriodKeywordGroups)
      ? parsed.additionalPeriodKeywordGroups.flatMap((item) => {
          if (!item || typeof item !== "object") return [];
          const group = item as Record<string, unknown>;
          if (typeof group.year !== "string") return [];
          return [{
            year: group.year,
            months: Array.isArray(group.months) ? group.months.filter((value): value is string => typeof value === "string") : [],
            keywords: Array.isArray(group.keywords) ? uniqueKeywords(group.keywords.filter((value): value is string => typeof value === "string")) : [],
            commercialMode: "all" as MaxResultsMode,
            processCount: typeof group.processCount === "number" && Number.isFinite(group.processCount) ? group.processCount : undefined,
            opportunityIds: Array.isArray(group.opportunityIds)
              ? group.opportunityIds.filter((value): value is number => typeof value === "number" && Number.isFinite(value))
              : undefined,
          }];
        })
      : [];
    const searchMode = ["append", "replace"].includes(String(parsed.searchMode))
      ? parsed.searchMode as SearchMode
      : defaults.searchMode;
    return {
      keywords: activeKeywords,
      runIds,
      keyword: savedDraftKeywords[0] || activeKeywords[0] || defaults.keyword,
      keyword2: savedDraftKeywords[1] || activeKeywords[1] || "",
      keyword3: savedDraftKeywords[2] || activeKeywords[2] || "",
      nomenclatureFilter: typeof parsed.nomenclatureFilter === "string" ? parsed.nomenclatureFilter : "",
      entityFilter: typeof parsed.entityFilter === "string" ? parsed.entityFilter : "",
      entityKeyword: typeof parsed.entityKeyword === "string" ? parsed.entityKeyword : "",
      entityKeyword2: typeof parsed.entityKeyword2 === "string" ? parsed.entityKeyword2 : "",
      entityKeyword3: typeof parsed.entityKeyword3 === "string" ? parsed.entityKeyword3 : "",
      publicationDateFrom: typeof parsed.publicationDateFrom === "string" ? parsed.publicationDateFrom : "",
      publicationDateTo: typeof parsed.publicationDateTo === "string" ? parsed.publicationDateTo : "",
      years,
      months,
      appliedYears,
      appliedMonths,
      periodKeywordGroups,
      additionalPeriodKeywordGroups: savedAdditionalPeriodKeywordGroups,
      maxResultsMode,
      searchMode,
    };
  } catch {
    return defaults;
  }
}

export function loadActiveSearchState(scope: string, fallbackScope?: string): SavedOpportunityViewState {
  try {
    const raw = window.localStorage.getItem(activeSearchStorageKey(scope))
      || (fallbackScope ? window.localStorage.getItem(activeSearchStorageKey(fallbackScope)) : null);
    return normalizeActiveSearchState(raw);
  } catch {
    return defaultOpportunityViewState();
  }
}

export function opportunityViewStateRichness(state: SavedOpportunityViewState) {
  const groups = [...state.periodKeywordGroups, ...state.additionalPeriodKeywordGroups];
  const opportunityIds = new Set(groups.flatMap((group) => group.opportunityIds || []));
  const explicitProcessCount = groups.reduce((total, group) => total + Math.max(0, group.processCount || 0), 0);
  const configuredPeriods = groups.reduce((total, group) => total + group.months.length, 0);
  return opportunityIds.size * 100_000
    + explicitProcessCount * 1_000
    + state.runIds.length * 100
    + groups.length * 10
    + configuredPeriods
    + state.keywords.length;
}

export function saveActiveSearchState(scope: string, state: SavedOpportunityViewState) {
  try {
    window.localStorage.setItem(activeSearchStorageKey(scope), JSON.stringify(state));
  } catch {
    // Local persistence is a convenience; the backend remains the source of truth.
  }
}

export function periodFiltersFromRuns(runs: Run[], runIds: number[]) {
  const selectedIds = new Set(runIds);
  const years = new Set<string>();
  const months = new Set<string>();
  runs.forEach((run) => {
    if (!selectedIds.has(run.id) || isProcessActionRun(run)) return;
    const period = periodPartsFromRun(run);
    period.years.forEach((value) => years.add(value));
    period.months.forEach((value) => months.add(value));
  });
  return {
    years: [...years].sort((left, right) => Number(right) - Number(left)),
    months: [...months].sort((left, right) => Number(left) - Number(right)),
  };
}

export function periodPartsFromRun(run: Run) {
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

export function periodKeywordGroupsFromRuns(
  runs: Run[],
  runIds: number[],
  fallbackMode: MaxResultsMode = "active",
): ActivePeriodKeywordGroup[] {
  const selectedIds = new Set(runIds);
  const groups = new Map<string, ActivePeriodKeywordGroup>();
  runs.forEach((run) => {
    if (!selectedIds.has(run.id) || isProcessActionRun(run)) return;
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

export function periodKeywordGroupsForSelection(
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

export function periodGroupKey(group: ActivePeriodKeywordGroup) {
  return `${group.year}|${uniqueDefined(group.months).sort((left, right) => Number(left) - Number(right)).join(",")}|${group.commercialMode}|${uniqueKeywords(group.keywords).map(normalizedSearchTerm).sort().join(",")}`;
}

export function processCountLabel(count: number) {
  return `${count} ${count === 1 ? "Proceso" : "Procesos"}`;
}

export function inferAdditionalRunCount(group: ActivePeriodKeywordGroup, runs: Run[]) {
  const groupKeywords = new Set(group.keywords.map(normalizedSearchTerm));
  const latestByKeyword = new Map<string, Run>();
  runs
    .filter((run) => commercialModeFromRun(run, "active") === "all")
    .filter((run) => {
      const period = periodPartsFromRun(run);
      return period.years.includes(group.year) && group.months.some((month) => period.months.includes(month));
    })
    .sort((left, right) => right.id - left.id)
    .forEach((run) => {
      const keyword = normalizedSearchTerm(keywordFromRun(run));
      if (groupKeywords.has(keyword) && !latestByKeyword.has(keyword)) latestByKeyword.set(keyword, run);
    });
  return [...latestByKeyword.values()].reduce((total, run) => total + Number(run.rows_found || 0), 0);
}

export function opportunityMatchesAdditionalGroup(item: Opportunity, group: ActivePeriodKeywordGroup, runs: Run[]) {
  if (group.opportunityIds) return group.opportunityIds.includes(item.id);
  if ((group.processCount ?? inferAdditionalRunCount(group, runs)) === 0) return false;
  return opportunityMatchesPeriodGroup(item, group);
}

export function mergePeriodKeywordGroups(...collections: ActivePeriodKeywordGroup[][]) {
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

export function commercialModeOrder(mode: MaxResultsMode) {
  return mode === "all" ? 0 : 1;
}

export function commercialModeFromRun(run: Run, fallbackMode: MaxResultsMode) {
  const value = String(run.diagnostics || "").match(/semaforo\s*=\s*(active|all)/i)?.[1]?.toLowerCase();
  return value === "all" || value === "active" ? value as MaxResultsMode : fallbackMode;
}

export function opportunityMatchesPeriodGroup(item: Opportunity, group: ActivePeriodKeywordGroup) {
  const isChile = sourceBelongsToCountry(item.source, "Chile");
  const timestamp = isChile
    ? parseDate(presentationDeadline(item)) ?? parseDate(item.publication_date)
    : parseDate(item.publication_date) ?? parseDate(presentationDeadline(item));
  if (timestamp === null) return false;
  const date = new Date(timestamp);
  if (String(date.getFullYear()) !== group.year || !group.months.includes(String(date.getMonth() + 1))) return false;
  const haystack = `${item.entity} ${item.nomenclature} ${item.description}`;
  const keywordMatch = !group.keywords.length || group.keywords.some((keyword) => matchesCompletePhrase(haystack, keyword));
  const commercialMatch = group.commercialMode === "all" || commercialSignal(item).className !== "red";
  return keywordMatch && commercialMatch;
}

export function normalizedKeywordSet(keywords: string[]) {
  return new Set(keywords.map(normalizedSearchTerm));
}

export function isKeywordSubset(left: Set<string>, right: Set<string>) {
  return Array.from(left).every((keyword) => right.has(keyword));
}

export function monthLabels(months: string[]) {
  return months.map((value) => monthOptions.find(([month]) => month === value)?.[1].slice(0, 3) || value);
}

export function isProcessActionRun(run: Run) {
  return /max_detalles\s*=\s*12(?:\D|$)/i.test(String(run.diagnostics || ""));
}

export function ArchivedProcesses({
  country,
  token,
  onRestored,
}: {
  country: Country;
  token: string;
  onRestored: () => Promise<void>;
}) {
  const [rows, setRows] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const countryCode = country === "Chile" ? "chile" : "peru";

  async function loadArchived() {
    setLoading(true);
    setError("");
    try {
      setRows(await api.archivedOpportunities(token, countryCode));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudo cargar el histórico");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadArchived();
  }, [token, countryCode]);

  async function restoreProcess(item: Opportunity) {
    await api.restoreOpportunity(token, item.id);
    setRows((current) => current.filter((row) => row.id !== item.id));
    await onRestored();
  }

  return (
    <section className="panel archived-processes-panel">
      <div className="panel-title archived-processes-heading">
        <div>
          <h2>Histórico Procesos Eliminados {country === "Chile" ? "CL" : "PE"}</h2>
          <p>Respaldo permanente de decisiones comerciales. Estas nomenclaturas no ingresarán en actualizaciones automáticas mientras permanezcan aquí.</p>
        </div>
        <button className="ghost" type="button" onClick={loadArchived} disabled={loading}>
          {loading ? "Actualizando..." : "Actualizar"}
        </button>
      </div>
      <div className="archive-summary" role="status">
        <span className="archive-summary-icon" aria-hidden="true">↺</span>
        <div>
          <strong>{rows.length} {rows.length === 1 ? "proceso respaldado" : "procesos respaldados"}</strong>
          <span>Usa “Regresar al módulo Oportunidades” si el retiro fue un error.</span>
        </div>
      </div>
      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {loading && !rows.length ? <Empty text="Cargando procesos retirados..." /> : (
        <OpportunityTable
          rows={rows}
          country={country}
          token={token}
          resetKey={`archived:${countryCode}`}
          onRevalidateProposal={async () => false}
          highlightTerms={[]}
          actionMode="restore"
          onProcessAction={restoreProcess}
          allowRevalidation={false}
        />
      )}
    </section>
  );
}

export function OpportunityTable({
  rows,
  country,
  token,
  resetKey,
  onRevalidateProposal,
  highlightTerms,
  actionMode = "archive",
  onProcessAction,
  allowRevalidation = true,
}: {
  rows: Opportunity[];
  country: Country;
  token: string;
  resetKey: string;
  onRevalidateProposal: (item: Opportunity) => Promise<boolean>;
  highlightTerms: string[];
  actionMode?: "archive" | "restore";
  onProcessAction: (item: Opportunity) => Promise<void>;
  allowRevalidation?: boolean;
}) {
  const [commercialFilter, setCommercialFilter] = useState<CommercialClass | null>(null);
  const [columnFilters, setColumnFilters] = useState<TableColumnFilters>(emptyTableColumnFilters);
  const [countdownNow, setCountdownNow] = useState(() => Date.now());
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<Opportunity | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [revalidatingIds, setRevalidatingIds] = useState<Set<number>>(new Set());
  const [unavailableProposalIds, setUnavailableProposalIds] = useState<Set<number>>(new Set());
  const [manualProposalUpdates, setManualProposalUpdates] = useState<Map<number, string>>(new Map());
  const topScrollRef = useRef<HTMLDivElement | null>(null);
  const tableScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setPendingRemoval(null);
    setActionError("");
    setUnavailableProposalIds(new Set());
    setManualProposalUpdates(new Map());
    setColumnFilters(emptyTableColumnFilters);
  }, [resetKey]);

  useEffect(() => {
    const timer = window.setInterval(() => setCountdownNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const rowsWithSignals = useMemo(
    () => rows.map((item) => ({ item, signal: commercialSignal(item) })),
    [rows],
  );

  const filteredRows = useMemo(() => {
    const numericMatch = (value: number | null, minimum: string, maximum: string) => value !== null
      && (!minimum || value >= Number(minimum)) && (!maximum || value <= Number(maximum));
    const dateMatch = (value: string | null, from: string, to: string) => {
      if (!from && !to) return true;
      const timestamp = parseDate(value);
      if (timestamp === null) return false;
      const start = from ? new Date(`${from}T00:00:00`).getTime() : null;
      const end = to ? new Date(`${to}T23:59:59.999`).getTime() : null;
      return (start === null || timestamp >= start) && (end === null || timestamp <= end);
    };
    const entityNeedle = normalizedSearchTerm(columnFilters.entity);
    const processNeedle = normalizedSearchTerm(columnFilters.process);
    const descriptionNeedle = normalizedSearchTerm(columnFilters.description);
    return rowsWithSignals.filter(({ item, signal }) => {
      if (commercialFilter && signal.className !== commercialFilter) return false;
      if (columnFilters.priority && item.priority.toUpperCase() !== columnFilters.priority) return false;
      if (entityNeedle && !normalizedSearchTerm(item.entity).includes(entityNeedle)) return false;
      if (processNeedle && !normalizedSearchTerm(item.nomenclature).includes(processNeedle)) return false;
      if (descriptionNeedle && !normalizedSearchTerm(item.description).includes(descriptionNeedle)) return false;
      if (!dateMatch(item.publication_date, columnFilters.publicationFrom, columnFilters.publicationTo)) return false;
      if (!dateMatch(item.consultation_deadline, columnFilters.consultationFrom, columnFilters.consultationTo)) return false;
      if ((columnFilters.consultationDaysMin || columnFilters.consultationDaysMax) && !numericMatch(remainingWholeDays(item.consultation_deadline, countdownNow), columnFilters.consultationDaysMin, columnFilters.consultationDaysMax)) return false;
      if (!dateMatch(presentationDeadline(item), columnFilters.proposalFrom, columnFilters.proposalTo)) return false;
      if ((columnFilters.proposalDaysMin || columnFilters.proposalDaysMax) && !numericMatch(remainingWholeDays(presentationDeadline(item), countdownNow), columnFilters.proposalDaysMin, columnFilters.proposalDaysMax)) return false;
      if (columnFilters.amountReserved) return !Number.isFinite(item.amount) || item.amount <= 0;
      return !(columnFilters.amountMin || columnFilters.amountMax) || numericMatch(item.amount, columnFilters.amountMin, columnFilters.amountMax);
    });
  }, [rowsWithSignals, commercialFilter, columnFilters, countdownNow]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((left, right) => {
      const commercialResult = commercialOrder(left.signal.className) - commercialOrder(right.signal.className);
      if (commercialResult !== 0) return commercialResult;
      const dateResult = compareValues(parseDate(left.item.publication_date), parseDate(right.item.publication_date));
      if (dateResult !== 0) return -dateResult;
      return right.item.id - left.item.id;
    });
  }, [filteredRows]);

  function updateColumnFilter(key: keyof TableColumnFilters, value: string | boolean) {
    setColumnFilters((current) => ({ ...current, [key]: value }));
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
    { green: 0, amber: 0, pending: 0, red: 0 },
  );

  function confirmRemove(item: Opportunity) {
    setPendingRemoval(item);
  }

  async function removePendingRow() {
    if (!pendingRemoval) return;
    setActionPending(true);
    setActionError("");
    try {
      await onProcessAction(pendingRemoval);
      setPendingRemoval(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "No se pudo completar la acción");
    } finally {
      setActionPending(false);
    }
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
          <button className="export-excel-button" type="button" onClick={() => void exportOpportunitiesToExcel(token, sortedRows, "Oportunidades GovRadar", country)}>
            <img src={excelLogoUrl} alt="" aria-hidden="true" loading="lazy" decoding="async" />
            <span>Exportar a Excel</span>
          </button>
        </div>
      </div>
      <p className="mobile-table-hint">Desliza horizontalmente para consultar todas las columnas.</p>
      <div className="table-scroll-top" ref={topScrollRef} onScroll={() => syncTableScroll("top")} aria-label="Desplazamiento horizontal de oportunidades">
        <div />
      </div>
      <div className="table-wrap" ref={tableScrollRef} onScroll={() => syncTableScroll("table")}>
        <table>
          <thead>
            <tr>
              <FilterTh label="Prioridad" active={Boolean(columnFilters.priority)} onClear={() => updateColumnFilter("priority", "")}>
                <label>Prioridad<select value={columnFilters.priority} onChange={(event) => updateColumnFilter("priority", event.target.value)}><option value="">Todas</option><option value="A">A</option><option value="B">B</option><option value="C">C</option></select></label>
              </FilterTh>
              <th><span className="plain-header">Semaforo<br />comercial</span></th>
              <FilterTh label="Entidad" active={Boolean(columnFilters.entity)} onClear={() => updateColumnFilter("entity", "")}>
                <label>Nombre de entidad<input value={columnFilters.entity} onChange={(event) => updateColumnFilter("entity", event.target.value)} placeholder="Escribir entidad" /></label>
              </FilterTh>
              <FilterTh label="Proceso" active={Boolean(columnFilters.process)} onClear={() => updateColumnFilter("process", "")}>
                <label>Nomenclatura<input value={columnFilters.process} onChange={(event) => updateColumnFilter("process", event.target.value)} placeholder="Escribir proceso" /></label>
              </FilterTh>
              <th><span className="plain-header">Documentos</span></th>
              <FilterTh label="Descripcion" active={Boolean(columnFilters.description)} onClear={() => updateColumnFilter("description", "")}>
                <label>Descripción<input value={columnFilters.description} onChange={(event) => updateColumnFilter("description", event.target.value)} placeholder="Escribir descripción" /></label>
              </FilterTh>
              <FilterTh label="Fecha de\nconvocatoria" active={Boolean(columnFilters.publicationFrom || columnFilters.publicationTo)} onClear={() => setColumnFilters((current) => ({ ...current, publicationFrom: "", publicationTo: "" }))}>
                <DateRangeFilter from={columnFilters.publicationFrom} to={columnFilters.publicationTo} onFromChange={(value) => updateColumnFilter("publicationFrom", value)} onToChange={(value) => updateColumnFilter("publicationTo", value)} />
              </FilterTh>
              <FilterTh label="Fin\nConsultas" active={Boolean(columnFilters.consultationFrom || columnFilters.consultationTo)} onClear={() => setColumnFilters((current) => ({ ...current, consultationFrom: "", consultationTo: "" }))}>
                <DateRangeFilter from={columnFilters.consultationFrom} to={columnFilters.consultationTo} onFromChange={(value) => updateColumnFilter("consultationFrom", value)} onToChange={(value) => updateColumnFilter("consultationTo", value)} />
              </FilterTh>
              <FilterTh label="Dias\nConsultas" active={Boolean(columnFilters.consultationDaysMin || columnFilters.consultationDaysMax)} onClear={() => setColumnFilters((current) => ({ ...current, consultationDaysMin: "", consultationDaysMax: "" }))}>
                <NumberRangeFilter unit="días" minimum={columnFilters.consultationDaysMin} maximum={columnFilters.consultationDaysMax} onMinimumChange={(value) => updateColumnFilter("consultationDaysMin", value)} onMaximumChange={(value) => updateColumnFilter("consultationDaysMax", value)} />
              </FilterTh>
              <FilterTh label="Fin\nPropuesta" active={Boolean(columnFilters.proposalFrom || columnFilters.proposalTo)} onClear={() => setColumnFilters((current) => ({ ...current, proposalFrom: "", proposalTo: "" }))}>
                <DateRangeFilter from={columnFilters.proposalFrom} to={columnFilters.proposalTo} onFromChange={(value) => updateColumnFilter("proposalFrom", value)} onToChange={(value) => updateColumnFilter("proposalTo", value)} />
              </FilterTh>
              <FilterTh label="Dias\nPropuesta" active={Boolean(columnFilters.proposalDaysMin || columnFilters.proposalDaysMax)} onClear={() => setColumnFilters((current) => ({ ...current, proposalDaysMin: "", proposalDaysMax: "" }))}>
                <NumberRangeFilter unit="días" minimum={columnFilters.proposalDaysMin} maximum={columnFilters.proposalDaysMax} onMinimumChange={(value) => updateColumnFilter("proposalDaysMin", value)} onMaximumChange={(value) => updateColumnFilter("proposalDaysMax", value)} />
              </FilterTh>
              <FilterTh label="Monto" align="right" active={Boolean(columnFilters.amountMin || columnFilters.amountMax || columnFilters.amountReserved)} onClear={() => setColumnFilters((current) => ({ ...current, amountMin: "", amountMax: "", amountReserved: false }))}>
                <NumberRangeFilter unit="soles o pesos" minimum={columnFilters.amountMin} maximum={columnFilters.amountMax} disabled={columnFilters.amountReserved} onMinimumChange={(value) => updateColumnFilter("amountMin", value)} onMaximumChange={(value) => updateColumnFilter("amountMax", value)} />
                <label className="reserved-amount-filter"><input type="checkbox" checked={columnFilters.amountReserved} onChange={(event) => setColumnFilters((current) => ({ ...current, amountReserved: event.target.checked, amountMin: event.target.checked ? "" : current.amountMin, amountMax: event.target.checked ? "" : current.amountMax }))} /><span>Monto reservado</span></label>
              </FilterTh>
            </tr>
          </thead>
          <tbody>
            {sortedRows.slice(0, 100).map(({ item, signal }) => (
              <OpportunityRow
                item={item}
                signal={signal}
                country={country}
                key={item.id}
                onOpenDocuments={setSelectedOpportunity}
                onRemove={confirmRemove}
                actionMode={actionMode}
                allowRevalidation={allowRevalidation}
                onRevalidateProposal={revalidateRow}
                isRevalidating={revalidatingIds.has(item.id)}
                proposalUnavailable={unavailableProposalIds.has(item.id)}
                highlightTerms={highlightTerms}
                manualProposalUpdatedAt={manualProposalUpdates.get(item.id) || null}
                countdownNow={countdownNow}
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
          title={actionMode === "archive" ? "Retirar de esta vista" : "Regresar al módulo Oportunidades"}
          message={actionMode === "archive"
            ? "¿Está seguro de retirar este proceso? Se moverá al histórico y quedará excluido de las actualizaciones automáticas."
            : "¿Está seguro de regresar este proceso al módulo Oportunidades? Volverá a participar en las actualizaciones automáticas."}
          confirmLabel={actionPending ? "Procesando..." : actionMode === "archive" ? "Sí, retirar" : "Sí, regresar"}
          cancelLabel="No"
          onConfirm={removePendingRow}
          onCancel={() => setPendingRemoval(null)}
        />
      ) : null}
      {actionError ? <div className="notice danger archive-action-notice" role="alert">{actionError}</div> : null}
    </>
  );
}

export function FilterTh({ label, active, onClear, align = "left", children }: {
  label: string;
  active: boolean;
  onClear: () => void;
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  const labelParts = label.split(/\\n|\n/);
  return (
    <th className="filter-table-header">
      <div className="filter-header">
        <span>{labelParts.map((part, index) => <React.Fragment key={`${part}-${index}`}>{part}{index < labelParts.length - 1 ? <br /> : null}</React.Fragment>)}</span>
        <details className={`column-filter ${active ? "active" : ""} ${align === "right" ? "align-right" : ""}`}>
          <summary
            aria-label={`Filtrar por ${label.replace("\\n", " ")}`}
            title={`Filtrar por ${label.replace("\\n", " ")}`}
            onClick={(event) => {
              const current = event.currentTarget.closest("details");
              document.querySelectorAll<HTMLDetailsElement>("details.column-filter[open]").forEach((details) => {
                if (details !== current) details.removeAttribute("open");
              });
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="5.75" /><path d="m15 15 4.25 4.25" /></svg>
          </summary>
          <div className="column-filter-panel">
            {children}
            {active ? <button className="column-filter-clear" type="button" onClick={(event) => { onClear(); event.currentTarget.closest("details")?.removeAttribute("open"); }}>Limpiar filtro</button> : null}
          </div>
        </details>
      </div>
    </th>
  );
}

export function DateRangeFilter({ from, to, onFromChange, onToChange }: { from: string; to: string; onFromChange: (value: string) => void; onToChange: (value: string) => void }) {
  return <div className="column-filter-fields"><label>Desde<input type="date" value={from} onChange={(event) => onFromChange(event.target.value)} /></label><label>Hasta<input type="date" value={to} min={from || undefined} onChange={(event) => onToChange(event.target.value)} /></label></div>;
}

export function NumberRangeFilter({ unit, minimum, maximum, disabled = false, onMinimumChange, onMaximumChange }: { unit: string; minimum: string; maximum: string; disabled?: boolean; onMinimumChange: (value: string) => void; onMaximumChange: (value: string) => void }) {
  return <div className="column-filter-fields"><span className="column-filter-unit">Rango en {unit}</span><label>Desde<input type="number" value={minimum} disabled={disabled} onChange={(event) => onMinimumChange(event.target.value)} placeholder="Mínimo" /></label><label>Hasta<input type="number" value={maximum} disabled={disabled} min={minimum || undefined} onChange={(event) => onMaximumChange(event.target.value)} placeholder="Máximo" /></label></div>;
}

export function OpportunityRow({
  item,
  signal,
  country,
  onOpenDocuments,
  onRemove,
  onRevalidateProposal,
  isRevalidating,
  proposalUnavailable,
  highlightTerms,
  manualProposalUpdatedAt,
  countdownNow,
  actionMode,
  allowRevalidation,
}: {
  item: Opportunity;
  signal: ReturnType<typeof commercialSignal>;
  country: Country;
  onOpenDocuments: (item: Opportunity) => void;
  onRemove: (item: Opportunity) => void;
  onRevalidateProposal: (item: Opportunity) => Promise<void>;
  isRevalidating: boolean;
  proposalUnavailable: boolean;
  highlightTerms: string[];
  manualProposalUpdatedAt: string | null;
  countdownNow: number;
  actionMode: "archive" | "restore";
  allowRevalidation: boolean;
}) {
  const proposalDeadline = presentationDeadline(item);
  const isLargePurchase = item.source.toLowerCase() === "mercado_publico_grandes_compras";
  const isNewOpportunity = isOpportunityNew(item);
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
          <div className="process-identifier">
            <span>{item.nomenclature}</span>
            {isNewOpportunity ? (
              <span className="new-opportunity-badge" title="Proceso incorporado a GovRadar durante los últimos 7 días" aria-label="Proceso nuevo">
                NEW
              </span>
            ) : null}
            {isLargePurchase ? <span className="large-purchase-badge" title="Gran Compra">GC</span> : null}
          </div>
          <button className={`remove-view-button ${actionMode === "restore" ? "restore-view-button" : ""}`} type="button" onClick={() => onRemove(item)}>
            {actionMode === "restore" ? "Regresar al módulo Oportunidades" : "Retirar de esta vista"}
          </button>
        </div>
      </td>
      <td>
        <button className="pdf-button" onClick={() => onOpenDocuments(item)} title="Ver detalle y documentos">
          <span>PDF</span>
        </button>
      </td>
      <td><HighlightedText text={item.description} terms={highlightTerms} /></td>
      <td>{formatDate(item.publication_date)}</td>
      <td>
        {item.consultation_deadline ? formatDate(item.consultation_deadline) : country === "Chile" && signal.className === "red" && allowRevalidation ? (
          proposalUnavailable ? (
            <span className="proposal-unavailable">Fecha no disponible en Mercado Público</span>
          ) : (
            <button className="revalidate-button chile-revalidate-button" type="button" disabled={isRevalidating} onClick={() => onRevalidateProposal(item)}>
              {isRevalidating ? (
                <>
                  <span className="button-spinner compact" aria-hidden="true" />
                  <span>Consultando ML CL</span>
                </>
              ) : (
                "Revalidar fecha de fin de proceso en ML CL"
              )}
            </button>
          )
        ) : "-"}
      </td>
      <td>{formatDeadlineCountdown(item.consultation_deadline, countdownNow)}</td>
      <td>
        {proposalDeadline ? (
          manualProposalUpdatedAt ? (
            <span className="manual-proposal-date">
              <b>{formatDate(proposalDeadline)}</b>
              <small>*Actualizado manual desde {country === "Chile" ? "Mercado Público" : "Seace"} ({formatManualTimestamp(manualProposalUpdatedAt)})</small>
            </span>
          ) : (
            formatDate(proposalDeadline)
          )
        ) : country === "Chile" || !allowRevalidation ? (
          "-"
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
      <td>{formatDeadlineCountdown(proposalDeadline, countdownNow)}</td>
      <td>{formatMoney(item.amount, sourceBelongsToCountry(item.source, "Chile") ? "Chile" : "Peru")}</td>
    </tr>
  );
}

export function isOpportunityNew(item: Pick<Opportunity, "is_new">) {
  return item.is_new;
}

export function OpportunityDetailModal({
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
  const emptyDocumentsText = sourceBelongsToCountry(opportunity.source, "Chile")
    ? "Aun no hay documentos registrados. Usa Buscar documentos para consultar MercadoPublico.cl desde backend."
    : "Aun no hay documentos registrados. Usa Buscar documentos para consultar SEACE desde backend.";
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
        <div className="modal-body" tabIndex={0} aria-label="Contenido desplazable del detalle del proceso">
          <article className="detail-card">
            <div className="detail-card-title">Informacion general</div>
            <div className="detail-grid">
              <span>Proceso</span><strong>{opportunity.nomenclature || "-"}</strong>
              <span>Fecha</span><strong>{formatDate(opportunity.publication_date)}</strong>
              <span>Entidad</span><strong>{opportunity.entity || "-"}</strong>
              <span>Monto</span><strong>{formatMoney(opportunity.amount, sourceBelongsToCountry(opportunity.source, "Chile") ? "Chile" : "Peru")}</strong>
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
                <Empty text={emptyDocumentsText} />
              ) : null}
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}

export function remainingWholeDays(value: string | null, now: number) {
  const timestamp = parseDate(value);
  if (timestamp === null) return null;
  return Math.max(0, Math.floor((timestamp - now) / (24 * 60 * 60 * 1000)));
}

export function formatDeadlineCountdown(value: string | null, now: number) {
  const timestamp = parseDate(value);
  if (timestamp === null) return "-";
  const difference = timestamp - now;
  const expired = difference < 0;
  const totalHours = Math.floor(Math.abs(difference) / (60 * 60 * 1000));
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  const urgency = expired ? "expired" : days <= 3 ? "urgent" : days <= 7 ? "warning" : "safe";
  const dayLabel = days === 1 ? "día" : "días";
  const expiredLabel = totalHours < 24
    ? `Fuera de Plazo hace ${totalHours} ${totalHours === 1 ? "hora" : "horas"}`
    : `Fuera de Plazo hace ${days} ${dayLabel}`;
  return (
    <strong className={`deadline-countdown ${urgency}`} title={formatDate(value)}>
      {expired ? expiredLabel : `${days} ${dayLabel} ${hours} h para fin`}
    </strong>
  );
}

export function commercialOrder(value: CommercialClass) {
  return value === "green" ? 1 : value === "amber" ? 2 : 3;
}

export function compareValues(left: string | number | null, right: string | number | null) {
  if (left === null && right === null) return 0;
  if (left === null) return -1;
  if (right === null) return 1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), "es", { numeric: true, sensitivity: "base" });
}

export default Opportunities;
