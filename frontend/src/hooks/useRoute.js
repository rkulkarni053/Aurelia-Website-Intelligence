import { useCallback, useEffect, useRef, useState } from "react";

export const VIEWS = ["projects", "sites", "crawls", "settings"];
export const MODES = [
  "overview",
  "diagnose",
  "audit",
  "opportunities",
  "design",
  "socials",
  "brain",
  "proposal",
  "deliver",
  "verify",
];

const BASE = "/app/";

function parse() {
  const segment = window.location.pathname.slice(BASE.length).split("/")[0] || "";
  const params = new URLSearchParams(window.location.search);
  const base = {
    site: params.get("site") || "",
    crawl: params.get("crawl") || "",
    category: params.get("category") || "",
  };
  if (VIEWS.includes(segment)) return { ...base, view: segment, mode: "overview" };
  if (MODES.includes(segment)) return { ...base, view: "dashboard", mode: segment };
  return { ...base, view: "dashboard", mode: "overview" };
}

function toUrl(route) {
  const segment =
    route.view === "dashboard" ? (route.mode === "overview" ? "" : route.mode) : route.view;
  const params = new URLSearchParams();
  if (route.site) params.set("site", route.site);
  if (route.crawl) params.set("crawl", route.crawl);
  if (
    route.category &&
    route.view === "dashboard" &&
    (route.mode === "audit" || route.mode === "diagnose")
  ) {
    params.set("category", route.category);
  }
  const query = params.toString();
  return `${BASE}${segment}${query ? `?${query}` : ""}`;
}

/**
 * URL-backed navigation. `onPop` fires only for browser back/forward so
 * callers can resync data without reacting to their own navigations.
 */
export default function useRoute(onPop) {
  const [route, setRoute] = useState(parse);
  const routeRef = useRef(route);
  const onPopRef = useRef(onPop);
  onPopRef.current = onPop;

  useEffect(() => {
    const handler = () => {
      const next = parse();
      routeRef.current = next;
      setRoute(next);
      onPopRef.current?.(next);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  const navigate = useCallback((patch, { replace = false } = {}) => {
    const next = { ...routeRef.current, ...patch };
    if (patch.view && patch.view !== "dashboard") next.mode = "overview";
    if (!(next.view === "dashboard" && (next.mode === "audit" || next.mode === "diagnose"))) {
      next.category = "";
    }
    const url = toUrl(next);
    const current = window.location.pathname + window.location.search;
    routeRef.current = next;
    setRoute(next);
    if (url === current) return;
    if (replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
  }, []);

  return [route, navigate];
}
