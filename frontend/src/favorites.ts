import { useEffect, useSyncExternalStore } from "react";
import { api, FavoriteKind } from "./api";

/* One shared, per-session favorites store: every star on every page reads the
   same set, so starring a contract in "Por vencer" also lights it in Historial. */

type Snapshot = { keys: ReadonlySet<string>; loaded: boolean };

let snapshot: Snapshot = { keys: new Set(), loaded: false };
let loadedFor = "";
const listeners = new Set<() => void>();

const id = (kind: FavoriteKind, refKey: string) => `${kind}::${refKey}`;

function publish(keys: ReadonlySet<string>, loaded = true) {
  snapshot = { keys, loaded };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function load(token: string) {
  if (!token || loadedFor === token) return;
  loadedFor = token;
  api.favorites(token)
    .then((items) => publish(new Set(items.map((item) => id(item.kind, item.ref_key)))))
    .catch(() => { loadedFor = ""; });
}

export function useFavorites(token: string) {
  const state = useSyncExternalStore(subscribe, () => snapshot);
  useEffect(() => load(token), [token]);

  const isFavorite = (kind: FavoriteKind, refKey: string) => state.keys.has(id(kind, refKey));
  const count = (kind: FavoriteKind) => [...state.keys].filter((key) => key.startsWith(`${kind}::`)).length;

  /** Optimistic toggle; rolls back if the API call fails. */
  async function toggle(kind: FavoriteKind, refKey: string, label = "") {
    const key = id(kind, refKey);
    const before = snapshot.keys;
    const next = new Set(before);
    const adding = !next.has(key);
    if (adding) next.add(key);
    else next.delete(key);
    publish(next);
    try {
      if (adding) await api.addFavorite(token, { kind, ref_key: refKey, label: label.slice(0, 300) });
      else await api.removeFavorite(token, kind, refKey);
    } catch {
      publish(before);
    }
  }

  return { isFavorite, toggle, count, keys: state.keys, loaded: state.loaded };
}

/** localStorage-backed state for filters that must survive page/module switches. */
export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode / blocked storage: filters just won't persist.
  }
}
