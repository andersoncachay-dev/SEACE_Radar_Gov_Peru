import { useCallback, useEffect, useRef, useState } from "react";
import { readStored, writeStored } from "../../favorites";
import { activeHistCountry, useHistCountry } from "./country";
import {
  HistoricoDetail,
  HistoricoFilterOptions,
  HistoricoFilters,
  HistoricoKind,
  HistoricoPage,
  HistoricoRowByKind,
  HistoricoStatus,
} from "../../api";

/** Histórico data is monthly, so it is fetched per view on demand (no 60 s
 * polling like the live radar) and cached per country for the session. */

/** useState that survives page and module switches (and reloads) via
 * localStorage, so a filter set up once is still there when the user returns. */
export function useStoredState<T>(key: string, initial: T) {
  const storageKey = `govradar.hist.${useHistCountry().storagePrefix}${key}`;
  const [value, setValue] = useState<T>(() => readStored(storageKey, initial));
  useEffect(() => writeStored(storageKey, value), [storageKey, value]);
  return [value, setValue] as const;
}

const optionsCache: Partial<Record<string, HistoricoFilterOptions>> = {};
const statusCache: Partial<Record<string, HistoricoStatus>> = {};

export function useHistoricoMeta(token: string) {
  const country = useHistCountry();
  const [options, setOptions] = useState<HistoricoFilterOptions | null>(optionsCache[country.code] ?? null);
  const [status, setStatus] = useState<HistoricoStatus | null>(statusCache[country.code] ?? null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const cached = optionsCache[country.code];
    Promise.all([cached ? Promise.resolve(cached) : country.api.filters(token), country.api.status(token)])
      .then(([nextOptions, nextStatus]) => {
        optionsCache[country.code] = nextOptions;
        statusCache[country.code] = nextStatus;
        if (active) {
          setOptions(nextOptions);
          setStatus(nextStatus);
        }
      })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : `No se pudo cargar ${country.label}`); });
    return () => { active = false; };
  }, [token, country]);
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
  const { api } = useHistCountry();
  const [page, setPage] = useState(1);
  const filterKey = JSON.stringify(filters);
  useEffect(() => { setPage(1); }, [filterKey, sort]);
  const result = useLatest<HistoricoPage<HistoricoRowByKind[K]>>(
    () => api.list(token, kind, filters, page, pageSize, sort),
    [api, token, kind, filterKey, sort, page, pageSize],
  );
  return { ...result, page, setPage, pageSize };
}

export function useHistoricoDetail(token: string, kind: HistoricoKind, id: number | null) {
  const { api } = useHistCountry();
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
    api.detail(token, kind, id)
      .then((value) => { if (active) setDetail(value); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "No se pudo cargar el detalle"); });
    return () => { active = false; };
  }, [api, token, kind, id]);
  return { detail, error };
}

export async function downloadExport(token: string, kind: HistoricoKind, filters: HistoricoFilters, sort?: string) {
  const country = activeHistCountry();
  const blob = await country.api.exportXlsx(token, kind, filters, sort);
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
  link.download = `${country.label} - ${names[kind]} ${stamp}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toggleValue<T>(values: T[] | undefined, value: T): T[] {
  const current = values ?? [];
  return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
}

// toLocaleString/toLocaleDateString build a new Intl formatter on every call;
// Histórico lists format thousands of cells, so keep one per locale (this was
// most of the time spent opening Histórico on a phone).
const formatters = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat>();
function cached<T extends Intl.NumberFormat | Intl.DateTimeFormat>(key: string, build: () => T): T {
  let formatter = formatters.get(key) as T | undefined;
  if (!formatter) {
    formatter = build();
    formatters.set(key, formatter);
  }
  return formatter;
}
const integer = (locale: string) => cached(`int:${locale}`, () => new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }));
const oneDecimal = (locale: string) => cached(`dec1:${locale}`, () => new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }));
const dayMonthYear = (locale: string) => cached(`dmy:${locale}`, () => new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", year: "numeric" }));

export const money = (value: number) => {
  const { currency, locale } = activeHistCountry();
  return `${currency} ${integer(locale).format(Math.round(value || 0))}`;
};

export function moneyShort(value: number) {
  const { currency, locale } = activeHistCountry();
  // From 10 thousand million on (Chilean pesos), "mil M" keeps figures short.
  if (value >= 1e10) return `${currency} ${integer(locale).format(Math.round(value / 1e9))} mil M`;
  if (value >= 1e6) return `${currency} ${(value >= 1e8 ? integer(locale) : oneDecimal(locale)).format(value / 1e6)} M`;
  if (value >= 1e3) return `${currency} ${integer(locale).format(Math.round(value / 1e3))} mil`;
  return money(value);
}

/** Integers in the active country's format (12.345 in Chile, 12,345 in Perú). */
export const num = (value: number) => integer(activeHistCountry().locale).format(value || 0);

export function shortDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return dayMonthYear(activeHistCountry().locale).format(new Date(`${iso.slice(0, 10)}T12:00:00`));
}

/** CONOSCE and ChileCompra ship names in capitals; show them in title case. */
export function titleCase(value: string | null | undefined) {
  return String(value || "").toLocaleLowerCase("es").replace(/(^|[\s/(-])(\p{L})/gu, (_, gap: string, letter: string) => gap + letter.toLocaleUpperCase("es"));
}
