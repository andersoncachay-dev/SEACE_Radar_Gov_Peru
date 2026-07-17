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
  consultation_deadline: string | null;
  quote_deadline: string | null;
  proposal_deadline: string | null;
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

export type SchedulerStatus = {
  enabled: boolean;
  country: "peru" | "chile";
  is_running: boolean;
  next_update_at: string | null;
  interval_minutes: number;
  interval_seconds: number;
};

export type SchedulerIntervalConfig = {
  country: "peru" | "chile";
  days: number;
  hours: number;
  minutes: number;
  interval_seconds: number;
  next_update_at: string | null;
  enabled: boolean;
};

export type AlertRule = {
  id: number;
  name: string;
  channel: string;
  destination: string;
  keywords: string;
  min_priority: string;
  country: "peru" | "chile" | "both";
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
  country: "peru" | "chile";
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

export type AccessProfile = "peru" | "chile" | "both";

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
  access_profile: AccessProfile;
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
  access_profile: AccessProfile;
  role: "viewer" | "admin";
};

export type RadarKeyword = {
  id: number | null;
  country: "peru" | "chile";
  keyword: string;
  is_default: boolean;
};

export type LegalDocumentKey = "terms" | "privacy" | "confidentiality";

export type LegalDocumentRecord = {
  key: LegalDocumentKey;
  title: string;
  content: string;
  updated_at: string;
};

export type AppSettingsRecord = {
  version_label: string;
  updated_at: string | null;
};

export type ScoringFactor = { label: string; points: number; enabled: boolean; value: string; value_type: "list" | "number" | "text"; field: "description" | "entity" | "region" | "amount" | "origin" | "status" };
export type ScoringConfig = {
  country: "peru" | "chile";
  priority_a_min: number;
  priority_b_min: number;
  attractive_amount_min: number;
  score_target: number;
  factors: Record<string, ScoringFactor>;
};

export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
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
  updateAppSettings: (token: string, versionLabel: string) =>
    request<AppSettingsRecord>("/app-settings", token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_label: versionLabel }),
    }),
  scoringConfig: (token: string, country: "peru" | "chile") =>
    request<ScoringConfig>(`/app-settings/scoring/${country}`, token),
  updateScoringConfig: (token: string, country: "peru" | "chile", config: ScoringConfig) =>
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
  exportOpportunitiesXlsx: async (token: string, payload: { title: string; country: "peru" | "chile"; headers: string[]; rows: Array<Array<string | number | null>> }) => {
    const response = await fetch(`${API_URL}/opportunities/export/xlsx`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new ApiError("No se pudo generar el archivo Excel", response.status);
    return response.blob();
  },
  archivedOpportunities: (token: string, country: "peru" | "chile") =>
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
  archiveOpportunitiesByKeyword: (token: string, country: "peru" | "chile", keyword: string, remainingKeywords: string[]) =>
    request<{ archived: number; opportunity_ids: number[] }>("/opportunities/archive-by-keyword", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, keyword, remaining_keywords: remainingKeywords }),
    }),
  restoreOpportunity: (token: string, opportunityId: number) =>
    request<Opportunity>(`/opportunities/${opportunityId}/restore`, token, { method: "POST" }),
  runs: (token: string) => request<Run[]>("/runs", token, { cache: "no-store" }),
  schedulerStatus: (token: string, country: "peru" | "chile") =>
    request<SchedulerStatus>(`/runs/scheduler/status?country=${country}`, token),
  schedulerIntervalConfig: (token: string, country: "peru" | "chile") =>
    request<SchedulerIntervalConfig>(`/app-settings/scheduler/${country}`, token),
  updateSchedulerIntervalConfig: (token: string, country: "peru" | "chile", config: Pick<SchedulerIntervalConfig, "days" | "hours" | "minutes">) =>
    request<SchedulerIntervalConfig>(`/app-settings/scheduler/${country}`, token, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  radarKeywords: (token: string, country: "peru" | "chile") =>
    request<RadarKeyword[]>(`/radar-keywords/${country}`, token),
  createRadarKeyword: (token: string, country: "peru" | "chile", keyword: string) =>
    request<RadarKeyword>(`/radar-keywords/${country}`, token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword }),
    }),
  deleteRadarKeyword: (token: string, country: "peru" | "chile", keywordId: number) =>
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
};
