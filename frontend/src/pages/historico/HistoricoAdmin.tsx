import React, { useEffect, useRef, useState } from "react";
import { historicoApi, HistoricoImportRun, HistoricoKeyword, HistoricoStatus } from "../../api";

const ORIGIN_LABELS: Record<string, string> = {
  azure_job: "Automática (Azure)",
  pc_script: "Script de la PC",
  manual_upload: "Carga manual",
  reprocess: "Reproceso",
};
const STATUS_LABELS: Record<string, string> = {
  receiving: "Recibiendo archivos",
  queued: "En cola",
  running: "Procesando",
  completed: "Completada",
  failed: "Falló",
};
const KIND_LABELS: Record<HistoricoKeyword["kind"], string> = { include: "Incluir", review: "A revisar", exclude: "Excluir" };
const emptyKeyword: Omit<HistoricoKeyword, "id"> = { keyword: "", category: "Internet (sin especificar)", kind: "include", priority: 90, is_active: true };

function when(value: string | null) {
  return value ? new Date(value).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** Sistema › Histórico Perú: update chain status, manual uploads and keywords. */
export function HistoricoAdmin({ token }: { token: string }) {
  const [status, setStatus] = useState<HistoricoStatus | null>(null);
  const [runs, setRuns] = useState<HistoricoImportRun[]>([]);
  const [keywords, setKeywords] = useState<HistoricoKeyword[]>([]);
  const [draft, setDraft] = useState(emptyKeyword);
  const [refreshDay, setRefreshDay] = useState(9);
  const [upload, setUpload] = useState<{ run: HistoricoImportRun; done: string[]; failed: string[] } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function load() {
    const [imports, words] = await Promise.all([historicoApi.imports(token), historicoApi.keywords(token)]);
    setStatus(imports.status);
    setRefreshDay(imports.status.refresh_day);
    setRuns(imports.runs);
    setKeywords(words);
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "No se pudo cargar Histórico Perú"));
  }, [token]);

  // Poll while an import is in flight so progress shows without reloading.
  const active = runs.find((run) => ["receiving", "queued", "running"].includes(run.status));
  useEffect(() => {
    if (!active || active.status === "receiving") return;
    const timer = window.setInterval(() => { load().catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [active?.id, active?.status]);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "La operación no se completó");
    } finally {
      setBusy("");
    }
  }

  const requestRefresh = () => run("refresh", async () => {
    setStatus(await historicoApi.requestRefresh(token));
    setNotice("Actualización solicitada. El proceso automático la inicia antes de que pase una hora y se demora unos 40 minutos.");
  });

  const saveRefreshDay = () => run("day", async () => {
    setStatus(await historicoApi.updateSettings(token, refreshDay));
    setNotice(`La actualización mensual se intentará desde el día ${refreshDay} de cada mes.`);
  });

  const uploadFiles = (files: FileList | null) => run("upload", async () => {
    if (!files?.length) return;
    const created = await historicoApi.createUpload(token);
    const state = { run: created, done: [] as string[], failed: [] as string[] };
    setUpload({ ...state });
    for (const file of Array.from(files)) {
      try {
        await historicoApi.uploadFile(token, created.id, file);
        state.done.push(file.name);
      } catch (err) {
        state.failed.push(`${file.name}: ${err instanceof Error ? err.message : "error"}`);
      }
      setUpload({ ...state });
    }
    if (!state.done.length) throw new Error("Ningún archivo se pudo subir. Revisa que conserven el nombre original de CONOSCE.");
    await historicoApi.processUpload(token, created.id);
    setNotice(`${state.done.length} archivo(s) recibidos. El procesamiento sigue en segundo plano; el avance aparece en el historial.`);
    if (fileInput.current) fileInput.current.value = "";
    await load();
  });

  const saveKeyword = (event: React.FormEvent) => {
    event.preventDefault();
    run("keyword", async () => {
      const created = await historicoApi.createKeyword(token, { ...draft, keyword: draft.keyword.trim() });
      setKeywords((current) => [...current, created].sort((a, b) => a.priority - b.priority || a.keyword.localeCompare(b.keyword)));
      setDraft(emptyKeyword);
      setNotice(`"${created.keyword}" agregada. Se aplica en la próxima actualización.`);
    });
  };

  const toggleKeyword = (item: HistoricoKeyword) => run("keyword", async () => {
    const { id, ...payload } = item;
    const updated = await historicoApi.updateKeyword(token, id, { ...payload, is_active: !item.is_active });
    setKeywords((current) => current.map((row) => row.id === id ? updated : row));
  });

  const removeKeyword = (item: HistoricoKeyword) => run("keyword", async () => {
    await historicoApi.deleteKeyword(token, item.id);
    setKeywords((current) => current.filter((row) => row.id !== item.id));
  });

  return (
    <section className="panel historico-admin-panel" aria-labelledby="historico-admin-title">
      <div className="scheduler-admin-heading">
        <div>
          <p className="overline">Histórico Perú · datos abiertos OECE</p>
          <h2 id="historico-admin-title">Actualización de contrataciones, vencimientos y PAC</h2>
          <p>OECE publica los archivos en los primeros días de cada mes. La carga automática corre en Azure; si falla, lo intenta el script de la PC, y si también falla, los administradores reciben un correo para cargar los archivos aquí.</p>
        </div>
      </div>

      {status?.needs_fallback ? (
        <div className="notice danger" role="alert">La última actualización automática falló. Si el script de la PC no la completa, sube los archivos de CONOSCE en "Cargar archivos".</div>
      ) : null}

      <div className="historico-admin-grid">
        <article className="historico-admin-card">
          <h3>Estado</h3>
          <dl>
            <div><dt>Datos vigentes al</dt><dd>{status?.data_cut_date ? new Date(`${status.data_cut_date}T12:00:00`).toLocaleDateString("es-PE") : "Sin importación completada"}</dd></div>
            <div><dt>Última importación completa</dt><dd>{when(status?.latest_completed_at ?? null)}</dd></div>
            <div><dt>Este mes</dt><dd>{status?.completed_this_month ? "Actualizado" : status?.import_due ? "Pendiente: se ejecutará en la próxima hora" : "Programado"}</dd></div>
          </dl>
          <button className="primary" type="button" onClick={requestRefresh} disabled={Boolean(busy) || Boolean(active) || status?.refresh_requested}>
            {status?.refresh_requested ? "Actualización solicitada" : busy === "refresh" ? "Solicitando…" : "Actualizar ahora"}
          </button>
        </article>

        <article className="historico-admin-card">
          <h3>Día de actualización mensual</h3>
          <p>Desde este día, el proceso automático intenta la importación hasta completarla.</p>
          <label htmlFor="historico-refresh-day">Día del mes
            <input id="historico-refresh-day" type="number" min={1} max={28} value={refreshDay} onChange={(event) => setRefreshDay(Math.max(1, Math.min(28, Number(event.target.value))))} />
          </label>
          <button type="button" onClick={saveRefreshDay} disabled={Boolean(busy) || refreshDay === status?.refresh_day}>{busy === "day" ? "Guardando…" : "Guardar día"}</button>
        </article>

        <article className="historico-admin-card">
          <h3>Cargar archivos</h3>
          <p>Sube los Excel de CONOSCE con su nombre original (órdenes por mes, adjudicaciones, contratación directa, contratos, PAC, entidades). Solo se reemplazan los periodos que subas.</p>
          <input ref={fileInput} id="historico-upload" type="file" multiple accept=".xlsx,.csv" onChange={(event) => uploadFiles(event.target.files)} disabled={Boolean(busy) || Boolean(active)} />
          {upload ? (
            <p className="historico-upload-progress" role="status">
              Carga #{upload.run.id}: {upload.done.length} subido(s){upload.failed.length ? `, ${upload.failed.length} rechazado(s)` : ""}.
              {upload.failed.map((item) => <span key={item}>{item}</span>)}
            </p>
          ) : null}
        </article>
      </div>

      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {notice ? <div className="notice success" role="status">{notice}</div> : null}

      <h3 className="historico-admin-subtitle">Historial de actualizaciones</h3>
      <div className="table-scroll">
        <table className="historico-admin-table">
          <thead><tr><th>#</th><th>Origen</th><th>Estado</th><th>Inicio</th><th>Fin</th><th>Resultado</th></tr></thead>
          <tbody>
            {runs.length ? runs.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{ORIGIN_LABELS[item.origin] ?? item.origin}</td>
                <td>{STATUS_LABELS[item.status] ?? item.status}{["queued", "running"].includes(item.status) ? ` · ${item.progress}%` : ""}</td>
                <td>{when(item.started_at ?? item.created_at)}</td>
                <td>{when(item.finished_at)}</td>
                <td>{item.status === "failed" ? item.error : item.status === "completed"
                  ? Object.entries(item.counts).filter(([, value]) => typeof value === "number").map(([key, value]) => `${key}: ${Number(value).toLocaleString("es-PE")}`).join(" · ")
                  : item.message}</td>
              </tr>
            )) : <tr><td colSpan={6}>Aún no hay actualizaciones. Usa "Actualizar ahora" o carga los archivos.</td></tr>}
          </tbody>
        </table>
      </div>

      <h3 className="historico-admin-subtitle">Palabras clave del rubro</h3>
      <p className="historico-admin-help">"Incluir" hace que la contratación cuente y asigna la categoría. "A revisar" solo envía a revisión los procesos mayores a 8 UIT. "Excluir" descarta frases que son falsos positivos conocidos. Los cambios se aplican en la próxima actualización.</p>
      <form className="historico-keyword-form" onSubmit={saveKeyword}>
        <label htmlFor="historico-keyword">Palabra o frase<input id="historico-keyword" required minLength={2} value={draft.keyword} onChange={(event) => setDraft({ ...draft, keyword: event.target.value })} placeholder="Ej. fibra óptica" /></label>
        <label htmlFor="historico-category">Categoría<input id="historico-category" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} /></label>
        <label htmlFor="historico-kind">Uso<select id="historico-kind" value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as HistoricoKeyword["kind"] })}>
          {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label htmlFor="historico-priority">Prioridad<input id="historico-priority" type="number" min={1} max={999} value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: Number(event.target.value) })} /></label>
        <button className="primary" type="submit" disabled={busy === "keyword"}>Agregar</button>
      </form>
      <div className="table-scroll">
        <table className="historico-admin-table">
          <thead><tr><th>Palabra o frase</th><th>Categoría</th><th>Uso</th><th>Prioridad</th><th>Activa</th><th></th></tr></thead>
          <tbody>
            {keywords.map((item) => (
              <tr key={item.id} className={item.is_active ? "" : "is-muted"}>
                <td>{item.keyword}</td>
                <td>{item.category}</td>
                <td>{KIND_LABELS[item.kind]}</td>
                <td>{item.priority}</td>
                <td><input type="checkbox" aria-label={`Activar ${item.keyword}`} checked={item.is_active} onChange={() => toggleKeyword(item)} /></td>
                <td><button className="ghost" type="button" onClick={() => removeKeyword(item)}>Quitar</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
