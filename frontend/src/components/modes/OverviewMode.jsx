import { formatDate } from "../../api";
import { crawlDuration } from "../../lib/crawl";
import Icon from "../Icon";

function axisLabels(history) {
  const dates = history.map((h) => new Date(h.date));
  const sameDay = dates.every((d) => d.toDateString() === dates[0].toDateString());
  return dates.map((d) =>
    sameDay
      ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  );
}

function scoreTone(value) {
  const n = Number(value);
  if (value == null || Number.isNaN(n)) return "none";
  if (n >= 8) return "good";
  if (n >= 5) return "fair";
  return "poor";
}

function MetricTile({ label, value, icon, tone = "", onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag className={`tile metric-tile ${tone}`} type={onClick ? "button" : undefined} onClick={onClick}>
      <span className="tile-icon">
        <Icon name={icon} size={16} />
      </span>
      <span className="tile-label">{label}</span>
      <strong className="tile-value">{value ?? "—"}</strong>
    </Tag>
  );
}

function ScoreTile({ label, value, note, icon, onDetails }) {
  const n = Number(value);
  const pct = value == null || Number.isNaN(n) ? 0 : Math.max(0, Math.min(10, n)) / 10;
  const r = 18;
  const c = 2 * Math.PI * r;
  return (
    <button type="button" className={`tile score-tile ${scoreTone(value)}`} onClick={onDetails} title={`${label} details`}>
      <span className="score-ring-wrap" aria-hidden="true">
        <svg className="ring" viewBox="0 0 44 44">
          <circle className="ring-track" cx="22" cy="22" r={r} />
          <circle
            className="ring-fill"
            cx="22"
            cy="22"
            r={r}
            strokeDasharray={c}
            strokeDashoffset={c * (1 - pct)}
          />
        </svg>
        <Icon name={icon} size={15} />
      </span>
      <span className="tile-label">{label}</span>
      <strong className="tile-value">{value ?? "—"}</strong>
      <span className="tile-note">{note}</span>
    </button>
  );
}

const SCORE_CATEGORIES = [
  { id: "seo", label: "SEO", icon: "search" },
  { id: "performance", label: "Performance", icon: "bolt" },
  { id: "accessibility", label: "Accessibility", icon: "person" },
  { id: "security", label: "Security", icon: "shield" },
];

const STATUS_ICON = { completed: "check", failed: "warning", running: "clock", queued: "clock" };

function HistoryChart({ history }) {
  if (history.length < 1) {
    return <div className="chart-empty">Run more crawls to see the findings trend.</div>;
  }
  const W = 420;
  const H = 120;
  const pad = { l: 28, r: 8, t: 8, b: 24 };
  const labels = axisLabels(history);
  const labelEvery = Math.ceil(history.length / 6);
  const max = Math.max(4, ...history.map((h) => h.total));
  const step = Math.ceil(max / 3);
  const top = step * 3;
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;
  const slot = innerW / Math.max(history.length, 8);
  const barW = Math.min(22, slot * 0.55);
  const y = (v) => pad.t + innerH - (v / top) * innerH;
  const points = history.map((h, i) => [pad.l + slot * i + slot / 2, y(h.high)]);

  return (
    <svg className="history-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Findings per crawl">
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={y(step * i)} y2={y(step * i)} className="grid-line" />
          <text x={pad.l - 6} y={y(step * i) + 3} className="axis-label" textAnchor="end">
            {step * i}
          </text>
        </g>
      ))}
      {history.map((h, i) => {
        const prev = history[i - 1];
        const tone = !prev ? "flat" : h.total > prev.total ? "up" : h.total < prev.total ? "down" : "flat";
        const x = pad.l + slot * i + (slot - barW) / 2;
        return (
          <rect
            key={h.id}
            className={`bar-${tone}`}
            x={x}
            y={y(h.total)}
            width={barW}
            height={Math.max(1, pad.t + innerH - y(h.total))}
            rx="2"
          >
            <title>
              {formatDate(h.date)}: {h.total} findings, {h.high} high
            </title>
          </rect>
        );
      })}
      {labels.map((label, i) =>
        i % labelEvery === 0 || i === labels.length - 1 ? (
          <text key={`l${i}`} x={pad.l + slot * i + slot / 2} y={H - 6} className="axis-label" textAnchor="middle">
            {label}
          </text>
        ) : null
      )}
      <polyline className="trend-line" points={points.map((p) => p.join(",")).join(" ")} />
      {points.map(([px, py], i) => (
        <circle key={i} cx={px} cy={py} r="2.5" className="trend-dot" />
      ))}
    </svg>
  );
}

export default function OverviewMode({
  summary,
  scores,
  crawlMeta,
  comparison,
  crawls,
  crawlId,
  history,
  conversionPath,
  competitors,
  upgrades,
  verification,
  busy = {},
  onOpenAudit,
  onSelectCrawl,
  onVerify,
}) {
  const byCat = scores?.by_category || {};
  const method = scores?.method || "heuristic_v1";
  const overallNote = String(method).includes("lighthouse") ? "Lighthouse/10" : "Heuristic/10";

  const metrics = [
    { label: "Findings", value: summary?.total, icon: "search", tone: "" },
    { label: "High priority", value: summary?.by_severity?.high, icon: "warning", tone: "rose" },
    { label: "Medium", value: summary?.by_severity?.medium, icon: "box", tone: "" },
    { label: "Pages crawled", value: crawlMeta.pagesCrawled, icon: "file", tone: "" },
  ];

  const last = history[history.length - 1];
  const prev = history[history.length - 2];
  const delta = last && prev ? last.total - prev.total : null;
  const recent = crawls.slice(0, 5);

  return (
    <div className="mode-body overview-mode">
      <section className="ov-section">
        <div className="ov-section-head">
          <h3>Snapshot</h3>
          <button type="button" className="button small" onClick={() => onOpenAudit("")}>
            Open audit
          </button>
        </div>
        <div className="tile-row cols-4">
          {metrics.map((m) => (
            <MetricTile key={m.label} {...m} onClick={() => onOpenAudit("")} />
          ))}
        </div>
        <div className="tile-row cols-5">
          <ScoreTile
            label="Overall"
            value={scores?.overall}
            note={overallNote}
            icon="trend"
            onDetails={() => onOpenAudit("")}
          />
          {SCORE_CATEGORIES.map((cat) => (
            <ScoreTile
              key={cat.id}
              label={cat.label}
              value={byCat[cat.id]}
              note={
                summary?.by_category?.[cat.id] != null
                  ? `${summary.by_category[cat.id]} findings`
                  : "Category"
              }
              icon={cat.icon}
              onDetails={() => onOpenAudit(cat.id)}
            />
          ))}
        </div>
      </section>

      <div className="ov-grid cols-2">
        <section className="panel ov-card">
          <div className="ov-section-head">
            <h3>Crawl pulse</h3>
            <span className="panel-meta">
              Latest <span className="live-dot" />
            </span>
          </div>
          <div className="table-wrap">
            <table className="pulse-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Timestamp</th>
                  <th>Pages</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {!recent.length ? (
                  <tr>
                    <td colSpan={4} className="table-empty">
                      No crawls yet.
                    </td>
                  </tr>
                ) : (
                  recent.map((c) => (
                    <tr
                      key={c.id}
                      className={String(c.id) === String(crawlId) ? "current" : ""}
                      onClick={() => onSelectCrawl(c.id)}
                    >
                      <td>
                        <span className={`row-status ${c.status}`}>
                          <Icon name={STATUS_ICON[c.status] || "clock"} size={13} />
                          {c.status}
                        </span>
                      </td>
                      <td>{formatDate(c.started_at || c.created_at)}</td>
                      <td>
                        {c.pages_crawled || 0} / {c.pages_discovered || 0}
                      </td>
                      <td>{crawlDuration(c)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="pulse-foot">
            <span>
              Started <strong>{crawlMeta.started}</strong>
            </span>
            <span>
              Completed <strong>{crawlMeta.completed}</strong>
            </span>
          </div>
        </section>

        <section className="panel ov-card">
          <div className="ov-section-head">
            <h3>Vs previous crawl</h3>
            <span className="panel-meta">Trend</span>
          </div>
          <div className="compare-grid">
            <div className="compare-card new">
              <span className="compare-label">New</span>
              <strong>{comparison.new}</strong>
              {delta != null ? (
                <span className="compare-pill">
                  {delta ? <Icon name={delta > 0 ? "arrowUp" : "arrowDown"} size={11} /> : null}
                  {delta ? `${Math.abs(delta)} total` : "No change"}
                </span>
              ) : null}
            </div>
            <div className="compare-card resolved">
              <span className="compare-label">Resolved</span>
              <strong>{comparison.resolved}</strong>
              {last ? (
                <span className="compare-pill">
                  <Icon name="check" size={11} />
                  {last.total} open
                </span>
              ) : null}
            </div>
            <div className="compare-card unchanged">
              <span className="compare-label">Unchanged</span>
              <strong>{comparison.unchanged}</strong>
            </div>
          </div>
          <HistoryChart history={history} />
          <div className="ov-card-actions">
            <button
              type="button"
              className="button primary block"
              onClick={onVerify}
              disabled={busy.verification}
            >
              <Icon name="check" size={14} />
              {busy.verification
                ? "Building…"
                : verification?.pdf_file
                  ? "Rebuild verification PDF"
                  : "Build verification PDF"}
            </button>
          </div>
        </section>
      </div>

      <div className="ov-grid cols-3">
        <section className="panel ov-card">
          <div className="ov-section-head">
            <h3>Conversion path</h3>
            <span className="panel-meta">{conversionPath?.strength || "—"}</span>
          </div>
          {conversionPath?.funnel?.length ? (
            <ul className="funnel-list">
              {conversionPath.funnel.map((step) => (
                <li key={step.step} className={step.ok ? "ok" : "gap"}>
                  <strong>{step.step}</strong>
                  <span>{step.ok ? "ok" : "gap"}</span>
                  {step.url ? <span className="panel-meta">{step.url}</span> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="card-subtitle">Run a crawl to map Home → Offer → Convert.</p>
          )}
          {conversionPath?.gaps?.length ? (
            <ul className="gap-list">
              {conversionPath.gaps.slice(0, 3).map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="panel ov-card">
          <div className="ov-section-head">
            <h3>Competitors</h3>
            <span className="panel-meta">{(competitors?.competitors || []).length} peers</span>
          </div>
          {competitors?.scoreboard?.length ? (
            <div className="table-wrap">
              <table className="pulse-table">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Overall</th>
                    <th>Conv.</th>
                    <th>Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {competitors.scoreboard.map((row) => (
                    <tr key={row.domain}>
                      <td>
                        {row.domain}
                        {row.role === "competitor" ? <span className="role-pill">comp</span> : null}
                      </td>
                      <td>{row.overall ?? "—"}</td>
                      <td>{row.conversion_strength || "—"}</td>
                      <td>{row.findings_total ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="card-subtitle">Add competitor URLs on this project, crawl them, then compare here.</p>
          )}
          {competitors?.insights?.length ? (
            <ul className="gap-list">
              {competitors.insights.slice(0, 2).map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="panel ov-card">
          <div className="ov-section-head">
            <h3>Stack upgrades</h3>
            <span className="panel-meta">{(upgrades?.opportunities || []).length}</span>
          </div>
          {(upgrades?.opportunities || []).length ? (
            <ul className="gap-list">
              {upgrades.opportunities.slice(0, 4).map((o) => (
                <li key={o.title || o.technology}>
                  <strong>{o.title}</strong>
                  <span className="panel-meta"> {o.summary}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="card-subtitle">No CMS/stack upgrade signals for this crawl yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
