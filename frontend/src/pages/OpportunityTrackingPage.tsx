import React, { useEffect, useMemo, useState } from "react";
import {
  api,
  AssignableUser,
  CountryScope,
  Opportunity,
  OpportunityTracking as OpportunityTrackingRecord,
  OpportunityTrackingStage,
  OpportunityTrackingSummary,
  TrackingArea,
  TrackingDateRefreshStatus,
  TrackingPhase,
  TrackingResponsible,
  TrackingResponsiblePayload,
  TrackingStageTemplate,
} from "../api";
import { ConfirmModal, Empty, formatDate, useDismissableMenu } from "../shared";
import { excelLogoUrl, OpportunityDetailModal } from "./OpportunitiesPage";

function countryScopeLabel(scope: CountryScope) {
  return scope === "ambos" ? "Perú y Chile" : scope === "peru" ? "Perú" : "Chile";
}

// Ventana de una etapa: desde el vencimiento de la etapa anterior (o el inicio de la fase) hasta su propio vencimiento.
function stageWindowStart(
  stagesInPhase: OpportunityTrackingStage[],
  stage: OpportunityTrackingStage,
  phaseRangeStart: string | null,
): string | null {
  const ordered = [...stagesInPhase].sort((left, right) => left.sort_order - right.sort_order);
  const index = ordered.findIndex((item) => item.id === stage.id);
  if (index <= 0) return phaseRangeStart;
  return ordered[index - 1].due_date;
}

function daysAllocated(stage: OpportunityTrackingStage, windowStart: string | null): number | null {
  if (stage.is_outcome_step || !stage.due_date || !windowStart) return null;
  const diffMs = new Date(stage.due_date).getTime() - new Date(windowStart).getTime();
  return Math.round(diffMs / (1000 * 60 * 60 * 24));
}

type TimeStatus = "on_time" | "atender" | "urgente" | "vencido";

// Mientras el estado siga en su valor por defecto ("pendiente"), se deriva
// automáticamente de la fecha de hoy respecto a la ventana de la etapa: antes de que
// empiece = pendiente, dentro de la ventana = en progreso, y una vez vencida =
// bloqueado. En cuanto el estado deja de ser "pendiente" -ya sea porque se marcó
// completada (el backend lo sincroniza) o porque se eligió a mano en el selector-
// ese valor manda y sigue siendo editable normalmente desde el selector.
function deriveEffectiveStatus(stage: OpportunityTrackingStage, windowStart: string | null): string {
  if (stage.status !== "pendiente") return stage.status;
  if (!stage.due_date || !windowStart) return stage.status;
  const now = Date.now();
  const startMs = new Date(windowStart).getTime();
  const dueMs = new Date(stage.due_date).getTime();
  if (now > dueMs) return "bloqueado";
  if (now >= startMs) return "en_progreso";
  return "pendiente";
}

const TIME_STATUS_LABELS: Record<TimeStatus, string> = {
  on_time: "A tiempo",
  atender: "Atender",
  urgente: "Urgente",
  vencido: "Vencido",
};

// Semáforo de 4 estados según el % de tiempo restante dentro de la ventana asignada a la etapa:
// >=80% resta = a tiempo (verde), 40-79% = atender (ámbar), 0-39% = urgente (rojo), vencida = rojo oscuro.
function computeTimeStatus(dueDate: string | null, windowStart: string | null): TimeStatus | null {
  if (!dueDate || !windowStart) return null;
  const dueMs = new Date(dueDate).getTime();
  const startMs = new Date(windowStart).getTime();
  const totalMs = dueMs - startMs;
  if (!Number.isFinite(totalMs) || totalMs <= 0) return null;
  const now = Date.now();
  if (now > dueMs) return "vencido";
  const remainingPct = ((dueMs - now) / totalMs) * 100;
  if (remainingPct >= 80) return "on_time";
  if (remainingPct >= 40) return "atender";
  return "urgente";
}

function StageSupportButton({ token, stage }: { token: string; stage: OpportunityTrackingStage }) {
  const [open, setOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const menuRef = useDismissableMenu(open, () => setOpen(false));

  function toggleSelected(id: number) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  async function send() {
    if (!selectedIds.length) return;
    setSending(true);
    setError("");
    setFeedback("");
    try {
      const result = await api.sendStageSupportRequest(token, stage.id, selectedIds, note.trim());
      setFeedback(
        result.failed
          ? `Enviado a ${result.sent} de ${result.sent + result.failed} responsables (${result.failed} fallaron).`
          : `Correo enviado a ${result.sent} responsable${result.sent === 1 ? "" : "s"}.`,
      );
      setSelectedIds([]);
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo enviar la solicitud de apoyo");
    } finally {
      setSending(false);
    }
  }

  if (!stage.assignees.length) return null;

  return (
    <div className="tracking-stage-anchor" ref={menuRef as React.RefObject<HTMLDivElement>}>
      <button
        type="button"
        className="tracking-support-button"
        onClick={() => {
          setOpen((value) => !value);
          setFeedback("");
          setError("");
        }}
      >
        ✉ Enviar alerta
      </button>
      {open ? (
        <div className="tracking-chip-menu tracking-support-menu" role="menu">
          <span className="tracking-support-menu-title">¿A quién le pedimos apoyo?</span>
          {stage.assignees.map((responsible) => (
            <label key={responsible.id}>
              <input
                type="checkbox"
                checked={selectedIds.includes(responsible.id)}
                onChange={() => toggleSelected(responsible.id)}
              />
              {responsible.full_name}
            </label>
          ))}
          <textarea
            className="tracking-support-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Nota adicional (opcional)"
            rows={3}
            maxLength={1000}
          />
          {error ? <small className="tracking-templates-error" role="alert">{error}</small> : null}
          {feedback ? <small className="tracking-support-feedback" role="status">{feedback}</small> : null}
          <button type="button" className="primary" disabled={sending || !selectedIds.length} onClick={() => void send()}>
            {sending ? "Enviando..." : "Enviar"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function TimeStatusBadge({ status }: { status: TimeStatus | null }) {
  if (!status) return null;
  return <span className={`tracking-time-status status-${status}`}>{TIME_STATUS_LABELS[status]}</span>;
}

function StageCard({
  token,
  stage,
  daysAllocated,
  timeStatus,
  effectiveStatus,
  areas,
  responsibles,
  busy,
  onChangeDueDate,
  onChangeStatus,
  onChangeAreas,
  onChangeAssignees,
  onSetOutcome,
  onToggleAlert,
}: {
  token: string;
  stage: OpportunityTrackingStage;
  daysAllocated: number | null;
  timeStatus: TimeStatus | null;
  effectiveStatus: string;
  areas: TrackingArea[];
  responsibles: TrackingResponsible[];
  busy: boolean;
  onChangeDueDate: (stage: OpportunityTrackingStage, value: string) => void;
  onChangeStatus: (stage: OpportunityTrackingStage, value: string) => void;
  onChangeAreas: (stage: OpportunityTrackingStage, areaIds: number[]) => void;
  onChangeAssignees: (stage: OpportunityTrackingStage, responsibleIds: number[]) => void;
  onSetOutcome?: (stage: OpportunityTrackingStage, outcome: "ganado" | "perdido" | "pendiente") => void;
  onToggleAlert: (stage: OpportunityTrackingStage, key: "alert_atender_enabled" | "alert_urgente_enabled", value: boolean) => void;
}) {
  const [areaMenuOpen, setAreaMenuOpen] = useState(false);
  const [assigneeMenuOpen, setAssigneeMenuOpen] = useState(false);
  const areaMenuRef = useDismissableMenu(areaMenuOpen, () => setAreaMenuOpen(false));
  const assigneeMenuRef = useDismissableMenu(assigneeMenuOpen, () => setAssigneeMenuOpen(false));

  const showTimeStatus = !stage.is_outcome_step && effectiveStatus !== "completado" && effectiveStatus !== "bloqueado";
  const outcomeCardClass = stage.is_outcome_step ? `outcome-card-${stage.outcome || "pendiente"}` : "";

  return (
    <div className={`tracking-stage-card status-${effectiveStatus} ${outcomeCardClass} ${stage.completed ? "completed" : ""}`}>
      <div className="tracking-stage-header">
        <span className="tracking-stage-title">
          <strong>{stage.name}</strong>
          {!stage.is_outcome_step && daysAllocated !== null ? (
            <span className="tracking-stage-days" title="Días asignados desde la fecha límite de la etapa anterior">
              {daysAllocated} {Math.abs(daysAllocated) === 1 ? "día" : "días"}
            </span>
          ) : null}
          {showTimeStatus ? <TimeStatusBadge status={timeStatus} /> : null}
        </span>
        {!stage.is_outcome_step ? (
          <select
            className={`tracking-status-select status-${effectiveStatus}`}
            value={effectiveStatus}
            disabled={busy}
            onChange={(event) => onChangeStatus(stage, event.target.value)}
          >
            <option value="pendiente">Pendiente</option>
            <option value="en_progreso">En progreso</option>
            <option value="completado">Completado</option>
            <option value="bloqueado">Bloqueado</option>
          </select>
        ) : null}
      </div>
      {!stage.is_outcome_step ? (
        <div className="tracking-alert-switches">
          <span className="tracking-alert-switches-label">Alertas por correo:</span>
          <label className="tracking-switch">
            <input
              type="checkbox"
              checked={stage.alert_atender_enabled}
              disabled={busy}
              onChange={(event) => onToggleAlert(stage, "alert_atender_enabled", event.target.checked)}
            />
            <span className="tracking-switch-track" aria-hidden="true" />
            Atender
          </label>
          <label className="tracking-switch">
            <input
              type="checkbox"
              checked={stage.alert_urgente_enabled}
              disabled={busy}
              onChange={(event) => onToggleAlert(stage, "alert_urgente_enabled", event.target.checked)}
            />
            <span className="tracking-switch-track" aria-hidden="true" />
            Urgente
          </label>
        </div>
      ) : null}
      {stage.is_outcome_step && onSetOutcome ? (
        <div className="tracking-outcome-picker">
          {(["ganado", "perdido", "pendiente"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`outcome-${value} ${stage.outcome === value ? "active" : ""}`}
              disabled={busy}
              onClick={() => onSetOutcome(stage, value)}
            >
              {value === "ganado" ? "Ganado" : value === "perdido" ? "Perdido" : "Pendiente"}
            </button>
          ))}
        </div>
      ) : null}
      <div className="tracking-stage-meta">
        <label className="tracking-stage-due">
          Fecha límite
          <input
            type="date"
            disabled={busy}
            value={stage.due_date ? stage.due_date.slice(0, 10) : ""}
            onChange={(event) => onChangeDueDate(stage, event.target.value)}
          />
        </label>
        <div className="tracking-stage-anchor" ref={areaMenuRef as React.RefObject<HTMLDivElement>}>
          <button type="button" className="tracking-chip-button" onClick={() => setAreaMenuOpen((value) => !value)}>
            Áreas: {stage.areas.length ? stage.areas.map((area) => area.name).join(", ") : "Sin asignar"}
          </button>
          {areaMenuOpen ? (
            <div className="tracking-chip-menu" role="menu">
              {areas.map((area) => {
                const checked = stage.areas.some((item) => item.id === area.id);
                return (
                  <label key={area.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const nextIds = event.target.checked
                          ? [...stage.areas.map((item) => item.id), area.id]
                          : stage.areas.filter((item) => item.id !== area.id).map((item) => item.id);
                        onChangeAreas(stage, nextIds);
                      }}
                    />
                    {area.name}
                  </label>
                );
              })}
            </div>
          ) : null}
        </div>
        <div className="tracking-stage-anchor" ref={assigneeMenuRef as React.RefObject<HTMLDivElement>}>
          <button type="button" className="tracking-chip-button" onClick={() => setAssigneeMenuOpen((value) => !value)}>
            Responsables: {stage.assignees.length ? stage.assignees.map((item) => item.full_name).join(", ") : "Sin asignar"}
          </button>
          {assigneeMenuOpen ? (
            <div className="tracking-chip-menu" role="menu">
              {responsibles.map((responsible) => {
                const checked = stage.assignees.some((item) => item.id === responsible.id);
                return (
                  <label key={responsible.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const nextIds = event.target.checked
                          ? [...stage.assignees.map((item) => item.id), responsible.id]
                          : stage.assignees.filter((item) => item.id !== responsible.id).map((item) => item.id);
                        onChangeAssignees(stage, nextIds);
                      }}
                    />
                    {responsible.full_name}
                  </label>
                );
              })}
            </div>
          ) : null}
        </div>
        <StageSupportButton token={token} stage={stage} />
      </div>
    </div>
  );
}

function TrackingTimeline({
  token,
  stages,
  areas,
  responsibles,
  rangeStart,
  rangeEnd,
  busy,
  onChangeDueDate,
  onChangeStatus,
  onChangeAreas,
  onChangeAssignees,
  onSetOutcome,
  onToggleAlert,
}: {
  token: string;
  stages: OpportunityTrackingStage[];
  areas: TrackingArea[];
  responsibles: TrackingResponsible[];
  rangeStart: string | null;
  rangeEnd: string | null;
  busy: boolean;
  onChangeDueDate: (stage: OpportunityTrackingStage, value: string) => void;
  onChangeStatus: (stage: OpportunityTrackingStage, value: string) => void;
  onChangeAreas: (stage: OpportunityTrackingStage, areaIds: number[]) => void;
  onChangeAssignees: (stage: OpportunityTrackingStage, responsibleIds: number[]) => void;
  onSetOutcome: (stage: OpportunityTrackingStage, outcome: "ganado" | "perdido" | "pendiente") => void;
  onToggleAlert: (stage: OpportunityTrackingStage, key: "alert_atender_enabled" | "alert_urgente_enabled", value: boolean) => void;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);

  if (!stages.length) {
    return <Empty text="Esta fase todavía no tiene etapas registradas." />;
  }
  const outcomeIndex = stages.findIndex((stage) => stage.is_outcome_step);
  const proposalDeadlineIndex = rangeEnd && outcomeIndex > 0 ? outcomeIndex - 1 : -1;

  const rangeStartMs = rangeStart ? new Date(rangeStart).getTime() : null;
  const rangeEndMs = rangeEnd ? new Date(rangeEnd).getTime() : null;
  const rangeTotalMs = rangeStartMs !== null && rangeEndMs !== null ? rangeEndMs - rangeStartMs : null;
  const rangeProgressPct =
    rangeTotalMs !== null && rangeTotalMs > 0 && rangeStartMs !== null
      ? Math.min(100, Math.max(0, ((now - rangeStartMs) / rangeTotalMs) * 100))
      : null;
  const rangeOverdue = rangeEndMs !== null && now > rangeEndMs;

  return (
    <div className="tracking-timeline">
      {rangeStart || rangeEnd ? (
        <div className="tracking-timeline-range">
          <span className="tracking-timeline-range-start">{rangeStart ? formatDate(rangeStart) : "Sin fecha de publicación"}</span>
          <span className="tracking-timeline-range-line" aria-hidden="true">
            {rangeProgressPct !== null ? (
              <span
                className={`tracking-timeline-range-progress ${rangeOverdue ? "overdue" : ""}`}
                style={{ width: `${rangeProgressPct}%` }}
              />
            ) : null}
          </span>
          <span className="tracking-timeline-range-end">{rangeEnd ? formatDate(rangeEnd) : "Sin fecha límite de propuesta"}</span>
        </div>
      ) : null}
      <ol className="tracking-timeline-list">
        {stages.map((stage, index) => (
          <li key={stage.id} className={`tracking-stage-node ${stage.completed ? "completed" : ""}`}>
            <span className="tracking-stage-dot" aria-hidden="true" />
            {index === proposalDeadlineIndex ? (
              <div className="tracking-proposal-deadline-flag">
                Fecha fin de presentación de propuesta: <strong>{formatDate(rangeEnd)}</strong>
              </div>
            ) : null}
            <StageCard
              token={token}
              stage={stage}
              daysAllocated={daysAllocated(stage, index === 0 ? rangeStart : stages[index - 1].due_date)}
              timeStatus={computeTimeStatus(stage.due_date, index === 0 ? rangeStart : stages[index - 1].due_date)}
              effectiveStatus={deriveEffectiveStatus(stage, index === 0 ? rangeStart : stages[index - 1].due_date)}
              areas={areas}
              responsibles={responsibles}
              busy={busy}
              onChangeDueDate={onChangeDueDate}
              onChangeStatus={onChangeStatus}
              onChangeAreas={onChangeAreas}
              onChangeAssignees={onChangeAssignees}
              onSetOutcome={stage.is_outcome_step ? onSetOutcome : undefined}
              onToggleAlert={onToggleAlert}
            />
          </li>
        ))}
      </ol>
    </div>
  );
}

function DateRefreshStatusBlock({ token, country }: { token: string; country: "peru" | "chile" }) {
  const [status, setStatus] = useState<TrackingDateRefreshStatus | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let active = true;
    function load() {
      api
        .trackingDateRefreshStatus(token, country)
        .then((result) => {
          if (active) setStatus(result);
        })
        .catch(() => undefined);
    }
    load();
    const refreshId = setInterval(load, 120000);
    return () => {
      active = false;
      clearInterval(refreshId);
    };
  }, [token, country]);

  useEffect(() => {
    const tickId = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tickId);
  }, []);

  const seconds = status?.next_update_at ? Math.max(0, Math.ceil((new Date(status.next_update_at).getTime() - now) / 1000)) : null;

  let message = "Consultando próxima verificación...";
  if (status && !status.enabled) {
    message = "Verificación automática pausada";
  } else if (seconds !== null) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    const parts = [
      days ? `${days} d` : "",
      hours ? `${hours} h` : "",
      `${minutes} m`,
      `${String(remainingSeconds).padStart(2, "0")} s`,
    ].filter(Boolean);
    message = seconds === 0 ? "Verificando fechas..." : `Próxima verificación en ${parts.join(" ")}`;
  }

  const lastRun = status?.last_run;
  const changedItems = lastRun?.changed ?? [];

  return (
    <div className="tracking-date-refresh-block">
      <div className="tracking-date-refresh-header">
        <span className="tracking-date-refresh-title">Verificación automática de fechas (SEACE / Mercado Público)</span>
        <span className="update-countdown">{message}</span>
      </div>
      {lastRun ? (
        changedItems.length > 0 ? (
          <div className="tracking-date-refresh-changes">
            <button type="button" className="tracking-date-refresh-toggle" onClick={() => setExpanded((value) => !value)}>
              ⚠ {changedItems.length} {changedItems.length === 1 ? "proceso con cambio de fecha detectado" : "procesos con cambios de fecha detectados"}
            </button>
            {expanded ? (
              <ul className="tracking-date-refresh-list">
                {changedItems.map((item) => (
                  <li key={item.opportunity_id}>
                    <strong>{item.nomenclature || item.entity}</strong>
                    {item.changes.map((change) => (
                      <span key={change.field} className="tracking-date-refresh-change">
                        {change.label}:{" "}
                        <span className="tracking-date-refresh-old">{change.old ? formatDate(change.old) : "—"}</span>
                        {" → "}
                        <span className="tracking-date-refresh-new">{change.new ? formatDate(change.new) : "—"}</span>
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : (
          <small className="tracking-date-refresh-ok">Sin cambios en la última verificación ({lastRun.checked} procesos revisados).</small>
        )
      ) : null}
    </div>
  );
}

function TrackingWorkspace({
  token,
  country,
  currentUserId,
}: {
  token: string;
  country: "peru" | "chile";
  currentUserId: number;
}) {
  const [summaries, setSummaries] = useState<OpportunityTrackingSummary[]>([]);
  const [phases, setPhases] = useState<TrackingPhase[]>([]);
  const [areas, setAreas] = useState<TrackingArea[]>([]);
  const [responsibles, setResponsibles] = useState<TrackingResponsible[]>([]);
  const [assignableUsers, setAssignableUsers] = useState<AssignableUser[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tracking, setTracking] = useState<OpportunityTrackingRecord | null>(null);
  const [selectedPhaseId, setSelectedPhaseId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [busy, setBusy] = useState(false);
  const [coResponsibleSelection, setCoResponsibleSelection] = useState<number | null>(null);
  const [coResponsibleBusy, setCoResponsibleBusy] = useState(false);
  const [confirmingWithdraw, setConfirmingWithdraw] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoadingList(true);
    Promise.all([
      api.opportunityTrackings(token, { country, mineOnly }),
      api.trackingPhases(token, country),
      api.trackingAreas(token),
      api.trackingResponsibles(token, { country }),
      api.assignableUsers(token, country),
    ])
      .then(([trackings, phaseList, areaList, responsibleList, userList]) => {
        setSummaries(trackings);
        setPhases(phaseList);
        setAreas(areaList);
        setResponsibles(responsibleList);
        setAssignableUsers(userList);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "No se pudo cargar el seguimiento"))
      .finally(() => setLoadingList(false));
  }, [token, country, mineOnly]);

  async function loadDetail(opportunityId: number) {
    setLoadingDetail(true);
    setError("");
    try {
      const detail = await api.opportunityTracking(token, opportunityId);
      setTracking(detail);
      setCoResponsibleSelection(detail.co_responsible_id);
      setSelectedPhaseId((current) => {
        const currentPhase = current !== null ? phases.find((item) => item.id === current) : null;
        const currentPhaseUnlocked =
          currentPhase !== null && currentPhase !== undefined
            ? currentPhase.key === "cotizacion" || detail.quotation_outcome === "ganado"
            : false;
        if (current && currentPhaseUnlocked && detail.stages.some((stage) => stage.phase_id === current)) return current;
        return detail.current_phase_id ?? detail.stages[0]?.phase_id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la oportunidad");
    } finally {
      setLoadingDetail(false);
    }
  }

  function selectOpportunity(id: number) {
    setSelectedId(id);
    void loadDetail(id);
  }

  async function refreshDetail() {
    if (selectedId !== null) await loadDetail(selectedId);
  }

  const filteredSummaries = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return summaries;
    return summaries.filter(
      (item) => item.entity.toLowerCase().includes(needle) || item.nomenclature.toLowerCase().includes(needle),
    );
  }, [summaries, search]);

  const selectedSummary = summaries.find((item) => item.opportunity_id === selectedId) || null;
  const canManageCoResponsible = tracking !== null && tracking.started_by_id === currentUserId;

  const phasesWithStages = useMemo(() => {
    if (!tracking) return [];
    const startedPhaseIds = new Set(tracking.stages.map((stage) => stage.phase_id));
    return phases.map((phase) => ({
      phase,
      // La fase de Cotización siempre está disponible; las siguientes (Perfeccionamiento
      // de Contrato, Implementación) solo se habilitan si la convocatoria quedó Ganada -
      // con Perdido o Pendiente permanecen bloqueadas aunque ya tengan etapas sembradas
      // de un resultado anterior.
      started: phase.key === "cotizacion" ? true : startedPhaseIds.has(phase.id) && tracking.quotation_outcome === "ganado",
    }));
  }, [phases, tracking]);

  const activeStages = useMemo(() => {
    if (!tracking || selectedPhaseId === null) return [];
    return tracking.stages
      .filter((stage) => stage.phase_id === selectedPhaseId)
      .sort((left, right) => left.sort_order - right.sort_order);
  }, [tracking, selectedPhaseId]);

  const selectedPhase = phases.find((phase) => phase.id === selectedPhaseId) || null;
  const isCotizacionPhase = selectedPhase?.key === "cotizacion";
  const isPerfeccionamientoPhase = selectedPhase?.key === "perfeccionamiento_contrato";
  const canAdvance = isPerfeccionamientoPhase && activeStages.length > 0 && activeStages.every((stage) => stage.completed);

  async function withBusy(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refreshDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo completar la acción");
    } finally {
      setBusy(false);
    }
  }

  function handleChangeDueDate(stage: OpportunityTrackingStage, value: string) {
    void withBusy(() => api.updateTrackingStage(token, stage.id, { due_date: value ? `${value}T00:00:00` : null }));
  }

  function handleChangeStatus(stage: OpportunityTrackingStage, value: string) {
    void withBusy(() => api.updateTrackingStage(token, stage.id, { status: value, completed: value === "completado" }));
  }

  function handleToggleAlert(stage: OpportunityTrackingStage, key: "alert_atender_enabled" | "alert_urgente_enabled", value: boolean) {
    void withBusy(() => api.updateTrackingStage(token, stage.id, { [key]: value }));
  }

  function handleChangeAreas(stage: OpportunityTrackingStage, areaIds: number[]) {
    void withBusy(() => api.updateTrackingStageAreas(token, stage.id, areaIds));
  }

  function handleChangeAssignees(stage: OpportunityTrackingStage, responsibleIds: number[]) {
    void withBusy(() => api.updateTrackingStageAssignees(token, stage.id, responsibleIds));
  }

  function handleSetOutcome(_stage: OpportunityTrackingStage, outcome: "ganado" | "perdido" | "pendiente") {
    if (selectedId === null) return;
    void withBusy(async () => {
      await api.setQuotationOutcome(token, selectedId, outcome);
      setSummaries((current) =>
        current.map((item) => (item.opportunity_id === selectedId ? { ...item, quotation_outcome: outcome } : item)),
      );
    });
  }

  function handleAdvancePhase() {
    if (selectedId === null) return;
    void withBusy(() => api.advanceTrackingPhase(token, selectedId));
  }

  async function handleSaveCoResponsible() {
    if (selectedId === null) return;
    setCoResponsibleBusy(true);
    setError("");
    try {
      const updated = await api.setCoResponsible(token, selectedId, coResponsibleSelection);
      setTracking(updated);
      setCoResponsibleSelection(updated.co_responsible_id);
      setSummaries((current) =>
        current.map((item) =>
          item.opportunity_id === selectedId
            ? { ...item, co_responsible_id: updated.co_responsible_id, co_responsible_name: updated.co_responsible_name }
            : item,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el corresponsable");
    } finally {
      setCoResponsibleBusy(false);
    }
  }

  async function handleWithdraw() {
    if (selectedId === null) return;
    setWithdrawing(true);
    setError("");
    try {
      await api.withdrawTracking(token, selectedId);
      setSummaries((current) => current.filter((item) => item.opportunity_id !== selectedId));
      setSelectedId(null);
      setTracking(null);
      setConfirmingWithdraw(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo retirar la oportunidad de seguimiento");
    } finally {
      setWithdrawing(false);
    }
  }

  return (
    <div className="tracking-workspace">
      {error ? <div className="notice danger">{error}</div> : null}
      <div className="tracking-layout">
        <DateRefreshStatusBlock token={token} country={country} />
        <aside className="tracking-selector">
          <input
            type="search"
            placeholder="Buscar por entidad o nomenclatura"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <label className="tracking-mine-toggle" title="Oportunidades que tú enviaste a seguimiento (no incluye las que solo tienes como corresponsable)">
            <input type="checkbox" checked={mineOnly} onChange={(event) => setMineOnly(event.target.checked)} />
            Solo mis oportunidades
          </label>
          {loadingList ? (
            <Empty text="Cargando oportunidades en seguimiento..." />
          ) : filteredSummaries.length ? (
            <ul className="tracking-selector-list">
              {filteredSummaries.map((item) => (
                <li key={item.opportunity_id}>
                  <button
                    type="button"
                    className={item.opportunity_id === selectedId ? "active" : ""}
                    onClick={() => selectOpportunity(item.opportunity_id)}
                  >
                    <strong>{item.nomenclature || `Oportunidad #${item.opportunity_id}`}</strong>
                    <small>{item.entity}</small>
                    {item.co_responsible_name ? (
                      <span className="tracking-selector-co-responsible">✓ Corresponsable: {item.co_responsible_name}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty text="Aún no hay oportunidades enviadas a seguimiento." />
          )}
        </aside>
        <div className="tracking-detail">
          {!selectedId ? (
            <Empty text="Selecciona una oportunidad para ver su seguimiento." />
          ) : loadingDetail || !tracking ? (
            <Empty text="Cargando seguimiento..." />
          ) : (
            <>
              <div className="tracking-detail-header">
                <div className="tracking-detail-header-main">
                  <h3>{selectedSummary?.nomenclature}</h3>
                  <p>{selectedSummary?.entity}</p>
                  {selectedSummary?.description ? <p className="tracking-detail-description">{selectedSummary.description}</p> : null}
                </div>
                <div className="tracking-detail-header-people">
                  <span className="tracking-owner">
                    Responsable: <strong>{tracking.started_by_name || "Sin asignar"}</strong>
                  </span>
                  {canManageCoResponsible ? (
                    <>
                      <label className="tracking-co-responsible">
                        Corresponsable
                        <select
                          value={coResponsibleSelection ?? ""}
                          disabled={coResponsibleBusy}
                          onChange={(event) => setCoResponsibleSelection(event.target.value ? Number(event.target.value) : null)}
                        >
                          <option value="">Sin asignar</option>
                          {assignableUsers.map((user) => (
                            <option key={user.id} value={user.id}>
                              {user.full_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        className="primary tracking-co-responsible-save"
                        disabled={coResponsibleBusy || coResponsibleSelection === tracking.co_responsible_id}
                        onClick={() => void handleSaveCoResponsible()}
                      >
                        {coResponsibleBusy ? "Guardando..." : "Guardar"}
                      </button>
                      {coResponsibleSelection === tracking.co_responsible_id && tracking.co_responsible_id ? (
                        <span className="tracking-co-responsible-status" role="status">
                          ✓ Corresponsable asignado
                        </span>
                      ) : null}
                    </>
                  ) : (
                    <span className="tracking-owner" title="Solo el responsable de la oportunidad puede cambiar al corresponsable">
                      Corresponsable: <strong>{tracking.co_responsible_name || "Sin asignar"}</strong>
                    </span>
                  )}
                  {canManageCoResponsible ? (
                    <button
                      type="button"
                      className="ghost tracking-withdraw-button"
                      disabled={withdrawing}
                      onClick={() => setConfirmingWithdraw(true)}
                      title="Solo el responsable de la oportunidad puede retirarla de seguimiento"
                    >
                      Retirar de seguimiento
                    </button>
                  ) : null}
                </div>
              </div>
              {confirmingWithdraw ? (
                <ConfirmModal
                  title="Retirar de seguimiento"
                  message="¿Está seguro de retirar esta oportunidad del módulo de Seguimiento? Se quitará de la lista, pero el historial de etapas y responsables queda guardado."
                  confirmLabel={withdrawing ? "Retirando..." : "Sí, retirar"}
                  cancelLabel="Cancelar"
                  onConfirm={() => void handleWithdraw()}
                  onCancel={() => setConfirmingWithdraw(false)}
                />
              ) : null}
              <div className="country-config-tabs" role="tablist" aria-label="Fase">
                {phasesWithStages.map(({ phase, started }) => (
                  <button
                    key={phase.id}
                    type="button"
                    role="tab"
                    aria-selected={phase.id === selectedPhaseId}
                    className={phase.id === selectedPhaseId ? "active" : ""}
                    disabled={!started}
                    title={!started ? "Esta fase aún no se ha iniciado" : undefined}
                    onClick={() => setSelectedPhaseId(phase.id)}
                  >
                    {phase.name}
                  </button>
                ))}
              </div>
              <TrackingTimeline
                token={token}
                stages={activeStages}
                areas={areas}
                responsibles={responsibles}
                rangeStart={isCotizacionPhase ? selectedSummary?.publication_date ?? null : null}
                rangeEnd={isCotizacionPhase ? selectedSummary?.proposal_deadline || selectedSummary?.quote_deadline || null : null}
                busy={busy}
                onChangeDueDate={handleChangeDueDate}
                onChangeStatus={handleChangeStatus}
                onChangeAreas={handleChangeAreas}
                onChangeAssignees={handleChangeAssignees}
                onSetOutcome={handleSetOutcome}
                onToggleAlert={handleToggleAlert}
              />
              {isPerfeccionamientoPhase ? (
                <div className="tracking-advance-row">
                  <button className="primary" type="button" disabled={!canAdvance || busy} onClick={handleAdvancePhase}>
                    Avanzar a Implementación
                  </button>
                  {!canAdvance ? <small>Completa todas las etapas de esta fase para avanzar.</small> : null}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

type StageColumn = { phaseId: number; phaseName: string; phaseKey: string; name: string; sortOrder: number };

function buildStageColumns(phases: TrackingPhase[], details: OpportunityTrackingRecord[]): StageColumn[] {
  const columns: StageColumn[] = [];
  const orderedPhases = [...phases].sort((left, right) => left.sort_order - right.sort_order);
  for (const phase of orderedPhases) {
    const uniqueByName = new Map<string, OpportunityTrackingStage>();
    for (const detail of details) {
      for (const stage of detail.stages) {
        if (stage.phase_id === phase.id && !stage.is_outcome_step && !uniqueByName.has(stage.name)) {
          uniqueByName.set(stage.name, stage);
        }
      }
    }
    const orderedStages = [...uniqueByName.values()].sort((left, right) => left.sort_order - right.sort_order);
    for (const stage of orderedStages) {
      columns.push({ phaseId: phase.id, phaseName: phase.name, phaseKey: phase.key, name: stage.name, sortOrder: stage.sort_order });
    }
  }
  return columns;
}

function ConsolidatedView({ token, country }: { token: string; country: "peru" | "chile" }) {
  const [summaries, setSummaries] = useState<OpportunityTrackingSummary[]>([]);
  const [phases, setPhases] = useState<TrackingPhase[]>([]);
  const [details, setDetails] = useState<Map<number, OpportunityTrackingRecord>>(new Map());
  const [opportunities, setOpportunities] = useState<Map<number, Opportunity>>(new Map());
  const [documentsOpportunity, setDocumentsOpportunity] = useState<Opportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [phaseFilter, setPhaseFilter] = useState<number | "all">("all");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([api.opportunityTrackings(token, { country }), api.trackingPhases(token, country), api.opportunities(token)])
      .then(async ([summaryList, phaseList, opportunityList]) => {
        setSummaries(summaryList);
        setPhases(phaseList);
        setOpportunities(new Map(opportunityList.map((item) => [item.id, item])));
        const entries = await Promise.all(
          summaryList.map((item) =>
            api.opportunityTracking(token, item.opportunity_id).then((detail) => [item.opportunity_id, detail] as const),
          ),
        );
        setDetails(new Map(entries));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "No se pudo cargar el consolidado"))
      .finally(() => setLoading(false));
  }, [token, country]);

  const filteredSummaries = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return summaries;
    return summaries.filter(
      (item) => item.entity.toLowerCase().includes(needle) || item.nomenclature.toLowerCase().includes(needle),
    );
  }, [summaries, search]);

  const allStageColumns = useMemo(() => buildStageColumns(phases, [...details.values()]), [phases, details]);
  const stageColumns = useMemo(
    () => (phaseFilter === "all" ? allStageColumns : allStageColumns.filter((column) => column.phaseId === phaseFilter)),
    [allStageColumns, phaseFilter],
  );

  function phaseRangeStartFor(column: StageColumn, summary: OpportunityTrackingSummary): string | null {
    return column.phaseKey === "cotizacion" ? summary.publication_date : null;
  }

  function cellDataFor(column: StageColumn, summary: OpportunityTrackingSummary) {
    const detail = details.get(summary.opportunity_id);
    const phaseStages = (detail?.stages || []).filter((item) => item.phase_id === column.phaseId);
    const stage = phaseStages.find((item) => item.name === column.name);
    if (!stage) return { stage: null, days: null, status: null as TimeStatus | null, effectiveStatus: null as string | null };
    const windowStart = stageWindowStart(phaseStages, stage, phaseRangeStartFor(column, summary));
    return {
      stage,
      days: daysAllocated(stage, windowStart),
      status: computeTimeStatus(stage.due_date, windowStart),
      effectiveStatus: deriveEffectiveStatus(stage, windowStart),
    };
  }

  function timeStatusLabelFor(status: TimeStatus | null, effectiveStatus: string | null): string {
    if (effectiveStatus === "completado") return "Completado";
    if (effectiveStatus === "bloqueado") return "Bloqueado";
    return status ? TIME_STATUS_LABELS[status] : "";
  }

  async function exportToExcel() {
    setExporting(true);
    setError("");
    try {
      const headers = [
        "Entidad",
        "Proceso",
        "Documentos",
        "Descripción",
        "Estado",
        "Fecha de Convocatoria",
        ...stageColumns.flatMap((column) => [
          `${column.phaseName} - ${column.name} - Fecha`,
          `${column.phaseName} - ${column.name} - Días`,
          `${column.phaseName} - ${column.name} - Estado`,
        ]),
        "Fecha Fin Propuesta",
      ];
      const rows = filteredSummaries.map((summary) => {
        const row: Array<string | number | null> = [
          summary.entity,
          summary.nomenclature,
          summary.documents_count,
          summary.description,
          summary.quotation_outcome,
          summary.publication_date ? formatDate(summary.publication_date) : "",
        ];
        for (const column of stageColumns) {
          const { stage, days, status, effectiveStatus } = cellDataFor(column, summary);
          row.push(stage?.due_date ? formatDate(stage.due_date) : "");
          row.push(days ?? "");
          row.push(timeStatusLabelFor(status, effectiveStatus));
        }
        row.push(summary.proposal_deadline ? formatDate(summary.proposal_deadline) : summary.quote_deadline ? formatDate(summary.quote_deadline) : "");
        return row;
      });
      const blob = await api.exportTrackingXlsx(token, { title: "Consolidado de Seguimiento", headers, rows });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `seguimiento-consolidado-${country}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo exportar el archivo");
    } finally {
      setExporting(false);
    }
  }

  if (loading) return <Empty text="Cargando consolidado..." />;

  return (
    <div className="tracking-consolidated">
      {error ? <div className="notice danger">{error}</div> : null}
      <div className="tracking-consolidated-toolbar">
        <input
          type="search"
          placeholder="Buscar por entidad o nomenclatura"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select value={phaseFilter} onChange={(event) => setPhaseFilter(event.target.value === "all" ? "all" : Number(event.target.value))}>
          <option value="all">Todas las fases</option>
          {phases.map((phase) => (
            <option key={phase.id} value={phase.id}>
              {phase.name}
            </option>
          ))}
        </select>
        <button type="button" className="export-excel-button" disabled={exporting || !filteredSummaries.length} onClick={() => void exportToExcel()}>
          <img src={excelLogoUrl} alt="" aria-hidden="true" loading="lazy" decoding="async" />
          <span>{exporting ? "Exportando..." : "Exportar a Excel"}</span>
        </button>
      </div>
      {!filteredSummaries.length ? (
        <Empty text="No hay oportunidades en seguimiento que coincidan con el filtro." />
      ) : (
        <div className="table-scroll tracking-consolidated-table-wrap">
          <table className="tracking-consolidated-table">
            <thead>
              <tr>
                <th rowSpan={2}>Entidad</th>
                <th rowSpan={2}>Proceso</th>
                <th rowSpan={2}>Documentos</th>
                <th rowSpan={2}>Descripción</th>
                <th rowSpan={2}>Estado</th>
                <th rowSpan={2}>Fecha de Convocatoria</th>
                {stageColumns.map((column) => (
                  <th key={`${column.phaseId}-${column.name}`} colSpan={3} className="tracking-consolidated-stage-head">
                    {column.phaseName}: {column.name}
                  </th>
                ))}
                <th rowSpan={2}>Fecha Fin Propuesta</th>
              </tr>
              <tr>
                {stageColumns.map((column) => (
                  <React.Fragment key={`${column.phaseId}-${column.name}-sub`}>
                    <th>Fecha</th>
                    <th>Días</th>
                    <th>Estado</th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredSummaries.map((summary) => (
                <tr key={summary.opportunity_id}>
                  <td>{summary.entity}</td>
                  <td>{summary.nomenclature}</td>
                  <td>
                    {opportunities.get(summary.opportunity_id) ? (
                      <button
                        type="button"
                        className="pdf-button"
                        title="Ver detalle y documentos"
                        onClick={() => setDocumentsOpportunity(opportunities.get(summary.opportunity_id) ?? null)}
                      >
                        <span>PDF</span>
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="tracking-consolidated-description" title={summary.description}>
                    {summary.description || "—"}
                  </td>
                  <td>
                    <span className={`tracking-outcome-pill outcome-${summary.quotation_outcome}`}>
                      {summary.quotation_outcome === "ganado" ? "Ganado" : summary.quotation_outcome === "perdido" ? "Perdido" : "Pendiente"}
                    </span>
                  </td>
                  <td>{summary.publication_date ? formatDate(summary.publication_date) : "—"}</td>
                  {stageColumns.map((column) => {
                    const { stage, days, status, effectiveStatus } = cellDataFor(column, summary);
                    return (
                      <React.Fragment key={`${column.phaseId}-${column.name}-${summary.opportunity_id}`}>
                        <td>{stage?.due_date ? formatDate(stage.due_date) : "—"}</td>
                        <td>{days ?? "—"}</td>
                        <td>
                          {effectiveStatus === "completado" ? (
                            <span className="tracking-time-status status-on_time">Completado</span>
                          ) : effectiveStatus === "bloqueado" ? (
                            <span className="tracking-time-status status-vencido">Bloqueado</span>
                          ) : status ? (
                            <TimeStatusBadge status={status} />
                          ) : (
                            "—"
                          )}
                        </td>
                      </React.Fragment>
                    );
                  })}
                  <td>
                    {summary.proposal_deadline
                      ? formatDate(summary.proposal_deadline)
                      : summary.quote_deadline
                        ? formatDate(summary.quote_deadline)
                        : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {documentsOpportunity ? (
        <OpportunityDetailModal opportunity={documentsOpportunity} token={token} onClose={() => setDocumentsOpportunity(null)} />
      ) : null}
    </div>
  );
}

const emptyResponsibleForm: TrackingResponsiblePayload = {
  full_name: "",
  email: "",
  country_scope: "ambos",
  is_active: true,
  area_ids: [],
};

function StageTemplateEditor({
  token,
  phase,
  areas,
  stages,
  onChanged,
  isAdmin,
}: {
  token: string;
  phase: TrackingPhase;
  areas: TrackingArea[];
  stages: TrackingStageTemplate[];
  onChanged: () => Promise<void>;
  isAdmin: boolean;
}) {
  const [newName, setNewName] = useState("");
  const [newAreaIds, setNewAreaIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editingStageId, setEditingStageId] = useState<number | null>(null);
  const [stageDraftName, setStageDraftName] = useState("");
  const [stageDraftAreaIds, setStageDraftAreaIds] = useState<number[]>([]);

  function toggleNewAreaId(areaId: number) {
    setNewAreaIds((current) => (current.includes(areaId) ? current.filter((id) => id !== areaId) : [...current, areaId]));
  }

  function toggleStageDraftAreaId(areaId: number) {
    setStageDraftAreaIds((current) => (current.includes(areaId) ? current.filter((id) => id !== areaId) : [...current, areaId]));
  }

  function startEditStage(stage: TrackingStageTemplate) {
    setEditingStageId(stage.id);
    setStageDraftName(stage.name);
    setStageDraftAreaIds(stage.areas.map((area) => area.id));
    setError("");
  }

  function cancelEditStage() {
    setEditingStageId(null);
    setError("");
  }

  async function addStage() {
    if (!newName.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.createStageTemplate(token, phase.id, { name: newName.trim(), sort_order: stages.length, area_ids: newAreaIds });
      setNewName("");
      setNewAreaIds([]);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo agregar la etapa");
    } finally {
      setBusy(false);
    }
  }

  async function saveStageEdit(stage: TrackingStageTemplate) {
    if (!stageDraftName.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.updateStageTemplate(token, stage.id, { name: stageDraftName.trim(), area_ids: stageDraftAreaIds });
      setEditingStageId(null);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la etapa");
    } finally {
      setBusy(false);
    }
  }

  async function deactivateStage(stage: TrackingStageTemplate) {
    setBusy(true);
    setError("");
    try {
      await api.deleteStageTemplate(token, stage.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo desactivar la etapa");
    } finally {
      setBusy(false);
    }
  }

  async function moveStage(stage: TrackingStageTemplate, direction: -1 | 1) {
    const ordered = [...stages].sort((left, right) => left.sort_order - right.sort_order);
    const index = ordered.findIndex((item) => item.id === stage.id);
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= ordered.length) return;
    const reordered = [...ordered];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    setBusy(true);
    setError("");
    try {
      await api.reorderStageTemplates(token, reordered.map((item) => item.id));
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo reordenar");
    } finally {
      setBusy(false);
    }
  }

  const orderedStages = [...stages].sort((left, right) => left.sort_order - right.sort_order);

  return (
    <div className="tracking-stage-template-group">
      <h4>{phase.name}</h4>
      {error ? <small className="tracking-templates-error" role="alert">{error}</small> : null}
      <ul className="tracking-stage-template-list">
        {orderedStages.map((stage, index) => {
          const isEditing = isAdmin && editingStageId === stage.id;
          return (
            <li key={stage.id} className={isEditing ? "editing" : ""}>
              {isEditing ? (
                <div className="tracking-stage-template-edit">
                  <input
                    value={stageDraftName}
                    disabled={busy}
                    onChange={(event) => setStageDraftName(event.target.value)}
                    autoFocus
                  />
                  <div className="tracking-area-checklist">
                    {areas.map((area) => (
                      <label key={area.id}>
                        <input
                          type="checkbox"
                          checked={stageDraftAreaIds.includes(area.id)}
                          onChange={() => toggleStageDraftAreaId(area.id)}
                        />
                        {area.name}
                      </label>
                    ))}
                  </div>
                  <div className="tracking-row-actions">
                    <button type="button" className="ghost" disabled={busy} onClick={cancelEditStage}>Cancelar</button>
                    <button type="button" className="primary" disabled={busy || !stageDraftName.trim()} onClick={() => saveStageEdit(stage)}>
                      {busy ? "Guardando..." : "Guardar"}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <span>{stage.name}</span>
                  <span className="tracking-stage-template-areas">{stage.areas.map((area) => area.name).join(", ") || "Sin área"}</span>
                  {isAdmin ? (
                    <div className="tracking-stage-template-actions">
                      <button type="button" className="ghost" disabled={busy} onClick={() => startEditStage(stage)}>Editar</button>
                      <button type="button" className="ghost" disabled={busy || index === 0} onClick={() => moveStage(stage, -1)}>↑</button>
                      <button type="button" className="ghost" disabled={busy || index === orderedStages.length - 1} onClick={() => moveStage(stage, 1)}>↓</button>
                      <button type="button" className="ghost" disabled={busy} onClick={() => deactivateStage(stage)}>Desactivar</button>
                    </div>
                  ) : null}
                </>
              )}
            </li>
          );
        })}
      </ul>
      {isAdmin ? (
        <div className="tracking-stage-template-new">
          <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Nueva etapa" disabled={busy} />
          <div className="tracking-area-checklist">
            {areas.map((area) => (
              <label key={area.id}>
                <input type="checkbox" checked={newAreaIds.includes(area.id)} onChange={() => toggleNewAreaId(area.id)} />
                {area.name}
              </label>
            ))}
          </div>
          <button type="button" className="primary" disabled={busy || !newName.trim()} onClick={addStage}>Agregar etapa</button>
        </div>
      ) : null}
    </div>
  );
}

function ResponsiblesAdmin({ token, country, isAdmin }: { token: string; country: "peru" | "chile"; isAdmin: boolean }) {
  const [areas, setAreas] = useState<TrackingArea[]>([]);
  const [allAreas, setAllAreas] = useState<TrackingArea[]>([]);
  const [responsibles, setResponsibles] = useState<TrackingResponsible[]>([]);
  const [phases, setPhases] = useState<TrackingPhase[]>([]);
  const [stageTemplatesByPhase, setStageTemplatesByPhase] = useState<Map<number, TrackingStageTemplate[]>>(new Map());
  const [form, setForm] = useState<TrackingResponsiblePayload>(emptyResponsibleForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [newAreaName, setNewAreaName] = useState("");
  const [areaBusy, setAreaBusy] = useState(false);
  const [areaError, setAreaError] = useState("");
  const [editingAreaId, setEditingAreaId] = useState<number | null>(null);
  const [areaDraftName, setAreaDraftName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [areaList, allAreaList, responsibleList, phaseList] = await Promise.all([
        api.trackingAreas(token),
        api.trackingAreas(token, { activeOnly: false }),
        api.trackingResponsibles(token, { activeOnly: false, country }),
        api.trackingPhases(token, country),
      ]);
      setAreas(areaList);
      setAllAreas(allAreaList);
      setResponsibles(responsibleList);
      setPhases(phaseList);
      const templateEntries = await Promise.all(
        phaseList.map((phase) => api.trackingStageTemplates(token, phase.id).then((stages) => [phase.id, stages] as const)),
      );
      setStageTemplatesByPhase(new Map(templateEntries));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la información");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, [token, country]);

  async function addArea() {
    if (!newAreaName.trim()) return;
    setAreaBusy(true);
    setAreaError("");
    try {
      await api.createTrackingArea(token, { name: newAreaName.trim(), sort_order: allAreas.length });
      setNewAreaName("");
      await loadAll();
    } catch (err) {
      setAreaError(err instanceof Error ? err.message : "No se pudo crear el área");
    } finally {
      setAreaBusy(false);
    }
  }

  function startEditArea(area: TrackingArea) {
    setEditingAreaId(area.id);
    setAreaDraftName(area.name);
    setAreaError("");
  }

  function cancelEditArea() {
    setEditingAreaId(null);
    setAreaError("");
  }

  async function saveAreaEdit(area: TrackingArea) {
    if (!areaDraftName.trim()) return;
    setAreaBusy(true);
    setAreaError("");
    try {
      await api.updateTrackingArea(token, area.id, { name: areaDraftName.trim() });
      setEditingAreaId(null);
      await loadAll();
    } catch (err) {
      setAreaError(err instanceof Error ? err.message : "No se pudo renombrar el área");
    } finally {
      setAreaBusy(false);
    }
  }

  async function toggleAreaActive(area: TrackingArea) {
    setAreaBusy(true);
    setAreaError("");
    try {
      await api.updateTrackingArea(token, area.id, { is_active: !area.is_active });
      await loadAll();
    } catch (err) {
      setAreaError(err instanceof Error ? err.message : "No se pudo actualizar el área");
    } finally {
      setAreaBusy(false);
    }
  }

  function updateField<K extends keyof TrackingResponsiblePayload>(field: K, value: TrackingResponsiblePayload[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setError("");
    setSuccess("");
  }

  function toggleAreaId(areaId: number) {
    setForm((current) => ({
      ...current,
      area_ids: current.area_ids.includes(areaId) ? current.area_ids.filter((id) => id !== areaId) : [...current.area_ids, areaId],
    }));
  }

  function resetForm() {
    setForm(emptyResponsibleForm);
    setEditingId(null);
    setError("");
    setSuccess("");
  }

  function editResponsible(responsible: TrackingResponsible) {
    setEditingId(responsible.id);
    setForm({
      full_name: responsible.full_name,
      email: responsible.email,
      country_scope: responsible.country_scope,
      is_active: responsible.is_active,
      area_ids: responsible.areas.map((area) => area.id),
    });
  }

  async function submitForm(event: React.FormEvent) {
    event.preventDefault();
    if (!form.full_name.trim() || !form.email.trim() || !form.area_ids.length) {
      setError("Completa nombre, correo y al menos un área");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      if (editingId) {
        await api.updateTrackingResponsible(token, editingId, form);
        setSuccess("Responsable actualizado");
      } else {
        await api.createTrackingResponsible(token, form);
        setSuccess("Responsable creado");
      }
      resetForm();
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el responsable");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(responsible: TrackingResponsible) {
    setError("");
    try {
      await api.updateTrackingResponsible(token, responsible.id, { is_active: !responsible.is_active });
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el estado");
    }
  }

  if (loading) return <Empty text="Cargando..." />;

  return (
    <div className="tracking-responsibles-admin">
      {error ? <div className="notice danger">{error}</div> : null}
      {success ? <div className="notice success">{success}</div> : null}
      <div className="panel tracking-areas-admin">
        <h3>Áreas</h3>
        <p>
          {isAdmin
            ? "Agrega áreas nuevas (por ejemplo, \"Legal\") para poder asignarlas a responsables y etapas."
            : "Áreas disponibles para asignar en las etapas. Solo un administrador puede crear o editar áreas."}
        </p>
        {areaError ? <small className="tracking-templates-error" role="alert">{areaError}</small> : null}
        <ul className="tracking-area-admin-list">
          {allAreas.map((area) => {
            const isEditing = isAdmin && editingAreaId === area.id;
            return (
              <li key={area.id} className={`${area.is_active ? "" : "inactive-row"} ${isEditing ? "editing" : ""}`}>
                {isEditing ? (
                  <input
                    value={areaDraftName}
                    disabled={areaBusy}
                    onChange={(event) => setAreaDraftName(event.target.value)}
                    autoFocus
                  />
                ) : (
                  <span>{area.name}</span>
                )}
                <span className={`tracking-status-pill ${area.is_active ? "status-completado" : "status-pendiente"}`}>
                  {area.is_active ? "Activa" : "Inactiva"}
                </span>
                {isAdmin ? (
                  isEditing ? (
                    <div className="tracking-row-actions">
                      <button type="button" className="ghost" disabled={areaBusy} onClick={cancelEditArea}>Cancelar</button>
                      <button type="button" className="primary" disabled={areaBusy || !areaDraftName.trim()} onClick={() => saveAreaEdit(area)}>
                        {areaBusy ? "Guardando..." : "Guardar"}
                      </button>
                    </div>
                  ) : (
                    <div className="tracking-row-actions">
                      <button type="button" className="ghost" disabled={areaBusy} onClick={() => startEditArea(area)}>Editar</button>
                      <button type="button" className="ghost" disabled={areaBusy} onClick={() => toggleAreaActive(area)}>
                        {area.is_active ? "Desactivar" : "Activar"}
                      </button>
                    </div>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
        {isAdmin ? (
          <div className="tracking-area-admin-new">
            <input
              value={newAreaName}
              onChange={(event) => setNewAreaName(event.target.value)}
              placeholder="Nueva área, ej. Legal"
              disabled={areaBusy}
            />
            <button type="button" className="primary" disabled={areaBusy || !newAreaName.trim()} onClick={addArea}>
              Agregar área
            </button>
          </div>
        ) : null}
      </div>
      <div className="tracking-admin-grid" style={isAdmin ? undefined : { gridTemplateColumns: "1fr" }}>
        {isAdmin ? (
          <form className="panel tracking-responsible-form" onSubmit={submitForm}>
            <h3>{editingId ? "Editar responsable" : "Nuevo responsable"}</h3>
            <label>Nombre completo<input value={form.full_name} onChange={(event) => updateField("full_name", event.target.value)} required /></label>
            <label>Correo<input type="email" value={form.email} onChange={(event) => updateField("email", event.target.value)} required /></label>
            <label>
              País
              <select value={form.country_scope} onChange={(event) => updateField("country_scope", event.target.value as CountryScope)}>
                <option value="ambos">Perú y Chile</option>
                <option value="peru">Perú</option>
                <option value="chile">Chile</option>
              </select>
            </label>
            <fieldset className="tracking-area-checklist">
              <legend>Áreas</legend>
              {areas.map((area) => (
                <label key={area.id}>
                  <input type="checkbox" checked={form.area_ids.includes(area.id)} onChange={() => toggleAreaId(area.id)} />
                  {area.name}
                </label>
              ))}
            </fieldset>
            <label className="tracking-active-toggle">
              <input type="checkbox" checked={form.is_active} onChange={(event) => updateField("is_active", event.target.checked)} />
              Activo
            </label>
            <div className="tracking-form-actions">
              {editingId ? <button type="button" className="ghost" onClick={resetForm}>Cancelar</button> : null}
              <button type="submit" className="primary" disabled={saving}>
                {saving ? "Guardando..." : editingId ? "Guardar cambios" : "Crear responsable"}
              </button>
            </div>
          </form>
        ) : null}
        <div className="panel tracking-responsible-list">
          <h3>Responsables</h3>
          {!isAdmin ? <p>Solo un administrador puede agregar o editar responsables.</p> : null}
          <div className="table-scroll">
            <table>
              <thead><tr><th>Nombre</th><th>Correo</th><th>País</th><th>Áreas</th><th>Estado</th>{isAdmin ? <th></th> : null}</tr></thead>
              <tbody>
                {responsibles.map((responsible) => (
                  <tr key={responsible.id} className={responsible.is_active ? "" : "inactive-row"}>
                    <td>{responsible.full_name}</td>
                    <td>{responsible.email}</td>
                    <td>
                      <span className={`tracking-country-pill country-${responsible.country_scope}`}>
                        {countryScopeLabel(responsible.country_scope)}
                      </span>
                    </td>
                    <td>{responsible.areas.map((area) => area.name).join(", ") || "-"}</td>
                    <td>
                      <span className={`tracking-status-pill ${responsible.is_active ? "status-completado" : "status-pendiente"}`}>
                        {responsible.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    {isAdmin ? (
                      <td>
                        <div className="tracking-row-actions">
                          <button className="ghost" type="button" onClick={() => editResponsible(responsible)}>Editar</button>
                          <button className="ghost" type="button" onClick={() => toggleActive(responsible)}>
                            {responsible.is_active ? "Desactivar" : "Activar"}
                          </button>
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div className="panel tracking-templates-admin">
        <h3>Etapas por fase ({country === "peru" ? "Perú" : "Chile"})</h3>
        <p>
          Estas etapas son independientes de las de {country === "peru" ? "Chile" : "Perú"}.
          {!isAdmin ? " Solo un administrador puede agregar, renombrar o reordenar etapas." : ""}
        </p>
        {phases.map((phase) => (
          <StageTemplateEditor
            key={phase.id}
            token={token}
            phase={phase}
            areas={areas}
            stages={stageTemplatesByPhase.get(phase.id) || []}
            onChanged={loadAll}
            isAdmin={isAdmin}
          />
        ))}
      </div>
    </div>
  );
}

type TopTab = "seguimiento" | "consolidado" | "responsables";

function OpportunityTrackingCountry({
  token,
  isAdmin,
  currentUserId,
  country,
}: {
  token: string;
  isAdmin: boolean;
  currentUserId: number;
  country: "peru" | "chile";
}) {
  const [topTab, setTopTab] = useState<TopTab>("seguimiento");
  const countryLabel = country === "peru" ? "Perú" : "Chile";

  return (
    <section className="panel tracking-page">
      <div className="panel-title">
        <div>
          <h2>Seguimiento de Oportunidades {countryLabel}</h2>
          <p>Gestiona cada oportunidad de {countryLabel} enviada a seguimiento a través de sus fases, etapas y responsables.</p>
        </div>
      </div>
      <div className="country-config-tabs" role="tablist" aria-label="Sección">
        <button type="button" role="tab" aria-selected={topTab === "seguimiento"} className={topTab === "seguimiento" ? "active" : ""} onClick={() => setTopTab("seguimiento")}>
          Seguimiento
        </button>
        <button type="button" role="tab" aria-selected={topTab === "consolidado"} className={topTab === "consolidado" ? "active" : ""} onClick={() => setTopTab("consolidado")}>
          Consolidado
        </button>
        <button type="button" role="tab" aria-selected={topTab === "responsables"} className={topTab === "responsables" ? "active" : ""} onClick={() => setTopTab("responsables")}>
          Áreas y Responsables
        </button>
      </div>
      {topTab === "seguimiento" ? (
        <TrackingWorkspace token={token} country={country} currentUserId={currentUserId} />
      ) : topTab === "consolidado" ? (
        <ConsolidatedView token={token} country={country} />
      ) : (
        <ResponsiblesAdmin token={token} country={country} isAdmin={isAdmin} />
      )}
    </section>
  );
}

export function OpportunityTrackingPeru({ token, isAdmin, currentUserId }: { token: string; isAdmin: boolean; currentUserId: number }) {
  return <OpportunityTrackingCountry token={token} isAdmin={isAdmin} currentUserId={currentUserId} country="peru" />;
}

export default function OpportunityTrackingChile({ token, isAdmin, currentUserId }: { token: string; isAdmin: boolean; currentUserId: number }) {
  return <OpportunityTrackingCountry token={token} isAdmin={isAdmin} currentUserId={currentUserId} country="chile" />;
}
