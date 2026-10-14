// GovRadar SaaS — marca configurable por cliente (tenant).
// Fuente: docs/design/brand.ts. El cliente elige SOLO un color primario (y su
// logo); todo lo demás se deriva aquí. Las señales y urgencias nunca cambian
// con la marca.

export type TenantBrand = {
  name: string; // "RODAR Consulting"
  logoUrl: string | null; // logo sobre fondo blanco; se muestra en una pastilla blanca
  primary: string; // "#185bc1"
};

export const DEFAULT_BRAND: TenantBrand = {
  name: "RODAR Consulting",
  logoUrl: "/assets/Rodarfondoblanco.png",
  primary: "#185bc1",
};

export const SUGGESTED_PRIMARIES = ["#185bc1", "#0b6e74", "#b4461b", "#1f2a44"];

const HEX = /^#?([0-9a-f]{6})$/i;

export function isHexColor(value: string): boolean {
  return HEX.test(value.trim());
}

function toRgb(hex: string): [number, number, number] {
  const m = HEX.exec(hex.trim());
  if (!m) throw new Error(`Color inválido: ${hex}`);
  const n = parseInt(m[1], 16);
  return [n >> 16, (n >> 8) & 255, n & 255];
}

function toHex(rgb: number[]): string {
  return "#" + rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");
}

/** Mezcla un color con negro (target 0) o blanco (target 255) en proporción w (0–1). */
export function mix(hex: string, target: 0 | 255, w: number): string {
  return toHex(toRgb(hex).map((c) => c + (target - c) * w));
}

function luminance(hex: string): number {
  const [r, g, b] = toRgb(hex).map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Garantiza texto blanco legible (>= 4.5:1) sobre el primario.
 * Si el color del cliente es muy claro, lo oscurece en pasos de 5% y avisa.
 */
export function safePrimary(primary: string): { color: string; adjusted: boolean } {
  let color = primary;
  let step = 0;
  while (contrast(color, "#ffffff") < 4.5 && step < 12) {
    step += 1;
    color = mix(primary, 0, step * 0.05);
  }
  return { color, adjusted: color.toLowerCase() !== primary.toLowerCase() };
}

export function deriveBrandVars(primary: string): Record<string, string> {
  const { color } = safePrimary(primary);
  const [r, g, b] = toRgb(color);
  return {
    "--brand": color,
    "--brand-hover": mix(color, 0, 0.18),
    "--brand-soft": mix(color, 255, 0.9),
    "--brand-ink": mix(color, 0, 0.35),
    "--brand-ring": `rgba(${r}, ${g}, ${b}, 0.22)`,
    "--on-brand": "#ffffff",
  };
}

/** Llamar al iniciar sesión / al cargar la configuración del tenant. */
export function applyTenantBrand(brand: TenantBrand, root: HTMLElement = document.documentElement) {
  const primary = isHexColor(brand.primary) ? brand.primary : DEFAULT_BRAND.primary;
  const vars = deriveBrandVars(primary.startsWith("#") ? primary : `#${primary}`);
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
}

/** Normaliza lo que venga de app_settings (puede faltar o venir parcial). */
export function normalizeBrand(value: Partial<TenantBrand> | null | undefined): TenantBrand {
  return {
    name: value?.name?.trim() || DEFAULT_BRAND.name,
    logoUrl: value?.logoUrl || DEFAULT_BRAND.logoUrl,
    primary: value?.primary && isHexColor(value.primary) ? value.primary : DEFAULT_BRAND.primary,
  };
}
