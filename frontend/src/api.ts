export type Stats = {
  total: number;
  by_source: Record<string, number>;
  by_priority: Record<string, number>;
  vigentes: number;
  cerrados: number;
  total_amount: number;
};

export type Opportunity = {
  id: number;
  source: string;
  entity: string;
  nomenclature: string;
  object_type: string;
  description: string;
  region: string;
  amount: number;
  currency: string;
  status: string;
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
};

export type Run = {
  id: number;
  source: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  rows_found: number;
  diagnostics: string;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AlertRule = {
  id: number;
  name: string;
  channel: string;
  destination: string;
  min_priority: string;
  hours_before_deadline: number;
  is_active: boolean;
};

export type Alert = {
  id: number;
  opportunity_id: number;
  rule_id: number;
  alert_type: string;
  status: string;
  message: string;
  sent_at: string | null;
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
    const detail = await response.text();
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

export const api = {
  stats: (token: string) => request<Stats>("/opportunities/stats", token),
  opportunities: (token: string, options: { runIds?: number[] } = {}) => {
    const params = new URLSearchParams();
    if (options.runIds?.length) {
      params.set("run_ids", options.runIds.join(","));
    }
    const query = params.toString();
    return request<Opportunity[]>(`/opportunities${query ? `?${query}` : ""}`, token);
  },
  runs: (token: string) => request<Run[]>("/runs", token),
  run: (token: string, id: number) => request<Run>(`/runs/${id}`, token),
  startRun: (
    token: string,
    payload: {
      source: string;
      keyword: string;
      nomenclature?: string;
      year: string;
      month?: string;
      years?: string[];
      months?: string[];
      version: string;
      max_results: number;
      max_details: number;
      enrich_details: boolean;
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
    payload: {
      name: string;
      channel: string;
      destination: string;
      min_priority: string;
      hours_before_deadline: number;
      is_active: boolean;
    },
  ) =>
    request<AlertRule>("/alerts/rules", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
