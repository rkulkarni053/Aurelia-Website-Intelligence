export function crawlBadgeClass(status) {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "running" || status === "queued") return "running";
  return "";
}

export function isActiveCrawl(status) {
  return status === "running" || status === "queued";
}

export function crawlDuration(crawl) {
  if (!crawl?.started_at || !crawl?.completed_at) return "—";
  const s = Math.max(0, (new Date(crawl.completed_at) - new Date(crawl.started_at)) / 1000);
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function shortDate(value, { withTime = false } = {}) {
  if (!value) return "—";
  const d = new Date(value);
  const date = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (!withTime) return date;
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${date} ${time}`;
}
