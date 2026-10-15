import React, { useEffect, useMemo, useRef, useState } from "react";
import { HistoricoFilterOptions, HistoricoFilters, HistoricoKind, HistoricoPriority, HistoricoRunwayItem } from "../../api";
import { Chip, ExcelIcon, FavoriteButton, Icon } from "../../ui";
import { FavoriteKind, HistoricoComment } from "../../api";
import { useFavorites } from "../../favorites";
import { activeHistCountry, useHistCountry } from "./country";
import { useHistoricoDetail, money, moneyShort, shortDate, titleCase, num } from "./useHistorico";

export const PRIORITY_LABEL: Record<HistoricoPriority, string> = { P1: "Crítica", P2: "Alta", P3: "Media", P4: "Baja" };
const MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"];
export const monthName = (month: number) => MONTHS[month - 1] ?? String(month);

/* ---------- priority badge: ui Chip p1–p4 (color + label + glyph, never color alone) ---------- */

const PRIORITY_TONE = { P1: "p1", P2: "p2", P3: "p3", P4: "p4" } as const;

export function PriorityBadge({ priority }: { priority: HistoricoPriority | null | undefined }) {
  if (!priority) return <span className="ui-chip ui-chip-p4">Sin alerta</span>;
  return <Chip tone={PRIORITY_TONE[priority]} label={PRIORITY_LABEL[priority]} />;
}

export const priorityTone = (priority: string | null | undefined) =>
  priority === "P1" ? "var(--urg-p1-ink)" : priority === "P2" ? "var(--urg-p2-ink)" : priority === "P3" ? "var(--urg-p3-ink)" : "var(--urg-p4-ink)";

/* ---------- favorites ---------- */

/** "Por vencer" rows star the underlying award, so it also shows in Historial. */
export const FAV_KIND: Record<HistoricoKind, FavoriteKind> = {
  contrataciones: "hist_contratacion",
  vencimientos: "hist_contratacion",
  recurrentes: "hist_recurrente",
  pac: "hist_pac",
};

export function HistFav({ token, kind, row, size = "sm" }: {
  token: string;
  kind: HistoricoKind;
  row: { fav_key?: string; entity_name?: string; nomenclature?: string; supplier_name?: string; item_description?: string };
  size?: "sm" | "md";
}) {
  const favorites = useFavorites(token);
  if (!row.fav_key) return null;
  const label = [titleCase(row.entity_name ?? ""), row.nomenclature || row.supplier_name || row.item_description || ""].filter(Boolean).join(" · ");
  return (
    <FavoriteButton
      size={size}
      active={favorites.isFavorite(FAV_KIND[kind], row.fav_key)}
      onToggle={() => void favorites.toggle(FAV_KIND[kind], row.fav_key!, label)}
      label={label}
    />
  );
}

/* ---------- multi-select filter bar ---------- */

export type FilterDim = "years" | "government_levels" | "process_groups" | "categories" | "departments" | "patterns" | "situations" | "months";

const BASE_DIM_LABEL: Record<FilterDim, string> = {
  years: "Años",
  government_levels: "Nivel de gobierno",
  process_groups: "Tipo de proceso",
  categories: "Categoría",
  departments: "Departamento",
  patterns: "Patrón de compra",
  situations: "Situación",
  months: "Mes previsto",
};

/** Filter names in the active country's terms (Región / Sector in Chile). */
const DIM_LABEL = new Proxy(BASE_DIM_LABEL, {
  get(target, dim: FilterDim) {
    const country = activeHistCountry();
    if (dim === "departments") return country.department;
    if (dim === "government_levels") return country.level;
    return target[dim];
  },
}) as Record<FilterDim, string>;

function dimOptions(dim: FilterDim, options: HistoricoFilterOptions | null): Array<[string, string]> {
  if (!options) return [];
  switch (dim) {
    case "years": return options.years.map((y) => [String(y), String(y)]);
    case "government_levels": return options.government_levels.map((v) => [v, v]);
    case "process_groups": return options.process_groups.map((v) => [v, v]);
    case "categories": return options.categories.map((v) => [v, v]);
    case "departments": return options.departments.map((v) => [v, titleCase(v)]);
    case "patterns": return options.recurring_patterns.map((v) => [v, v]);
    case "situations": return options.pac_situations.map((v) => [v, v]);
    case "months": return MONTHS.map((m, i) => [String(i + 1), m]);
  }
}

function selected(filters: HistoricoFilters, dim: FilterDim): string[] {
  return ((filters[dim] as Array<string | number> | undefined) ?? []).map(String);
}

function withDim(filters: HistoricoFilters, dim: FilterDim, values: string[]): HistoricoFilters {
  const numeric = dim === "years" || dim === "months";
  return { ...filters, [dim]: numeric ? values.map(Number) : values };
}

export function FilterBar({
  dims,
  options,
  filters,
  onChange,
  extra,
  onExport,
  exporting,
  result,
  favorites = false,
}: {
  dims: FilterDim[];
  options: HistoricoFilterOptions | null;
  filters: HistoricoFilters;
  onChange: (next: HistoricoFilters) => void;
  extra?: React.ReactNode;
  onExport?: () => void;
  exporting?: boolean;
  result?: string;
  /** Show the "Favoritos" toggle (filters.favorites_only). */
  favorites?: boolean;
}) {
  const [open, setOpen] = useState<FilterDim | null>(null);
  const [search, setSearch] = useState("");
  const barRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!barRef.current?.contains(event.target as Node)) setOpen(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(null); };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", escape); };
  }, [open]);

  const chips = dims.flatMap((dim) => {
    const labels = new Map(dimOptions(dim, options));
    return selected(filters, dim).map((value) => ({ dim, value, label: `${DIM_LABEL[dim]}: ${labels.get(value) ?? value}` }));
  });
  if (filters.q) chips.push({ dim: "q" as FilterDim, value: filters.q, label: `Texto: ${filters.q}` });
  if (filters.favorites_only) chips.push({ dim: "favorites_only" as FilterDim, value: "1", label: "Solo favoritos" });
  if (filters.min_amount) chips.push({ dim: "min_amount" as FilterDim, value: String(filters.min_amount), label: `Monto ≥ ${moneyShort(filters.min_amount)}` });

  function remove(dim: string, value: string) {
    if (dim === "q") onChange({ ...filters, q: "" });
    else if (dim === "min_amount") onChange({ ...filters, min_amount: 0 });
    else if (dim === "favorites_only") onChange({ ...filters, favorites_only: false });
    else onChange(withDim(filters, dim as FilterDim, selected(filters, dim as FilterDim).filter((item) => item !== value)));
  }

  function clearAll() {
    const next: HistoricoFilters = { ...filters, q: "", min_amount: 0, favorites_only: false };
    dims.forEach((dim) => { (next as Record<string, unknown>)[dim] = []; });
    onChange(next);
  }

  return (
    <div className="hist-fbar" ref={barRef}>
      <div className="hist-fbar-row">
        {dims.map((dim) => {
          const values = selected(filters, dim);
          const all = dimOptions(dim, options);
          const label = values.length === 1 ? (all.find(([v]) => v === values[0])?.[1] ?? DIM_LABEL[dim]) : DIM_LABEL[dim];
          const visible = search && open === dim ? all.filter(([, l]) => l.toLowerCase().includes(search.toLowerCase())) : all;
          return (
            <div className="hist-msel" key={dim}>
              <button
                type="button"
                className={values.length ? "has-value" : ""}
                aria-expanded={open === dim}
                aria-haspopup="true"
                onClick={() => { setOpen(open === dim ? null : dim); setSearch(""); }}
              >
                {label}
                {values.length > 1 ? <span className="hist-badge">{values.length}</span> : null}
                <span className="hist-caret" aria-hidden="true">▾</span>
              </button>
              {open === dim ? (
                <div className="hist-pop" role="dialog" aria-label={DIM_LABEL[dim]}>
                  {all.length > 10 ? <input className="hist-pop-search" type="search" autoFocus placeholder={`Buscar ${DIM_LABEL[dim].toLowerCase()}`} value={search} onChange={(event) => setSearch(event.target.value)} /> : null}
                  <div className="hist-pop-opts">
                    {visible.map(([value, text]) => (
                      <label key={value}>
                        <input
                          type="checkbox"
                          checked={values.includes(value)}
                          onChange={(event) => onChange(withDim(filters, dim, event.target.checked ? [...values, value] : values.filter((item) => item !== value)))}
                        />
                        {text}
                      </label>
                    ))}
                    {!visible.length ? <p className="hist-muted">Sin opciones</p> : null}
                  </div>
                  <div className="hist-pop-actions">
                    <button type="button" onClick={() => onChange(withDim(filters, dim, []))}>Quitar selección</button>
                    <button type="button" onClick={() => setOpen(null)}>Listo</button>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
        {extra}
        {favorites ? (
          <button
            type="button"
            className="ui-fchip hist-fav-toggle"
            aria-pressed={Boolean(filters.favorites_only)}
            onClick={() => onChange({ ...filters, favorites_only: !filters.favorites_only })}
          >
            <Icon name="star" size={16} />Favoritos
          </button>
        ) : null}
        <span className="hist-spacer" />
        {onExport ? (
          <button className="ui-btn ui-btn-secondary" type="button" onClick={onExport} disabled={exporting}>
            <ExcelIcon /><span className="hist-export-label">{exporting ? "Generando…" : "Descargar Excel"}</span>
          </button>
        ) : null}
      </div>
      {chips.length || result ? (
        <div className="hist-chips">
          {chips.map((chip) => (
            <span className="hist-achip" key={`${chip.dim}-${chip.value}`}>
              {chip.label}
              <button type="button" aria-label={`Quitar ${chip.label}`} onClick={() => remove(chip.dim, chip.value)}>×</button>
            </span>
          ))}
          {chips.length ? <button className="hist-clear" type="button" onClick={clearAll}>Limpiar filtros</button> : null}
          {result ? <span className="hist-muted">{result}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

/** Free-text search with a short debounce, plus an optional minimum amount. */
export function SearchAndAmount({ filters, onChange, placeholder, amount = true }: {
  filters: HistoricoFilters;
  onChange: (next: HistoricoFilters) => void;
  placeholder: string;
  amount?: boolean;
}) {
  const [text, setText] = useState(filters.q ?? "");
  useEffect(() => { setText(filters.q ?? ""); }, [filters.q]);
  useEffect(() => {
    if (text === (filters.q ?? "")) return;
    const timer = window.setTimeout(() => onChange({ ...filters, q: text.trim() }), 350);
    return () => window.clearTimeout(timer);
  }, [text]);
  return (
    <>
      <input className="hist-search" type="search" aria-label="Buscar" placeholder={placeholder} value={text} onChange={(event) => setText(event.target.value)} />
      {amount ? (
        <select className="hist-select" aria-label="Monto mínimo" value={filters.min_amount ?? 0} onChange={(event) => onChange({ ...filters, min_amount: Number(event.target.value) })}>
          <option value={0}>Cualquier monto</option>
          {[50000, 100000, 500000, 1000000].map((value) => <option key={value} value={value}>≥ {moneyShort(value)}</option>)}
        </select>
      ) : null}
    </>
  );
}

/* ---------- charts ---------- */

export function HBars({ rows, limit = 8, format = (row) => moneyShort(row.value) }: {
  rows: Array<{ label: string; value: number }>;
  limit?: number;
  format?: (row: { label: string; value: number }) => string;
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  if (!rows.length) return <p className="hist-empty">Sin datos con estos filtros.</p>;
  return (
    <div className="hist-hbars">
      {rows.slice(0, limit).map((row) => (
        <div className="hist-hbar" key={row.label}>
          <span className="hist-hbar-label">{row.label}</span>
          <span className="hist-num">{format(row)}</span>
          <span className="hist-track"><i style={{ width: `${(100 * row.value) / max}%` }} /></span>
        </div>
      ))}
    </div>
  );
}

const RUNWAY_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"];

/** "Pista de vencimientos": every contract ending in the next 12 months. */
export function Runway({ items, onOpen, compact = false }: { items: HistoricoRunwayItem[]; onOpen: (id: number) => void; compact?: boolean }) {
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  // Favorite contracts glow on the runway (same store as the table stars).
  const favorites = useFavorites(localStorage.getItem("rodar_token") || "");
  const isFav = (item: HistoricoRunwayItem) => Boolean(item.fav_key && favorites.keys.has(`hist_contratacion::${item.fav_key}`));
  const W = 1000, H = compact ? 300 : 400, top = 18, base = H - 34, span = 365;
  const LANES = 16; // stacked contracts per week before marks start to overlap
  const x = (days: number) => 30 + (W - 60) * Math.min(1, Math.max(0, days / span));
  const marks = useMemo(() => {
    // Radius against the 95th percentile so one huge contract does not
    // shrink every other mark to a dot.
    const amounts = items.map((item) => item.amount).sort((a, b) => a - b);
    const ref = amounts[Math.floor(amounts.length * 0.95)] || 1;
    const lanes = new Map<number, number>();
    return [...items].sort((a, b) => b.amount - a.amount).map((item) => {
      const week = Math.floor(item.days / 7);
      const lane = lanes.get(week) ?? 0;
      lanes.set(week, lane + 1);
      return { item, cx: x(item.days), cy: base - 8 - (lane % LANES) * ((base - top - 10) / LANES), r: 3 + 8 * Math.min(1.4, Math.sqrt(item.amount / ref)) };
    });
  }, [items, compact]);
  const today = new Date();
  const ticks: Array<{ days: number; label: string }> = [];
  for (let m = 1; m <= 12; m++) {
    const date = new Date(today.getFullYear(), today.getMonth() + m, 1);
    const days = Math.round((date.getTime() - today.getTime()) / 864e5);
    if (days <= span) ticks.push({ days, label: `${RUNWAY_MONTHS[date.getMonth()]}${date.getMonth() === 0 ? ` ${date.getFullYear()}` : ""}` });
  }
  return (
    <div className="hist-runway-block">
      <div className="hist-runway-wrap">
        <div className="hist-runway" style={{ height: H + 10 }} onMouseLeave={() => setTip(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${items.length} contratos que vencen en los próximos 12 meses`}>
            <rect x={30} y={top} width={x(90) - 30} height={base - top} style={{ fill: "var(--urg-p1-bg)" }} opacity={0.6} />
            <rect x={x(90)} y={top} width={x(180) - x(90)} height={base - top} style={{ fill: "var(--urg-p2-bg)" }} opacity={0.5} />
            <text x={36} y={top + 13} style={{ fill: "var(--urg-p1-ink)" }} fontSize={11} fontWeight={700}>≤ 90 días</text>
            <text x={x(90) + 6} y={top + 13} style={{ fill: "var(--urg-p2-ink)" }} fontSize={11} fontWeight={700}>91–180 días</text>
            {ticks.map((tick) => (
              <g key={tick.days}>
                <line x1={x(tick.days)} x2={x(tick.days)} y1={top} y2={base} stroke="var(--line)" strokeDasharray="2 4" />
                <text x={x(tick.days)} y={base + 18} style={{ fill: "var(--muted)" }} fontSize={11} textAnchor="middle">{tick.label}</text>
              </g>
            ))}
            <line x1={30} x2={W - 30} y1={base} y2={base} stroke="var(--muted)" />
            <line x1={30} x2={30} y1={top - 6} y2={base} stroke="var(--urg-p1-ink)" strokeWidth={2} />
            <text x={30} y={top - 9} style={{ fill: "var(--urg-p1-ink)" }} fontSize={11} fontWeight={700} textAnchor="middle">hoy</text>
            {[...marks].sort((a, b) => Number(isFav(a.item)) - Number(isFav(b.item))).map(({ item, cx, cy, r }) => (
              <g
                key={item.id}
                className={`hist-mark${isFav(item) ? " is-fav" : ""}`}
                tabIndex={0}
                role="button"
                aria-label={`${titleCase(item.entity_name)}, ${moneyShort(item.amount)}, vence ${shortDate(item.end_date)}`}
                onClick={() => onOpen(item.id)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(item.id); } }}
                onMouseEnter={(event) => {
                  const box = (event.currentTarget.ownerSVGElement?.parentElement as HTMLElement).getBoundingClientRect();
                  const mark = event.currentTarget.getBoundingClientRect();
                  setTip({ text: `${titleCase(item.entity_name)} · ${moneyShort(item.amount)} · vence ${shortDate(item.end_date)} (${item.is_real_date ? activeHistCountry().realDate.toLowerCase() : "estimada"})`, x: Math.min(box.width - 270, Math.max(0, mark.left - box.left - 20)), y: Math.max(0, mark.top - box.top - 52) });
                }}
              >
                <line x1={cx} x2={cx} y1={cy} y2={base} stroke={priorityTone(item.priority)} strokeOpacity={0.35} />
                {isFav(item) ? <>
                  <circle className="hist-mark-glow" cx={cx} cy={cy} r={r + 3} />
                  <circle className="hist-mark-glow is-delayed" cx={cx} cy={cy} r={r + 3} />
                </> : null}
                <circle className="hist-mark-dot" cx={cx} cy={cy} r={r} style={{ fill: priorityTone(item.priority), fillOpacity: item.is_real_date ? 1 : 0.5 }} />
              </g>
            ))}
          </svg>
          {tip ? <div className="hist-tooltip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div> : null}
        </div>
      </div>
      <div className="hist-legend">
        <span><i style={{ background: "var(--urg-p1-ink)" }} />Crítica ≤ 30 d</span>
        <span><i style={{ background: "var(--urg-p2-ink)" }} />Alta</span>
        <span><i style={{ background: "var(--urg-p3-ink)" }} />Media</span>
        <span><i style={{ background: "var(--urg-p4-ink)" }} />Baja</span>
        {items.some(isFav) ? <span><i className="hist-legend-fav" />Favorito</span> : null}
        <span>Punto lleno = {activeHistCountry().code === "chile" ? "plazo declarado en la licitación" : "fecha real del contrato"} · tamaño = monto · {items.length.toLocaleString(activeHistCountry().locale)} contratos</span>
      </div>
    </div>
  );
}

/* ---------- pager ---------- */

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  return (
    <div className="hist-pager">
      <span className="hist-num">{num(from)}–{num(Math.min(total, page * pageSize))} de {num(total)}</span>
      <span className="hist-pager-actions">
        <button className="ui-btn ui-btn-secondary" type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>Anterior</button>
        <span className="hist-num">Página {page} de {pages}</span>
        <button className="ui-btn ui-btn-secondary" type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Siguiente</button>
      </span>
    </div>
  );
}

/* ---------- detail drawer ---------- */

function Fact({ label, value, wide = false }: { label: string; value: React.ReactNode; wide?: boolean }) {
  return <div className={wide ? "hist-fact-wide" : ""}><dt>{label}</dt><dd>{value || "—"}</dd></div>;
}

/* ---------- comments on a record ---------- */

type CommentRow = { fav_key?: string; comment?: { body: string; user_name: string; created_at: string } | null; comment_count?: number };

/** "Comentario" column: latest note + quick add without opening the detail. */
export function CommentCell({ token, kind, row }: { token: string; kind: HistoricoKind; row: CommentRow }) {
  const { api } = useHistCountry();
  const [latest, setLatest] = useState(row.comment ?? null);
  const [count, setCount] = useState(row.comment_count ?? 0);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setLatest(row.comment ?? null); setCount(row.comment_count ?? 0); }, [row.comment?.created_at, row.comment_count]);
  if (!row.fav_key) return null;

  async function save() {
    const body = draft.trim();
    if (!body || !row.fav_key) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.addComment(token, FAV_KIND[kind], row.fav_key, body);
      setLatest({ body: created.body, user_name: created.user_name, created_at: created.created_at });
      setCount((value) => value + 1);
      setDraft("");
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="hist-comment-cell" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      {latest && !editing ? (
        <p className="hist-comment-snippet" title={`${latest.body} — ${latest.user_name}`}>
          {latest.body}
          <span className="hist-sub">{latest.user_name}{count > 1 ? ` · ${count} comentarios` : ""}</span>
        </p>
      ) : null}
      {editing ? (
        <div className="hist-comment-inline">
          <textarea
            className="ui-input"
            autoFocus
            rows={2}
            maxLength={2000}
            value={draft}
            placeholder="Escribe y presiona Enter"
            aria-label="Nuevo comentario"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void save(); }
              if (event.key === "Escape") { setEditing(false); setDraft(""); }
            }}
          />
          <div className="hist-comment-inline-actions">
            <button type="button" className="hist-clear" onClick={() => { setEditing(false); setDraft(""); }}>Cancelar</button>
            <button type="button" className="ui-btn ui-btn-primary ui-btn-sm" disabled={busy || !draft.trim()} onClick={() => void save()}>{busy ? "Guardando…" : "Guardar"}</button>
          </div>
          {error ? <span className="hist-comment-error" role="alert">{error}</span> : null}
        </div>
      ) : (
        <button type="button" className="hist-comment-add" onClick={() => setEditing(true)}>{latest ? "+ Comentar" : "+ Agregar comentario"}</button>
      )}
    </div>
  );
}

function HistComments({ token, kind, refKey }: { token: string; kind: HistoricoKind; refKey: string }) {
  const { api, locale } = useHistCountry();
  const [items, setItems] = useState<HistoricoComment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setItems(null);
    api.comments(token, FAV_KIND[kind], refKey)
      .then((rows) => { if (active) setItems(rows); })
      .catch((err) => { if (active) { setItems([]); setError(err instanceof Error ? err.message : "No se pudieron cargar los comentarios"); } });
    return () => { active = false; };
  }, [api, token, kind, refKey]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!body) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.addComment(token, FAV_KIND[kind], refKey, body);
      setItems((current) => [created, ...(current ?? [])]);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el comentario");
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: HistoricoComment) {
    setError("");
    try {
      await api.deleteComment(token, item.id);
      setItems((current) => (current ?? []).filter((row) => row.id !== item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo borrar el comentario");
    }
  }

  return (
    <section className="hist-comments" aria-label="Comentarios">
      <h3>Comentarios{items?.length ? ` (${items.length})` : ""}</h3>
      <form className="hist-comment-form" onSubmit={add}>
        <textarea
          className="ui-input"
          value={draft}
          maxLength={2000}
          rows={3}
          placeholder="Agrega una nota para el equipo: contacto, próximos pasos, observaciones…"
          aria-label="Nuevo comentario"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button className="ui-btn ui-btn-primary ui-btn-sm" type="submit" disabled={busy || !draft.trim()}>{busy ? "Guardando…" : "Agregar comentario"}</button>
      </form>
      {error ? <div className="notice danger" role="alert">{error}</div> : null}
      {items === null ? <p className="hist-muted">Cargando comentarios…</p> : null}
      {items?.length === 0 ? <p className="hist-muted">Aún no hay comentarios.</p> : null}
      <ul className="hist-comment-list">
        {(items ?? []).map((item) => (
          <li key={item.id}>
            <div className="hist-row">
              <span className="hist-strong">{item.user_name}</span>
              <span className="hist-muted">{new Date(item.created_at.endsWith("Z") ? item.created_at : `${item.created_at}Z`).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}</span>
            </div>
            <p>{item.body}</p>
            {item.can_delete ? <button type="button" className="hist-clear" onClick={() => void remove(item)}>Borrar</button> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DetailDrawer({ token, kind, id, onClose }: { token: string; kind: HistoricoKind; id: number | null; onClose: () => void }) {
  const country = useHistCountry();
  const { detail, error } = useHistoricoDetail(token, kind, id);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (id === null) return;
    closeRef.current?.focus();
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [id]);
  if (id === null) return null;
  const record = (detail?.record ?? {}) as Record<string, any>;
  const history = detail?.entity_history ?? [];
  const maxYear = Math.max(...history.map((item) => item.amount), 1);
  const start = record.start_date || record.date;
  const pct = start && record.end_date
    ? Math.min(100, Math.max(0, (100 * (Date.now() - new Date(start).getTime())) / (new Date(record.end_date).getTime() - new Date(start).getTime() || 1)))
    : null;
  return (
    <div className="hist-overlay">
      <div className="hist-scrim" onClick={onClose} />
      <aside className="hist-drawer" role="dialog" aria-modal="true" aria-labelledby="hist-drawer-title">
        <header>
          <div className="hist-drawer-heading">
            <span className="hist-tags">
              {record.priority !== undefined ? <PriorityBadge priority={record.priority} /> : null}
              {record.bucket ? <span className="hist-tag">{record.bucket}</span> : null}
              {record.is_real_date !== undefined ? <span className={`hist-tag ${record.is_real_date ? "real" : ""}`}>{record.is_real_date ? country.realDate : "Fecha estimada"}</span> : null}
              {record.possibly_renewed ? <span className="hist-tag">Posible renovado</span> : null}
            </span>
            <h2 id="hist-drawer-title">{detail ? titleCase(record.entity_name) : "Cargando…"}</h2>
            <span className="hist-sub">{record.nomenclature || record.supplier_name || record.process_type || ""}</span>
          </div>
          <div className="hist-drawer-actions">
            {detail ? <HistFav token={token} kind={kind} row={record} size="md" /> : null}
            <button ref={closeRef} className="ui-btn ui-btn-ghost ui-btn-icon-only" type="button" onClick={onClose} aria-label="Cerrar detalle"><Icon name="close" size={18} /></button>
          </div>
        </header>
        <div className="hist-drawer-body">
          {error ? <div className="notice danger" role="alert">{error}</div> : null}
          {detail && pct !== null && record.end_date ? (
            <section>
              <div className="hist-timeline">
                <div className="hist-tl-track" />
                <div className="hist-tl-fill" style={{ width: `${pct}%` }} />
                <div className="hist-tl-now" style={{ left: `${pct}%` }} />
                <span className="hist-tl-label" style={{ left: 0 }}>Inicio {shortDate(start)}</span>
                <span className="hist-tl-label" style={{ right: 0 }}>Fin {shortDate(record.end_date)}</span>
              </div>
              <p className="hist-muted">{record.date_source}. {record.days_to_end >= 0 ? <>Vence en <strong>{record.days_to_end} días</strong>.</> : <>Venció hace {-record.days_to_end} días.</>}</p>
            </section>
          ) : null}
          {detail ? (
            <dl className="hist-facts">
              {kind === "recurrentes" ? <>
                <Fact label="Proveedor actual" value={titleCase(record.supplier_name)} />
                <Fact label="Patrón" value={record.pattern} />
                <Fact label="Próxima compra estimada" value={shortDate(record.next_purchase_date)} />
                <Fact label="Monto 12 meses (proveedor)" value={money(record.amount_12m_supplier)} />
                <Fact label="Órdenes en 12 meses" value={record.orders_12m} />
                <Fact label="Proveedores de la entidad" value={record.suppliers_12m} />
                <Fact label="Última orden" value={record.last_order_description} wide />
              </> : kind === "pac" ? <>
                <Fact label="Mes previsto" value={monthName(record.planned_month)} />
                <Fact label="Situación" value={record.situation} />
                <Fact label="Tipo de proceso" value={record.process_type} />
                <Fact label="Objeto" value={record.object_type} />
                <Fact label="Cantidad" value={`${record.quantity ?? ""} ${record.unit ?? ""}`} />
                <Fact label="Lugar del ítem" value={[record.item_department, record.province, record.district].filter(Boolean).map(titleCase).join(" · ")} />
                <Fact label="Descripción" value={record.item_description || record.process_description} wide />
              </> : <>
                <Fact label="Proveedor" value={titleCase(record.supplier_name)} />
                <Fact label="Monto adjudicado" value={money(record.amount)} />
                {record.monthly_amount !== undefined ? <Fact label="Monto mensual aprox." value={money(record.monthly_amount)} /> : null}
                {record.extras_amount !== undefined && (country.code === "peru" || record.extras_amount > 0) ? <Fact label="Adicionales y prórrogas" value={money(record.extras_amount)} /> : null}
                <Fact label="Tipo de proceso" value={record.process_group} />
                <Fact label="Categoría" value={record.category} />
                <Fact label={country.department} value={titleCase(record.department)} />
                <Fact label={country.level} value={record.government_level} />
                {record.direct_cause ? <Fact label={country.code === "chile" ? "Causal (trato directo)" : "Causal (contratación directa)"} value={record.direct_cause} wide /> : null}
                <Fact label="Descripción" value={record.description} wide />
              </>}
            </dl>
          ) : null}
          {record.contract_url ? <a className="ui-btn ui-btn-secondary" href={record.contract_url} target="_blank" rel="noopener noreferrer">{country.officialRecordLink}</a> : null}
          {detail && record.fav_key ? <HistComments token={token} kind={kind} refKey={record.fav_key} /> : null}
          {history.length ? (
            <section>
              <h3>Compras del rubro de la entidad por año</h3>
              <div className="hist-years">
                {history.map((item) => (
                  <div key={item.year}><i style={{ height: `${Math.max(3, (56 * item.amount) / maxYear)}px` }} title={money(item.amount)} /><span>{item.year}</span></div>
                ))}
              </div>
            </section>
          ) : null}
          {detail?.entity_suppliers.length ? (
            <section>
              <h3>Proveedores de esta entidad</h3>
              <HBars rows={detail.entity_suppliers.map((item) => ({ label: titleCase(item.name), value: item.amount }))} limit={5} />
            </section>
          ) : null}
          {detail?.related_awards.length ? (
            <section>
              <h3>Otros procesos adjudicados por la entidad</h3>
              <ul className="hist-related">
                {detail.related_awards.slice(0, 5).map((award) => (
                  <li key={award.id}><strong>{award.nomenclature}</strong><span>{shortDate(award.date)} · {titleCase(award.supplier_name)} · {moneyShort(award.amount)}</span></li>
                ))}
              </ul>
            </section>
          ) : null}
          {kind === "recurrentes" && record.orders?.length ? (
            <section>
              <h3>Órdenes recientes</h3>
              <ul className="hist-related">
                {record.orders.slice(0, 8).map((order: any) => <li key={order.id}><strong>{shortDate(order.date)} · {money(order.amount)}</strong><span>{order.description}</span></li>)}
              </ul>
            </section>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
