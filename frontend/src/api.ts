export function chileStatusSlug(status: string): string {
  const match = status.toLowerCase().match(/[a-z]+/);
  return match ? match[0] : "";
}

export type Stats = {
  total: number;
  by_source: Record<string, number>;
  by_priority: Record<string, number>;
  by_region: Record<string, number>;
  vigentes: number;
  cerrados: number;
  total_amount: number;
  with_ruc: number;
  with_region: number;
  ocds_total: number;
  documents_known: number;
};

export type Opportunity = {
  id: number;
  source: string;
  external_id: string;
  entity: string;
  nomenclature: string;
  object_type: string;
  description: string;
  record_type: string;
  expediente: string;
  contracting_unit: string;
  financial_service: string;
  region: string;
  buyer_ruc: string;
  ocid: string;
  tender_id: string;
  ocds_source_id: string;
  release_id: string;
  documents_count: number;
  amount: number;
  currency: string;
  status: string;
  source_status: string;
  contract_duration: string;
  priority: string;
  score: number;
  reasons: string;
  detail_url: string;
  requirement_pdf_url: string;
  requirement_pdf_local: string;
  publication_date: string | null;
  opening_date: string | null;
  consultation_deadline: string | null;
  quote_deadline: string | null;
  proposal_deadline: string | null;
  schedule_source: string;
  schedule_validated_at: string | null;
  is_archived: boolean;
  archived_at: string | null;
  archived_by_id: number | null;
  archive_country: string;
  archive_reason: string;
  is_new: boolean;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: number;
  source: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  rows_found: number;
  progress: number;
  progress_message: string;
  cancel_requested: boolean;
  diagnostics: string;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type CountryCode = "peru" | "chile" | "argentina";

export type SchedulerStatus = {
  enabled: boolean;
  country: CountryCode;
  is_running: boolean;
  next_update_at: string | null;
  interval_minutes: number;
  interval_seconds: number;
};

export type SchedulerIntervalConfig = {
  country: CountryCode;
  days: number;
  hours: number;
  minutes: number;
  interval_seconds: number;
  next_update_at: string | null;
  enabled: boolean;
};

export type TrackingDateRefreshChange = {
  field: string;
  label: string;
  old: string | null;
  new: string | null;
};

export type TrackingDateRefreshedOpportunity = {
  opportunity_id: number;
  entity: string;
  nomenclature: string;
  changes: TrackingDateRefreshChange[];
};

export type TrackingDateRefreshLastRun = {
  ran_at: string | null;
  checked: number;
  changed: TrackingDateRefreshedOpportunity[];
  errors: number;
};

export type TrackingDateRefreshStatus = {
  days: number;
  hours: number;
  minutes: number;
  interval_seconds: number;
  next_update_at: string | null;
  enabled: boolean;
  last_run: TrackingDateRefreshLastRun | null;
};

export type AlertRule = {
  id: number;
  name: string;
  channel: string;
  destination: string;
  keywords: string;
  min_priority: string;
  country: CountryCode | "both";
  is_active: boolean;
};

export type AlertRulePayload = Omit<AlertRule, "id">;

export type Alert = {
  id: number;
  opportunity_id: number;
  rule_id: number;
  alert_type: string;
  status: string;
  message: string;
  attempt_count: number;
  next_attempt_at: string | null;
  last_attempt_at: string | null;
  last_error: string;
  provider_message_id: string;
  sent_at: string | null;
  created_at: string;
  country: CountryCode;
  channel: string;
  entity: string;
  description: string;
  destination: string;
  keywords: string;
  run_id: number | null;
  rule_is_active: boolean;
};

export type DocumentRecord = {
  id: number;
  opportunity_id: number | null;
  title: string;
  document_type: string;
  source_url: string;
  filename: string;
  mime_type: string;
  status: string;
  error_message: string;
  created_at: string;
};

export type OpportunityViewStateRecord = {
  scope: string;
  state: Record<string, unknown>;
  updated_at: string;
};

// Comma-separated subset of CountryCode, e.g. "peru,chile". "both" is the
// legacy all-countries value predating Argentina support, still accepted
// for backward compatibility - see parseAccessProfile/formatAccessProfile.
export type AccessProfile = string;

const ACCESS_PROFILE_COUNTRIES: CountryCode[] = ["peru", "chile", "argentina"];

export function parseAccessProfile(profile: AccessProfile): CountryCode[] {
  if (profile === "both") return [...ACCESS_PROFILE_COUNTRIES];
  const selected = new Set(profile.split(",").map((value) => value.trim()));
  return ACCESS_PROFILE_COUNTRIES.filter((country) => selected.has(country));
}

export function formatAccessProfile(countries: CountryCode[]): AccessProfile {
  const selected = new Set(countries);
  return ACCESS_PROFILE_COUNTRIES.filter((country) => selected.has(country)).join(",");
}

// Product modules, independent of the per-country access_profile. Admins
// always reach every module (the backend's require_module enforces it too).
export type AppModule = "radar" | "historico_peru";
export type ModuleAccess = string;
export const APP_MODULES: AppModule[] = ["radar", "historico_peru"];

export function parseModuleAccess(value: ModuleAccess | undefined | null): AppModule[] {
  const selected = new Set((value || "").split(",").map((item) => item.trim()));
  return APP_MODULES.filter((module) => selected.has(module));
}

export function formatModuleAccess(modules: AppModule[]): ModuleAccess {
  const selected = new Set(modules);
  return APP_MODULES.filter((module) => selected.has(module)).join(",");
}

export type UserRecord = {
  id: number;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  position: string;
  address: string;
  phone_peru: string;
  phone_chile: string;
  phone_argentina: string;
  access_profile: AccessProfile;
  module_access: ModuleAccess;
  historico_digest: boolean;
  role: "viewer" | "admin";
  is_active: boolean;
  created_at: string;
};

export type UserCreatePayload = {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  position: string;
  address: string;
  phone_peru: string;
  phone_chile: string;
  phone_argentina: string;
  access_profile: AccessProfile;
  module_access: ModuleAccess;
  historico_digest: boolean;
  role: "viewer" | "admin";
};

export type RadarKeyword = {
  id: number | null;
  country: CountryCode;
  keyword: string;
};

export type LegalDocumentKey = "terms" | "privacy" | "confidentiality";

export type LegalDocumentRecord = {
  key: LegalDocumentKey;
  title: string;
  content: string;
  updated_at: string;
};

export type TenantBrandRecord = {
  name: string;
  logoUrl: string;
  primary: string;
  updated_at: string | null;
};

export type AppSettingsRecord = {
  version_label: string;
  updated_at: string | null;
};

export type CountryScope = CountryCode | "ambos";

export type TrackingArea = {
  id: number;
  key: string;
  name: string;
  sort_order: number;
  is_active: boolean;
};

export type TrackingAreaPayload = {
  name: string;
  sort_order?: number;
  is_active?: boolean;
};

export type TrackingResponsible = {
  id: number;
  full_name: string;
  email: string;
  country_scope: CountryScope;
  is_active: boolean;
  areas: TrackingArea[];
};

export type TrackingResponsiblePayload = {
  full_name: string;
  email: string;
  country_scope: CountryScope;
  is_active: boolean;
  area_ids: number[];
};

export type TrackingPhase = {
  id: number;
  country: CountryCode;
  key: string;
  name: string;
  sort_order: number;
};

export type TrackingStageTemplate = {
  id: number;
  phase_id: number;
  name: string;
  sort_order: number;
  is_active: boolean;
  is_outcome_step: boolean;
  is_informational: boolean;
  default_duration_days: number | null;
  areas: TrackingArea[];
};

export type TrackingStageTemplatePayload = {
  name?: string;
  sort_order?: number;
  is_active?: boolean;
  is_outcome_step?: boolean;
  is_informational?: boolean;
  default_duration_days?: number | null;
  area_ids?: number[];
};

export type OpportunityTrackingStage = {
  id: number;
  phase_id: number;
  stage_template_id: number | null;
  name: string;
  sort_order: number;
  is_outcome_step: boolean;
  is_informational: boolean;
  due_date: string | null;
  completed: boolean;
  completed_at: string | null;
  status: "pendiente" | "en_progreso" | "completado" | "bloqueado" | string;
  outcome: "" | "ganado" | "perdido" | "pendiente";
  alert_atender_enabled: boolean;
  alert_urgente_enabled: boolean;
  areas: TrackingArea[];
  assignees: TrackingResponsible[];
};

export type OpportunityTracking = {
  id: number;
  opportunity_id: number;
  status: string;
  current_phase_id: number | null;
  quotation_outcome: "pendiente" | "ganado" | "perdido";
  started_at: string;
  started_by_id: number | null;
  started_by_name: string;
  co_responsible_id: number | null;
  co_responsible_name: string;
  stages: OpportunityTrackingStage[];
};

export type AssignableUser = {
  id: number;
  full_name: string;
  access_profile: AccessProfile;
};

export type OpportunityTrackingSummary = {
  opportunity_id: number;
  entity: string;
  nomenclature: string;
  description: string;
  source: string;
  status: string;
  current_phase_id: number | null;
  current_stage_name: string;
  quotation_outcome: string;
  publication_date: string | null;
  proposal_deadline: string | null;
  quote_deadline: string | null;
  documents_count: number;
  requirement_pdf_url: string;
  started_by_id: number | null;
  started_by_name: string;
  co_responsible_id: number | null;
  co_responsible_name: string;
};

export type OpportunityReview = {
  opportunity_id: number;
  status: "standby" | "resolved";
};

export type OpportunityReviewComment = {
  id: number;
  author_id: number | null;
  author_name: string;
  comment: string;
  created_at: string;
};

export type OpportunityReviewDetail = {
  opportunity_id: number;
  status: "standby" | "resolved";
  comments: OpportunityReviewComment[];
};

export type ScoringFactor = { label: string; points: number; enabled: boolean; value: string; value_type: "list" | "number" | "text"; field: "description" | "entity" | "region" | "amount" | "origin" | "status" };
export type ScoringConfig = {
  country: CountryCode;
  priority_a_min: number;
  priority_b_min: number;
  attractive_amount_min: number;
  score_target: number;
  factors: Record<string, ScoringFactor>;
};

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;

// Called once from main.tsx so any expired/invalid token, from any API call
// through `request`, sends the user back to the login screen instead of
// leaving the UI stuck on failed requests.
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (response.status === 401 && token) {
    onUnauthorized?.();
  }
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = typeof parsed.detail === "string"
        ? parsed.detail
        : Array.isArray(parsed.detail)
          ? parsed.detail.map((item: { msg?: string }) => item.msg || "Dato invalido").join(". ")
          : body;
    } catch {
      // Preserve non-JSON backend responses.
    }
    throw new ApiError(detail || response.statusText, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new ApiError("Credenciales invalidas o backend no disponible", response.status);
  }
  return response.json() as Promise<{ access_token: string; token_type: string }>;
}

export async function requestPasswordReset(email: string) {
  return request<{ message: string }>("/auth/forgot-password", "", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export async function confirmPasswordReset(token: string, password: string) {
  return request<{ message: string }>("/auth/reset-password", "", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
}

export const api = {
  appSettings: () => request<AppSettingsRecord>("/app-settings", ""),
  tenantBrand: () => request<TenantBrandRecord>("/app-settings/brand", ""),
  updateTenantBrand: (token: string, brand: { name: string; logoUrl: string; primary: string }) =>
    request<TenantBrandRecord>("/app-settings/brand", token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(brand),
    }),
  updateAppSettings: (token: string, versionLabel: string) =>
    request<AppSettingsRecord>("/app-settings", token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_label: versionLabel }),
    }),
  scoringConfig: (token: string, country: CountryCode) =>
    request<ScoringConfig>(`/app-settings/scoring/${country}`, token),
  updateScoringConfig: (token: string, country: CountryCode, config: ScoringConfig) =>
    request<ScoringConfig>(`/app-settings/scoring/${country}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  legalDocuments: () => request<LegalDocumentRecord[]>("/legal-documents", ""),
  updateLegalDocument: (token: string, key: LegalDocumentKey, content: string) =>
    request<LegalDocumentRecord>(`/legal-documents/${key}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),
  me: (token: string) => request<UserRecord>("/auth/me", token),
  users: (token: string) => request<UserRecord[]>("/users", token),
  createUser: (token: string, payload: UserCreatePayload) =>
    request<UserRecord>("/users", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateUser: (token: string, userId: number, payload: Partial<UserCreatePayload> & { is_active?: boolean }) =>
    request<UserRecord>(`/users/${userId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  stats: (token: string) => request<Stats>("/opportunities/stats", token, { cache: "no-store" }),
  opportunities: (token: string, options: { runIds?: number[] } = {}) => {
    const params = new URLSearchParams();
    if (options.runIds?.length) {
      params.set("run_ids", options.runIds.join(","));
    }
    const query = params.toString();
    return request<Opportunity[]>(`/opportunities${query ? `?${query}` : ""}`, token, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
  },
  opportunityViewState: (token: string, scope: string) =>
    request<OpportunityViewStateRecord>(`/opportunity-view-states/${encodeURIComponent(scope)}`, token, { cache: "no-store" }),
  saveOpportunityViewState: (token: string, scope: string, state: object) =>
    request<OpportunityViewStateRecord>(`/opportunity-view-states/${encodeURIComponent(scope)}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state }),
    }),
  exportOpportunitiesXlsx: async (token: string, payload: { title: string; country: CountryCode; headers: string[]; rows: Array<Array<string | number | null>> }) => {
    const response = await fetch(`${API_URL}/opportunities/export/xlsx`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new ApiError("No se pudo generar el archivo Excel", response.status);
    return response.blob();
  },
  archivedOpportunities: (token: string, country: CountryCode) =>
    request<Opportunity[]>(`/opportunities/archived?country=${country}`, token),
  archiveOpportunity: (token: string, opportunityId: number, reason: string = "") =>
    request<Opportunity>(`/opportunities/${opportunityId}/archive`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  updateArchiveReason: (token: string, opportunityId: number, reason: string) =>
    request<Opportunity>(`/opportunities/${opportunityId}/archive-reason`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  archiveOpportunitiesByKeyword: (token: string, country: CountryCode, keyword: string, remainingKeywords: string[]) =>
    request<{ archived: number; opportunity_ids: number[] }>("/opportunities/archive-by-keyword", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, keyword, remaining_keywords: remainingKeywords }),
    }),
  restoreOpportunity: (token: string, opportunityId: number) =>
    request<Opportunity>(`/opportunities/${opportunityId}/restore`, token, { method: "POST" }),
  runs: (token: string) => request<Run[]>("/runs", token, { cache: "no-store" }),
  schedulerStatus: (token: string, country: CountryCode) =>
    request<SchedulerStatus>(`/runs/scheduler/status?country=${country}`, token),
  triggerSchedulerRun: (token: string, country: CountryCode) =>
    request<SchedulerStatus>(`/runs/scheduler/trigger?country=${country}`, token, { method: "POST" }),
  schedulerIntervalConfig: (token: string, country: CountryCode) =>
    request<SchedulerIntervalConfig>(`/app-settings/scheduler/${country}`, token),
  updateSchedulerIntervalConfig: (token: string, country: CountryCode, config: Pick<SchedulerIntervalConfig, "days" | "hours" | "minutes">) =>
    request<SchedulerIntervalConfig>(`/app-settings/scheduler/${country}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  trackingDateRefreshStatus: (token: string, country: CountryCode) =>
    request<TrackingDateRefreshStatus>(`/opportunity-tracking/date-refresh/status?country=${country}`, token),
  updateTrackingDateRefreshInterval: (token: string, country: CountryCode, config: { days: number; hours: number; minutes: number }) =>
    request<TrackingDateRefreshStatus>(`/app-settings/tracking-date-refresh/${country}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  radarKeywords: (token: string, country: CountryCode) =>
    request<RadarKeyword[]>(`/radar-keywords/${country}`, token),
  createRadarKeyword: (token: string, country: CountryCode, keyword: string) =>
    request<RadarKeyword>(`/radar-keywords/${country}`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword }),
    }),
  deleteRadarKeyword: (token: string, country: CountryCode, keywordId: number) =>
    request<void>(`/radar-keywords/${country}/${keywordId}`, token, { method: "DELETE" }),
  run: (token: string, id: number) => request<Run>(`/runs/${id}?_=${Date.now()}`, token, {
    cache: "no-store",
    headers: { "Cache-Control": "no-cache" },
  }),
  cancelRun: (token: string, id: number) => request<Run>(`/runs/${id}/cancel`, token, { method: "POST" }),
  startRun: (
    token: string,
    payload: {
      source: string;
      keyword: string;
      nomenclature?: string;
      entity_filter?: string;
      year: string;
      month?: string;
      years?: string[];
      months?: string[];
      publication_date_from?: string;
      publication_date_to?: string;
      version: string;
      max_results: number;
      max_details: number;
      enrich_details: boolean;
      revalidate_closed_detail?: boolean;
      direct_detail_lookup?: boolean;
      commercial_mode?: "active" | "all";
    },
  ) =>
    request<Run>("/runs/start", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  alertRules: (token: string) => request<AlertRule[]>("/alerts/rules", token),
  alerts: (token: string) => request<Alert[]>("/alerts", token),
  opportunityDocuments: (token: string, opportunityId: number) =>
    request<DocumentRecord[]>(`/documents/opportunity/${opportunityId}`, token),
  discoverDocuments: (token: string, opportunityId: number) =>
    request<DocumentRecord[]>(`/documents/opportunity/${opportunityId}/discover`, token, { method: "POST" }),
  documentDownloadUrl: (token: string, documentId: number) =>
    `${API_URL}/documents/${documentId}/download?token=${encodeURIComponent(token)}`,
  createAlertRule: (
    token: string,
    payload: AlertRulePayload,
  ) =>
    request<AlertRule>("/alerts/rules", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateAlertRule: (token: string, ruleId: number, payload: Partial<AlertRulePayload>) =>
    request<AlertRule>(`/alerts/rules/${ruleId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteAlertRule: (token: string, ruleId: number) =>
    request<void>(`/alerts/rules/${ruleId}`, token, { method: "DELETE" }),
  trackingAreas: (token: string, options: { activeOnly?: boolean } = {}) => {
    const query = options.activeOnly === false ? "?active_only=false" : "";
    return request<TrackingArea[]>(`/tracking-areas${query}`, token);
  },
  createTrackingArea: (token: string, payload: TrackingAreaPayload) =>
    request<TrackingArea>("/tracking-areas", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateTrackingArea: (token: string, areaId: number, payload: Partial<TrackingAreaPayload>) =>
    request<TrackingArea>(`/tracking-areas/${areaId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  trackingResponsibles: (token: string, options: { areaId?: number; country?: string; activeOnly?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (options.areaId) params.set("area_id", String(options.areaId));
    if (options.country) params.set("country", options.country);
    if (options.activeOnly === false) params.set("active_only", "false");
    const query = params.toString();
    return request<TrackingResponsible[]>(`/tracking-responsibles${query ? `?${query}` : ""}`, token);
  },
  createTrackingResponsible: (token: string, payload: TrackingResponsiblePayload) =>
    request<TrackingResponsible>("/tracking-responsibles", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateTrackingResponsible: (token: string, responsibleId: number, payload: Partial<TrackingResponsiblePayload>) =>
    request<TrackingResponsible>(`/tracking-responsibles/${responsibleId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  trackingPhases: (token: string, country?: CountryCode) =>
    request<TrackingPhase[]>(`/tracking-templates/phases${country ? `?country=${country}` : ""}`, token),
  trackingStageTemplates: (token: string, phaseId: number) =>
    request<TrackingStageTemplate[]>(`/tracking-templates/phases/${phaseId}/stages`, token),
  createStageTemplate: (token: string, phaseId: number, payload: TrackingStageTemplatePayload) =>
    request<TrackingStageTemplate>(`/tracking-templates/phases/${phaseId}/stages`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateStageTemplate: (token: string, stageTemplateId: number, payload: TrackingStageTemplatePayload) =>
    request<TrackingStageTemplate>(`/tracking-templates/stages/${stageTemplateId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  reorderStageTemplates: (token: string, orderedStageTemplateIds: number[]) =>
    request<TrackingStageTemplate[]>("/tracking-templates/stages/reorder", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ordered_stage_template_ids: orderedStageTemplateIds }),
    }),
  deleteStageTemplate: (token: string, stageTemplateId: number) =>
    request<void>(`/tracking-templates/stages/${stageTemplateId}`, token, { method: "DELETE" }),
  opportunityTrackings: (token: string, options: { opportunityIds?: number[]; country?: CountryCode; mineOnly?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (options.opportunityIds?.length) params.set("opportunity_ids", options.opportunityIds.join(","));
    if (options.country) params.set("country", options.country);
    if (options.mineOnly) params.set("mine_only", "true");
    const query = params.toString();
    return request<OpportunityTrackingSummary[]>(`/opportunity-tracking${query ? `?${query}` : ""}`, token);
  },
  opportunityTracking: (token: string, opportunityId: number) =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}`, token),
  setCoResponsible: (token: string, opportunityId: number, userId: number | null) =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}/co-responsible`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    }),
  withdrawTracking: (token: string, opportunityId: number) =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}/withdraw`, token, { method: "POST" }),
  assignableUsers: (token: string, country?: CountryCode) =>
    request<AssignableUser[]>(`/users/assignable${country ? `?country=${country}` : ""}`, token),
  startOpportunityTracking: (token: string, opportunityId: number) =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}/start`, token, { method: "POST" }),
  updateTrackingStage: (
    token: string,
    stageId: number,
    payload: {
      due_date?: string | null;
      status?: string;
      completed?: boolean;
      alert_atender_enabled?: boolean;
      alert_urgente_enabled?: boolean;
    },
  ) =>
    request<OpportunityTrackingStage>(`/opportunity-tracking/stages/${stageId}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateTrackingStageAreas: (token: string, stageId: number, areaIds: number[]) =>
    request<OpportunityTrackingStage>(`/opportunity-tracking/stages/${stageId}/areas`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ area_ids: areaIds }),
    }),
  updateTrackingStageAssignees: (token: string, stageId: number, responsibleIds: number[]) =>
    request<OpportunityTrackingStage>(`/opportunity-tracking/stages/${stageId}/assignees`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ responsible_ids: responsibleIds }),
    }),
  setQuotationOutcome: (token: string, opportunityId: number, outcome: "ganado" | "perdido" | "pendiente") =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}/quotation-outcome`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome }),
    }),
  advanceTrackingPhase: (token: string, opportunityId: number) =>
    request<OpportunityTracking>(`/opportunity-tracking/${opportunityId}/advance-phase`, token, { method: "POST" }),
  refreshTrackingDates: (token: string, opportunityId: number) =>
    request<{
      ran_at: string;
      checked: number;
      errors: number;
      changed: { opportunity_id: number; changes: { field: string; label: string; old: string | null; new: string | null }[] }[];
    }>(`/opportunity-tracking/${opportunityId}/refresh-dates`, token, { method: "POST" }),
  sendStageSupportRequest: (token: string, stageId: number, responsibleIds: number[], message: string = "") =>
    request<{ sent: number; failed: number }>(`/opportunity-tracking/stages/${stageId}/notify`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ responsible_ids: responsibleIds, message }),
    }),
  opportunityReviews: (token: string, opportunityIds?: number[]) => {
    const query = opportunityIds?.length ? `?opportunity_ids=${opportunityIds.join(",")}` : "";
    return request<OpportunityReview[]>(`/opportunity-reviews${query}`, token);
  },
  opportunityReview: (token: string, opportunityId: number) =>
    request<OpportunityReviewDetail>(`/opportunity-reviews/${opportunityId}`, token),
  startOpportunityReview: (token: string, opportunityId: number, comment: string = "") =>
    request<OpportunityReviewDetail>(`/opportunity-reviews/${opportunityId}`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    }),
  addOpportunityReviewComment: (token: string, opportunityId: number, comment: string) =>
    request<OpportunityReviewDetail>(`/opportunity-reviews/${opportunityId}/comments`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    }),
  resolveOpportunityReview: (token: string, opportunityId: number) =>
    request<OpportunityReviewDetail>(`/opportunity-reviews/${opportunityId}/resolve`, token, { method: "POST" }),
  exportTrackingXlsx: async (token: string, payload: { title: string; headers: string[]; rows: Array<Array<string | number | null>> }) => {
    const response = await fetch(`${API_URL}/opportunity-tracking/export/xlsx`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new ApiError("No se pudo generar el archivo Excel", response.status);
    return response.blob();
  },
};

// --- Histórico Perú (CONOSCE open data) -------------------------------------

export type HistoricoKind = "contrataciones" | "vencimientos" | "recurrentes" | "pac";
export type HistoricoPriority = "P1" | "P2" | "P3" | "P4";

export type HistoricoFilters = {
  years?: number[];
  months?: number[];
  departments?: string[];
  categories?: string[];
  process_groups?: string[];
  government_levels?: string[];
  buckets?: string[];
  patterns?: string[];
  situations?: string[];
  datasets?: string[];
  q?: string;
  relevance?: "ok" | "revisar";
  real_date_only?: boolean;
  hide_renewed?: boolean;
  min_amount?: number;
};

export type HistoricoAlertPreference = {
  configured?: boolean;
  kinds: string[];
  categories: string[];
  departments: string[];
  government_levels: string[];
  process_groups: string[];
  keywords: string[];
  min_amount: number;
  min_priority: HistoricoPriority;
  historico_digest: boolean;
};

export type HistoricoPacSummary = {
  totals: { items: number; entities: number; already_awarded: number; to_call: number };
  by_month: Array<{ key: number; count: number }>;
  by_process_group: Array<{ key: string; count: number }>;
  by_department: Array<{ key: string; count: number }>;
  by_situation: Array<{ key: string; count: number }>;
  by_category: Array<{ key: string; count: number }>;
};

export type HistoricoStatus = {
  latest_run_id: number | null;
  latest_status: string | null;
  latest_completed_at: string | null;
  data_cut_date: string | null;
  refresh_day: number;
  refresh_requested: boolean;
  import_due: boolean;
  needs_fallback: boolean;
  completed_this_month: boolean;
};

export type HistoricoFilterOptions = {
  years: number[];
  departments: string[];
  categories: string[];
  process_groups: string[];
  government_levels: string[];
  expiring_buckets: string[];
  recurring_buckets: string[];
  recurring_patterns: string[];
  pac_situations: string[];
  pac_years: number[];
};

export type HistoricoGroup = { key: string; amount: number; count: number };

export type HistoricoRunwayItem = {
  id: number;
  end_date: string;
  days: number;
  amount: number;
  entity_name: string;
  department: string;
  is_real_date: boolean;
  possibly_renewed: boolean;
  priority: HistoricoPriority;
};

export type HistoricoSummary = {
  totals: { amount: number; count: number; entities: number; suppliers: number };
  by_month: HistoricoGroup[];
  by_process_group: HistoricoGroup[];
  by_category: HistoricoGroup[];
  by_government_level: HistoricoGroup[];
  by_department: HistoricoGroup[];
  top_entities: Array<{ ruc: string; name: string; department: string; amount: number; count: number }>;
  top_suppliers: Array<{ ruc: string; name: string; amount: number; count: number; entities: number }>;
  expiring_buckets: HistoricoGroup[];
  recurring_buckets: HistoricoGroup[];
  runway: HistoricoRunwayItem[];
};

export type HistoricoContracting = {
  id: number;
  dataset: "orden" | "adjudicacion";
  year: number;
  month: string;
  date: string | null;
  process_group: string;
  procedure: string;
  nomenclature: string;
  entity_ruc: string;
  entity_name: string;
  department: string;
  description: string;
  category: string;
  amount: number;
  reference_amount: number;
  supplier_ruc: string;
  supplier_name: string;
  status: string;
  direct_cause: string;
  object_type: string;
  government_level: string;
  relevance: string;
};

export type HistoricoExpiring = HistoricoContracting & {
  contracting_id: number;
  start_date: string | null;
  end_date: string;
  date_source: string;
  is_real_date: boolean;
  days_to_end: number;
  bucket: string;
  monthly_amount: number;
  extras_amount: number;
  possibly_renewed: boolean;
  priority: HistoricoPriority | null;
  contract_number: string;
  contract_url: string;
};

export type HistoricoRecurring = {
  id: number;
  entity_ruc: string;
  entity_name: string;
  department: string;
  government_level: string;
  supplier_ruc: string;
  supplier_name: string;
  category: string;
  orders_12m: number;
  months_12m: number;
  amount_12m_supplier: number;
  amount_12m_entity: number;
  suppliers_12m: number;
  last_order_date: string | null;
  last_order_amount: number;
  last_order_description: string;
  pattern: string;
  next_purchase_date: string | null;
  days_to_next: number;
  bucket: string;
};

export type HistoricoPacItem = {
  id: number;
  year: number;
  entity_ruc: string;
  entity_name: string;
  department: string;
  government_level: string;
  version: string;
  reference_number: string;
  process_description: string;
  process_type: string;
  process_group: string;
  object_type: string;
  item_number: string;
  item_description: string;
  category: string;
  quantity: number;
  unit: string;
  item_department: string;
  province: string;
  district: string;
  planned_month: number;
  published_at: string | null;
  situation: string;
  already_awarded: boolean;
};

export type HistoricoRowByKind = {
  contrataciones: HistoricoContracting;
  vencimientos: HistoricoExpiring;
  recurrentes: HistoricoRecurring;
  pac: HistoricoPacItem;
};

export type HistoricoPage<T> = { items: T[]; total: number; amount: number; page: number; page_size: number };

export type HistoricoDetail = {
  kind: HistoricoKind;
  record: Record<string, unknown> & { orders?: HistoricoContracting[] };
  entity_history: Array<{ year: number; amount: number; count: number }>;
  entity_suppliers: Array<{ ruc: string; name: string; amount: number; count: number; last_date: string | null }>;
  related_awards: HistoricoContracting[];
};

export type HistoricoAlertStatus = "nueva" | "vista" | "en_gestion" | "descartada";

export type HistoricoAlert = {
  id: number;
  kind: "vencimiento" | "recurrente" | "pac";
  priority: HistoricoPriority;
  priority_label: string;
  score: number;
  title: string;
  detail: string;
  entity_name: string;
  department: string;
  amount: number;
  due_date: string | null;
  category: string;
  process_group: string;
  government_level: string;
  status: HistoricoAlertStatus;
  assignee_id: number | null;
  expiring_id: number | null;
  recurring_id: number | null;
  pac_item_id: number | null;
  created_at: string;
  is_active: boolean;
};

export type HistoricoAlertPage = HistoricoPage<HistoricoAlert> & { counts: Record<HistoricoPriority, number> };

export type HistoricoKeyword = {
  id: number;
  keyword: string;
  category: string;
  kind: "include" | "review" | "exclude";
  priority: number;
  is_active: boolean;
};

export type HistoricoImportRun = {
  id: number;
  origin: string;
  status: string;
  progress: number;
  message: string;
  error: string;
  files: string[];
  counts: Record<string, number | string[]>;
  data_cut_date: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

function historicoQuery(filters: HistoricoFilters = {}, extra: Record<string, string | number | undefined> = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
    else if (typeof value === "boolean") {
      if (value) params.set(key, "true");
    } else if (value !== undefined && value !== "") params.set(key, String(value));
  });
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const historicoApi = {
  status: (token: string) => request<HistoricoStatus>("/historico/status", token, { cache: "no-store" }),
  filters: (token: string) => request<HistoricoFilterOptions>("/historico/filters", token),
  summary: (token: string, filters: HistoricoFilters) => request<HistoricoSummary>(`/historico/summary${historicoQuery(filters)}`, token),
  list: <K extends HistoricoKind>(token: string, kind: K, filters: HistoricoFilters, page = 1, pageSize = 50, sort?: string) =>
    request<HistoricoPage<HistoricoRowByKind[K]>>(`/historico/${kind}${historicoQuery(filters, { page, page_size: pageSize, sort })}`, token),
  buckets: (token: string, kind: "vencimientos" | "recurrentes", filters: HistoricoFilters) =>
    request<HistoricoGroup[]>(`/historico/${kind}/buckets${historicoQuery(filters)}`, token),
  detail: (token: string, kind: HistoricoKind, id: number) => request<HistoricoDetail>(`/historico/${kind}/${id}`, token),
  exportXlsx: async (token: string, kind: HistoricoKind, filters: HistoricoFilters, sort?: string) => {
    const response = await fetch(`${API_URL}/historico/${kind}/export.xlsx${historicoQuery(filters, { sort })}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new ApiError("No se pudo generar el archivo Excel", response.status);
    return response.blob();
  },
  runway: (token: string, filters: HistoricoFilters) => request<HistoricoRunwayItem[]>(`/historico/vencimientos-runway${historicoQuery(filters)}`, token),
  pacSummary: (token: string, filters: HistoricoFilters) => request<HistoricoPacSummary>(`/historico/pac-summary${historicoQuery(filters)}`, token),
  alerts: (token: string, params: { kinds?: string[]; priorities?: string[]; statuses?: string[]; departments?: string[]; categories?: string[]; q?: string; mine?: boolean; page?: number; page_size?: number }) => {
    const { page, page_size, mine, ...filters } = params;
    return request<HistoricoAlertPage>(`/historico/alerts/list${historicoQuery(filters as HistoricoFilters, { page, page_size, mine: mine ? "true" : undefined })}`, token, { cache: "no-store" });
  },
  alertPreferences: (token: string) => request<HistoricoAlertPreference>("/historico/alerts/preferences", token, { cache: "no-store" }),
  saveAlertPreferences: (token: string, preference: HistoricoAlertPreference) =>
    request<HistoricoAlertPreference>("/historico/alerts/preferences", token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preference),
    }),
  previewAlertPreferences: (token: string, preference: HistoricoAlertPreference) =>
    request<{ total: number; counts: Record<HistoricoPriority, number> }>("/historico/alerts/preview", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preference),
    }),
  updateAlert: (token: string, id: number, payload: { status?: HistoricoAlertStatus; assignee_id?: number | null }) =>
    request<HistoricoAlert>(`/historico/alerts/${id}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  keywords: (token: string) => request<HistoricoKeyword[]>("/historico/admin/keywords", token),
  createKeyword: (token: string, payload: Omit<HistoricoKeyword, "id">) =>
    request<HistoricoKeyword>("/historico/admin/keywords", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateKeyword: (token: string, id: number, payload: Omit<HistoricoKeyword, "id">) =>
    request<HistoricoKeyword>(`/historico/admin/keywords/${id}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteKeyword: (token: string, id: number) => request<void>(`/historico/admin/keywords/${id}`, token, { method: "DELETE" }),
  imports: (token: string) => request<{ status: HistoricoStatus; runs: HistoricoImportRun[] }>("/historico/admin/imports", token, { cache: "no-store" }),
  importRun: (token: string, id: number) => request<HistoricoImportRun>(`/historico/admin/imports/${id}`, token, { cache: "no-store" }),
  requestRefresh: (token: string) => request<HistoricoStatus>("/historico/admin/refresh", token, { method: "POST" }),
  updateSettings: (token: string, refreshDay: number) =>
    request<HistoricoStatus>("/historico/admin/settings", token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_day: refreshDay }),
    }),
  createUpload: (token: string) => request<HistoricoImportRun>("/historico/admin/imports", token, { method: "POST" }),
  uploadFile: (token: string, runId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ filename: string; dataset: string; year: number | null; month: number | null }>(`/historico/admin/imports/${runId}/files`, token, {
      method: "POST",
      body,
    });
  },
  processUpload: (token: string, runId: number) => request<HistoricoImportRun>(`/historico/admin/imports/${runId}/process`, token, { method: "POST" }),
};
