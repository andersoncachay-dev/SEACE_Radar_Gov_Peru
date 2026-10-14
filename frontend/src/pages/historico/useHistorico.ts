import { useCallback, useEffect, useRef, useState } from "react";
import { readStored, writeStored } from "../../favorites";
import {
  historicoApi,
  HistoricoDetail,
  HistoricoFilterOptions,
  HistoricoFilters,
  HistoricoKind,
  HistoricoPage,
  HistoricoRowByKind,
  HistoricoStatus,
} from "../../api";

/** Data for Histórico Perú is monthly, so it is fetched per view on demand
 * (no 60 s polling like the live radar) and cached for the session. */

/** useState that survives page and module switches (and reloads) via
 * localStorage, so a filter set up once is still there when the user returns. */
export function useStoredState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => readStored(`govradar.hist.${key}`, initial));
  useEffect(() => writeStored(`govradar.hist.${key}`, value), [key, value]);
  return [value, setValue] as const;
}

let optionsCache: HistoricoFilterOptions | null = null;
let statusCache: HistoricoStatus | null = null;

export function useHistoricoMeta(token: string) {
  const [options, setOptions] = useState<HistoricoFilterOptions | null>(optionsCache);
  const [status, setStatus] = useState<HistoricoStatus | null>(statusCache);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([optionsCache ? Promise.resolve(optionsCache) : historicoApi.filters(token), historicoApi.status(token)])
      .then(([nextOptions, nextStatus]) => {
        optionsCache = nextOptions;
        statusCache = nextStatus;
        if (active) {
          setOptions(nextOptions);
          setStatus(nextStatus);
        }
      })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "No se pudo cargar Histórico Perú"); });
    return () => { active = false; };
  }, [token]);
  return { options, status, error };
}

/** Run `load` whenever its dependencies change, ignoring stale responses. */
export function useLatest<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const ticket = useRef(0);
  const reload = useCallback(() => {
    const current = ++ticket.current;
    setLoading(true);
    setError("");
    load()
      .then((value) => { if (current === ticket.current) setData(value); })
      .catch((err) => { if (current === ticket.current) setError(err instanceof Error ? err.message : "No se pudo cargar la información"); })
      .finally(() => { if (current === ticket.current) setLoading(false); });
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, error, reload };
}

export function useHistoricoList<K extends HistoricoKind>(token: string, kind: K, filters: HistoricoFilters, sort: string, pageSize = 50) {
  const [page, setPage] = useState(1);
  const filterKey = JSON.stringify(filters);
  useEffect(() => { setPage(1); }, [filterKey, sort]);
  const result = useLatest<HistoricoPage<HistoricoRowByKind[K]>>(
    () => historicoApi.list(token, kind, filters, page, pageSize, sort),
    [token, kind, filterKey, sort, page, pageSize],
  );
  return { ...result, page, setPage, pageSize };
}

export function useHistoricoDetail(token: string, kind: HistoricoKind, id: number | null) {
  const [detail, setDetail] = useState<HistoricoDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (id === null) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetail(null);
    setError("");
    historicoApi.detail(token, kind, id)
      .then((value) => { if (active) setDetail(value); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "No se pudo cargar el detalle"); });
    return () => { active = false; };
  }, [token, kind, id]);
  return { detail, error };
}

export async function downloadExport(token: string, kind: HistoricoKind, filters: HistoricoFilters, sort?: string) {
  const blob = await historicoApi.exportXlsx(token, kind, filters, sort);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  const names: Record<HistoricoKind, string> = {
    contrataciones: "Historial de contrataciones",
    vencimientos: "Contratos por vencer",
    recurrentes: "Compras recurrentes",
    pac: "PAC",
  };
  link.href = url;
  link.download = `Histórico Perú - ${names[kind]} ${stamp}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toggleValue<T>(values: T[] | undefined, value: T): T[] {
  const current = values ?? [];
  return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
}

export const money = (value: number) => `S/ ${Math.round(value || 0).toLocaleString("es-PE")}`;

export function moneyShort(value: number) {
  if (value >= 1e6) return `S/ ${(value / 1e6).toLocaleString("es-PE", { maximumFractionDigits: 1 })} M`;
  if (value >= 1e3) return `S/ ${Math.round(value / 1e3).toLocaleString("es-PE")} mil`;
  return money(value);
}

export function shortDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
}

/** CONOSCE ships entity and supplier names in capitals; show them in title case. */
export function titleCase(value: string | null | undefined) {
  return String(value || "").toLocaleLowerCase("es").replace(/(^|[\s/(-])(\p{L})/gu, (_, gap: string, letter: string) => gap + letter.toLocaleUpperCase("es"));
}
