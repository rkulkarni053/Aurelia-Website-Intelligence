import Icon from "../Icon";

const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };

function money(amount, currency = "EUR") {
  if (amount == null || amount === "") return "—";
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  if ((currency || "EUR").toUpperCase() === "EUR") return `€${n.toLocaleString("en-IE", { maximumFractionDigits: 0 })}`;
  return `${currency} ${n.toLocaleString()}`;
}

function SellCard({ sell, busy, onAccept, onCustomize, onBuildProposal, onOpenDesign }) {
  if (!sell) {
    return (
      <section className="panel sell-card">
        <div className="panel-head">
          <h3>
            <Icon name="signature" size={20} className="panel-icon blue" />
            Sell this
          </h3>
        </div>
        <div className="empty-inline">Generate opportunities to see a package recommendation.</div>
      </section>
    );
  }

  const packages = sell.packages || {};
  const why = sell.why || sell.reasons || [];

  return (
    <section className="panel sell-card">
      <div className="panel-head">
        <h3>
          <Icon name="signature" size={20} className="panel-icon blue" />
          Recommended engagement
        </h3>
        {sell.accepted ? <span className="badge good">Accepted</span> : <span className="panel-meta">Aurelia recommends · you decide</span>}
      </div>
      <div className="sell-hero">
        <div>
          <span className="eyebrow">Recommended package</span>
          <strong className="sell-name">{sell.package_name || sell.recommended_package}</strong>
          <div className="sell-price">{money(sell.price, sell.currency)}</div>
          {sell.duration_days ? <span className="panel-meta">~{sell.duration_days} days</span> : null}
          {sell.summary ? <p className="sell-summary">{sell.summary}</p> : null}
        </div>
        <div className="sell-packages">
          {Object.entries(packages).map(([key, pkg]) => (
            <button
              key={key}
              type="button"
              className={`sell-pkg${key === sell.recommended_package ? " active" : ""}`}
              onClick={() => onAccept(key)}
              disabled={busy.sell}
            >
              <strong>{pkg.name || key}</strong>
              <span>{money(pkg.price, sell.currency)}</span>
            </button>
          ))}
        </div>
      </div>
      {why.length ? (
        <div className="sell-why">
          <h4 className="sub-head">Why this package</h4>
          <ul className="rec-list check">
            {why.map((line) => (
              <li key={line}>
                <Icon name="check" size={12} />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="panel-actions sell-actions">
        <button type="button" className="button primary" onClick={() => onAccept(sell.recommended_package)} disabled={busy.sell}>
          <Icon name="check" size={14} />
          {busy.sell ? "Saving…" : "Accept recommendation"}
        </button>
        <button type="button" className="button" onClick={onCustomize} disabled={busy.sell}>
          Customize
        </button>
        <button type="button" className="button" onClick={onBuildProposal} disabled={busy.proposal}>
          <Icon name="signature" size={14} />
          Build proposal
        </button>
        {onOpenDesign ? (
          <button type="button" className="button" onClick={onOpenDesign}>
            <Icon name="brush" size={14} />
            Build demo
          </button>
        ) : null}
      </div>
    </section>
  );
}

function OpportunityCard({ item, busyId, onAction }) {
  const evidenceCount = item.evidence_count || item.evidence?.finding_count || 1;
  const title = item.client_title || item.title;
  const priority = (item.priority || "medium").toLowerCase();

  return (
    <article className={`opp-card priority-${priority} status-${item.status}`}>
      <header className="opp-card-head">
        <div>
          <span className={`sev-pill ${priority}`}>{priority}</span>
          <h4>{title}</h4>
        </div>
        <span className="panel-meta">{item.selected_package || "—"}</span>
      </header>
      <p className="opp-problem">{item.problem}</p>
      <dl className="opp-meta">
        <div>
          <dt>Business impact</dt>
          <dd>{item.business_impact}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{evidenceCount} piece{evidenceCount === 1 ? "" : "s"}</dd>
        </div>
        <div>
          <dt>Recommended action</dt>
          <dd>{item.recommendation}</dd>
        </div>
        <div>
          <dt>Effort</dt>
          <dd>{item.estimated_effort || "medium"}</dd>
        </div>
      </dl>
      <div className="opp-actions">
        <button type="button" className="button small primary" disabled={busyId === item.id} onClick={() => onAction(item.id, { status: "approved", proposal_status: "selected" })}>
          Approve
        </button>
        <button type="button" className="button small" disabled={busyId === item.id} onClick={() => onAction(item.id, { proposal_status: "selected", status: "approved" })}>
          Add to proposal
        </button>
        <button type="button" className="button small" disabled={busyId === item.id} onClick={() => onAction(item.id, { status: "deferred", proposal_status: "not_in_proposal" })}>
          Defer
        </button>
        <button type="button" className="button small ghost" disabled={busyId === item.id} onClick={() => onAction(item.id, { status: "rejected", proposal_status: "not_in_proposal" })}>
          Reject
        </button>
      </div>
      <footer className="opp-foot">
        <span className="panel-meta">Status: {item.status}</span>
        <span className="panel-meta">Score {item.commercial_score ?? "—"}</span>
      </footer>
    </article>
  );
}

export default function OpportunitiesMode({
  opportunities,
  sell,
  loading,
  busy = {},
  onGenerate,
  onPatch,
  onAcceptSell,
  onBuildProposal,
  onOpenDiagnose,
  onOpenDesign,
}) {
  const items = opportunities || [];
  const busyId = busy.opportunityId;

  if (loading && !items.length) {
    return (
      <section className="panel brain-empty">
        <div className="brain-orb gold">
          <Icon name="trend" size={28} />
        </div>
        <h3>Building opportunities…</h3>
        <p>Clustering technical findings into business opportunities you can approve and sell.</p>
      </section>
    );
  }

  if (!items.length) {
    return (
      <section className="panel brain-empty">
        <div className="brain-orb">
          <Icon name="trend" size={28} />
        </div>
        <h3>No opportunities yet</h3>
        <p>After a crawl, Aurelia turns clustered evidence into commercial opportunities — not one proposal line per finding.</p>
        <div className="panel-actions" style={{ justifyContent: "center", marginTop: 12 }}>
          <button type="button" className="action-btn primary solo" onClick={onGenerate}>
            <Icon name="trend" size={15} />
            <span>Generate opportunities</span>
          </button>
          <button type="button" className="button" onClick={onOpenDiagnose}>
            Review audit
          </button>
        </div>
      </section>
    );
  }

  const high = items
    .filter((o) => (o.priority || "").toLowerCase() === "high" && !["rejected", "deferred"].includes(o.status))
    .sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9));
  const rest = items.filter((o) => !high.includes(o) && !["rejected"].includes(o.status));
  const deferred = items.filter((o) => o.status === "deferred" || o.status === "rejected");

  return (
    <div className="mode-body opportunities-mode">
      <SellCard
        sell={sell}
        busy={busy}
        onAccept={(pkg) => onAcceptSell(pkg)}
        onCustomize={() => onAcceptSell(sell?.recommended_package, true)}
        onBuildProposal={onBuildProposal}
        onOpenDesign={onOpenDesign}
      />

      <section className="panel">
        <div className="panel-head">
          <h3>
            <Icon name="trend" size={20} className="panel-icon blue" />
            High priority
          </h3>
          <button type="button" className="button small" onClick={onGenerate} disabled={busy.opportunities}>
            <Icon name="refresh" size={13} /> Regenerate
          </button>
        </div>
        {high.length ? (
          <div className="opp-grid">
            {high.map((item) => (
              <OpportunityCard key={item.id} item={item} busyId={busyId} onAction={onPatch} />
            ))}
          </div>
        ) : (
          <div className="empty-inline">No high-priority opportunities. Review the list below.</div>
        )}
      </section>

      {rest.length ? (
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="clipboard" size={20} className="panel-icon blue" />
              More opportunities
            </h3>
            <span className="panel-meta">{rest.length}</span>
          </div>
          <div className="opp-grid">
            {rest.map((item) => (
              <OpportunityCard key={item.id} item={item} busyId={busyId} onAction={onPatch} />
            ))}
          </div>
        </section>
      ) : null}

      {deferred.length ? (
        <section className="panel">
          <div className="panel-head">
            <h3>Deferred / rejected</h3>
            <span className="panel-meta">{deferred.length}</span>
          </div>
          <ul className="scope-list">
            {deferred.map((item) => (
              <li key={item.id}>
                <strong>{item.client_title || item.title}</strong>
                <span className="panel-meta">{item.status}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
