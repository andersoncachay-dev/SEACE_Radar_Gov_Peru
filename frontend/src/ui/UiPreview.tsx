import { useState } from "react";
import { applyTenantBrand, contrast, DEFAULT_BRAND, safePrimary, SUGGESTED_PRIMARIES } from "./brand";
import { Button, Card, Chip, ChipTone, FilterChip, KpiCard, KpiGrid, PageHeader, SearchField, SelectField, TextField } from "./components";
import { DataTable } from "./DataTable";
import { AppShell, CountrySelector, ModuleSwitcher, ModuleValue } from "./AppShell";

/** Dev-only page (/ui-preview) mirroring docs/design/mockups/Componentes.dc.html. */

type Row = { id: number; tone: ChipTone; signal: string; entity: string; desc: string; source: string; amount: string; due: string; left: string };
const ROWS: Row[] = [
  { id: 1, tone: "signal-green", signal: "Verde", entity: "Municipalidad Provincial de Arequipa", desc: "Servicio de internet satelital para 12 sedes rurales", source: "SEACE", amount: "S/ 240 500", due: "17/10/2026", left: "en 4 días" },
  { id: 2, tone: "signal-amber", signal: "Ámbar", entity: "Gobierno Regional de Cusco", desc: "Conectividad para instituciones educativas, lote 2", source: "OCDS", amount: "S/ 1 210 000", due: "15/10/2026", left: "en 2 días" },
  { id: 3, tone: "signal-red", signal: "Rojo", entity: "Ministerio de Transportes y Comunicaciones", desc: "Enlaces de respaldo para estaciones remotas", source: "SEACE", amount: "S/ 85 300", due: "14/10/2026", left: "mañana" },
  { id: 4, tone: "signal-pending", signal: "Pendiente", entity: "Hospital Regional de Loreto", desc: "Servicio de telecomunicaciones VSAT", source: "SEACE", amount: "S/ 412 000", due: "24/10/2026", left: "en 11 días" },
];
const COUNTRIES = [
  { value: "Peru", label: "Perú", code: "PE", flagUrl: "/assets/flag-peru.svg" },
  { value: "Chile", label: "Chile", code: "CL", flagUrl: "/assets/flag-chile.svg" },
  { value: "Argentina", label: "Argentina", code: "AR", flagUrl: "/assets/flag-argentina.svg" },
];

export default function UiPreview() {
  const [primary, setPrimary] = useState(DEFAULT_BRAND.primary);
  const [module, setModule] = useState<ModuleValue>("radar");
  const [country, setCountry] = useState("Peru");
  const [filter, setFilter] = useState("todas");
  const [page, setPage] = useState("oportunidades");
  const brand = { ...DEFAULT_BRAND, primary };
  const ratio = contrast(safePrimary(primary).color, "#ffffff");

  function pick(color: string) {
    setPrimary(color);
    applyTenantBrand({ ...DEFAULT_BRAND, primary: color });
  }

  const sections = module === "radar"
    ? [
      { label: "Perú", items: [
        { id: "inicio", label: "Inicio", icon: "home" as const },
        { id: "oportunidades", label: "Oportunidades", shortLabel: "Oport.", icon: "target" as const },
        { id: "seguimiento", label: "Seguimiento", shortLabel: "Seguim.", icon: "tracking" as const },
        { id: "alertas", label: "Alertas", icon: "bell" as const, badge: 3 },
        { id: "eliminados", label: "Procesos eliminados", shortLabel: "Elimin.", icon: "database" as const },
      ] },
      { label: "Administración", items: [
        { id: "usuarios", label: "Usuarios", icon: "users" as const },
        { id: "config", label: "Configuración", shortLabel: "Config.", icon: "settings" as const },
      ] },
    ]
    : [
      { label: "Histórico Perú", items: [
        { id: "resumen", label: "Resumen", icon: "chart" as const },
        { id: "historial", label: "Historial de contrataciones", shortLabel: "Historial", icon: "database" as const },
        { id: "vencer", label: "Contratos por vencer", shortLabel: "Por vencer", icon: "clock" as const },
        { id: "pac", label: "PAC Perú", shortLabel: "PAC", icon: "file" as const },
        { id: "alertas-h", label: "Alertas", icon: "bell" as const, badge: 5 },
      ] },
      { label: "Administración", items: [{ id: "config", label: "Configuración", shortLabel: "Config.", icon: "settings" as const }] },
    ];

  return (
    <AppShell
      brand={brand}
      module={module}
      modules={["radar", "historico_peru"]}
      onModuleChange={(next) => { setModule(next); setPage(next === "radar" ? "oportunidades" : "vencer"); }}
      sections={sections}
      phoneTabs={module === "radar" ? ["inicio", "oportunidades", "seguimiento", "alertas"] : ["resumen", "historial", "vencer", "alertas-h"]}
      currentId={page}
      onNavigate={setPage}
      pageLabel="Componentes"
      topbarEnd={<><SearchField placeholder="Buscar entidad, proceso o palabra clave" className="ui-preview-topsearch" /><CountrySelector value={country} options={COUNTRIES} onChange={setCountry} /></>}
      phoneEnd={<CountrySelector value={country} options={COUNTRIES} onChange={setCountry} compact onDark />}
      user={{ name: "Anderson Cachay", roleLabel: "Administrador", initials: "AC" }}
      onLogout={() => undefined}
    >
      <PageHeader
        title="Un solo set de componentes para Radar e Histórico"
        meta="Página interna de desarrollo · /ui-preview · replica docs/design/mockups/Componentes.dc.html"
        actions={<><Button icon="download">Exportar</Button><Button variant="primary" icon="refresh">Actualizar ahora</Button></>}
      />
      <KpiGrid>
        <KpiCard label="Activas" value="128" hint="+9 nuevas hoy" />
        <KpiCard label="Vencen en 7 días" value="14" hint="3 vencen mañana" />
        <KpiCard label="Señal verde" value="32" hint="Listas para cotizar" onClick={() => undefined} active />
        <KpiCard label="Requieren revisión" value="6" hint="Señal roja" />
        <KpiCard label="En seguimiento" value="18" hint="4 responsables" />
      </KpiGrid>
      <div className="ui-preview-grid">
        <Card title="Botones" subtitle="Radio 8px, peso 600, 14px. Alturas 32 · 40 · 44.">
          <div className="ui-preview-row">
            <Button variant="primary">Actualizar ahora</Button>
            <Button icon="download">Exportar</Button>
            <Button variant="ghost">Cancelar</Button>
            <Button variant="danger">Eliminar</Button>
          </div>
          <div className="ui-preview-row">
            <Button variant="primary" size="sm">Seguir</Button>
            <Button size="sm" icon="columns">Columnas</Button>
            <Button variant="primary" size="touch">Táctil 44px</Button>
            <Button icon="download" iconOnly aria-label="Exportar" />
          </div>
        </Card>
        <Card title="Campos" subtitle="Borde --control-border; foco con --brand-ring.">
          <div className="ui-preview-stack">
            <TextField label="Correo para alertas" defaultValue="ventas@empresa.com" />
            <SelectField label="País" defaultValue="Perú"><option>Perú</option><option>Chile</option><option>Argentina</option></SelectField>
            <SearchField placeholder="Buscar entidad" />
            <TextField label="RUC" defaultValue="2010" error="El RUC debe tener 11 dígitos." />
          </div>
        </Card>
        <Card title="Estado: señal · urgencia · ejecución" subtitle="Misma píldora 24px; color + texto + marca.">
          <div className="ui-preview-stack">
            <div className="ui-preview-row"><Chip tone="signal-green" label="Verde" /><Chip tone="signal-amber" label="Ámbar" /><Chip tone="signal-pending" label="Pendiente" /><Chip tone="signal-red" label="Rojo" /></div>
            <div className="ui-preview-row"><Chip tone="p1" label="P1 · Crítica" /><Chip tone="p2" label="P2 · Alta" /><Chip tone="p3" label="P3 · Media" /><Chip tone="p4" label="P4 · Baja" /></div>
            <div className="ui-preview-row"><Chip tone="signal-green" label="Completado" /><Chip tone="p3" label="En curso" /><Chip tone="signal-red" label="Fallido" /><Chip tone="signal-pending" label="En cola" /></div>
          </div>
        </Card>
        <Card title="Escala tipográfica (Inter)">
          <div className="ui-preview-type">
            <span>Cifra KPI</span><strong className="ui-kpi-value">128</strong><span>28 / 800</span>
            <span>Título de página</span><strong className="ui-page-title">Oportunidades</strong><span>20 / 700</span>
            <span>Sección</span><strong style={{ fontSize: "var(--text-section)" }}>Por vencer</strong><span>16 / 700</span>
            <span>Cuerpo</span><span style={{ color: "var(--ink)" }}>Proceso publicado</span><span>14 / 400</span>
            <span>Tabla · etiqueta</span><span className="ui-field-label">Fecha de presentación</span><span>13 / 400·600</span>
            <span>Nota</span><span>Actualizado hace 4 min</span><span>12 / 400</span>
          </div>
        </Card>
        <Card title="Marca de la empresa" subtitle="El cliente elige sólo el color primario; el resto se deriva.">
          <div className="ui-preview-stack">
            <div className="ui-preview-row">
              {SUGGESTED_PRIMARIES.map((color) => (
                <button key={color} type="button" className="ui-preview-swatch" style={{ background: color }} aria-pressed={primary === color} aria-label={`Usar ${color}`} onClick={() => pick(color)} />
              ))}
              <input type="color" className="ui-color-input" aria-label="Color primario" value={primary} onChange={(event) => pick(event.target.value)} />
            </div>
            <div className="ui-preview-row">
              <Button variant="primary">Vista previa</Button>
              <Chip tone={ratio >= 4.5 ? "signal-green" : "signal-red"} label={`Blanco sobre primario ${ratio.toFixed(1)}:1`} />
            </div>
            <div className="ui-preview-row">
              <ModuleSwitcher value={module} modules={["radar", "historico_peru"]} onChange={setModule} variant="light" />
            </div>
          </div>
        </Card>
      </div>
      <Card padding="none">
        <div className="ui-toolbar">
          <FilterChip active={filter === "todas"} count={128} onClick={() => setFilter("todas")}>Todas</FilterChip>
          <FilterChip active={filter === "verde"} count={32} dot="green" onClick={() => setFilter("verde")}>Verde</FilterChip>
          <FilterChip active={filter === "ambar"} count={21} dot="amber" onClick={() => setFilter("ambar")}>Ámbar</FilterChip>
          <FilterChip active={filter === "p1"} count={12} glyph="p1" onClick={() => setFilter("p1")}>P1</FilterChip>
          <div className="ui-toolbar-end"><Button variant="ghost" size="sm" icon="filter">Más filtros</Button><Button variant="ghost" size="sm">Columnas</Button></div>
        </div>
        <DataTable
          rows={ROWS}
          rowKey={(row) => row.id}
          onRowClick={() => undefined}
          columns={[
            { key: "signal", header: "Señal", width: 132, render: (row) => <Chip tone={row.tone} label={row.signal} /> },
            { key: "entity", header: "Entidad y descripción", render: (row) => <><span className="ui-cell-strong">{row.entity}</span><span className="ui-cell-sub">{row.desc}</span></> },
            { key: "source", header: "Fuente", width: 110, priority: 2, render: (row) => <span style={{ color: "var(--muted)" }}>{row.source}</span> },
            { key: "amount", header: "Monto", width: 120, align: "right", render: (row) => <span className="ui-num ui-cell-strong">{row.amount}</span> },
            { key: "due", header: "Presentación", width: 130, render: (row) => <><span className="ui-num ui-cell-strong">{row.due}</span><span className="ui-cell-sub">{row.left}</span></> },
          ]}
          renderTabletRow={(row) => ({
            main: <><span className="ui-mcard-top"><Chip tone={row.tone} label={row.signal} /><span className="ui-cell-sub" style={{ margin: 0 }}>{row.source}</span></span><span className="ui-mcard-title">{row.entity}</span><span className="ui-mcard-desc">{row.desc}</span></>,
            side: <><span className="ui-num ui-cell-strong">{row.amount}</span><span className="ui-num ui-cell-strong" style={{ fontSize: "var(--text-table)" }}>{row.due}</span><span className="ui-cell-sub">{row.left}</span></>,
          })}
          renderMobileCard={(row) => <>
            <span className="ui-mcard-top"><Chip tone={row.tone} label={row.signal} /><span className="ui-cell-sub" style={{ margin: 0 }}>{row.source}</span><span className="ui-mcard-right">{row.left}</span></span>
            <span className="ui-mcard-title">{row.entity}</span>
            <span className="ui-mcard-desc">{row.desc}</span>
            <span className="ui-mcard-foot"><strong>{row.amount}</strong><span className="ui-cell-sub" style={{ margin: 0 }}>Vence {row.due}</span></span>
          </>}
        />
      </Card>
    </AppShell>
  );
}
