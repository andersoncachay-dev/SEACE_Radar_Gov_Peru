import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { Icon, IconName } from "./icons";

/* ---------- Button ---------- */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "touch";

type ButtonProps = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  iconOnly?: boolean;
  block?: boolean;
  children?: React.ReactNode;
};

/** One primary per screen; export is always secondary + download icon. */
export function Button({ variant = "secondary", size = "md", icon, iconOnly = false, block = false, className = "", type = "button", children, ...rest }: ButtonProps) {
  if (iconOnly && !rest["aria-label"]) {
    console.warn("Button iconOnly requires aria-label");
  }
  const classes = [
    "ui-btn",
    `ui-btn-${variant}`,
    size !== "md" ? `ui-btn-${size}` : "",
    iconOnly ? "ui-btn-icon-only" : "",
    block ? "ui-btn-block" : "",
    className,
  ].filter(Boolean).join(" ");
  return (
    <button type={type} className={classes} {...rest}>
      {icon ? <Icon name={icon} size={size === "sm" ? 16 : 20} /> : null}
      {iconOnly ? null : children}
    </button>
  );
}

/* ---------- Chip (single state component) ---------- */

export type ChipTone = "signal-green" | "signal-amber" | "signal-pending" | "signal-red" | "p1" | "p2" | "p3" | "p4" | "info";

const GLYPH: Partial<Record<ChipTone, string>> = { p1: "▲▲", p2: "▲", p3: "●", p4: "○" };

/** Color + text + mark (dot for signals, glyph for urgency): never color alone. */
export function Chip({ tone, label, title }: { tone: ChipTone; label: React.ReactNode; title?: string }) {
  const glyph = GLYPH[tone];
  return (
    <span className={`ui-chip ui-chip-${tone}`} title={title}>
      {glyph ? <b className="ui-chip-glyph" aria-hidden="true">{glyph}</b> : <i className="ui-chip-dot" aria-hidden="true" />}
      {label}
    </span>
  );
}

/* ---------- FilterChip ---------- */

/** Green Excel logo for "Descargar / Exportar a Excel" buttons. */
export function ExcelIcon({ size = 18 }: { size?: number }) {
  return <img className="ui-excel-icon" src="/assets/logoexcel.png" alt="" aria-hidden="true" width={size} height={size} decoding="async" />;
}

/** Star toggle for a process/contract. Stops propagation so it works inside clickable rows. */
export function FavoriteButton({ active, onToggle, label, size = "md" }: {
  active: boolean;
  onToggle: () => void;
  label: string;
  size?: "sm" | "md";
}) {
  const action = active ? "Quitar de favoritos" : "Marcar como favorito";
  // "Pop" only when the user stars it, not for stars already on at load.
  const [popping, setPopping] = React.useState(false);
  return (
    <button
      type="button"
      className={`ui-fav ${size === "sm" ? "ui-fav-sm" : ""}${popping ? " is-popping" : ""}`}
      aria-pressed={active}
      aria-label={`${action}: ${label}`}
      title={action}
      onAnimationEnd={() => setPopping(false)}
      onClick={(event) => { event.stopPropagation(); if (!active) setPopping(true); onToggle(); }}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <Icon name="star" size={size === "sm" ? 16 : 18} />
    </button>
  );
}

export function FilterChip({
  active = false,
  count,
  dot,
  glyph,
  children,
  onClick,
}: {
  active?: boolean;
  count?: number;
  dot?: "green" | "amber" | "pending" | "red";
  glyph?: "p1" | "p2" | "p3" | "p4";
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <button type="button" className="ui-fchip" aria-pressed={active} onClick={onClick}>
      {dot ? <i className={`ui-chip-dot ui-fchip-dot-${dot}`} aria-hidden="true" /> : null}
      {glyph ? <b className={`ui-chip-glyph ui-fchip-glyph-${glyph}`} aria-hidden="true">{GLYPH[glyph]}</b> : null}
      {children}
      {count !== undefined ? <span className="ui-num"> · {count.toLocaleString("es-PE")}</span> : null}
    </button>
  );
}

/* ---------- Card / KpiCard ---------- */

export function Card({
  padding = "md",
  title,
  subtitle,
  actions,
  className = "",
  children,
  as: Tag = "section",
}: {
  padding?: "none" | "sm" | "md" | "lg";
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag className={`ui-card ${padding !== "none" ? `ui-card-pad-${padding}` : ""} ${className}`.trim()}>
      {title || actions ? (
        <div className="ui-card-head">
          <div>{title ? <h2>{title}</h2> : null}{subtitle ? <p>{subtitle}</p> : null}</div>
          {actions ? <div className="ui-page-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </Tag>
  );
}

export function KpiCard({ label, value, hint, onClick, active }: {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
}) {
  const body = (
    <>
      <span className="ui-kpi-label">{label}</span>
      <span className="ui-kpi-value">{value}</span>
      {hint ? <span className="ui-kpi-hint">{hint}</span> : null}
    </>
  );
  if (onClick) {
    return <button type="button" className="ui-card ui-kpi" aria-pressed={active} onClick={onClick}>{body}</button>;
  }
  return <div className="ui-card ui-kpi">{body}</div>;
}

export function KpiGrid({ children, columns = 5 }: { children: React.ReactNode; columns?: 4 | 5 }) {
  return <div className={`ui-kpi-grid ${columns === 4 ? "ui-kpi-grid-4" : ""}`}>{children}</div>;
}

/* ---------- Fields ---------- */

type FieldShell = { label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; className?: string };

function Field({ id, label, hint, error, className = "", children }: FieldShell & { id: string; children: React.ReactNode }) {
  return (
    <div className={`ui-field ${className}`.trim()}>
      {label ? <label className="ui-field-label" htmlFor={id}>{label}</label> : null}
      {children}
      {error ? <span className="ui-field-error" id={`${id}-error`}>{error}</span> : hint ? <span className="ui-field-hint" id={`${id}-hint`}>{hint}</span> : null}
    </div>
  );
}

export function TextField({ label, hint, error, className, id, inputSize, ...rest }: FieldShell & React.InputHTMLAttributes<HTMLInputElement> & { inputSize?: "sm" | "md" }) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} className={className}>
      <input
        id={fieldId}
        className={`ui-input ${inputSize === "sm" ? "ui-input-sm" : ""}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
        {...rest}
      />
    </Field>
  );
}

export function SelectField({ label, hint, error, className, id, inputSize, children, ...rest }: FieldShell & React.SelectHTMLAttributes<HTMLSelectElement> & { inputSize?: "sm" | "md" }) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} className={className}>
      <span className="ui-input-wrap">
        <select id={fieldId} className={`ui-input ${inputSize === "sm" ? "ui-input-sm" : ""}`} aria-invalid={error ? true : undefined} {...rest}>{children}</select>
        <span className="ui-select-caret"><Icon name="chevronDown" size={16} /></span>
      </span>
    </Field>
  );
}

export function SearchField({ label, hint, className, id, placeholder = "Buscar", ...rest }: FieldShell & React.InputHTMLAttributes<HTMLInputElement>) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <Field id={fieldId} label={label} hint={hint} className={`ui-search ${className ?? ""}`}>
      <span className="ui-input-wrap">
        <span className="ui-search-icon"><Icon name="search" /></span>
        <input id={fieldId} type="search" className="ui-input" placeholder={placeholder} aria-label={label ? undefined : placeholder} {...rest} />
      </span>
    </Field>
  );
}

/* ---------- PageHeader ---------- */

export function PageHeader({ title, meta, actions }: { title: React.ReactNode; meta?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="ui-page-header">
      <div className="ui-page-header-text">
        <h1 className="ui-page-title">{title}</h1>
        {meta ? <span className="ui-page-meta">{meta}</span> : null}
      </div>
      {actions ? <div className="ui-page-actions">{actions}</div> : null}
    </div>
  );
}

/* ---------- EmptyState / ConfirmModal ---------- */

export function EmptyState({ title, text, action }: { title?: React.ReactNode; text: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="ui-empty" role="status">
      {title ? <strong>{title}</strong> : null}
      <p>{text}</p>
      {action}
    </div>
  );
}

/** Same API as shared.tsx ConfirmModal (title/message/confirmLabel/onConfirm/onCancel). */
export function ConfirmModal({
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: React.ReactNode;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="ui-overlay ui-overlay-center">
      <div className="ui-scrim" onClick={onCancel} />
      <div className="ui-modal" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <h2 id={titleId}>{title}</h2>
        <p>{message}</p>
        <div className="ui-modal-actions">
          <button ref={cancelRef} type="button" className="ui-btn ui-btn-ghost" onClick={onCancel}>{cancelLabel}</button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={busy}>{busy ? "Procesando…" : confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Sheet (bottom sheet on phone) ---------- */

export function Sheet({ title, onClose, children }: { title: React.ReactNode; onClose: () => void; children: React.ReactNode }) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  // Portal to <body>: opened from the sticky phone header, the sheet would
  // otherwise live in the header's stacking context (z-index 30), under the
  // bottom tab bar (50), hiding its last options and inheriting white text.
  return createPortal(
    <div className="ui-overlay">
      <div className="ui-scrim" onClick={onClose} />
      <div className="ui-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <span className="ui-sheet-grip" aria-hidden="true" />
        <h2 className="ui-sheet-title" id={titleId}>{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  );
}
