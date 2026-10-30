import { useEffect, useState } from "react";
import Icon from "./Icon";

function ago(date, now) {
  if (!date) return "never";
  const s = Math.max(0, Math.round((now - new Date(date)) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s} seconds ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export default function StatusBar({ refreshedAt, lastCrawlAt, brainStatus, onRefresh }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(id);
  }, []);

  const brainLabel =
    brainStatus == null
      ? "Brain: checking…"
      : brainStatus.ok
        ? `Brain: ${brainStatus.configured_model}${brainStatus.model_ready ? "" : " (not pulled)"}`
        : "Brain: offline";

  return (
    <footer className="status-bar">
      <button type="button" className="status-refresh" onClick={onRefresh}>
        <Icon name="refresh" size={13} />
        Refreshed {ago(refreshedAt, now)}
      </button>
      <div className="status-right">
        <span className={brainStatus?.ok ? "ok" : brainStatus ? "bad" : ""}>{brainLabel}</span>
        <span>Last crawl {ago(lastCrawlAt, now)}</span>
        <span>
          <Icon name="server" size={12} /> Local
        </span>
      </div>
    </footer>
  );
}
