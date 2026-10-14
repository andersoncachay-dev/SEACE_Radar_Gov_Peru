import { useEffect, useState } from "react";

export type Breakpoint = "phone" | "tablet" | "laptop";

const PHONE = "(max-width: 639px)";
const TABLET = "(min-width: 640px) and (max-width: 1023px)";

function current(): Breakpoint {
  if (typeof window === "undefined" || !window.matchMedia) return "laptop";
  if (window.matchMedia(PHONE).matches) return "phone";
  if (window.matchMedia(TABLET).matches) return "tablet";
  return "laptop";
}

/** phone < 640 · tablet 640–1023 · laptop >= 1024 (docs/design/HANDOFF.md). */
export function useBreakpoint(): Breakpoint {
  const [value, setValue] = useState<Breakpoint>(current);
  useEffect(() => {
    const queries = [window.matchMedia(PHONE), window.matchMedia(TABLET)];
    const update = () => setValue(current());
    queries.forEach((query) => query.addEventListener("change", update));
    update();
    return () => queries.forEach((query) => query.removeEventListener("change", update));
  }, []);
  return value;
}
