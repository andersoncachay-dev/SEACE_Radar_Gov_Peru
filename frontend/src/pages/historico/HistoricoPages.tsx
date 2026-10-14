import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  historicoApi,
  HistoricoAlert,
  HistoricoAlertPreference,
  HistoricoAlertStatus,
  HistoricoFilterOptions,
  HistoricoFilters,
  HistoricoKind,
  HistoricoPriority,
  HistoricoStatus,
} from "../../api";
import { Icon } from "../../ui";
import { DetailDrawer, FilterBar, HBars, HistFav, monthName, Pager, PriorityBadge, priorityTone, Runway, SearchAndAmount } from "./HistoricoUI";
import { downloadExport, money, moneyShort, shortDate, titleCase, toggleValue, useHistoricoList, useHistoricoMeta, useLatest, useStoredState } from "./useHistorico";

type PageProps = { token: string };

/* ---------- shared frame: data date, empty state, export state ---------- */

function Frame({ status, error, children }: { status: HistoricoStatus | null; error: string; children: React.ReactNode }) {
  return (
    <div className="hist-module">
      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {status && !status.latest_completed_at ? (
        <section className="hist-panel hist-empty-state">
          <h2>Aún no hay datos de CONOSCE</h2>
          <p>La primera carga se hace desde Sistema › Histórico Perú (botón "Actualizar ahora" o "Cargar archivos"). Toma unos 40 minutos; luego el módulo se actualiza solo cada mes.</p>
        </section>
      ) : null}
      {status?.needs_fallback ? (
        <div className="hist-banner" role="status">La última actualización automática falló. Los datos que ves son de la carga anterior{status.data_cut_date ? `, al ${shortDate(status.data_cut_date)}` : ""}.</div>
      ) : null}
      {children}
    </div>
  );
}

function useExport(token: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(kind: HistoricoKind, filters: HistoricoFilters, sort?: string) {
    setBusy(true);
    setError("");
    try {
      await downloadExport(token, kind, filters, sort);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo generar el Excel");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function Panel({ title, subtitle, action, children, className = "" }: { title: string; subtitle?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`hist-panel ${className}`}>
      <div className="hist-panel-head">
        <div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

const num = (value: number) => (value || 0).toLocaleString("es-PE");

/* ---------- Peru map (repo SVG, painted by amount) ---------- */

function normalizeDept(id: string) {
  return id.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/([a-z])([A-Z])/g, "$1 $2").toUpperCase();
}

function PeruMap({ amounts, selected, onToggle }: { amounts: Map<string, number>; selected: string[]; onToggle: (dept: string) => void }) {
  const [svg, setSvg] = useState("");
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    import("../../assets_mapa/peru-regions.svg?raw").then((module) => setSvg(module.default.replace(/<style>[\s\S]*?<\/style>/, "")));
  }, []);
  useEffect(() => {
    const root = ref.current;
    if (!root || !svg) return;
    const max = Math.max(...amounts.values(), 1);
    root.querySelectorAll<SVGElement>("svg [id]").forEach((element) => {
      if (element.id === "LagoTiticaca") {
        element.setAttribute("class", "hist-map-lake");
        return;
      }
      // Region shapes carry the department name as id ("Áncash", "MadreDeDios");
      // helper shapes have generated ids such as "path4242".
      if (!element.id || /^path\d+$/.test(element.id)) return;
      const dept = normalizeDept(element.id);
      const value = amounts.get(dept);
      const t = Math.sqrt((value ?? 0) / max);
      element.setAttribute("class", `hist-map-region${selected.includes(dept) ? " is-active" : ""}`);
      element.style.fill = `color-mix(in srgb, var(--blue-700) ${Math.round(10 + 80 * t)}%, var(--surface-2))`;
      element.dataset.dept = dept;
      element.setAttribute("tabindex", "0");
      element.setAttribute("aria-label", `${titleCase(dept)}: ${moneyShort(value ?? 0)}`);
    });
  }, [svg, amounts, selected]);
  function pick(target: EventTarget | null) {
    const dept = (target as Element | null)?.closest<SVGElement>("[data-dept]")?.dataset.dept;
    if (dept) onToggle(dept);
  }
  return (
    <div
      ref={ref}
      className="hist-map"
      aria-busy={!svg}
      onClick={(event) => pick(event.target)}
      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pick(event.target); } }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

/* ---------- Resumen ---------- */

const SUMMARY_DIMS = ["years", "government_levels", "process_groups", "categories", "departments"] as const;

export function HistoricoResumen({ token, onGo }: PageProps & { onGo: (page: "Contratos por Vencer") => void }) {
  const { options, status, error } = useHistoricoMeta(token);
  const [filters, setFilters] = useStoredState<HistoricoFilters>("resumen.filters", {});
  const [openId, setOpenId] = useState<number | null>(null);
  const key = JSON.stringify(filters);
  const { data, loading, error: loadError } = useLatest(() => historicoApi.summary(token, filters), [token, key]);
  const exporter = useExport(token);
  const amounts = useMemo(() => new Map((data?.by_department ?? []).map((row) => [row.key, row.amount])), [data]);
  const totals = data?.totals;
  const months = data?.by_month ?? [];
  const maxMonth = Math.max(...months.map((m) => m.amount), 1);
  const toggleDept = (dept: string) => setFilters((current) => ({ ...current, departments: toggleValue(current.departments, dept) }));
  return (
    <Frame status={status} error={error || loadError || exporter.error}>
      <FilterBar
        dims={[...SUMMARY_DIMS]}
        options={options}
        filters={filters}
        onChange={setFilters}
        onExport={() => exporter.run("contrataciones", filters)}
        exporting={exporter.busy}
        result={totals ? `${num(totals.count)} contrataciones con estos filtros` : loading ? "Calculando…" : undefined}
      />
      <section className="ui-kpi-grid ui-kpi-grid-4" aria-label="Totales" aria-busy={loading}>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Monto contratado</span><span className="ui-kpi-value">{moneyShort(totals?.amount ?? 0)}</span><span className="ui-kpi-hint">{filters.years?.length ? [...filters.years].sort().join(", ") : "Todo el periodo"}</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Contrataciones</span><span className="ui-kpi-value">{num(totals?.count ?? 0)}</span><span className="ui-kpi-hint">ticket promedio {moneyShort(totals?.count ? totals.amount / totals.count : 0)}</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Entidades</span><span className="ui-kpi-value">{num(totals?.entities ?? 0)}</span><span className="ui-kpi-hint">con compras del rubro</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Proveedores</span><span className="ui-kpi-value">{num(totals?.suppliers ?? 0)}</span><span className="ui-kpi-hint">con al menos una venta</span></div>
      </section>
      <Panel
        title="Pista de vencimientos"
        subtitle="Contratos > 8 UIT que terminan en los próximos 12 meses, con los mismos filtros (salvo años)."
        action={<button className="ui-btn ui-btn-secondary" type="button" onClick={() => onGo("Contratos por Vencer")}>Ver contratos por vencer</button>}
      >
        <Runway items={data?.runway ?? []} onOpen={setOpenId} compact />
      </Panel>
      <div className="hist-two">
        <Panel title="Dónde se compra" subtitle="Haz clic en el mapa o en la lista para filtrar por departamento.">
          <div className="hist-map-box">
            <PeruMap amounts={amounts} selected={filters.departments ?? []} onToggle={toggleDept} />
            <div className="hist-rank">
              {(data?.by_department ?? []).slice(0, 8).map((row) => (
                <button key={row.key} type="button" className={(filters.departments ?? []).includes(row.key) ? "is-active" : ""} onClick={() => toggleDept(row.key)}>
                  <span className="hist-strong">{titleCase(row.key)}</span>
                  <span className="hist-num">{moneyShort(row.amount)}</span>
                  <span className="hist-track"><i style={{ width: `${(100 * row.amount) / Math.max(data!.by_department[0].amount, 1)}%` }} /></span>
                  <small>{num(row.count)} contrataciones</small>
                </button>
              ))}
            </div>
          </div>
        </Panel>
        <div className="hist-stack">
          <Panel title="Monto por mes" subtitle="El mes en curso es parcial: OECE lo completa en la siguiente publicación.">
            <div className="hist-months" role="img" aria-label="Monto por mes">
              {months.map((m, index) => <i key={m.key} className={index === months.length - 1 ? "partial" : ""} style={{ height: `${Math.max(2, (100 * m.amount) / maxMonth)}%` }} title={`${m.key}: ${money(m.amount)}`} />)}
            </div>
            <div className="hist-axis"><span>{months[0]?.key}</span><span>{months[months.length - 1]?.key}</span></div>
          </Panel>
          <Panel title="Por tipo de proceso"><HBars rows={(data?.by_process_group ?? []).map((row) => ({ label: row.key, value: row.amount }))} limit={6} /></Panel>
        </div>
      </div>
      <div className="hist-three">
        <Panel title="Por categoría"><HBars rows={(data?.by_category ?? []).map((row) => ({ label: row.key, value: row.amount }))} /></Panel>
        <Panel title="Entidades que más compran"><HBars rows={(data?.top_entities ?? []).map((row) => ({ label: titleCase(row.name), value: row.amount }))} limit={6} /></Panel>
        <Panel title="Proveedores con más ventas"><HBars rows={(data?.top_suppliers ?? []).map((row) => ({ label: titleCase(row.name), value: row.amount }))} limit={6} /></Panel>
      </div>
      <DetailDrawer token={token} kind="vencimientos" id={openId} onClose={() => setOpenId(null)} />
    </Frame>
  );
}

/* ---------- Historial de contrataciones ---------- */

export function HistoricoContrataciones({ token }: PageProps) {
  const { options, status, error } = useHistoricoMeta(token);
  const [filters, setFilters] = useStoredState<HistoricoFilters>("contrataciones.filters", {});
  const [sort, setSort] = useStoredState("contrataciones.sort", "date_desc");
  const [openId, setOpenId] = useState<number | null>(null);
  const list = useHistoricoList(token, "contrataciones", filters, sort);
  const exporter = useExport(token);
  const rows = list.data?.items ?? [];
  return (
    <Frame status={status} error={error || list.error || exporter.error}>
      <FilterBar
        dims={[...SUMMARY_DIMS]}
        options={options}
        filters={filters}
        onChange={setFilters}
        extra={<SearchAndAmount filters={filters} onChange={setFilters} placeholder="Busca entidad, proveedor, RUC o nomenclatura" />}
        onExport={() => exporter.run("contrataciones", filters, sort)}
        favorites
        exporting={exporter.busy}
        result={list.data ? `${num(list.data.total)} contrataciones · ${moneyShort(list.data.amount)}` : undefined}
      />
      <Panel
        title="Historial de contrataciones"
        subtitle="Órdenes ≤ 8 UIT (fecha de emisión) e ítems adjudicados > 8 UIT (fecha de buena pro)."
        action={
          <select className="hist-select" aria-label="Ordenar" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="date_desc">Más recientes primero</option>
            <option value="date_asc">Más antiguas primero</option>
            <option value="amount_desc">Mayor monto</option>
          </select>
        }
      >
        {rows.length ? <>
          <div className="hist-table-wrap">
            <table className="hist-table">
              <thead><tr><th className="hist-fav-col"><span className="sr-only">Favorito</span></th><th>Fecha</th><th>Tipo</th><th>Entidad · descripción</th><th className="hist-col-opt">Proveedor</th><th className="hist-col-opt">Categoría</th><th className="hist-money">Monto</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} onClick={() => setOpenId(row.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setOpenId(row.id); }}>
                    <td className="hist-fav-col"><HistFav token={token} kind="contrataciones" row={row} /></td>
                    <td className="hist-num">{shortDate(row.date)}</td>
                    <td>{row.process_group}</td>
                    <td><span className="hist-strong">{titleCase(row.entity_name)}</span><span className="hist-sub">{row.description}</span></td>
                    <td className="hist-col-opt">{titleCase(row.supplier_name)}</td>
                    <td className="hist-col-opt">{row.category}</td>
                    <td className="hist-money hist-strong">{money(row.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hist-cards">
            {rows.map((row) => (
              <div className="hist-card-item" key={row.id}>
              <button type="button" className="hist-card" onClick={() => setOpenId(row.id)}>
                <span className="hist-row"><span className="hist-tag">{row.process_group}</span><span className="hist-strong hist-num">{moneyShort(row.amount)}</span></span>
                <span className="hist-strong">{titleCase(row.entity_name)}</span>
                <span className="hist-sub">{shortDate(row.date)} · {row.description}</span>
              </button>
              <HistFav token={token} kind="contrataciones" row={row} />
              </div>
            ))}
          </div>
          <Pager page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPage={list.setPage} />
        </> : <p className="hist-empty">{list.loading ? "Cargando contrataciones…" : "Ninguna contratación cumple estos filtros. Quita alguno para ver resultados."}</p>}
      </Panel>
      <DetailDrawer token={token} kind="contrataciones" id={openId} onClose={() => setOpenId(null)} />
    </Frame>
  );
}

/* ---------- Contratos por vencer (+ compras recurrentes) ---------- */

const UPCOMING_BUCKETS = ["Vence ≤ 90 días", "Vence 91–180 días", "Vence 181–365 días", "Vence > 1 año"];

const EXPIRING_TONE: Record<string, HistoricoPriority | ""> = {
  "Vence ≤ 90 días": "P1", "Vence 91–180 días": "P2", "Vence 181–365 días": "P3", "Vence > 1 año": "P4", "Vencido": "",
};

function BucketStrip({ buckets, active, onSelect, tones, suffix = "" }: {
  buckets: Array<{ key: string; count: number; amount: number }>;
  active: string | null;
  onSelect: (key: string | null) => void;
  tones: (key: string) => string;
  suffix?: string;
}) {
  return (
    <div className="hist-buckets" role="group" aria-label="Filtrar por ventana">
      {buckets.map((bucket) => (
        <button
          key={bucket.key}
          type="button"
          className="hist-bucket"
          aria-pressed={active === bucket.key}
          style={{ "--tone": tones(bucket.key) } as React.CSSProperties}
          onClick={() => onSelect(active === bucket.key ? null : bucket.key)}
        >
          <span>{bucket.key}</span>
          <b className="hist-num">{num(bucket.count)}</b>
          <span className="hist-num">{moneyShort(bucket.amount)}{suffix}</span>
        </button>
      ))}
    </div>
  );
}

export function HistoricoVencimientos({ token }: PageProps) {
  const [tab, setTab] = useStoredState<"contratos" | "recurrentes">("vencimientos.tab", "contratos");
  return (
    <div className="hist-module">
      <div className="hist-tabs" role="tablist" aria-label="Tipo de vencimiento">
        <button type="button" role="tab" aria-selected={tab === "contratos"} onClick={() => setTab("contratos")}>Contratos &gt; 8 UIT</button>
        <button type="button" role="tab" aria-selected={tab === "recurrentes"} onClick={() => setTab("recurrentes")}>Compras recurrentes ≤ 8 UIT</button>
      </div>
      {tab === "contratos" ? <ExpiringContracts token={token} /> : <RecurringPurchases token={token} />}
    </div>
  );
}

function ExpiringContracts({ token }: PageProps) {
  const { options, status, error } = useHistoricoMeta(token);
  const [filters, setFilters] = useStoredState<HistoricoFilters>("vencimientos.filters", {});
  const [bucket, setBucket] = useStoredState<string | null>("vencimientos.bucket", null);
  const [sort, setSort] = useStoredState("vencimientos.sort", "days_asc");
  const [openId, setOpenId] = useState<number | null>(null);
  const key = JSON.stringify(filters);
  // Without a selected window the list shows what is still running; expired
  // contracts (most of the history) only appear when "Vencido" is picked.
  const listFilters = useMemo(() => ({ ...filters, buckets: bucket ? [bucket] : UPCOMING_BUCKETS }), [key, bucket]);
  const list = useHistoricoList(token, "vencimientos", listFilters, sort);
  const buckets = useLatest(() => historicoApi.buckets(token, "vencimientos", filters), [token, key]);
  const runway = useLatest(() => historicoApi.runway(token, filters), [token, key]);
  const exporter = useExport(token);
  const rows = list.data?.items ?? [];
  const toggles = (
    <>
      <SearchAndAmount filters={filters} onChange={setFilters} placeholder="Busca entidad, proveedor o nomenclatura" />
      <label className="hist-toggle"><input type="checkbox" checked={Boolean(filters.real_date_only)} onChange={(event) => setFilters({ ...filters, real_date_only: event.target.checked })} /> Solo fecha real</label>
      <label className="hist-toggle"><input type="checkbox" checked={Boolean(filters.hide_renewed)} onChange={(event) => setFilters({ ...filters, hide_renewed: event.target.checked })} /> Ocultar posibles renovados</label>
    </>
  );
  return (
    <Frame status={status} error={error || list.error || exporter.error}>
      <FilterBar
        dims={["government_levels", "process_groups", "categories", "departments"]}
        options={options}
        filters={filters}
        onChange={setFilters}
        extra={toggles}
        onExport={() => exporter.run("vencimientos", listFilters, sort)}
        favorites
        exporting={exporter.busy}
        result={buckets.data ? `${num(buckets.data.reduce((s, b) => s + b.count, 0))} contratos con estos filtros` : undefined}
      />
      <BucketStrip buckets={buckets.data ?? []} active={bucket} onSelect={setBucket} tones={(k) => priorityTone(EXPIRING_TONE[k] || null)} />
      <Panel title="Pista de vencimientos" subtitle="Próximos 12 meses. Toca un punto para ver el contrato.">
        <Runway items={runway.data ?? []} onOpen={setOpenId} />
      </Panel>
      <Panel
        title={bucket ?? "Próximos a vencer"}
        subtitle={list.data ? `${num(list.data.total)} contratos · ${moneyShort(list.data.amount)}` : undefined}
        action={
          <select className="hist-select" aria-label="Ordenar" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="days_asc">Ordenar: días para vencer</option>
            <option value="amount_desc">Ordenar: mayor monto</option>
            <option value="days_desc">Ordenar: más lejanos primero</option>
          </select>
        }
      >
        {rows.length ? <>
          <div className="hist-table-wrap">
            <table className="hist-table">
              <thead><tr><th className="hist-fav-col"><span className="sr-only">Favorito</span></th><th>Prioridad</th><th>Días</th><th>Fin de vigencia</th><th>Entidad · proceso</th><th className="hist-col-opt">Proveedor actual</th><th className="hist-money">Monto</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} onClick={() => setOpenId(row.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setOpenId(row.id); }}>
                    <td className="hist-fav-col"><HistFav token={token} kind="vencimientos" row={row} /></td>
                    <td><PriorityBadge priority={row.priority} /></td>
                    <td className="hist-days" style={{ color: priorityTone(row.priority) }}>{row.days_to_end}</td>
                    <td className="hist-num">{shortDate(row.end_date)}<span className="hist-sub"><span className={`hist-tag ${row.is_real_date ? "real" : ""}`}>{row.is_real_date ? "Fecha real" : "Estimada"}</span>{row.possibly_renewed ? <span className="hist-tag">Posible renovado</span> : null}</span></td>
                    <td><span className="hist-strong">{titleCase(row.entity_name)}</span><span className="hist-sub">{row.nomenclature} · {titleCase(row.department)} · {row.category}</span></td>
                    <td className="hist-col-opt">{titleCase(row.supplier_name)}</td>
                    <td className="hist-money hist-strong">{money(row.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hist-cards">
            {rows.map((row) => (
              <div className="hist-card-item" key={row.id}>
              <button type="button" className="hist-card" style={{ "--tone": priorityTone(row.priority) } as React.CSSProperties} onClick={() => setOpenId(row.id)}>
                <span className="hist-row"><PriorityBadge priority={row.priority} /><span className="hist-days" style={{ color: priorityTone(row.priority) }}>{row.days_to_end} días</span></span>
                <span className="hist-strong">{titleCase(row.entity_name)}</span>
                <span className="hist-row"><span className="hist-sub">{titleCase(row.supplier_name)}</span><span className="hist-strong hist-num">{moneyShort(row.amount)}</span></span>
              </button>
              <HistFav token={token} kind="vencimientos" row={row} />
              </div>
            ))}
          </div>
          <Pager page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPage={list.setPage} />
        </> : <p className="hist-empty">{list.loading ? "Cargando contratos…" : "Ningún contrato cumple estos filtros. Quita alguno para ver resultados."}</p>}
      </Panel>
      <DetailDrawer token={token} kind="vencimientos" id={openId} onClose={() => setOpenId(null)} />
    </Frame>
  );
}

function RecurringPurchases({ token }: PageProps) {
  const { options, status, error } = useHistoricoMeta(token);
  const [filters, setFilters] = useStoredState<HistoricoFilters>("recurrentes.filters", {});
  const [bucket, setBucket] = useStoredState<string | null>("recurrentes.bucket", null);
  const [sort, setSort] = useStoredState("recurrentes.sort", "days_asc");
  const [openId, setOpenId] = useState<number | null>(null);
  const key = JSON.stringify(filters);
  const listFilters = useMemo(() => ({ ...filters, buckets: bucket ? [bucket] : [] }), [key, bucket]);
  const list = useHistoricoList(token, "recurrentes", listFilters, sort);
  const buckets = useLatest(() => historicoApi.buckets(token, "recurrentes", filters), [token, key]);
  const exporter = useExport(token);
  const rows = list.data?.items ?? [];
  return (
    <Frame status={status} error={error || list.error || exporter.error}>
      <FilterBar
        dims={["government_levels", "categories", "departments", "patterns"]}
        options={options}
        filters={filters}
        onChange={setFilters}
        extra={<SearchAndAmount filters={filters} onChange={setFilters} placeholder="Busca entidad o proveedor" />}
        onExport={() => exporter.run("recurrentes", listFilters, sort)}
        favorites
        exporting={exporter.busy}
        result={list.data ? `${num(list.data.total)} pares entidad–proveedor` : undefined}
      />
      <BucketStrip
        buckets={(buckets.data ?? []).filter((b) => b.key !== "> 1 año")}
        active={bucket}
        onSelect={setBucket}
        tones={(k) => (k.startsWith("Atrasada") ? "var(--urg-p4-ink)" : k === "≤ 30 días" ? "var(--urg-p2-ink)" : "var(--urg-p3-ink)")}
        suffix=" en 12 m"
      />
      <Panel
        title="Próximas compras ≤ 8 UIT"
        subtitle="Entidad + proveedor con órdenes en los últimos 12 meses. La próxima compra se estima por la frecuencia de órdenes o el plazo de la descripción."
        action={
          <select className="hist-select" aria-label="Ordenar" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="days_asc">Ordenar: próxima compra</option>
            <option value="amount_desc">Ordenar: mayor monto</option>
          </select>
        }
      >
        {rows.length ? <>
          <div className="hist-table-wrap">
            <table className="hist-table">
              <thead><tr><th className="hist-fav-col"><span className="sr-only">Favorito</span></th><th>Próxima compra</th><th>Patrón</th><th>Entidad</th><th className="hist-col-opt">Proveedor actual</th><th>Órdenes 12m</th><th className="hist-money">Monto 12m</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} onClick={() => setOpenId(row.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setOpenId(row.id); }}>
                    <td className="hist-fav-col"><HistFav token={token} kind="recurrentes" row={row} /></td>
                    <td className="hist-num"><span className="hist-strong">{shortDate(row.next_purchase_date)}</span><span className="hist-sub">{row.days_to_next < 0 ? `atrasada ${-row.days_to_next} días` : `en ${row.days_to_next} días`}</span></td>
                    <td>{row.pattern}</td>
                    <td><span className="hist-strong">{titleCase(row.entity_name)}</span><span className="hist-sub">{titleCase(row.department)}</span></td>
                    <td className="hist-col-opt">{titleCase(row.supplier_name)}</td>
                    <td className="hist-num">{row.orders_12m}</td>
                    <td className="hist-money hist-strong">{money(row.amount_12m_supplier)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hist-cards">
            {rows.map((row) => (
              <div className="hist-card-item" key={row.id}>
              <button type="button" className="hist-card" onClick={() => setOpenId(row.id)}>
                <span className="hist-row"><span className="hist-strong">{shortDate(row.next_purchase_date)}</span><span className="hist-tag">{row.pattern}</span></span>
                <span className="hist-strong">{titleCase(row.entity_name)}</span>
                <span className="hist-row"><span className="hist-sub">{titleCase(row.supplier_name)}</span><span className="hist-strong hist-num">{moneyShort(row.amount_12m_supplier)}</span></span>
              </button>
              <HistFav token={token} kind="recurrentes" row={row} />
              </div>
            ))}
          </div>
          <Pager page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPage={list.setPage} />
        </> : <p className="hist-empty">{list.loading ? "Cargando compras…" : "Ninguna compra cumple estos filtros."}</p>}
      </Panel>
      <DetailDrawer token={token} kind="recurrentes" id={openId} onClose={() => setOpenId(null)} />
    </Frame>
  );
}

/* ---------- PAC ---------- */

export function HistoricoPac({ token }: PageProps) {
  const { options, status, error } = useHistoricoMeta(token);
  const [filters, setFilters] = useStoredState<HistoricoFilters>("pac.filters", {});
  const [openId, setOpenId] = useState<number | null>(null);
  const key = JSON.stringify(filters);
  const summary = useLatest(() => historicoApi.pacSummary(token, filters), [token, key]);
  const list = useHistoricoList(token, "pac", filters, "month_asc");
  const exporter = useExport(token);
  const nowMonth = new Date().getMonth() + 1;
  const byMonth = Array.from({ length: 12 }, (_, i) => summary.data?.by_month.find((m) => m.key === i + 1)?.count ?? 0);
  const maxMonth = Math.max(...byMonth, 1);
  const totals = summary.data?.totals;
  const rows = list.data?.items ?? [];
  return (
    <Frame status={status} error={error || summary.error || list.error || exporter.error}>
      <FilterBar
        dims={["situations", "months", "government_levels", "process_groups", "departments", "categories"]}
        options={options}
        filters={filters}
        onChange={setFilters}
        extra={<SearchAndAmount filters={filters} onChange={setFilters} placeholder="Busca entidad o descripción" amount={false} />}
        onExport={() => exporter.run("pac", filters)}
        favorites
        exporting={exporter.busy}
        result={totals ? `${num(totals.items)} ítems del PAC` : undefined}
      />
      <section className="ui-kpi-grid ui-kpi-grid-4" aria-label="PAC" aria-busy={summary.loading}>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Ítems programados</span><span className="ui-kpi-value">{num(totals?.items ?? 0)}</span><span className="ui-kpi-hint">Plan Anual de Contrataciones</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Por convocar</span><span className="ui-kpi-value" style={{ color: "var(--urg-p2-ink)" }}>{num(totals?.to_call ?? 0)}</span><span className="ui-kpi-hint">mes previsto ≥ {monthName(nowMonth).toLowerCase()}</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Entidades</span><span className="ui-kpi-value">{num(totals?.entities ?? 0)}</span><span className="ui-kpi-hint">con ítems del rubro</span></div>
        <div className="ui-card ui-kpi"><span className="ui-kpi-label">Ya adjudicaron en el año</span><span className="ui-kpi-value">{num(totals?.already_awarded ?? 0)}</span><span className="ui-kpi-hint">indicativo</span></div>
      </section>
      <div className="hist-two">
        <Panel title="Mes previsto de convocatoria" subtitle="Resaltados el mes actual y el siguiente: lo que conviene preparar ya.">
          <div className="hist-pac-months" role="img" aria-label="Ítems por mes previsto">
            {byMonth.map((count, i) => (
              <div key={i} className={i + 1 === nowMonth || i + 1 === nowMonth + 1 ? "is-soon" : ""}>
                <b>{count || ""}</b>
                <i style={{ height: `${Math.max(2, (110 * count) / maxMonth)}px` }} />
                <span>{monthName(i + 1)}</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Por tipo de proceso"><HBars rows={(summary.data?.by_process_group ?? []).map((row) => ({ label: row.key, value: row.count }))} limit={6} format={(row) => `${num(row.value)} ítems`} /></Panel>
      </div>
      <div className="hist-two">
        <Panel title="Por departamento"><HBars rows={(summary.data?.by_department ?? []).map((row) => ({ label: titleCase(row.key), value: row.count }))} format={(row) => `${num(row.value)} ítems`} /></Panel>
        <Panel title="Por categoría"><HBars rows={(summary.data?.by_category ?? []).map((row) => ({ label: row.key, value: row.count }))} format={(row) => `${num(row.value)} ítems`} /></Panel>
      </div>
      <Panel title="Ítems del PAC" subtitle="Ordenados por mes previsto.">
        {rows.length ? <>
          <div className="hist-table-wrap">
            <table className="hist-table">
              <thead><tr><th className="hist-fav-col"><span className="sr-only">Favorito</span></th><th>Mes previsto</th><th>Entidad</th><th>Tipo de proceso</th><th className="hist-col-opt">Descripción</th><th>Ya adjudicó</th></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} onClick={() => setOpenId(row.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setOpenId(row.id); }}>
                    <td className="hist-fav-col"><HistFav token={token} kind="pac" row={row} /></td>
                    <td className="hist-strong" style={{ color: row.situation.startsWith("Por convocar") ? "var(--urg-p2-ink)" : undefined }}>{monthName(row.planned_month)}</td>
                    <td><span className="hist-strong">{titleCase(row.entity_name)}</span><span className="hist-sub">{titleCase(row.department)} · {row.situation}</span></td>
                    <td>{row.process_type}</td>
                    <td className="hist-col-opt"><span className="hist-sub">{row.item_description || row.process_description}</span></td>
                    <td>{row.already_awarded ? <span className="hist-tag">Posible</span> : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="hist-cards">
            {rows.map((row) => (
              <div className="hist-card-item" key={row.id}>
              <button type="button" className="hist-card" style={{ "--tone": row.situation.startsWith("Por convocar") ? "var(--urg-p2-ink)" : "var(--line)" } as React.CSSProperties} onClick={() => setOpenId(row.id)}>
                <span className="hist-row"><span className="hist-strong">{monthName(row.planned_month)}</span><span className="hist-tag">{row.process_type}</span></span>
                <span className="hist-strong">{titleCase(row.entity_name)}</span>
                <span className="hist-sub">{row.item_description || row.process_description}</span>
              </button>
              <HistFav token={token} kind="pac" row={row} />
              </div>
            ))}
          </div>
          <Pager page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPage={list.setPage} />
        </> : <p className="hist-empty">{list.loading ? "Cargando PAC…" : "Ningún ítem cumple estos filtros."}</p>}
      </Panel>
      <DetailDrawer token={token} kind="pac" id={openId} onClose={() => setOpenId(null)} />
    </Frame>
  );
}

/* ---------- Centro de alertas ---------- */

const PRIORITIES: HistoricoPriority[] = ["P1", "P2", "P3", "P4"];
const PRIORITY_HINT: Record<HistoricoPriority, string> = {
  P1: "Vence en ≤ 30 días",
  P2: "≤ 90 días, monto alto o PAC del mes",
  P3: "91–180 días · compra mensual atrasada",
  P4: "181–365 días · compra en 31–90 días",
};
const KIND_LABEL: Record<HistoricoAlert["kind"], string> = { vencimiento: "Contrato por vencer", recurrente: "Próxima compra", pac: "PAC por convocar" };
const STATUS_OPTIONS: Array<[HistoricoAlertStatus, string]> = [["nueva", "Nueva"], ["vista", "Vista"], ["en_gestion", "En gestión"], ["descartada", "Descartar"]];

export function HistoricoAlertas({ token }: PageProps) {
  const { options, status, error } = useHistoricoMeta(token);
  const [scope, setScope] = useStoredState<"all" | "mine">("alertas.scope", "all");
  const [priority, setPriority] = useStoredState<HistoricoPriority | null>("alertas.priority", null);
  const [page, setPage] = useState(1);
  const [configOpen, setConfigOpen] = useState(false);
  const [detail, setDetail] = useState<{ kind: HistoricoKind; id: number } | null>(null);
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const preference = useLatest(() => historicoApi.alertPreferences(token), [token, version]);
  const alerts = useLatest(
    () => historicoApi.alerts(token, { mine: scope === "mine", priorities: priority ? [priority] : [], page, page_size: 40 }),
    [token, scope, priority, page, version],
  );
  useEffect(() => { setPage(1); }, [scope, priority]);

  async function changeStatus(alert: HistoricoAlert, next: HistoricoAlertStatus) {
    try {
      await historicoApi.updateAlert(token, alert.id, { status: next });
      setNotice(next === "descartada" ? "Alerta descartada. Volverá si cambia su fecha." : "Estado actualizado.");
      setVersion((v) => v + 1);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "No se pudo actualizar la alerta");
    }
  }

  function openDetail(alert: HistoricoAlert) {
    if (alert.expiring_id) setDetail({ kind: "vencimientos", id: alert.expiring_id });
    else if (alert.recurring_id) setDetail({ kind: "recurrentes", id: alert.recurring_id });
    else if (alert.pac_item_id) setDetail({ kind: "pac", id: alert.pac_item_id });
  }

  const counts = alerts.data?.counts;
  const rows = alerts.data?.items ?? [];
  return (
    <Frame status={status} error={error || alerts.error}>
      <div className="hist-scope">
        <div className="hist-tabs" role="tablist" aria-label="Alcance">
          <button type="button" role="tab" aria-selected={scope === "all"} onClick={() => setScope("all")}>Todas las alertas</button>
          <button type="button" role="tab" aria-selected={scope === "mine"} onClick={() => setScope("mine")}>Mis alertas</button>
        </div>
        <button className="ui-btn ui-btn-secondary" type="button" onClick={() => setConfigOpen(true)}><Icon name="settings" size={16} />Configurar mis alertas</button>
      </div>
      {scope === "mine" ? (
        <div className="hist-banner hist-banner-info">
          {preference.data?.configured ? describePreference(preference.data) : "Aún no configuras tus alertas: hoy ves todas. Usa \"Configurar mis alertas\" para elegir, por ejemplo, solo procesos satelitales."}
        </div>
      ) : null}
      {notice ? <div className="notice success" role="status">{notice}</div> : null}
      <div className="hist-buckets hist-buckets-4" role="group" aria-label="Filtrar por prioridad">
        {PRIORITIES.map((p) => (
          <button key={p} type="button" className="hist-bucket" aria-pressed={priority === p} style={{ "--tone": priorityTone(p) } as React.CSSProperties} onClick={() => setPriority(priority === p ? null : p)}>
            <span>{({ P1: "Crítica", P2: "Alta", P3: "Media", P4: "Baja" } as const)[p]}</span>
            <b className="hist-num">{num(counts?.[p] ?? 0)}</b>
            <span>{PRIORITY_HINT[p]}</span>
          </button>
        ))}
      </div>
      <Panel
        title={scope === "mine" ? "Mis alertas" : "Todas las alertas activas"}
        subtitle={alerts.data ? `${num(alerts.data.total)} alertas · ordenadas por prioridad y puntaje (urgencia, monto, fecha real)` : undefined}
      >
        {rows.length ? rows.map((alert) => (
          <article className="hist-alert" key={alert.id}>
            <PriorityBadge priority={alert.priority} />
            <div className="hist-alert-body">
              <h3>{alert.title}</h3>
              <p>{titleCase(alert.entity_name)} · {titleCase(alert.department)} · {KIND_LABEL[alert.kind]} · {alert.category}{alert.amount ? ` · ${money(alert.amount)}` : ""}</p>
            </div>
            <div className="hist-alert-actions">
              <select className="hist-select" aria-label={`Estado de ${alert.title}`} value={alert.status} onChange={(event) => changeStatus(alert, event.target.value as HistoricoAlertStatus)}>
                {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button className="ui-btn ui-btn-secondary" type="button" onClick={() => openDetail(alert)}>Detalle</button>
            </div>
          </article>
        )) : <p className="hist-empty">{alerts.loading ? "Cargando alertas…" : scope === "mine" ? "No hay alertas con tu configuración. Amplía categorías o baja la prioridad mínima." : "No hay alertas activas."}</p>}
        <Pager page={page} pageSize={40} total={alerts.data?.total ?? 0} onPage={setPage} />
      </Panel>
      {configOpen ? (
        <AlertConfig
          token={token}
          options={options}
          initial={preference.data}
          onClose={() => setConfigOpen(false)}
          onSaved={() => { setConfigOpen(false); setScope("mine"); setPriority(null); setVersion((v) => v + 1); setNotice("Guardado. Tu bandeja y tu resumen semanal usan esta configuración."); }}
        />
      ) : null}
      {detail ? <DetailDrawer token={token} kind={detail.kind} id={detail.id} onClose={() => setDetail(null)} /> : null}
    </Frame>
  );
}

function describePreference(preference: HistoricoAlertPreference) {
  const parts: string[] = [];
  if (preference.kinds.length) parts.push(preference.kinds.map((kind) => KIND_LABEL[kind as HistoricoAlert["kind"]] ?? kind).join(", "));
  if (preference.categories.length) parts.push(preference.categories.join(", "));
  if (preference.departments.length) parts.push(preference.departments.map(titleCase).join(", "));
  if (preference.government_levels.length) parts.push(preference.government_levels.join(", "));
  if (preference.process_groups.length) parts.push(preference.process_groups.join(", "));
  if (preference.keywords.length) parts.push(`con "${preference.keywords.join('", "')}"`);
  if (preference.min_amount) parts.push(`monto ≥ ${moneyShort(preference.min_amount)}`);
  parts.push(preference.min_priority === "P4" ? "todas las prioridades" : `prioridad ${({ P1: "crítica", P2: "alta o mayor", P3: "media o mayor", P4: "" } as const)[preference.min_priority]}`);
  return `Tu configuración: ${parts.join(" · ")}.${preference.historico_digest ? " Recibes el resumen por correo los lunes a las 8:00." : ""}`;
}

const EMPTY_PREFERENCE: HistoricoAlertPreference = {
  kinds: [], categories: [], departments: [], government_levels: [], process_groups: [], keywords: [], min_amount: 0, min_priority: "P4", historico_digest: false,
};

function AlertConfig({ token, options, initial, onClose, onSaved }: {
  token: string;
  options: HistoricoFilterOptions | null;
  initial: HistoricoAlertPreference | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<HistoricoAlertPreference>({ ...EMPTY_PREFERENCE, ...(initial ?? {}) });
  const [term, setTerm] = useState("");
  const [preview, setPreview] = useState<{ total: number; counts: Record<HistoricoPriority, number> } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const draftKey = JSON.stringify(draft);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      historicoApi.previewAlertPreferences(token, draft).then(setPreview).catch(() => setPreview(null));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [draftKey]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, []);

  const toggle = (field: "kinds" | "categories" | "departments" | "government_levels" | "process_groups", value: string) =>
    setDraft((current) => ({ ...current, [field]: toggleValue(current[field], value) }));

  function addTerm() {
    const value = term.trim();
    if (value && !draft.keywords.includes(value)) setDraft({ ...draft, keywords: [...draft.keywords, value] });
    setTerm("");
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await historicoApi.saveAlertPreferences(token, draft);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la configuración");
    } finally {
      setSaving(false);
    }
  }

  const satellite = (options?.categories ?? []).filter((category) => category.toLowerCase().startsWith("satelital"));
  const group = (field: "kinds" | "categories" | "departments" | "government_levels" | "process_groups", values: Array<[string, string]>) => (
    <div className="hist-opts">
      {values.map(([value, label]) => (
        <button key={value} type="button" className="ui-fchip" aria-pressed={draft[field].includes(value)} onClick={() => toggle(field, value)}>{label}</button>
      ))}
    </div>
  );

  return (
    <div className="hist-overlay">
      <div className="hist-scrim" onClick={onClose} />
      <aside className="hist-drawer" role="dialog" aria-modal="true" aria-labelledby="hist-config-title">
        <header>
          <div className="hist-drawer-heading">
            <h2 id="hist-config-title">Configurar mis alertas</h2>
            <span className="hist-sub">Elige qué te interesa. Un grupo sin selección incluye todo.</span>
          </div>
          <button className="ui-btn ui-btn-ghost ui-btn-icon-only" type="button" onClick={onClose} aria-label="Cerrar"><Icon name="close" size={18} /></button>
        </header>
        <div className="hist-drawer-body hist-config">
          <fieldset>
            <legend>Atajos</legend>
            <div className="hist-opts">
              <button className="ui-btn ui-btn-secondary" type="button" onClick={() => setDraft({ ...draft, categories: satellite })}>Solo satelital y Starlink</button>
              <button className="ui-btn ui-btn-secondary" type="button" onClick={() => setDraft({ ...draft, kinds: ["vencimiento"], min_amount: 500000 })}>Contratos ≥ S/ 500 mil</button>
              <button className="ui-btn ui-btn-secondary" type="button" onClick={() => setDraft({ ...draft, min_priority: "P2" })}>Solo críticas y altas</button>
              <button className="ui-btn ui-btn-ghost" type="button" onClick={() => setDraft({ ...EMPTY_PREFERENCE, historico_digest: draft.historico_digest })}>Ver todo</button>
            </div>
          </fieldset>
          <fieldset><legend>Tipo de alerta</legend>{group("kinds", [["vencimiento", "Contratos por vencer"], ["recurrente", "Compras recurrentes"], ["pac", "PAC por convocar"]])}</fieldset>
          <fieldset><legend>Categorías del rubro</legend>{group("categories", (options?.categories ?? []).map((c) => [c, c]))}</fieldset>
          <fieldset><legend>Nivel de gobierno</legend>{group("government_levels", (options?.government_levels ?? []).map((c) => [c, c]))}</fieldset>
          <fieldset><legend>Tipo de proceso</legend>{group("process_groups", (options?.process_groups ?? []).map((c) => [c, c]))}</fieldset>
          <fieldset><legend>Departamentos</legend>{group("departments", (options?.departments ?? []).map((c) => [c, titleCase(c)]))}</fieldset>
          <fieldset>
            <legend>Palabras en la descripción</legend>
            <div className="hist-terms">
              {draft.keywords.map((keyword) => (
                <span className="hist-achip" key={keyword}>{keyword}<button type="button" aria-label={`Quitar ${keyword}`} onClick={() => setDraft({ ...draft, keywords: draft.keywords.filter((k) => k !== keyword) })}>×</button></span>
              ))}
              <input
                id="hist-term"
                type="text"
                value={term}
                placeholder="Ej. vsat, starlink, fibra (Enter para agregar)"
                onChange={(event) => setTerm(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addTerm(); } }}
                onBlur={addTerm}
              />
            </div>
          </fieldset>
          <fieldset>
            <legend>Monto mínimo</legend>
            <div className="hist-opts">
              {[[0, "Cualquiera"], [50000, "≥ S/ 50 mil"], [100000, "≥ S/ 100 mil"], [500000, "≥ S/ 500 mil"], [1000000, "≥ S/ 1 M"]].map(([value, label]) => (
                <button key={value} type="button" className="ui-fchip" aria-pressed={draft.min_amount === value} onClick={() => setDraft({ ...draft, min_amount: Number(value) })}>{label}</button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Prioridad mínima</legend>
            <div className="hist-opts">
              {PRIORITIES.map((p) => (
                <button key={p} type="button" className="ui-fchip" aria-pressed={draft.min_priority === p} onClick={() => setDraft({ ...draft, min_priority: p })}>
                  {p === "P4" ? "Todas" : p === "P1" ? "Solo críticas" : `${({ P2: "Alta", P3: "Media" } as const)[p]} o mayor`}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="hist-check"><input type="checkbox" checked={draft.historico_digest} onChange={(event) => setDraft({ ...draft, historico_digest: event.target.checked })} /> Enviarme estas alertas por correo los lunes a las 8:00</label>
          <div className="hist-preview" role="status">
            <span className="hist-muted">Con esta configuración verías</span>
            <strong className="hist-num">{preview ? `${num(preview.total)} alertas` : "…"}</strong>
            {preview ? <span className="hist-muted hist-num">{preview.counts.P1} críticas · {preview.counts.P2} altas · {preview.counts.P3} medias · {preview.counts.P4} bajas</span> : null}
          </div>
          {error ? <div className="notice danger" role="alert">{error}</div> : null}
        </div>
        <footer>
          <button className="ui-btn ui-btn-ghost" type="button" onClick={onClose}>Cancelar</button>
          <button className="ui-btn ui-btn-primary" type="button" onClick={save} disabled={saving}>{saving ? "Guardando…" : "Guardar mis alertas"}</button>
        </footer>
      </aside>
    </div>
  );
}
