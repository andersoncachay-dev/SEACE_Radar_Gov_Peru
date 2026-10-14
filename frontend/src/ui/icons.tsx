

/** Stroke icons from docs/design/mockups (stroke 1.8, 20px, currentColor). */
const PATHS = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><path d="M12 12l6-6" /></>,
  tracking: <><path d="M9 11l3 3 8-8" /><path d="M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11" /></>,
  bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21h4" /></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  users: <><circle cx="9" cy="8" r="4" /><path d="M2 21c0-4 3-6 7-6s7 2 7 6" /><path d="M16 4a4 4 0 0 1 0 8" /><path d="M22 21c0-3-1.5-5-4-6" /></>,
  settings: <><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></>,
  chart: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  file: <><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>,
  filter: <path d="M4 5h16l-6 8v6l-4-2v-4z" />,
  download: <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />,
  refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>,
  chevronDown: <path d="M6 9l6 6 6-6" />,
  chevronRight: <path d="M9 6l6 6-6 6" />,
  more: <><circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  logout: <><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4" /><path d="M10 17l5-5-5-5M15 12H4" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  money: <><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5C14.8 7.5 13.6 7 12 7c-2 0-3.5 1-3.5 2.5S10 12 12 12s3.5 1 3.5 2.5S14 17 12 17c-1.6 0-2.8-.5-3.5-1.5M12 5v14" /></>,
  columns: <><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M9 4v16M15 4v16" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></>,
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className = "", label }: { name: IconName; size?: 16 | 18 | 20; className?: string; label?: string }) {
  return (
    <svg
      className={`ui-icon ${size === 16 ? "ui-icon-sm" : ""} ${className}`.trim()}
      style={size === 18 ? { width: 18, height: 18 } : undefined}
      viewBox="0 0 24 24"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      {PATHS[name]}
    </svg>
  );
}
