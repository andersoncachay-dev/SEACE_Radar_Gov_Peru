import React, { useRef, useState } from "react";
import { api, Alert, AlertRule } from "../api";
import { CountryFlagIcon, Empty } from "../shared";

export function ruleCountryFlags(country: string): Array<"Peru" | "Chile"> {
  if (country === "peru") return ["Peru"];
  if (country === "chile") return ["Chile"];
  return ["Peru", "Chile"];
}

export type AlertChannel = "email" | "whatsapp" | "in_app";

export type PhoneCountry = "Peru" | "Chile";

export type RuleCountry = "peru" | "chile" | "both";

export const ruleCountryOptions: Array<{ value: RuleCountry; label: string }> = [
  { value: "both", label: "Ambos" },
  { value: "peru", label: "Perú" },
  { value: "chile", label: "Chile" },
];

export function ruleCountryLabel(value: string) {
  if (value === "peru") return "Perú";
  if (value === "chile") return "Chile";
  return "Ambos países";
}

export const alertChannelOptions: Array<{ value: AlertChannel; label: string; description: string }> = [
  { value: "email", label: "Correo", description: "Entrega a una dirección de email" },
  { value: "whatsapp", label: "WhatsApp", description: "Envía al celular de Perú o Chile" },
  { value: "in_app", label: "En GovRadar", description: "Notificación dentro de la plataforma" },
];

export function alertTypeLabel(value: string) {
  if (value === "priority_match") return "Coincidencia de prioridad";
  if (value === "new_process") return "Nuevo proceso";
  if (value === "deadline") return "Vencimiento próximo";
  return value.replaceAll("_", " ");
}

export function alertStatusLabel(value: string) {
  if (value === "sent") return "Enviado";
  if (value === "pending") return "Pendiente";
  if (value === "error") return "Error de envío";
  if (value === "retrying") return "Reintentando";
  if (value === "failed") return "Falló definitivamente";
  if (value === "waiting_channel") return "Esperando habilitación";
  if (value === "skipped") return "Omitido";
  return value;
}

export function ruleChannelLabel(value: string) {
  if (value === "whatsapp") return "WhatsApp";
  if (["in_app", "message", "mensaje"].includes(value)) return "GovRadar";
  return "Correo";
}

export function formatRuleDestination(rule: AlertRule) {
  if (["in_app", "message", "mensaje"].includes(rule.channel)) return "Notificación interna";
  if (rule.channel !== "whatsapp") return rule.destination;
  const digits = rule.destination.replace(/\D/g, "");
  if (digits.startsWith("51") && digits.length === 11) return `+51 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  if (digits.startsWith("56") && digits.length === 11) return `+56 ${digits.slice(2, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`;
  return rule.destination;
}

export function ChannelSymbol({ channel }: { channel: string }) {
  if (channel === "whatsapp") {
    return <span className="channel-symbol whatsapp" aria-hidden="true"><img src="/assets/logowhatsapp.png" alt="" loading="lazy" decoding="async" /></span>;
  }
  return <span className={`channel-symbol ${channel}`} aria-hidden="true">{channel === "email" ? "@" : "R"}</span>;
}

export function RuleActionIcon({ name }: { name: "edit" | "pause" | "play" | "delete" }) {
  if (name === "edit") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-4-3L4 17v3Z" /><path d="m13.5 7.5 3 3" /></svg>;
  }
  if (name === "pause") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14" /><path d="M16 5v14" /></svg>;
  }
  if (name === "play") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5l12 7-12 7V5Z" /></svg>;
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>;
}

export function Alerts({ token, rules, alerts, refresh }: { token: string; rules: AlertRule[]; alerts: Alert[]; refresh: () => Promise<void> }) {
  const [channel, setChannel] = useState<AlertChannel>("email");
  const [ruleName, setRuleName] = useState("");
  const [emailDestination, setEmailDestination] = useState("");
  const [phoneCountry, setPhoneCountry] = useState<PhoneCountry>("Peru");
  const [localPhone, setLocalPhone] = useState("");
  const [keywords, setKeywords] = useState("");
  const [ruleCountry, setRuleCountry] = useState<RuleCountry>("both");
  const [activityCountry, setActivityCountry] = useState<RuleCountry>("both");
  const [saving, setSaving] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<number | null>(null);
  const [togglingRuleId, setTogglingRuleId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  // La prioridad ya no se elige en el formulario: las reglas se delimitan
  // solo por palabras clave, así que toda regla acepta cualquier prioridad.
  const ALL_PRIORITIES = "C";

  const phonePrefix = phoneCountry === "Peru" ? "+51" : "+56";
  const phoneDigits = localPhone.replace(/\D/g, "").slice(0, 9);
  const generatedRuleName = channel === "email"
    ? "Correo · alerta de negocio"
    : channel === "whatsapp"
      ? `WhatsApp ${phoneCountry === "Peru" ? "Perú" : "Chile"} · alerta de negocio`
      : "GovRadar · alerta de negocio";

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
    setRuleCountry("both");
    setError("");
  }

  function startEditingRule(rule: AlertRule) {
    const nextChannel = (["email", "whatsapp", "in_app"].includes(rule.channel) ? rule.channel : "email") as AlertChannel;
    setEditingRuleId(rule.id);
    setChannel(nextChannel);
    setRuleName(rule.name);
    setKeywords(rule.keywords || "");
    setRuleCountry((rule.country as RuleCountry) || "both");
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
        min_priority: ALL_PRIORITIES,
        country: ruleCountry,
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

  async function toggleRuleActive(rule: AlertRule) {
    setTogglingRuleId(rule.id);
    setError("");
    setSuccess("");
    try {
      await api.updateAlertRule(token, rule.id, { is_active: !rule.is_active });
      await refresh();
      setSuccess(`Regla “${rule.name}” ${rule.is_active ? "pausada" : "reactivada"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la regla de alerta");
    } finally {
      setTogglingRuleId(null);
    }
  }

  const visibleAlerts = activityCountry === "both" ? alerts : alerts.filter((alert) => alert.country === activityCountry);
  const errorCount = visibleAlerts.filter((alert) => ["error", "retrying", "failed"].includes(alert.status)).length;
  const sentCount = visibleAlerts.filter((alert) => alert.status === "sent").length;
  const waitingCount = visibleAlerts.filter((alert) => alert.status === "waiting_channel").length;

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
              <label>Correo de destino<input required type="email" autoComplete="email" value={emailDestination} onChange={(event) => setEmailDestination(event.target.value)} placeholder="equipo.comercial@empresa.com" /></label>
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
            <label>País de los procesos<select value={ruleCountry} onChange={(event) => setRuleCountry(event.target.value as RuleCountry)}>
              {ruleCountryOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
            </select></label>
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
                <span className="rule-country-flags">
                  {ruleCountryFlags(rule.country).map((flag) => <CountryFlagIcon country={flag} className="rule-country-flag-image" key={flag} />)}
                </span>
                <ChannelSymbol channel={rule.channel} />
                <div className="alert-rule-copy"><strong>{rule.name}</strong><span>{ruleChannelLabel(rule.channel)} · {formatRuleDestination(rule)} · <span className={`rule-country-badge ${rule.country}`}>{ruleCountryLabel(rule.country)}</span></span><small>Descripción: {rule.keywords || "cualquier descripción"}</small></div>
                <div className="alert-rule-controls">
                  <span className={`account-status ${rule.is_active ? "active" : "blocked"}`}>{rule.is_active ? "Activa" : "Inactiva"}</span>
                  <button type="button" className="rule-action-button" onClick={() => startEditingRule(rule)} aria-label={`Editar regla ${rule.name}`} title="Editar"><RuleActionIcon name="edit" /></button>
                  <button type="button" className={`rule-action-button ${rule.is_active ? "amber" : ""}`} onClick={() => toggleRuleActive(rule)} disabled={togglingRuleId === rule.id} aria-label={rule.is_active ? `Pausar regla ${rule.name}` : `Reactivar regla ${rule.name}`} title={rule.is_active ? "Pausar" : "Reactivar"}><RuleActionIcon name={rule.is_active ? "pause" : "play"} /></button>
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
        <div className="activity-country-filter" role="tablist" aria-label="Filtrar actividad por país">
          {ruleCountryOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={activityCountry === option.value}
              className={activityCountry === option.value ? "selected" : ""}
              onClick={() => setActivityCountry(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="alert-event-list">
          {visibleAlerts.map((alert) => (
            <article className="alert-event-row" key={alert.id}>
              <span className={`event-status-dot ${alert.status}`} aria-hidden="true" />
              <div><strong>{alertTypeLabel(alert.alert_type)}</strong><small><span className={`event-country-tag ${alert.country}`}>{alert.country === "chile" ? "Chile" : "Perú"}</span> · Regla #{alert.rule_id} · Oportunidad #{alert.opportunity_id}{alert.attempt_count ? ` · Intento ${alert.attempt_count}` : ""}</small></div>
              <span className={`event-status-label ${alert.status}`}>{alertStatusLabel(alert.status)}</span>
            </article>
          ))}
          {!visibleAlerts.length ? <Empty text="Las alertas aparecerán cuando una regla coincida con procesos nuevos o vencimientos." /> : null}
        </div>
      </article>
    </section>
  );
}

export default Alerts;
