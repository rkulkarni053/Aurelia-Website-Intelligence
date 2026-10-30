import Icon from "../Icon";

const LISTS = [
  ["Quick wins", "quick_wins", "bolt"],
  ["Strategic improvements", "strategic_improvements", "trend"],
  ["Proposal angles", "proposal_angles", "signature"],
];

function Placeholder({ meta, loading, onAsk }) {
  return (
    <section className="panel brain-empty">
      <div className="brain-orb">
        <Icon name="brain" size={30} />
      </div>
      <h3>{loading ? "Thinking…" : "Get recommendations"}</h3>
      <p>
        {loading
          ? "Reading the evidence pack, then building suggestions and a clickable demo site…"
          : "Brain turns crawl evidence into concrete suggestions plus a live demo website (and optional mockup images in Design)."}
      </p>
      {loading ? (
        <div className="skeleton-stack">
          <span className="skeleton line" />
          <span className="skeleton line" />
          <span className="skeleton line short" />
        </div>
      ) : (
        <button type="button" className="action-btn primary solo" onClick={onAsk}>
          <Icon name="brain" size={15} />
          <span>Recommend</span>
        </button>
      )}
      <span className="panel-meta">{meta}</span>
    </section>
  );
}

export default function BrainMode({
  recommendations,
  meta,
  loading,
  onAsk,
  demo,
  onOpenDesign,
  checklist,
  onToggleChecklist,
  opportunities = [],
}) {
  if (loading || !recommendations) return <Placeholder meta={meta} loading={loading} onAsk={onAsk} />;

  const rec = recommendations.recommendations || {};
  const scores = recommendations.scores || {};
  const byCat = scores.by_category || {};
  const story = rec.site_story_summary || {};
  const actions = rec.priority_actions || [];
  const demoUrl = demo?.url_path;
  const items = checklist?.items || [];
  const company = recommendations.company_profile || rec.company_profile || null;
  const topOpps = (opportunities || [])
    .filter((o) => (o.status || "").toLowerCase() !== "rejected")
    .slice(0, 5);
  const targetOverall =
    scores.overall != null ? Math.min(10, Math.round((Number(scores.overall) + 0.8) * 10) / 10) : null;

  return (
    <div className="mode-body">
      {company?.brand || company?.one_liner ? (
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="building" size={20} className="panel-icon blue" />
              Company understanding
            </h3>
            <span className="panel-meta">From crawl · instant</span>
          </div>
          <div className="rec-chips">
            {company.brand ? <span className="chip">{company.brand}</span> : null}
            {company.industry ? <span className="chip">{company.industry}</span> : null}
            {company.location ? <span className="chip">{company.location}</span> : null}
          </div>
          {company.one_liner ? <p className="finding-description">{company.one_liner}</p> : null}
          {company.usecase_summary ? (
            <p className="finding-meta">
              <strong>Use case:</strong> {company.usecase_summary}
            </p>
          ) : null}
          {(company.services || []).length ? (
            <p className="finding-meta">
              <strong>Services:</strong> {company.services.slice(0, 6).join(", ")}
            </p>
          ) : null}
          {(company.use_cases || []).length ? (
            <p className="finding-meta">
              <strong>Typical jobs:</strong> {company.use_cases.slice(0, 5).join(", ")}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="panel brain-hero">
        <div className="brain-hero-main">
          <span className="eyebrow">
            <Icon name="brain" size={14} /> Executive summary
          </span>
          <p className="brain-summary">{rec.executive_summary || "No summary returned."}</p>
          <div className="score-row">
            {scores.overall != null ? <span className="score-pill strong">Overall {scores.overall}/10</span> : null}
            {targetOverall != null ? (
              <span className="score-pill">Target ≥ {targetOverall}/10</span>
            ) : null}
            {Object.entries(byCat).map(([k, v]) => (
              <span className="score-pill" key={k}>
                {k === "seo" ? "SEO" : k} {v}/10
              </span>
            ))}
          </div>
        </div>
        <div className="brain-hero-side">
          <span className="panel-meta">{meta}</span>
          <button type="button" className="button small" onClick={onAsk}>
            <Icon name="refresh" size={13} /> Ask again
          </button>
          {demoUrl ? (
            <a className="button small" href={demoUrl} target="_blank" rel="noopener noreferrer">
              <Icon name="external" size={13} /> Open demo
            </a>
          ) : (
            <button type="button" className="button small" onClick={onOpenDesign}>
              <Icon name="brush" size={13} /> Build demo
            </button>
          )}
        </div>
      </section>

      <section className="panel brain-outputs">
        <div className="panel-head">
          <h3>
            <Icon name="brush" size={20} className="panel-icon blue" />
            From this brain run
          </h3>
          <span className="panel-meta">Suggestions + visual demo</span>
        </div>
        <div className="brain-outputs-grid">
          <div>
            <h4 className="sub-head">Suggestions</h4>
            {(demo?.content_suggestions || rec.content_suggestions || []).length ? (
              <ul className="content-suggestion-list">
                {(demo?.content_suggestions || rec.content_suggestions).slice(0, 6).map((c) => {
                  const area = typeof c === "string" ? "Copy" : c.area;
                  const suggested = typeof c === "string" ? c : c.suggested;
                  const why = typeof c === "string" ? "" : c.why;
                  return (
                    <li key={`${area}-${suggested}`}>
                      <strong>{area}</strong>
                      <span>{suggested}</span>
                      {why ? <em>{why}</em> : null}
                    </li>
                  );
                })}
              </ul>
            ) : (demo?.suggestions || []).length ? (
              <ul className="rec-list check">
                {demo.suggestions.slice(0, 6).map((s) => (
                  <li key={s}>
                    <Icon name="check" size={12} />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            ) : (rec.quick_wins || []).length ? (
              <ul className="rec-list check">
                {rec.quick_wins.slice(0, 6).map((s) => (
                  <li key={s}>
                    <Icon name="check" size={12} />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="empty-inline">Suggestions appear after Brain finishes.</div>
            )}
          </div>
          <div className="brain-demo-card">
            <h4 className="sub-head">Demo website</h4>
            {demoUrl ? (
              <>
                <iframe title="Brain demo preview" className="demo-frame compact" src={demoUrl} />
                <div className="panel-actions" style={{ marginTop: 10 }}>
                  <a className="button small" href={demoUrl} target="_blank" rel="noopener noreferrer">
                    <Icon name="external" size={13} /> Open full demo
                  </a>
                  <button type="button" className="button small" onClick={onOpenDesign}>
                    <Icon name="image" size={13} /> Mockup images
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-inline">
                <p>Demo builds automatically with Brain. Open Design to refresh or generate mockup images.</p>
                <button type="button" className="button small" onClick={onOpenDesign}>
                  <Icon name="brush" size={13} /> Go to Design
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

      {items.length ? (
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="clipboard" size={20} className="panel-icon blue" />
              Implementation checklist
            </h3>
            <span className="panel-meta">
              {checklist?.done_count || 0}/{checklist?.total || items.length} done
            </span>
          </div>
          <ul className="checklist">
            {items.map((item) => (
              <li key={item.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={Boolean(item.done)}
                    onChange={(e) => onToggleChecklist?.(item.id, e.target.checked)}
                  />
                  <span>
                    <strong>{item.title}</strong>
                    {item.how ? <em>{item.how}</em> : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {topOpps.length ? (
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="trend" size={20} className="panel-icon blue" />
              Commercial opportunities grounding this plan
            </h3>
            <span className="panel-meta">{topOpps.length} themes</span>
          </div>
          <ul className="rec-list check">
            {topOpps.map((o) => (
              <li key={o.id || o.client_title || o.title}>
                <Icon name="check" size={12} />
                <span>{o.client_title || o.title}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="brain-grid">
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="warning" size={20} className="panel-icon blue" />
              Priority actions
            </h3>
            <span className="panel-meta">{actions.length} actions · score-lifting plan</span>
          </div>
          {!actions.length ? (
            <div className="empty">No priority actions.</div>
          ) : (
            <ol className="action-list">
              {actions.map((a, idx) => (
                <li className="action-item" key={a.title || idx}>
                  <span className="action-num">{idx + 1}</span>
                  <div>
                    <div className="action-title">{a.title}</div>
                    <div className="rec-chips">
                      {a.impact ? <span className={`chip impact ${a.impact}`}>{a.impact} impact</span> : null}
                      {a.effort ? <span className="chip">{a.effort} effort</span> : null}
                      {a.category ? <span className="chip">{a.category}</span> : null}
                    </div>
                    {a.why ? <p className="finding-description">{a.why}</p> : null}
                    {a.how ? (
                      <p className="action-how">
                        <Icon name="arrow" size={12} />
                        {a.how}
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <div className="stack">
          {story.story || story.business_type ? (
            <section className="panel story-card">
              <div className="panel-head">
                <h3>
                  <Icon name="building" size={18} className="panel-icon blue" />
                  Site story
                </h3>
              </div>
              <div className="rec-chips">
                {story.business_type ? <span className="chip">{story.business_type}</span> : null}
                {story.tone ? <span className="chip">{story.tone}</span> : null}
                {story.audience ? <span className="chip">{story.audience}</span> : null}
              </div>
              {story.story ? <p className="finding-description">{story.story}</p> : null}
              {story.offer ? (
                <p className="finding-meta">
                  <strong>Offer:</strong> {story.offer}
                </p>
              ) : null}
              {(story.gaps || []).length ? (
                <>
                  <h4 className="sub-head">Gaps</h4>
                  <ul className="rec-list">
                    {story.gaps.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </section>
          ) : null}

          {LISTS.map(([title, key, icon]) => (
            <section className="panel" key={key}>
              <div className="panel-head">
                <h3>
                  <Icon name={icon} size={18} className="panel-icon blue" />
                  {title}
                </h3>
                <span className="panel-meta">{rec[key]?.length || 0}</span>
              </div>
              {rec[key]?.length ? (
                <ul className="rec-list check">
                  {rec[key].map((item) => (
                    <li key={item}>
                      <Icon name="check" size={12} />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty">None suggested.</div>
              )}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
