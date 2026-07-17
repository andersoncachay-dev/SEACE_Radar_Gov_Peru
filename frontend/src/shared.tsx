import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, LegalDocumentKey, LegalDocumentRecord, Opportunity, RadarKeyword, Run } from "./api";

export type Country = "Peru" | "Chile";

export type CommercialClass = "green" | "amber" | "pending" | "red";

export const retiredRadarKeywords = new Set(["radio enlace"]);

export const countryFlagUrls: Record<Country, string> = {
  Peru: "/assets/flag-peru.svg",
  Chile: "/assets/flag-chile.svg",
};

export const homeKeywordHints = [
  { label: "satelital", terms: ["satelital"] },
  { label: "internet", terms: ["internet"] },
  { label: "conectividad", terms: ["conectividad"] },
  { label: "telecomunicaciones", terms: ["telecomunicaciones"] },
  { label: "GEO", terms: ["geo"] },
  { label: "LEO", terms: ["leo"] },
  { label: "\u00f3rbita", terms: ["\u00f3rbita", "orbita"] },
];

export function sourceBelongsToCountry(source: string, country: Country) {
  const normalized = source.toLowerCase();
  if (country === "Chile") return normalized.startsWith("mercado_publico");
  return normalized.startsWith("seace") || normalized.includes("menor8") || normalized.startsWith("oece_ocds");
}

export function formatMoney(value: number, country: Country = "Peru") {
  if (!Number.isFinite(value) || value <= 0) {
    return <span className="reserved-amount">Monto reservado</span>;
  }
  if (country === "Chile") {
    return `PESO CL ${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(value)}`;
  }
  return new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency: "PEN",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

export function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-PE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function parseDate(value: string | null) {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

export function presentationDeadline(item: Opportunity) {
  return item.proposal_deadline || item.quote_deadline;
}

export function CountryFlagIcon({ country, className = "" }: { country: Country; className?: string }) {
  return (
    <img
      className={className}
      src={countryFlagUrls[country]}
      alt={country === "Chile" ? "Chile" : "Peru"}
      loading="eager"
    />
  );
}

export function LockIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function userInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

export function parseRunDetails(run?: Run | null) {
  const diagnostics = run?.diagnostics || "";
  const reviewed = diagnostics.match(/Cronogramas revisados:\s*(\d+)\/(\d+);\s*aplicados correctamente:\s*(\d+)/);
  const configured = diagnostics.match(/max_detalles=(\d+)/);
  const enrichEnabled = /leer_detalles=True/i.test(diagnostics);
  return {
    configured: configured ? Number(configured[1]) : null,
    configuredLabel: configured && Number(configured[1]) === 0 && enrichEnabled
      ? "Todos los vigentes"
      : configured?.[1] ?? "-",
    reviewed: reviewed ? Number(reviewed[1]) : null,
    requested: reviewed ? Number(reviewed[2]) : null,
    applied: reviewed ? Number(reviewed[3]) : null,
  };
}

export function estimateRunProgress(run: Run) {
  if (["completed", "failed", "cancelled"].includes(run.status)) return 100;
  if (run.status === "queued") return 0;
  return Math.max(0, Math.min(99, Number(run.progress || 0)));
}

export function commercialSignal(item: Opportunity): { label: string; hint: string; className: CommercialClass } {
  const now = Date.now();
  const consultationDeadline = parseDate(item.consultation_deadline);
  const presentationDeadline = parseDate(item.proposal_deadline) ?? parseDate(item.quote_deadline);
  const status = (item.status || "").toLowerCase();

  // Preserve the former Peru behavior while an SEACE proposal deadline is
  // still unavailable. OCDS continues to provide the discovery and enquiry
  // windows, so this is an open proposal candidate rather than a new UI state.
  if (
    presentationDeadline === null &&
    (status.includes("revisar cronograma") || status.includes("pendiente de validacion"))
  ) {
    return {
      label: "Vigente para Propuesta",
      hint: "Presentacion Cotizacion abierta",
      className: "amber",
    };
  }

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

export function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function matchesCompletePhrase(text: string, phrase: string) {
  const normalizedText = stripAccents(text).toLowerCase().replace(/\s+/g, " ").trim();
  const normalizedPhrase = stripAccents(phrase).toLowerCase().replace(/\s+/g, " ").trim();
  if (!normalizedPhrase) return true;
  const phrasePattern = normalizedPhrase.split(" ").map(escapeRegex).join("\\s+");
  return new RegExp(`(?:^|[^\\p{L}\\p{N}_])${phrasePattern}(?=$|[^\\p{L}\\p{N}_])`, "iu").test(normalizedText);
}

export function highlightTermsFromKeywords(keywords: string[]) {
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

export function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
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

export function stripAccents(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

export function defaultRadarKeywords(country: Country): RadarKeyword[] {
  return homeKeywordHints
    .filter((item) => item.label !== "telecomunicaciones")
    .map((item) => ({
      id: null,
      country: country.toLowerCase() as "peru" | "chile",
      keyword: item.label,
      is_default: true,
    }));
}

export function useRadarKeywords(token: string, country: Country) {
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

export type LegalView = LegalDocumentKey;

export type LegalDocumentsMap = Partial<Record<LegalView, LegalDocumentRecord>>;

export function legalInlineText(text: string) {
  return text.split(/(privacidad@rodar\.pe)/gi).map((part, index) => (
    part.toLowerCase() === "privacidad@rodar.pe"
      ? <a key={`${part}-${index}`} href="mailto:privacidad@rodar.pe">{part}</a>
      : <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>
  ));
}

export function LegalTextContent({ content }: { content: string }) {
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

export function TermsContent({ content }: { content?: string }) {
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

export function PrivacyContent({ content }: { content?: string }) {
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

export function ConfidentialityContent({ content }: { content?: string }) {
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

export function LegalDialog({ view, documents, onClose }: { view: LegalView; documents: LegalDocumentsMap; onClose: () => void }) {
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

export function updateIntervalLabel(intervalSeconds: number | null | undefined) {
  const totalSeconds = intervalSeconds ?? 15 * 60;
  const days = Math.floor(totalSeconds / 86_400);
  const hours = Math.floor((totalSeconds % 86_400) / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  const parts = [
    days ? `${days} ${days === 1 ? "día" : "días"}` : "",
    hours ? `${hours} ${hours === 1 ? "hora" : "horas"}` : "",
    minutes ? `${minutes} ${minutes === 1 ? "minuto" : "minutos"}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(", ").replace(/, ([^,]*)$/, " y $1") : "0 minutos";
}

export function RunProgress({ run, batchRuns = [], batchKeywords = [], resultRows = [], resultsFocused = false, country, onToggleResults }: { run: Run; batchRuns?: Run[]; batchKeywords?: string[]; resultRows?: Opportunity[]; resultsFocused?: boolean; country?: Country; onToggleResults?: () => void }) {
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
  const resultKeywords = uniqueKeywords(runs.map(keywordFromRun).filter(Boolean));
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
          <span><b>{detail.configuredLabel}</b> para revisar</span>
          <span><b>{detail.reviewed !== null ? `${detail.reviewed}/${detail.requested}` : "-"}</b> revisados</span>
        </div>
      )}
      {isLive ? <div className="progress-current">{currentRun?.progress_message || (currentKeyword ? `Procesando “${currentKeyword}”` : "Procesando búsqueda")}</div> : null}
      {!isLive && resultRows.length ? (
        <div className="run-result-detail">
          <div className="run-result-list">
            <strong>{resultRows.length === 1 ? "Proceso identificado" : "Procesos identificados"}</strong>
            {resultRows.map((item) => (
              <div className="run-result-item" key={item.id}>
                <b>{item.nomenclature || "Sin nomenclatura"}</b>
                <span><strong>Palabra clave:</strong> {resultKeywords.join(", ") || "No disponible"}</span>
                <span><strong>Entidad:</strong> {item.entity || "No disponible"}</span>
                {country === "Peru" ? (
                  <span><strong>Fin de propuesta (SEACE):</strong> {formatDate(presentationDeadline(item))}</span>
                ) : (
                  <span><strong>Fecha de convocatoria:</strong> {formatDate(item.publication_date)}</span>
                )}
              </div>
            ))}
          </div>
          {onToggleResults ? <button className="ghost" type="button" onClick={onToggleResults}>{resultsFocused ? "Mostrar búsqueda completa" : "Ver en la tabla"}</button> : null}
        </div>
      ) : null}
      {isBatch && failedCount ? <div className="notice danger">{failedCount} de {runs.length} búsquedas no pudieron completarse. Los resultados de las búsquedas terminadas se conservaron.</div> : null}
      {!isBatch && run.error_message ? <div className="notice danger">{run.error_message}</div> : null}
    </div>
  );
}

export function addKeyword(current: string[], keyword: string) {
  const normalized = keyword.trim();
  if (!normalized) return current;
  const exists = current.some((item) => item.toLowerCase() === normalized.toLowerCase());
  return exists ? current : [...current, normalized];
}

export function uniqueKeywords(values: string[]) {
  return values
    .filter((value) => !retiredRadarKeywords.has(normalizedSearchTerm(value)))
    .reduce<string[]>((items, value) => addKeyword(items, value), []);
}

export function normalizedSearchTerm(value: string) {
  return value.trim().toLocaleLowerCase("es");
}

export function keywordFromRun(run: Run) {
  const match = String(run.diagnostics || "").match(/keyword=([^|]+)/i);
  return match?.[1]?.trim() || "";
}

export function ConfirmModal({
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

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}
