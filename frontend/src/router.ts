import { useEffect, useState } from "react";

/** Minimal hash router (no dependency): "#/markets/abc?tab=news" ->
 * { path: ["markets", "abc"], query: { tab: "news" } }. */
export interface Route {
  path: string[];
  query: Record<string, string>;
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [pathPart, queryPart = ""] = raw.split("?");
  const path = pathPart.split("/").filter(Boolean).map(decodeURIComponent);
  const query: Record<string, string> = {};
  for (const [key, value] of new URLSearchParams(queryPart)) query[key] = value;
  return { path, query };
}

export function href(...segments: (string | undefined)[]): string {
  return "#/" + segments.filter((s): s is string => Boolean(s)).map(encodeURIComponent).join("/");
}

export function navigate(...segments: (string | undefined)[]): void {
  window.location.hash = href(...segments);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
