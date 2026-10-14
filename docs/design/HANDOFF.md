# GovRadar SaaS — handoff de diseño para implementación

Repositorio: `andersoncachay-dev/SEACE_Radar_Gov_Peru` · frontend en `frontend/` (React 19 + Vite, CSS plano en `src/styles.css`).

## Objetivo

1. **Homologar** Radar en vivo e Histórico Perú: un solo set de componentes, una escala tipográfica, un estilo de botón.
2. **Responsive real**: layouts distintos para celular, tablet y laptop, no la misma pantalla encogida.
3. **Base SaaS**: la marca (logo + color primario + nombre) se configura por cliente sin tocar código.

No se cambia lógica de negocio, endpoints ni datos. Es un cambio de presentación.

## Fuente de verdad

| Qué | Dónde |
|---|---|
| Mockups aprobados (7 pantallas) | `mockups/*.dc.html` en esta carpeta (lee el HTML/CSS; el `support.js` que referencian no existe fuera del lienzo, ignóralo) |
| Tokens | `tokens.css` en esta carpeta |
| Marca por cliente | `brand.ts` en esta carpeta |

Mockups: `Main.dc.html` (Radar laptop 1440), `Radar-Tablet.dc.html` (834), `Radar-Phone.dc.html` (390), `Historico-Laptop/Tablet/Phone.dc.html`, `Componentes.dc.html` (hoja de componentes y reglas).
Los datos de los mockups son de ejemplo; en la app se usan los reales.

## Reglas de diseño (no negociables)

- Todo color, tamaño, radio y espacio sale de `tokens.css`. Ningún hex nuevo en componentes.
- Botones: radio `--radius-sm` (8px), peso 600, 14px. Alturas: 32 (tablas/filtros), 40 (laptop), 44 (tablet y celular).
- Variantes de botón: `primary` (una sola por pantalla), `secondary`, `ghost`, `danger`. **Exportar siempre es `secondary` con ícono de descarga, en ambos módulos** (se elimina el verde de `.hist-btn-excel`).
- Peso 800 sólo en cifras KPI. Nada de 850/900.
- Escala tipográfica única: 28 KPI · 20 título de página · 16 sección · 15 título de tarjeta · 14 cuerpo · 13 tabla/etiqueta · 12 nota/chip · 11 micro.
- Estados (señal comercial, urgencia P1–P4, estado de ejecución) usan el MISMO componente `Chip`: píldora 24px, 12px/600, color + texto + marca (punto para señal, glifo ▲▲ ▲ ● ○ para urgencia). Nunca sólo color.
- Señales y urgencias NO cambian con la marca del cliente; sólo `--brand-*` cambia.
- Foco visible: `box-shadow: 0 0 0 3px var(--brand-ring)` + borde `--brand` en campos; outline equivalente en botones.
- Íconos: SVG de trazo 1.8, 20px, `currentColor` (los paths están en los mockups). Sin emojis.
- Respetar `prefers-reduced-motion`.

## Breakpoints y layout

| | Celular `< 640px` | Tablet `640–1023px` | Laptop `≥ 1024px` |
|---|---|---|---|
| Navegación | Barra inferior fija, 5 pestañas por módulo + badge de alertas; safe-area | Riel de íconos 76px (`--shell-bg`) con etiqueta corta | Sidebar 248px con logo, selector de módulo, secciones y usuario |
| Selector de módulo | Botón en encabezado oscuro ("Radar en vivo ▾") que abre hoja | Segmentado claro arriba del contenido | Segmentado oscuro dentro del sidebar |
| País | Botón compacto con bandera + código (PE) | Botón con bandera + nombre | Botón con bandera + nombre en topbar |
| KPI | Carrusel horizontal, tarjetas 132px, cifra 24px | Grilla 2 columnas (4 KPI) | Grilla 5 columnas |
| Listados | Tarjetas apiladas (chip + días restantes / entidad / descripción / monto + fecha) | Filas de 2 líneas, monto y fecha alineados a la derecha | Tabla completa, cabecera fija, columnas configurables |
| Filtros | Chips con scroll horizontal + botón "Filtros" que abre hoja inferior | Buscador + botón "Filtros · N" | Chips de filtro con conteo + "Más filtros" + "Columnas" |
| Acciones de página | Dentro de la tarjeta/hoja; botón flotante sólo si es la acción primaria | Exportar como ícono + primaria con texto | Exportar + primaria con texto |

Pestañas inferiores — Radar: Inicio · Oportunidades · Seguimiento · Alertas · Más. Histórico: Resumen · Historial · Por vencer · Alertas · Más.
"Más" lleva lo restante (Procesos eliminados, PAC Perú, Usuarios, Configuración).

## Componentes a crear (`frontend/src/ui/`)

| Componente | Props clave | Reemplaza |
|---|---|---|
| `Button` | `variant: primary\|secondary\|ghost\|danger`, `size: sm\|md\|touch`, `icon`, `iconOnly` + `aria-label` | `.primary`, `.ghost`, `.manual-update-button`, `.hist-btn*`, `.rule-action-button*` |
| `Chip` | `tone: signal-green\|signal-amber\|signal-pending\|signal-red\|p1\|p2\|p3\|p4\|info`, `label` | `.status.*`, `.priority`, `.commercial-signal.*`, `.home-status-badge.*`, `.hist-prio`, `.hist-tag` |
| `FilterChip` | `active`, `count`, `dot?`, `glyph?` | `.commercial-filter.*`, filtros del Histórico |
| `KpiCard` | `label`, `value`, `hint`, `onClick?`, `active?` | `.kpi`, `.kpi-action*`, KPI del Histórico |
| `Card` | `padding` | `.panel`, `.hist-panel`, `.list-row` |
| `TextField`, `SelectField`, `SearchField` | `label`, `hint`, `error` | `input/select` globales, `.hist-select`, `.hist-search` |
| `DataTable` | `columns` (con `priority` para decidir qué se ve en tablet), `rows`, `renderMobileCard(row)` | tablas de `OpportunitiesPage`, `OpportunityTrackingPage`, `HistoricoPages` |
| `AppShell` | `module`, `navItems`, `children` → renderiza `Sidebar` / `NavRail` / `BottomNav` según breakpoint | `.app-shell`, `.topbar`, `.launcher-*`, `.menu-toggle` |
| `ModuleSwitcher` | `value: radar\|historico_peru`, `variant: dark\|light\|sheet` | `.launcher-modules` |
| `CountrySelector` | `value`, `compact` | selector actual de país + `CountryFlagIcon` |
| `PageHeader` | `title`, `meta` (actualizado hace…/fuente), `actions` | encabezados actuales de cada página |
| `EmptyState`, `ConfirmModal` | — | `Empty`, `ConfirmModal` de `shared.tsx` (reestilizar, misma API) |

Usa un hook `useBreakpoint()` (`matchMedia`) para `AppShell` y `DataTable`; el resto responde con CSS.
Estilos: CSS Modules o un `ui.css` con clases prefijadas `ui-` — no Tailwind (no está en el proyecto).

## Marca configurable (SaaS)

- Guardar la marca del cliente en `app_settings` (ya existe el modelo `AppSetting` y el router `app_settings`) con la clave `tenant_brand`: `{ name, logoUrl, primary }`.
- Al cargar la app: leer `tenant_brand` → `applyTenantBrand()` de `brand.ts`. Sin configuración → `DEFAULT_BRAND`.
- Pantalla en Configuración (sólo admin): subir logo, elegir color (selector + 4 sugeridos), vista previa del botón primario y aviso de contraste (`contrast()` de `brand.ts`; si `< 4.5` se usa `safePrimary()` y se avisa).
- El logo se muestra siempre en una pastilla blanca (40px sidebar, 44px riel, 32px móvil).

## Plan por fases (un PR por fase)

**Fase 0 — Tokens y marca.** Agregar `src/ui/tokens.css` (importado antes de `styles.css` en `main.tsx`) y `src/ui/brand.ts`; aplicar la marca por defecto. Sin cambios visuales todavía.
*Listo cuando:* `npm run build` pasa y `applyTenantBrand` cambia `--brand` en runtime.

**Fase 1 — Componentes base.** Crear los componentes de la tabla anterior con una página interna `/ui-preview` (sólo dev) que replique `mockups/Componentes.dc.html`.
*Listo cuando:* la página de preview coincide con el mockup a 390, 834 y 1440 px.

**Fase 2 — Shell responsive.** `AppShell` + `ModuleSwitcher` + `CountrySelector` reemplazan el topbar/launcher actual en ambos módulos.
*Listo cuando:* navegación funciona igual que hoy en laptop y con barra inferior en celular y riel en tablet.

**Fase 3 — Radar en vivo.** Migrar `HomePage`, `OpportunitiesPage`, `OpportunityTrackingPage`, `AlertsPage`, `SystemPage`, `UsersPage` a los componentes; tablas con `DataTable` y vista tarjeta en celular.

**Fase 4 — Histórico Perú.** Migrar `pages/historico/*` a los mismos componentes; eliminar los estilos `hist-*` que queden sin uso. Urgencia con `Chip` P1–P4.

**Fase 5 — Limpieza y QA.** Borrar CSS muerto de `styles.css`; revisar contraste (AA), foco con teclado, objetivos táctiles de 44px, sin scroll horizontal de página a 390px (las tablas en laptop pueden hacer scroll dentro de su caja).

## Qué NO hacer

- No cambiar endpoints, `api.ts`, lógica de scoring, scrapers ni backend (salvo leer/guardar `tenant_brand`).
- No introducir librerías de UI (MUI, Chakra, shadcn) ni Tailwind.
- No inventar componentes fuera de la lista sin justificarlo en el PR.
- No usar el color de marca del cliente para estados (verde/ámbar/rojo/P1–P4).
