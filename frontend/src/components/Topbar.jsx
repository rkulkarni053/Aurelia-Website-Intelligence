import { formatDate, WORKFLOW_LABELS } from "../api";
import Icon from "./Icon";

function CompactSelect({ id, label, value, onChange, disabled, children }) {
  return (
    <label className="crumb-select" htmlFor={id}>
      <span className="visually-hidden">{label}</span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} title={label}>
        {children}
      </select>
    </label>
  );
}

export default function Topbar({
  hasWebsite,
  website,
  crawlStatus,
  companies,
  projects,
  websites,
  crawls,
  companyId,
  projectId,
  websiteId,
  crawlId,
  workflow,
  busy,
  completed,
  mode,
  onCompanyChange,
  onProjectChange,
  onWebsiteChange,
  onCrawlChange,
  onRefresh,
  onAskBrain,
  onProposal,
  onPdf,
  onCrawl,
  onAdvanceWorkflow,
  onGoMode,
}) {
  const title = hasWebsite
    ? website?.domain || "Website"
    : projectId
      ? "No website selected"
      : "Get started";

  const statusLabel = !hasWebsite
    ? "Idle"
    : crawlStatus
      ? crawlStatus.replaceAll("_", " ")
      : "No crawls yet";

  const modeActions =
    mode === "diagnose"
      ? [
          {
            key: "brain",
            icon: "brain",
            label: "Recommend",
            busyLabel: "Thinking…",
            onClick: onAskBrain,
            needsCompleted: true,
          },
        ]
      : mode === "proposal"
        ? [
            {
              key: "proposal",
              icon: "file",
              label: "Generate",
              busyLabel: "Writing…",
              onClick: onProposal,
              needsCompleted: true,
            },
            {
              key: "pdf",
              icon: "download",
              label: "PDF",
              busyLabel: "Exporting…",
              onClick: onPdf,
              needsCompleted: true,
            },
          ]
        : mode === "design"
          ? []
          : [
              {
                key: "refresh",
                icon: "refresh",
                label: "Refresh",
                busyLabel: "Refresh",
                onClick: onRefresh,
                needsCompleted: false,
              },
            ];

  return (
    <header className="page-header compact">
      <div className="crumb-trail" aria-label="Workspace context">
        <CompactSelect id="companySelect" label="Company" value={companyId} onChange={onCompanyChange}>
          {!companies.length ? <option value="">No companies</option> : null}
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </CompactSelect>
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <CompactSelect id="projectSelect" label="Project" value={projectId} onChange={onProjectChange}>
          {!projects.length ? <option value="">No projects</option> : null}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </CompactSelect>
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <CompactSelect id="websiteSelect" label="Website" value={websiteId} onChange={onWebsiteChange}>
          {!websites.length ? <option value="">No websites</option> : null}
          {websites.map((w) => (
            <option key={w.id} value={w.id}>
              {w.role === "competitor" ? "[comp] " : ""}
              {w.domain}
            </option>
          ))}
        </CompactSelect>
        {websites.length ? (
          <>
            <span className="crumb-sep" aria-hidden="true">
              /
            </span>
            <CompactSelect
              id="crawlSelect"
              label="Crawl"
              value={crawlId}
              onChange={onCrawlChange}
              disabled={!websites.length}
            >
              {!crawls.length ? <option value="">No crawls</option> : null}
              {crawls.map((c) => (
                <option key={c.id} value={c.id}>
                  {formatDate(c.completed_at || c.created_at)} · {c.status}
                </option>
              ))}
            </CompactSelect>
          </>
        ) : null}
      </div>

      <div className="header-row">
        <div className="site-title">
          <div className="site-text">
            <div className="title-line">
              <h2>{title}</h2>
              <div className={`status-line ${crawlStatus || "idle"}`}>
                <span className="status-dot" />
                {statusLabel}
              </div>
              {projectId && workflow.status ? (
                <span className={`chip-status inline ${workflow.status}`}>
                  <span className="status-dot" />
                  {WORKFLOW_LABELS[workflow.status] || workflow.status}
                </span>
              ) : null}
            </div>
            {hasWebsite && website?.url ? (
              <a className="website-url" href={website.url} target="_blank" rel="noopener noreferrer">
                {website.url}
              </a>
            ) : (
              <div className="website-url">
                {projectId ? "Add a website URL to this project" : "Add a company, project, and website to begin"}
              </div>
            )}
          </div>
        </div>

        <div className="header-actions">
          {projectId && workflow.status && (workflow.next || []).length ? (
            <div className="workflow-inline">
              {(workflow.next || []).map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip-btn"
                  onClick={() => {
                    onAdvanceWorkflow(s);
                    if (s === "awaiting_approval" && onGoMode) onGoMode("opportunities");
                    if (s === "verification" && onGoMode) onGoMode("verify");
                    if (s === "delivery" && onGoMode) onGoMode("deliver");
                  }}
                >
                  <Icon name="arrow" size={12} />
                  {WORKFLOW_LABELS[s] || s}
                </button>
              ))}
            </div>
          ) : null}

          <div className="action-card compact">
            {modeActions.map((a) => (
              <button
                key={a.key}
                type="button"
                className="action-btn"
                disabled={(a.needsCompleted && !completed) || busy[a.key]}
                onClick={a.onClick}
                title={a.needsCompleted && !completed ? "Available after a completed crawl" : a.label}
              >
                <Icon name={a.icon} size={15} />
                <span>{busy[a.key] ? a.busyLabel : a.label}</span>
              </button>
            ))}
            <button
              type="button"
              className="action-btn primary"
              disabled={!hasWebsite || busy.crawl}
              onClick={onCrawl}
            >
              <Icon name="play" size={14} />
              <span>{busy.crawl ? "Crawling…" : "Run crawl"}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
