import React, { createContext, useContext } from "react";
import { HistoricoApi, historicoApi, historicoChileApi } from "../../api";

/* Histórico Perú and Histórico Chile share every screen; what differs lives
   here: the API base, currency and number locale, and the labels that name
   Peruvian concepts (departamento, nivel de gobierno, UIT, SEACE...). */

export type HistCountryCode = "peru" | "chile";

export type HistCountry = {
  code: HistCountryCode;
  module: "historico_peru" | "historico_chile";
  api: HistoricoApi;
  label: string; // "Histórico Perú"
  source: string; // page subtitle
  sourceShort: string; // "CONOSCE"
  locale: string;
  currency: string;
  department: string;
  departments: string;
  level: string;
  taxId: string; // RUC / RUT
  awardDate: string; // buena pro / adjudicación
  contractsTab: string;
  contractsWindow: string; // "Contratos > 8 UIT"
  recurringTab: string;
  recurringTitle: string;
  smallPurchases: string; // history subtitle
  realDate: string; // tag on dates that come from the official record
  realDateOnly: string;
  officialRecordLink: string; // drawer button
  searchPlaceholder: string;
  hasPac: boolean;
  monthlyLag: string; // note under "Monto por mes"
  firstLoad: string;
  storagePrefix: string; // localStorage namespace (Perú keeps the original keys)
  amountChoices: Array<[number, string]>; // "Mis alertas" minimum amount
  highAmount: number; // "Contratos ≥ ..." shortcut
  map: "peru" | "chile";
};

const PERU: HistCountry = {
  code: "peru",
  module: "historico_peru",
  api: historicoApi,
  label: "Histórico Perú",
  source: "Datos abiertos OECE · CONOSCE",
  sourceShort: "CONOSCE",
  locale: "es-PE",
  currency: "S/",
  department: "Departamento",
  departments: "Departamentos",
  level: "Nivel de gobierno",
  taxId: "RUC",
  awardDate: "buena pro",
  contractsTab: "Contratos > 8 UIT",
  contractsWindow: "Contratos > 8 UIT",
  recurringTab: "Compras recurrentes ≤ 8 UIT",
  recurringTitle: "Próximas compras ≤ 8 UIT",
  smallPurchases: "Órdenes ≤ 8 UIT (fecha de emisión) e ítems adjudicados > 8 UIT (fecha de buena pro).",
  realDate: "Fecha real",
  realDateOnly: "Solo fecha real",
  officialRecordLink: "Ver contrato en SEACE",
  searchPlaceholder: "Busca entidad, proveedor, RUC o nomenclatura",
  hasPac: true,
  monthlyLag: "El mes en curso es parcial: OECE lo completa en la siguiente publicación.",
  firstLoad: 'La primera carga se hace desde Configuración › Histórico Perú (botón "Actualizar ahora" o "Cargar archivos"). Toma unos 40 minutos; luego el módulo se actualiza solo cada mes.',
  storagePrefix: "",
  amountChoices: [[0, "Cualquiera"], [50000, "≥ S/ 50 mil"], [100000, "≥ S/ 100 mil"], [500000, "≥ S/ 500 mil"], [1000000, "≥ S/ 1 M"]],
  highAmount: 500000,
  map: "peru",
};

const CHILE: HistCountry = {
  code: "chile",
  module: "historico_chile",
  api: historicoChileApi,
  label: "Histórico Chile",
  source: "Datos abiertos ChileCompra · Mercado Público",
  sourceShort: "ChileCompra",
  locale: "es-CL",
  currency: "$",
  department: "Región",
  departments: "Regiones",
  level: "Sector",
  taxId: "RUT",
  awardDate: "adjudicación",
  contractsTab: "Contratos (licitaciones)",
  contractsWindow: "Contratos adjudicados por licitación",
  recurringTab: "Compras recurrentes (Compra Ágil y trato directo)",
  recurringTitle: "Próximas compras por Compra Ágil y trato directo",
  smallPurchases: "Órdenes de compra de Compra Ágil, trato directo y convenio marco (fecha de envío) y líneas adjudicadas de licitaciones (fecha de adjudicación).",
  realDate: "Plazo declarado",
  realDateOnly: "Solo plazo declarado",
  officialRecordLink: "Ver licitación en Mercado Público",
  searchPlaceholder: "Busca organismo, proveedor, RUT o código",
  hasPac: false,
  monthlyLag: "El mes en curso es parcial: ChileCompra lo completa a medida que se emiten órdenes y se adjudican licitaciones.",
  firstLoad: 'La primera carga se hace desde Configuración › Histórico Chile (botón "Actualizar ahora"). Lee 2023 a hoy desde ChileCompra en unos 40 minutos; luego el módulo se actualiza solo cada mes.',
  storagePrefix: "chile.",
  amountChoices: [[0, "Cualquiera"], [10_000_000, "≥ $10 M"], [25_000_000, "≥ $25 M"], [125_000_000, "≥ $125 M"], [250_000_000, "≥ $250 M"]],
  highAmount: 125_000_000,
  map: "chile",
};

export const HIST_COUNTRIES: Record<HistCountryCode, HistCountry> = { peru: PERU, chile: CHILE };

// Plain helpers (money, dates, labels) read the country being rendered. Only
// one Histórico country is on screen at a time and the provider sets this
// before its children render.
let active: HistCountry = PERU;
export const activeHistCountry = () => active;

const HistCountryContext = createContext<HistCountry>(PERU);

export function HistCountryProvider({ country, children }: { country: HistCountryCode; children: React.ReactNode }) {
  active = HIST_COUNTRIES[country];
  return <HistCountryContext.Provider value={HIST_COUNTRIES[country]}>{children}</HistCountryContext.Provider>;
}

export function useHistCountry(): HistCountry {
  return useContext(HistCountryContext);
}
