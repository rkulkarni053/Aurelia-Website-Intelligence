import { useEffect, useState } from "react";
import Icon from "./Icon";

function elapsed(since, now) {
  if (!since) return "0s";
  const s = Math.max(0, Math.floor((now - new Date(since)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export default function CrawlProgress({ progress, crawl, domain }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const stages = progress?.stages || [];
  const step = progress?.step || 0;
  const total = progress?.total_steps || stages.length || 7;
  const subTotal = progress?.sub_total;
  const subDone = progress?.sub_done;
  const subFraction = subTotal ? Math.min(1, (subDone || 0) / subTotal) : 0;
  const percent = step ? Math.round(((step - 1 + subFraction) / total) * 100) : 2;
  const startedAt = progress?.started_at || crawl?.started_at || crawl?.created_at;
  const queued = (progress?.status || crawl?.status) === "queued" || !step;

  return (
    <div className="crawl-progress-wrap">
      <section className="panel crawl-progress" aria-live="polite">
        <div className="crawl-progress-head">
          <div className="crawl-progress-icon">
            <Icon name="pulse" size={20} />
          </div>
          <div className="crawl-progress-title">
            <span className="eyebrow">Crawl in progress</span>
            <h3>{queued ? "Waiting to start…" : progress?.label || "Working…"}</h3>
            <p>
              {domain ? <strong>{domain}</strong> : null}
              {step ? ` · Step ${step} of ${total}` : ""}
              {subTotal ? ` · page ${Math.min((subDone || 0) + 1, subTotal)} of ${subTotal}` : ""}
              {progress?.pages_crawled != null
                ? ` · ${progress.pages_crawled} / ${progress.pages_discovered ?? "?"} pages crawled`
                : ""}
            </p>
          </div>
          <div className="crawl-progress-time">
            <Icon name="clock" size={14} />
            {elapsed(startedAt, now)}
          </div>
        </div>

        <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
          <div className="progress-fill" style={{ width: `${percent}%` }} />
        </div>

        {stages.length ? (
          <ol className="stage-list">
            {stages.map((label, idx) => {
              const state = idx + 1 < step ? "done" : idx + 1 === step ? "active" : "todo";
              return (
                <li key={label} className={`stage ${state}`}>
                  <span className="stage-dot">
                    {state === "done" ? <Icon name="check" size={11} /> : idx + 1}
                  </span>
                  <span className="stage-label">{label}</span>
                </li>
              );
            })}
          </ol>
        ) : null}
      </section>

      <div className="skeleton-grid" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="skeleton-card">
            <span className="skeleton line short" />
            <span className="skeleton line tall" />
            <span className="skeleton line" />
          </div>
        ))}
      </div>
      <div className="skeleton-row" aria-hidden="true">
        <div className="skeleton-card big">
          <span className="skeleton line short" />
          <span className="skeleton block" />
        </div>
        <div className="skeleton-card big">
          <span className="skeleton line short" />
          <span className="skeleton block" />
        </div>
      </div>
    </div>
  );
}
