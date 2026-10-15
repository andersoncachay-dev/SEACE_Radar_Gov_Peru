import React, { useEffect, useRef, useState } from "react";
import { TenantBrand } from "./brand";
import { Button, Sheet } from "./components";
import { Icon, IconName } from "./icons";
import { useBreakpoint } from "./useBreakpoint";

export type ModuleValue = "radar" | "historico_peru";
export const MODULE_LABEL: Record<ModuleValue, string> = { radar: "Radar en vivo", historico_peru: "Histórico" };
const MODULE_LONG: Record<ModuleValue, string> = { radar: "Radar en vivo", historico_peru: "Histórico" };

export type NavItem = {
  id: string;
  label: string;
  shortLabel?: string;
  icon: IconName;
  badge?: number;
};

export type NavSection = { label: string; items: NavItem[] };

/* ---------- ModuleSwitcher ---------- */

export function ModuleSwitcher({ value, modules, onChange, variant }: {
  value: ModuleValue;
  modules: ModuleValue[];
  onChange: (module: ModuleValue) => void;
  variant: "dark" | "light" | "sheet";
}) {
  const [open, setOpen] = useState(false);
  if (modules.length < 2) return null;
  if (variant === "sheet") {
    return (
      <>
        <button type="button" className="ui-module-trigger" aria-haspopup="dialog" onClick={() => setOpen(true)}>
          {MODULE_LONG[value]}<Icon name="chevronDown" size={18} />
        </button>
        {open ? (
          <Sheet title="Módulo" onClose={() => setOpen(false)}>
            {modules.map((module) => (
              <button key={module} type="button" className="ui-sheet-item" aria-current={module === value ? "page" : undefined} onClick={() => { onChange(module); setOpen(false); }}>
                <Icon name={module === "radar" ? "target" : "chart"} />{MODULE_LONG[module]}
              </button>
            ))}
          </Sheet>
        ) : null}
      </>
    );
  }
  return (
    <nav className={`ui-seg ui-seg-${variant}`} aria-label="Módulo">
      {modules.map((module) => (
        <button key={module} type="button" aria-pressed={module === value} onClick={() => onChange(module)}>{MODULE_LABEL[module]}</button>
      ))}
    </nav>
  );
}

/* ---------- CountrySelector ---------- */

export type CountryOption<V extends string = string> = { value: V; label: string; code: string; flagUrl: string };

export function CountrySelector<V extends string>({ value, options, onChange, compact = false, onDark = false }: {
  value: V;
  options: CountryOption<V>[];
  onChange?: (value: V) => void;
  compact?: boolean;
  onDark?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const bp = useBreakpoint();
  const current = options.find((option) => option.value === value) ?? options[0];
  useEffect(() => {
    if (!open || bp === "phone") return;
    const close = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const esc = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [open, bp]);
  if (!current) return null;
  const selectable = Boolean(onChange) && options.length > 1;
  const size = bp === "laptop" ? "md" : "touch";
  const button = (
    <button
      type="button"
      className={`ui-btn ui-btn-secondary ${size === "touch" ? "ui-btn-touch" : ""} ${onDark ? "ui-country-on-dark" : ""}`}
      style={compact ? { padding: "0 10px" } : undefined}
      aria-haspopup={selectable ? "listbox" : undefined}
      aria-expanded={selectable ? open : undefined}
      aria-label={`País: ${current.label}`}
      onClick={() => selectable && setOpen((v) => !v)}
    >
      <img className="ui-flag" src={current.flagUrl} alt="" />
      {compact ? current.code : current.label}
      {selectable && !compact ? <Icon name="chevronDown" size={16} /> : null}
    </button>
  );
  if (!selectable) return button;
  const list = options.map((option) => (
    <button key={option.value} type="button" role="option" aria-selected={option.value === value} className="ui-sheet-item" aria-current={option.value === value ? "page" : undefined} onClick={() => { onChange?.(option.value); setOpen(false); }}>
      <img className="ui-flag" src={option.flagUrl} alt="" />{option.label}
    </button>
  ));
  return (
    <div className="ui-country" ref={ref}>
      {button}
      {open && bp === "phone" ? <Sheet title="País" onClose={() => setOpen(false)}>{list}</Sheet> : null}
      {open && bp !== "phone" ? <div className="ui-menu" role="listbox" aria-label="País">{list}</div> : null}
    </div>
  );
}

/* ---------- AppShell ---------- */

export type ShellUser = { name: string; roleLabel: string; initials: string };

type ShellProps = {
  brand: TenantBrand;
  appName?: string;
  module: ModuleValue;
  /** Breadcrumb / header name of the active module, e.g. "Histórico Chile". */
  moduleLabel?: string;
  modules: ModuleValue[];
  onModuleChange: (module: ModuleValue) => void;
  sections: NavSection[];
  /** Up to 4 phone tabs; a 5th "Más" tab opens a sheet with everything else. */
  phoneTabs: string[];
  currentId: string;
  onNavigate: (id: string) => void;
  pageLabel: string;
  topbarEnd?: React.ReactNode;
  phoneEnd?: React.ReactNode;
  user: ShellUser;
  onLogout: () => void;
  footer?: React.ReactNode;
  children: React.ReactNode;
};

function Logo({ brand, variant }: { brand: TenantBrand; variant: "sidebar" | "rail" | "phone" }) {
  return brand.logoUrl ? <img className={`ui-logo ui-logo-${variant}`} src={brand.logoUrl} alt={`Logo de ${brand.name}`} /> : null;
}

export function AppShell(props: ShellProps) {
  const { brand, appName = "GovRadar", module, moduleLabel, modules, onModuleChange, sections, phoneTabs, currentId, onNavigate, pageLabel, topbarEnd, phoneEnd, user, onLogout, footer, children } = props;
  const bp = useBreakpoint();
  const [moreOpen, setMoreOpen] = useState(false);
  const items = sections.flatMap((section) => section.items);
  const go = (id: string) => { setMoreOpen(false); onNavigate(id); };

  if (bp === "laptop") {
    return (
      <div className="ui-shell ui-shell-laptop ui-root">
        <aside className="ui-sidebar" aria-label="Navegación principal">
          <div className="ui-sidebar-brand">
            <Logo brand={brand} variant="sidebar" />
            <div className="ui-sidebar-brand-text"><strong>{appName}</strong><span>{brand.name}</span></div>
          </div>
          <ModuleSwitcher value={module} modules={modules} onChange={onModuleChange} variant="dark" />
          {sections.map((section) => (
            <React.Fragment key={section.label}>
              <div className="ui-nav-section">{section.label}</div>
              {section.items.map((item) => (
                <button key={item.id} type="button" className="ui-nav-item" aria-current={item.id === currentId ? "page" : undefined} onClick={() => go(item.id)}>
                  <Icon name={item.icon} /><span className="ui-nav-item-label">{item.label}</span>
                  {item.badge ? <span className="ui-nav-badge">{item.badge > 99 ? "99+" : item.badge}</span> : null}
                </button>
              ))}
            </React.Fragment>
          ))}
          <div className="ui-sidebar-user">
            <span className="ui-avatar" aria-hidden="true">{user.initials}</span>
            <div className="ui-sidebar-user-text"><strong>{user.name}</strong><span>{user.roleLabel}</span></div>
            <Button variant="ghost" size="sm" icon="logout" iconOnly aria-label="Cerrar sesión" onClick={onLogout} />
          </div>
        </aside>
        <div className="ui-shell-main">
          <header className="ui-topbar">
            <span className="ui-crumbs">{moduleLabel ?? MODULE_LONG[module]} <span aria-hidden="true">›</span> <strong>{pageLabel}</strong></span>
            <div className="ui-topbar-end">{topbarEnd}</div>
          </header>
          <main className="ui-shell-content" id="main-content">{children}{footer}</main>
        </div>
      </div>
    );
  }

  if (bp === "tablet") {
    const settings = items.filter((item) => item.icon === "settings" || item.icon === "users");
    const main = items.filter((item) => !settings.includes(item));
    return (
      <div className="ui-shell ui-shell-tablet ui-root">
        <nav className="ui-rail" aria-label="Navegación principal">
          <Logo brand={brand} variant="rail" />
          {main.map((item) => (
            <button key={item.id} type="button" className="ui-rail-btn" aria-current={item.id === currentId ? "page" : undefined} onClick={() => go(item.id)} title={item.label}>
              {item.badge ? <span className="ui-rail-dot" aria-label={`${item.badge} pendientes`} /> : null}
              <Icon name={item.icon} />{item.shortLabel ?? item.label}
            </button>
          ))}
          <span className="ui-rail-spacer" />
          {settings.map((item) => (
            <button key={item.id} type="button" className="ui-rail-btn" aria-current={item.id === currentId ? "page" : undefined} onClick={() => go(item.id)} title={item.label}>
              <Icon name={item.icon} />{item.shortLabel ?? item.label}
            </button>
          ))}
          <button type="button" className="ui-rail-btn" onClick={onLogout} title="Cerrar sesión"><Icon name="logout" />Salir</button>
          <span className="ui-avatar" title={user.name} aria-hidden="true">{user.initials}</span>
        </nav>
        <div className="ui-shell-main">
          <div className="ui-tablet-bar">
            <ModuleSwitcher value={module} modules={modules} onChange={onModuleChange} variant="light" />
            <div className="ui-topbar-end">{topbarEnd}</div>
          </div>
          <main className="ui-shell-content" id="main-content">{children}{footer}</main>
        </div>
      </div>
    );
  }

  const tabs = phoneTabs.map((id) => items.find((item) => item.id === id)).filter(Boolean) as NavItem[];
  const rest = items.filter((item) => !phoneTabs.includes(item.id));
  const moreActive = rest.some((item) => item.id === currentId);
  return (
    <div className="ui-shell ui-shell-phone ui-root" style={{ flexDirection: "column" }}>
      <header className="ui-phone-header">
        <div className="ui-phone-header-row">
          <Logo brand={brand} variant="phone" />
          {modules.length > 1
            ? <ModuleSwitcher value={module} modules={modules} onChange={onModuleChange} variant="sheet" />
            : <span className="ui-module-trigger" style={{ cursor: "default" }}>{moduleLabel ?? MODULE_LONG[module]}</span>}
          <div className="ui-topbar-end">{phoneEnd ?? topbarEnd}</div>
        </div>
      </header>
      <main className="ui-shell-content" id="main-content">{children}{footer}</main>
      <nav className="ui-bottom-nav" aria-label="Navegación principal">
        {tabs.map((item) => (
          <button key={item.id} type="button" className="ui-tab" aria-current={item.id === currentId ? "page" : undefined} onClick={() => go(item.id)}>
            <span className="ui-tab-pill"><Icon name={item.icon} /></span>
            {item.badge ? <span className="ui-tab-badge">{item.badge > 99 ? "99+" : item.badge}</span> : null}
            {item.shortLabel ?? item.label}
          </button>
        ))}
        <button type="button" className="ui-tab" aria-current={moreActive ? "page" : undefined} aria-haspopup="dialog" onClick={() => setMoreOpen(true)}>
          <span className="ui-tab-pill"><Icon name="more" /></span>Más
        </button>
      </nav>
      {moreOpen ? (
        <Sheet title="Más" onClose={() => setMoreOpen(false)}>
          {rest.map((item) => (
            <button key={item.id} type="button" className="ui-sheet-item" aria-current={item.id === currentId ? "page" : undefined} onClick={() => go(item.id)}>
              <Icon name={item.icon} />{item.label}
            </button>
          ))}
          <div className="ui-sheet-user"><span className="ui-avatar" aria-hidden="true">{user.initials}</span><span><strong>{user.name}</strong><small>{user.roleLabel}</small></span></div>
          <Button variant="secondary" size="touch" icon="logout" block onClick={onLogout}>Cerrar sesión</Button>
        </Sheet>
      ) : null}
    </div>
  );
}
