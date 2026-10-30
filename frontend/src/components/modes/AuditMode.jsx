import { useMemo, useState } from "react";
import Icon from "../Icon";

const LEVELS = [
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
  ["info", "Info"],
];
const SEVERITY_RANK = { high: 0, medium: 1, low: 2, info: 3 };
const CATEGORY_ICON = {
  seo: "search",
  performance: "bolt",
  accessibility: "person",
  security: "shield",
  technical: "server",
};

const categoryLabel = (cat) => (cat === "seo" ? "SEO" : cat);

function shortUrl(url) {
  try {
    const u = new URL(url);
    return `${u.pathname}${u.search}` || "/";
  } catch {
    return url;
  }
}

export default function AuditMode({
  findings,
  summary,
  annotated,
  domain,
  crawlId,
  reports = null,
  busy = {},
  onRebuildProof,
  category = "",
  onCategoryChange,
}) {
  const [severity, setSeverity] = useState("");
  const [query, setQuery] = useState("");
  const [cacheBust] = useState(() => Date.now());
  const reportUrls = reports?.urls || {};
  const siteoneScores = reports?.siteone?.scores || reports?.manifest?.siteone?.scores;
  const downloadItems = (reports?.manifest?.downloads || []).filter((d) => d.available);

  const bySeverity = summary?.by_severity || {};
  const total = Object.values(bySeverity).reduce((a, b) => a + Number(b || 0), 0);
  const categories = useMemo(() => {
    const counts = {};
    for (const f of findings) counts[f.category || "technical"] = (counts[f.category || "technical"] || 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [findings]);

  const inCategory = useMemo(
    () => findings.filter((f) => !category || (f.category || "technical") === category),
    [findings, category]
  );
  const severityCounts = useMemo(() => {
    const counts = {};
    for (const f of inCategory) counts[f.severity] = (counts[f.severity] || 0) + 1;
    return counts;
  }, [inCategory]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return inCategory
      .filter((f) => !severity || f.severity === severity)
      .filter(
        (f) =>
          !q ||
          [f.title, f.description, f.url, f.code].some((v) => String(v || "").toLowerCase().includes(q))
      )
      .sort((a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9));
  }, [inCategory, severity, query]);

  const filtered = Boolean(category || severity || query);

  return (
    <div className="mode-body">
      <section className="panel">
        <div className="panel-head">
          <h3>
            <Icon name="download" size={20} className="panel-icon blue" />
            Downloadable proofs
          </h3>
          <span className="panel-meta">
            {siteoneScores?.overall != null
              ? `SiteOne ${siteoneScores.overall}/10`
              : reports
                ? "Reports ready"
                : "After crawl"}
          </span>
        </div>
        {!domain || !crawlId ? (
          <div className="empty">Complete a crawl to download SiteOne reports and screenshot proofs.</div>
        ) : (
          <div className="deliver-list proof-actions">
            <a
              className="button primary block"
              href={reportUrls.proof_zip || `/data/websites/${domain}/crawls/${crawlId}/reports/proof-pack.zip`}
              download
            >
              <Icon name="download" size={14} />
              Download proof pack (ZIP)
            </a>
            <a
              className="button block"
              href={reportUrls.proof_index || `/data/websites/${domain}/crawls/${crawlId}/reports/index.html`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="file" size={14} />
              Open proof index
            </a>
            <a
              className="button block"
              href={reportUrls.siteone_html || `/data/websites/${domain}/crawls/${crawlId}/reports/siteone/report.html`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="search" size={14} />
              Open SiteOne SEO report
            </a>
            <a
              className="button block"
              href={reportUrls.siteone_json || `/data/websites/${domain}/crawls/${crawlId}/reports/siteone/report.json`}
              download
            >
              <Icon name="file" size={14} />
              Download SiteOne JSON
            </a>
            {onRebuildProof ? (
              <button
                type="button"
                className="button block"
                onClick={onRebuildProof}
                disabled={busy.proof}
              >
                <Icon name="refresh" size={14} />
                {busy.proof ? "Rebuilding…" : "Rebuild proof pack"}
              </button>
            ) : null}
            {downloadItems.length ? (
              <ul className="proof-file-list">
                {downloadItems.slice(0, 10).map((item) => (
                  <li key={item.path}>
                    <a href={item.url} download target="_blank" rel="noopener noreferrer">
                      {item.label}
                    </a>
                    <span>{item.kind}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {reports?.siteone && !reports.siteone.ok ? (
              <p className="fallback-note">
                <Icon name="warning" size={13} />
                {reports.siteone.skipped
                  ? "SiteOne binary missing — install with scripts/install_siteone.sh"
                  : reports.siteone.error || "SiteOne audit did not complete"}
              </p>
            ) : null}
          </div>
        )}
      </section>

      <div className="audit-layout">
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="clipboard" size={20} className="panel-icon blue" />
              Findings
            </h3>
            <span className="panel-meta">
              {filtered ? `${visible.length} of ${findings.length}` : `${findings.length} total`}
            </span>
          </div>

          <div className="audit-filters">
            <label className="filter-search">
              <Icon name="search" size={15} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search title, URL, or rule…"
                aria-label="Search findings"
              />
            </label>
            <div className="filter-row" role="group" aria-label="Category">
              <button
                type="button"
                className={`filter-chip${!category ? " active" : ""}`}
                onClick={() => onCategoryChange("")}
              >
                All categories
              </button>
              {categories.map(([cat, count]) => (
                <button
                  key={cat}
                  type="button"
                  className={`filter-chip${category === cat ? " active" : ""}`}
                  onClick={() => onCategoryChange(category === cat ? "" : cat)}
                >
                  <Icon name={CATEGORY_ICON[cat] || "box"} size={13} />
                  {categoryLabel(cat)}
                  <span className="filter-count">{count}</span>
                </button>
              ))}
            </div>
            <div className="filter-row" role="group" aria-label="Severity">
              {LEVELS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`filter-chip sev ${key}${severity === key ? " active" : ""}`}
                  onClick={() => setSeverity(severity === key ? "" : key)}
                >
                  <i className="sev-dot" />
                  {label}
                  <span className="filter-count">{severityCounts[key] || 0}</span>
                </button>
              ))}
              {filtered ? (
                <button
                  type="button"
                  className="filter-clear"
                  onClick={() => {
                    setSeverity("");
                    setQuery("");
                    onCategoryChange("");
                  }}
                >
                  <Icon name="close" size={12} />
                  Clear filters
                </button>
              ) : null}
            </div>
          </div>

          {!findings.length ? (
            <div className="empty">No findings for this crawl. Nice work.</div>
          ) : !visible.length ? (
            <div className="empty">No findings match these filters.</div>
          ) : (
            <div className="finding-list">
              {visible.map((f) => (
                <article className={`finding-card ${f.severity || ""}`} key={f.id || `${f.code}-${f.url}`}>
                  <span className={`finding-icon ${f.severity || ""}`}>
                    <Icon name={CATEGORY_ICON[f.category] || "box"} size={16} />
                  </span>
                  <div className="finding-main">
                    <div className="finding-top">
                      <span className="finding-title">{f.title}</span>
                      <span className={`severity ${f.severity}`}>{f.severity}</span>
                    </div>
                    <p className="finding-description">{f.description}</p>
                    <div className="finding-meta">
                      <span className="finding-tag">{categoryLabel(f.category)}</span>
                      {f.code ? <code>{f.code}</code> : null}
                      {f.url ? (
                        <a href={f.url} target="_blank" rel="noopener noreferrer" title={f.url}>
                          {shortUrl(f.url)}
                          <Icon name="external" size={11} />
                        </a>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <div className="stack">
          <section className="panel">
            <div className="panel-head">
              <h3>Severity</h3>
              <span className="panel-meta">{total} findings</span>
            </div>
            <div className="breakdown">
              {LEVELS.map(([key, label]) => {
                const value = Number(bySeverity[key] || 0);
                return (
                  <button
                    type="button"
                    className={`breakdown-row${severity === key ? " active" : ""}`}
                    key={key}
                    onClick={() => setSeverity(severity === key ? "" : key)}
                  >
                    <span>{label}</span>
                    <div className="bar">
                      <div className={`bar-fill bar-${key}`} style={{ width: `${total ? (value / total) * 100 : 0}%` }} />
                    </div>
                    <strong>{value}</strong>
                  </button>
                );
              })}
            </div>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h3>Categories</h3>
            </div>
            <div className="category-list">
              {!categories.length ? (
                <span className="card-subtitle">No findings</span>
              ) : (
                categories.map(([cat, count]) => (
                  <button
                    type="button"
                    className={`category${category === cat ? " active" : ""}`}
                    key={cat}
                    onClick={() => onCategoryChange(category === cat ? "" : cat)}
                  >
                    <Icon name={CATEGORY_ICON[cat] || "box"} size={14} />
                    {categoryLabel(cat)}
                    <strong>{count}</strong>
                  </button>
                ))
              )}
            </div>
          </section>
        </div>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3>
            <Icon name="image" size={20} className="panel-icon blue" />
            Annotated screenshots
          </h3>
          <span className="panel-meta">{annotated.length ? `${annotated.length} annotated` : "Findings overlay"}</span>
        </div>
        {!annotated.length || !domain ? (
          <div className="empty">Annotated screenshots appear after a crawl completes.</div>
        ) : (
          <div className="annotated-grid">
            {annotated.map((img) => (
              <div className="annotated-card" key={img.annotated_path}>
                <a
                  href={`/data/websites/${domain}/crawls/${crawlId}/${img.annotated_path}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    src={`/data/websites/${domain}/crawls/${crawlId}/${img.annotated_path}?t=${cacheBust}`}
                    alt={`Annotated findings for ${img.url || domain}`}
                    loading="lazy"
                  />
                </a>
                <div className="caption">
                  <span>{img.url ? shortUrl(img.url) : ""}</span>
                  <strong>{img.finding_count ?? 0} findings</strong>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
