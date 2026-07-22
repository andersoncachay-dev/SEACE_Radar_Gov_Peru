import React, { useEffect, useRef, useState } from "react";
import { api, LegalDocumentRecord, RadarKeyword, Run, SchedulerIntervalConfig, TrackingDateRefreshStatus } from "../api";
import { ConfidentialityContent, Country, Empty, LegalDialog, LegalDocumentsMap, LegalView, LockIcon, formatDate, updateIntervalLabel, useRadarKeywords } from "../shared";

export function SchedulerScheduleAdmin({ token }: { token: string }) {
  const [configs, setConfigs] = useState<Record<"peru" | "chile", SchedulerIntervalConfig | null>>({ peru: null, chile: null });
  const [savingCountry, setSavingCountry] = useState<"peru" | "chile" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all((["peru", "chile"] as const).map((country) => api.schedulerIntervalConfig(token, country)))
      .then(([peru, chile]) => { if (active) setConfigs({ peru, chile }); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "No se pudo cargar la programación automática"); });
    return () => { active = false; };
  }, [token]);

  function updateValue(country: "peru" | "chile", field: "days" | "hours" | "minutes", value: number) {
    setConfigs((current) => {
      const existing = current[country];
      if (!existing) return current;
      const updated = { ...existing, [field]: value };
      updated.interval_seconds = updated.days * 86_400 + updated.hours * 3_600 + updated.minutes * 60;
      return { ...current, [country]: updated };
    });
    setNotice("");
    setError("");
  }

  async function save(country: "peru" | "chile") {
    const config = configs[country];
    if (!config) return;
    if (config.days === 0 && config.hours === 0 && config.minutes === 0) {
      setError("El intervalo debe ser de al menos un minuto.");
      return;
    }
    setSavingCountry(country);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateSchedulerIntervalConfig(token, country, config);
      setConfigs((current) => ({ ...current, [country]: updated }));
      setNotice(`Programación de ${country === "peru" ? "Perú" : "Chile"} actualizada. La próxima ejecución ya usa el nuevo intervalo.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la programación");
    } finally {
      setSavingCountry(null);
    }
  }

  return (
    <section className="panel scheduler-admin-panel" aria-labelledby="scheduler-admin-title">
      <div className="scheduler-admin-heading">
        <div>
          <p className="overline">Automatización por país</p>
          <h2 id="scheduler-admin-title">Configuración del rango de updates automáticos</h2>
          <p>Define cada cuánto se ejecutará el radar. El cambio actualiza de inmediato Inicio y la cuenta regresiva de Última ejecución.</p>
        </div>
      </div>
      <div className="scheduler-country-grid">
        {(["peru", "chile"] as const).map((country) => {
          const config = configs[country];
          const label = country === "peru" ? "Perú" : "Chile";
          return (
            <article className="scheduler-country-config" key={country} aria-busy={!config}>
              <div className="scheduler-country-heading"><strong>{label}</strong><span>{config ? `Cada ${updateIntervalLabel(config.interval_seconds)}` : "Cargando…"}</span></div>
              {config ? <>
                <div className="scheduler-duration-fields">
                  <label>Días<input type="number" min="0" max="30" value={config.days} onChange={(event) => updateValue(country, "days", Math.max(0, Math.min(30, Number(event.target.value))))} /></label>
                  <label>Horas<input type="number" min="0" max="23" value={config.hours} onChange={(event) => updateValue(country, "hours", Math.max(0, Math.min(23, Number(event.target.value))))} /></label>
                  <label>Minutos<input type="number" min="0" max="59" value={config.minutes} onChange={(event) => updateValue(country, "minutes", Math.max(0, Math.min(59, Number(event.target.value))))} /></label>
                </div>
                <div className="scheduler-country-actions">
                  <small>{config.next_update_at ? `Próximo update: ${new Date(config.next_update_at).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" })}` : "El scheduler se encuentra pausado"}</small>
                  <button className="primary" type="button" onClick={() => save(country)} disabled={savingCountry !== null}>{savingCountry === country ? "Guardando…" : `Guardar ${label}`}</button>
                </div>
              </> : <p>Cargando configuración…</p>}
            </article>
          );
        })}
      </div>
      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {notice ? <div className="notice success" role="status">{notice}</div> : null}
    </section>
  );
}

export function RadarKeywordsAdmin({
  token,
  onOpenLegal,
  onSearchKeyword,
}: {
  token: string;
  onOpenLegal: (view: LegalView) => void;
  onSearchKeyword: (country: Country, keyword: string) => void;
}) {
  const [keywordCountry, setKeywordCountry] = useState<Country>("Peru");
  const [newKeyword, setNewKeyword] = useState("");
  const [keywordSaving, setKeywordSaving] = useState(false);
  const [keywordNotice, setKeywordNotice] = useState("");
  const radarKeywordState = useRadarKeywords(token, keywordCountry);

  useEffect(() => {
    setNewKeyword("");
    setKeywordNotice("");
  }, [keywordCountry]);

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
      setKeywordNotice(`“${cleanKeyword}” se agregó a ${keywordCountry}.`);
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

  return (
    <section className="panel keyword-manager-panel" aria-labelledby="keyword-manager-title">
      <div className="keyword-manager-heading">
        <div>
          <p className="overline">Radar automático</p>
          <h2 id="keyword-manager-title">Palabras clave de {keywordCountry === "Peru" ? "Perú" : "Chile"}</h2>
          <p>Todas las palabras son editables. Retirarlas no borra los procesos históricos ya detectados.</p>
        </div>
        <div className="country-config-tabs" role="tablist" aria-label="País a configurar">
          {(["Peru", "Chile"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={keywordCountry === option}
              className={keywordCountry === option ? "active" : ""}
              onClick={() => setKeywordCountry(option)}
            >
              {option === "Peru" ? "Perú" : "Chile"}
            </button>
          ))}
        </div>
      </div>
      {radarKeywordState.loading ? <span className="keyword-loading">Actualizando…</span> : null}
      <div className="keyword-chip-list">
        {radarKeywordState.keywords.map((item) => (
          <span className="keyword-config-chip" key={`${item.id ?? "pending"}-${item.keyword}`}>
            {item.keyword}
            <span className="keyword-chip-actions">
              <button className="keyword-search-button" type="button" onClick={() => onSearchKeyword(keywordCountry, item.keyword)}>Buscar y sumar</button>
              <button
                className="keyword-remove-button"
                type="button"
                aria-label={`Retirar ${item.keyword}`}
                disabled={keywordSaving || item.id === null}
                onClick={() => removeRadarKeyword(item)}
              >
                ×
              </button>
            </span>
          </span>
        ))}
      </div>
      <form className="keyword-add-form" onSubmit={addRadarKeyword}>
        <label htmlFor={`new-keyword-${keywordCountry}`}>Nueva palabra o frase</label>
        <div>
          <input
            id={`new-keyword-${keywordCountry}`}
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
      {radarKeywordState.error ? <div className="notice danger" role="alert">{radarKeywordState.error}</div> : null}
      {keywordNotice ? <div className="notice success" role="status">{keywordNotice}</div> : null}
      <div className="keyword-confidentiality-note">
        <LockIcon className="keyword-lock-icon" />
        <p>
          Tus palabras clave y criterios de búsqueda están protegidos bajo nuestra estricta{" "}
          <button type="button" onClick={() => onOpenLegal("confidentiality")}>Cláusula de Confidencialidad</button>.
          Rodar Consulting no comparte tus estrategias comerciales.
        </p>
      </div>
    </section>
  );
}

export function TrackingDateRefreshAdmin({ token }: { token: string }) {
  const [configs, setConfigs] = useState<Record<"peru" | "chile", TrackingDateRefreshStatus | null>>({ peru: null, chile: null });
  const [savingCountry, setSavingCountry] = useState<"peru" | "chile" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all((["peru", "chile"] as const).map((country) => api.trackingDateRefreshStatus(token, country)))
      .then(([peru, chile]) => { if (active) setConfigs({ peru, chile }); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "No se pudo cargar la verificación automática de fechas"); });
    return () => { active = false; };
  }, [token]);

  function updateValue(country: "peru" | "chile", field: "days" | "hours" | "minutes", value: number) {
    setConfigs((current) => {
      const existing = current[country];
      if (!existing) return current;
      const updated = { ...existing, [field]: value };
      updated.interval_seconds = updated.days * 86_400 + updated.hours * 3_600 + updated.minutes * 60;
      return { ...current, [country]: updated };
    });
    setNotice("");
    setError("");
  }

  async function save(country: "peru" | "chile") {
    const config = configs[country];
    if (!config) return;
    if (config.days === 0 && config.hours === 0 && config.minutes === 0) {
      setError("El intervalo debe ser de al menos un minuto.");
      return;
    }
    setSavingCountry(country);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateTrackingDateRefreshInterval(token, country, config);
      setConfigs((current) => ({ ...current, [country]: updated }));
      setNotice(`Verificación automática de ${country === "peru" ? "Perú" : "Chile"} actualizada. La próxima corrida ya usa el nuevo intervalo.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la verificación automática de fechas");
    } finally {
      setSavingCountry(null);
    }
  }

  return (
    <section className="panel scheduler-admin-panel" aria-labelledby="tracking-date-refresh-admin-title">
      <div className="scheduler-admin-heading">
        <div>
          <p className="overline">Seguimiento de Oportunidades</p>
          <h2 id="tracking-date-refresh-admin-title">Verificación automática de fechas (SEACE Perú / Mercado Público Chile)</h2>
          <p>
            Mientras una oportunidad en seguimiento activo no venza su fecha de propuesta, revisamos su ficha en el portal por si
            la entidad movió el Fin de Consultas, la Buena Pro u otra fecha. Define cada cuánto se ejecuta esta revisión, por país.
          </p>
        </div>
      </div>
      <div className="scheduler-country-grid">
        {(["peru", "chile"] as const).map((country) => {
          const config = configs[country];
          const label = country === "peru" ? "Perú (SEACE)" : "Chile (Mercado Público)";
          return (
            <article className="scheduler-country-config" key={country} aria-busy={!config}>
              <div className="scheduler-country-heading"><strong>{label}</strong><span>{config ? `Cada ${updateIntervalLabel(config.interval_seconds)}` : "Cargando…"}</span></div>
              {config ? <>
                <div className="scheduler-duration-fields">
                  <label>Días<input type="number" min="0" max="30" value={config.days} onChange={(event) => updateValue(country, "days", Math.max(0, Math.min(30, Number(event.target.value))))} /></label>
                  <label>Horas<input type="number" min="0" max="23" value={config.hours} onChange={(event) => updateValue(country, "hours", Math.max(0, Math.min(23, Number(event.target.value))))} /></label>
                  <label>Minutos<input type="number" min="0" max="59" value={config.minutes} onChange={(event) => updateValue(country, "minutes", Math.max(0, Math.min(59, Number(event.target.value))))} /></label>
                </div>
                <div className="scheduler-country-actions">
                  <small>{config.next_update_at ? `Próxima verificación: ${new Date(config.next_update_at).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" })}` : "El scheduler se encuentra pausado"}</small>
                  <button className="primary" type="button" onClick={() => void save(country)} disabled={savingCountry !== null}>{savingCountry === country ? "Guardando…" : `Guardar ${country === "peru" ? "Perú" : "Chile"}`}</button>
                </div>
              </> : <p>Cargando configuración…</p>}
            </article>
          );
        })}
      </div>
      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {notice ? <div className="notice success" role="status">{notice}</div> : null}
    </section>
  );
}

export function System({
  token,
  runs,
  refresh,
  legalDocuments,
  legalLoadError,
  onLegalDocumentUpdated,
  onOpenLegal,
  onSearchKeyword,
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
  onSearchKeyword: (country: Country, keyword: string) => void;
  versionLabel: string;
  onVersionUpdated: (versionLabel: string) => void;
}) {
  const [versionDraft, setVersionDraft] = useState(versionLabel);
  const [scoringCountry, setScoringCountry] = useState<"peru" | "chile">("peru");
  const [scoringConfig, setScoringConfig] = useState<import("../api").ScoringConfig | null>(null);
  const [scoringSaving, setScoringSaving] = useState(false);
  const [scoringError, setScoringError] = useState("");
  const [scoringNotice, setScoringNotice] = useState("");
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

  useEffect(() => {
    setScoringConfig(null);
    setScoringError("");
    setScoringNotice("");
    api.scoringConfig(token, scoringCountry)
      .then(setScoringConfig)
      .catch((err) => setScoringError(err instanceof Error ? err.message : "No se pudo cargar la configuración"));
  }, [token, scoringCountry]);

  function updateScoringField(field: "priority_a_min" | "priority_b_min" | "attractive_amount_min", value: number) {
    setScoringConfig((current) => current ? { ...current, [field]: value } : current);
    setScoringNotice("");
  }

  function updateScoringFactor(key: string, changes: { points?: number; enabled?: boolean; value?: string; label?: string; value_type?: "list" | "number" | "text"; field?: "description" | "entity" | "region" | "amount" | "origin" | "status" }) {
    setScoringConfig((current) => current ? {
      ...current,
      factors: { ...current.factors, [key]: { ...current.factors[key], ...changes } },
    } : current);
    setScoringNotice("");
  }

  async function saveScoring(event: React.FormEvent) {
    event.preventDefault();
    if (!scoringConfig) return;
    setScoringSaving(true); setScoringError(""); setScoringNotice("");
    try {
      const updated = await api.updateScoringConfig(token, scoringCountry, scoringConfig);
      setScoringConfig(updated);
      setScoringNotice(`Configuración de ${scoringCountry === "peru" ? "Perú" : "Chile"} actualizada. Se aplicará en las próximas corridas.`);
    } catch (err) {
      setScoringError(err instanceof Error ? err.message : "No se pudo guardar la configuración");
    } finally { setScoringSaving(false); }
  }

  const scoringMaximum = scoringConfig ? (() => {
    const statusKeys = new Set(["queries_and_proposal", "proposal_only", "evaluation"]);
    const additive = Object.entries(scoringConfig.factors).filter(([key, factor]) => factor.enabled && factor.points > 0 && !statusKeys.has(key)).reduce((sum, [, factor]) => sum + factor.points, 0);
    const statusMaximum = Math.max(0, ...Object.entries(scoringConfig.factors).filter(([key, factor]) => statusKeys.has(key) && factor.enabled).map(([, factor]) => factor.points));
    return additive + statusMaximum;
  })() : 0;
  const fixedSystemFactorKeys = new Set(["quick_purchase", "queries_and_proposal", "proposal_only", "evaluation", "closed"]);

  function addScoringFactor() {
    const key = `custom_${Date.now()}`;
    setScoringConfig((current) => current ? { ...current, factors: { ...current.factors, [key]: { label: "Nuevo factor", value: "valor", points: 0, enabled: true, value_type: "list", field: "description" } } } : current);
    setScoringNotice("");
  }

  function removeScoringFactor(key: string) {
    setScoringConfig((current) => {
      if (!current) return current;
      const factors = { ...current.factors }; delete factors[key];
      return { ...current, factors };
    });
  }

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
      <SchedulerScheduleAdmin token={token} />
      <RadarKeywordsAdmin token={token} onOpenLegal={onOpenLegal} onSearchKeyword={onSearchKeyword} />
      <TrackingDateRefreshAdmin token={token} />
      <section className="panel scoring-admin-panel" aria-labelledby="scoring-admin-title">
        <div className="scoring-admin-heading">
          <div>
            <p className="overline">Priorización comercial</p>
            <h2 id="scoring-admin-title">Configuración del score</h2>
            <p>Define los pesos y umbrales por país. Los cambios se aplican a las próximas búsquedas y actualizaciones automáticas.</p>
          </div>
          <div className="country-config-tabs" role="tablist" aria-label="País a configurar">
            {(["peru", "chile"] as const).map((country) => <button key={country} type="button" role="tab" aria-selected={scoringCountry === country} className={scoringCountry === country ? "active" : ""} onClick={() => setScoringCountry(country)}>{country === "peru" ? "Perú" : "Chile"}</button>)}
          </div>
        </div>
        {scoringConfig ? <form onSubmit={saveScoring}>
          <div className="scoring-thresholds">
            <label>Prioridad A desde<input type="number" min="1" max="100" value={scoringConfig.priority_a_min} onChange={(e) => updateScoringField("priority_a_min", Number(e.target.value))} /></label>
            <label>Prioridad B desde<input type="number" min="0" max="99" value={scoringConfig.priority_b_min} onChange={(e) => updateScoringField("priority_b_min", Number(e.target.value))} /></label>
            <label>Prioridad C desde<input type="number" value="0" disabled /></label>
          </div>
          <div className={`scoring-sum ${scoringMaximum === 100 ? "valid" : "invalid"}`} role="status"><span>Máximo score positivo alcanzable</span><strong>{scoringMaximum} / 100 puntos</strong><small>Los estados comerciales son excluyentes; se considera únicamente el mayor puntaje del grupo.</small></div>
          <div className="scoring-factor-list">
            <div className="scoring-factor-header"><span>Factor</span><span>Valor considerado</span><span>Puntos</span><span>Aplicar</span></div>
            {Object.entries(scoringConfig.factors).map(([key, factor]) => <div className={`scoring-factor-row ${factor.enabled ? "" : "disabled"} ${fixedSystemFactorKeys.has(key) ? "has-locked-value" : ""}`} key={key}>
              <div className="score-factor-identity">{key.startsWith("custom_") ? <input value={factor.label} aria-label="Nombre del factor" onChange={(e) => updateScoringFactor(key, { label: e.target.value })} /> : <label htmlFor={`score-${scoringCountry}-${key}`}>{factor.label}</label>}{fixedSystemFactorKeys.has(key) ? <span className="locked-value-badge">Bloqueado</span> : null}{key.startsWith("custom_") ? <><select value={factor.field} aria-label={`Campo para ${factor.label}`} onChange={(e) => { const field = e.target.value as "description" | "entity" | "region" | "amount" | "origin" | "status"; updateScoringFactor(key, { field, value_type: field === "amount" ? "number" : field === "origin" ? "text" : "list" }); }}><option value="description">Descripción/objeto</option><option value="entity">Entidad</option><option value="region">Región</option><option value="amount">Monto mínimo</option><option value="origin">Origen</option><option value="status">Estado comercial</option></select><button className="text-action score-remove-factor" type="button" onClick={() => removeScoringFactor(key)}>Eliminar</button></> : null}</div>
              <input className="score-factor-value" type={factor.value_type === "number" ? "number" : "text"} min={factor.value_type === "number" ? 0 : undefined} step={factor.value_type === "number" ? 1000 : undefined} value={factor.value} disabled={!factor.enabled} readOnly={fixedSystemFactorKeys.has(key)} aria-readonly={fixedSystemFactorKeys.has(key)} title={fixedSystemFactorKeys.has(key) ? "Valor definido por la lógica del sistema" : undefined} onChange={(e) => {
                updateScoringFactor(key, { value: e.target.value });
                if (key === "attractive_amount") updateScoringField("attractive_amount_min", Number(e.target.value));
              }} />
              <input id={`score-${scoringCountry}-${key}`} type="number" min="-100" max="100" value={factor.points} disabled={!factor.enabled} onChange={(e) => updateScoringFactor(key, { points: Number(e.target.value) })} />
              <label className="score-toggle"><input type="checkbox" checked={factor.enabled} onChange={(e) => updateScoringFactor(key, { enabled: e.target.checked })} /><span>{factor.enabled ? "Activo" : "No aplica"}</span></label>
            </div>)}
          </div>
          <button className="ghost add-score-factor" type="button" onClick={addScoringFactor}>+ Agregar factor</button>
          <div className="scoring-actions"><p>{scoringMaximum !== 100 ? "Ajusta los puntos hasta alcanzar exactamente 100 antes de guardar." : scoringCountry === "chile" ? "En Chile, Entidad objetivo y Compra rápida están desactivados por defecto." : "Configuración independiente para procesos de Perú."}</p><button className="primary" type="submit" disabled={scoringSaving || scoringConfig.priority_b_min >= scoringConfig.priority_a_min || scoringMaximum !== 100}>{scoringSaving ? "Guardando…" : `Guardar configuración de ${scoringCountry === "peru" ? "Perú" : "Chile"}`}</button></div>
          {scoringError ? <div className="notice danger" role="alert">{scoringError}</div> : null}
          {scoringNotice ? <div className="notice success" role="status">{scoringNotice}</div> : null}
        </form> : scoringError ? <div className="notice danger" role="alert">{scoringError}</div> : <p>Cargando configuración…</p>}
      </section>
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

export default System;
