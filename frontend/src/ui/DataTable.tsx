import React from "react";
import { useBreakpoint } from "./useBreakpoint";

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  render: (row: T) => React.ReactNode;
  align?: "left" | "right";
  width?: number | string;
  /** 1 = always (laptop + tablet table), 2 = laptop only. Phones use renderMobileCard. */
  priority?: 1 | 2;
};

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  /** Phone (< 640): stacked card. */
  renderMobileCard: (row: T) => React.ReactNode;
  /** Tablet (640–1023): 2-line row, main block + right-aligned side (amount, date). Falls back to priority-1 columns. */
  renderTabletRow?: (row: T) => { main: React.ReactNode; side?: React.ReactNode };
  empty?: React.ReactNode;
  caption?: string;
  maxHeight?: number | string;
};

/**
 * Unified listing: full table with sticky header on laptop, 2-line rows on
 * tablet, cards on phone (docs/design/HANDOFF.md · Breakpoints y layout).
 */
export function DataTable<T>({ columns, rows, rowKey, onRowClick, renderMobileCard, renderTabletRow, empty, caption, maxHeight }: Props<T>) {
  const bp = useBreakpoint();
  if (!rows.length) return <div className="ui-table-empty">{empty ?? "Sin resultados."}</div>;

  const activate = (row: T) => (event: React.KeyboardEvent) => {
    if (onRowClick && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      onRowClick(row);
    }
  };

  if (bp === "phone") {
    return (
      <div className="ui-mcards">
        {rows.map((row) => (
          onRowClick
            ? <button key={rowKey(row)} type="button" className="ui-mcard" onClick={() => onRowClick(row)}>{renderMobileCard(row)}</button>
            : <div key={rowKey(row)} className="ui-mcard" style={{ cursor: "default" }}>{renderMobileCard(row)}</div>
        ))}
      </div>
    );
  }

  if (bp === "tablet" && renderTabletRow) {
    return (
      <div className="ui-rows">
        {rows.map((row) => {
          const { main, side } = renderTabletRow(row);
          const body = <><div className="ui-row-main">{main}</div>{side ? <div className="ui-row-side">{side}</div> : <span />}</>;
          return onRowClick
            ? <button key={rowKey(row)} type="button" className="ui-row" data-clickable="true" onClick={() => onRowClick(row)}>{body}</button>
            : <div key={rowKey(row)} className="ui-row">{body}</div>;
        })}
      </div>
    );
  }

  const visible = bp === "tablet" ? columns.filter((column) => (column.priority ?? 1) === 1) : columns;
  return (
    <div className="ui-table-wrap" style={maxHeight ? ({ "--table-max-h": typeof maxHeight === "number" ? `${maxHeight}px` : maxHeight } as React.CSSProperties) : undefined}>
      <table className="ui-table">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {visible.map((column) => (
              <th key={column.key} className={column.align === "right" ? "ui-align-right" : undefined} style={column.width ? { width: column.width } : undefined}>{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              data-clickable={onRowClick ? "true" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={onRowClick ? activate(row) : undefined}
            >
              {visible.map((column) => (
                <td key={column.key} className={column.align === "right" ? "ui-align-right" : undefined}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
