import { useEffect, useMemo, useState } from "react";
import { formatDate } from "../../api";
import { BRAND } from "../../lib/brand";
import { renderMarkdown } from "../../lib/markdown";
import Icon from "../Icon";

function money(amount, currency = "EUR") {
  if (amount == null || amount === "") return "—";
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  if ((currency || "EUR").toUpperCase() === "EUR") {
    return `€${n.toLocaleString("en-IE", { maximumFractionDigits: 0 })}`;
  }
  return `${currency} ${n.toLocaleString()}`;
}

function ProposalEmpty({ loading, onGenerate }) {
  return (
    <section className="panel brain-empty">
      <div className="brain-orb gold">
        <Icon name="signature" size={28} />
      </div>
      <h3>{loading ? "Drafting proposal…" : "No proposal yet"}</h3>
      <p>
        {loading
          ? "Combining scores, findings, brain recommendations, and mockups into a client-ready document."
          : "Generate a proposal after asking the brain. Packages are scoped from audit findings."}
      </p>
      {loading ? (
        <div className="skeleton-stack">
          <span className="skeleton line" />
          <span className="skeleton line" />
          <span className="skeleton line short" />
        </div>
      ) : (
        <button type="button" className="action-btn primary solo" onClick={onGenerate}>
          <Icon name="signature" size={15} />
          <span>Generate Proposal</span>
        </button>
      )}
    </section>
  );
}

export default function ProposalMode({
  proposal,
  domain,
  crawlId,
  loading,
  busy = {},
  onGenerate,
  onExportPdf,
  onSave,
}) {
  const [editing, setEditing] = useState(false);
  const [executive, setExecutive] = useState("");
  const [opportunity, setOpportunity] = useState("");
  const [closing, setClosing] = useState("");
  const [pkg, setPkg] = useState("growth");
  const [markdownEdit, setMarkdownEdit] = useState("");

  useEffect(() => {
    if (!proposal) return;
    setExecutive(proposal.narratives?.executive_summary || "");
    setOpportunity(proposal.narratives?.opportunity || "");
    setClosing(proposal.narratives?.closing || "");
    setPkg(proposal.recommended_package || "growth");
    setMarkdownEdit(proposal.markdown || "");
  }, [proposal]);

  const body = useMemo(() => renderMarkdown(proposal?.markdown || ""), [proposal?.markdown]);

  if (loading || !proposal) return <ProposalEmpty loading={loading} onGenerate={onGenerate} />;

  const fileUrl = (file) => `/data/websites/${domain}/crawls/${crawlId}/${file}`;
  const packages = proposal.packages || {};
  const currency = proposal.config_snapshot?.currency || "EUR";
  const recKey = proposal.recommended_package;
  const recPkg = (recKey && packages[recKey]) || {};
  const sell = proposal.sell_recommendation || {};
  const facts = [
    ["Client", domain || "—"],
    ["Prepared by", proposal.company_name || BRAND.name],
    ["Package", recPkg.name || (recKey ? recKey.replace(/^\w/, (c) => c.toUpperCase()) : "—")],
    ["Investment", money(recPkg.price ?? sell.price, currency)],
    ["Generated", proposal.generated_at ? formatDate(proposal.generated_at) : "—"],
  ];

  async function handleSave() {
    if (!onSave) return;
    await onSave({
      narratives: {
        executive_summary: executive,
        opportunity,
        closing,
      },
      recommended_package: pkg,
      markdown: editing && markdownEdit !== proposal.markdown ? markdownEdit : undefined,
    });
    setEditing(false);
  }

  return (
    <div className="mode-body">
      <div className="proposal-layout">
        <article className="paper">
          <header className="paper-head">
            <span className="paper-logo">{BRAND.short}</span>
            <div>
              <span className="eyebrow">Website proposal</span>
              <strong>{domain}</strong>
            </div>
          </header>
          {editing ? (
            <textarea
              className="proposal-md-edit"
              value={markdownEdit}
              onChange={(e) => setMarkdownEdit(e.target.value)}
              rows={28}
            />
          ) : (
            <div className="markdown">{body.length ? body : <p>Proposal body is empty.</p>}</div>
          )}
        </article>

        <aside className="stack proposal-side">
          <section className="panel">
            <div className="panel-head">
              <h3>
                <Icon name="file" size={18} className="panel-icon blue" />
                Summary
              </h3>
            </div>
            <dl className="fact-list">
              {facts.map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            {proposal.error ? (
              <p className="fallback-note">
                <Icon name="warning" size={13} />
                Template fallback used: {proposal.error}
              </p>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h3>
                <Icon name="brush" size={18} className="panel-icon blue" />
                Edit before send
              </h3>
            </div>
            <label className="field-label">
              Recommended package
              <select value={pkg} onChange={(e) => setPkg(e.target.value)}>
                {Object.keys(packages).length
                  ? Object.entries(packages).map(([key, p]) => (
                      <option key={key} value={key}>
                        {p.name || key} — {money(p.price, currency)}
                      </option>
                    ))
                  : ["essentials", "growth", "redesign"].map((key) => (
                      <option key={key} value={key}>
                        {key}
                      </option>
                    ))}
              </select>
            </label>
            {(sell.why || sell.reasons || []).length ? (
              <div className="sell-why compact">
                <h4 className="sub-head">Why this price</h4>
                <ul className="rec-list check">
                  {(sell.why || sell.reasons).slice(0, 6).map((line) => (
                    <li key={line}>
                      <Icon name="check" size={12} />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <label className="field-label">
              Executive summary
              <textarea value={executive} onChange={(e) => setExecutive(e.target.value)} rows={4} />
            </label>
            <label className="field-label">
              Opportunity
              <textarea value={opportunity} onChange={(e) => setOpportunity(e.target.value)} rows={3} />
            </label>
            <label className="field-label">
              Closing
              <textarea value={closing} onChange={(e) => setClosing(e.target.value)} rows={3} />
            </label>
            <div className="deliver-list">
              <button
                type="button"
                className="button primary block"
                onClick={handleSave}
                disabled={busy.proposalSave}
              >
                <Icon name="check" size={14} />
                {busy.proposalSave ? "Saving…" : "Save edits"}
              </button>
              <button type="button" className="button block" onClick={() => setEditing((v) => !v)}>
                <Icon name="file" size={14} />
                {editing ? "Preview markdown" : "Edit raw markdown"}
              </button>
            </div>
          </section>

          {Object.keys(packages).length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>
                  <Icon name="box" size={18} className="panel-icon blue" />
                  Scoped packages
                </h3>
              </div>
              <ul className="scope-list package-prices">
                {Object.entries(packages).map(([key, p]) => (
                  <li key={key} className={key === proposal.recommended_package ? "recommended" : ""}>
                    <strong>
                      {p.name || key}
                      {key === proposal.recommended_package ? " ★" : ""}
                    </strong>
                    <span className="pkg-price">{money(p.price, currency)}</span>
                    <span className="panel-meta">
                      {(p.includes || []).length} deliverables
                      {p.duration_days ? ` · ~${p.duration_days} days` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="panel">
            <div className="panel-head">
              <h3>
                <Icon name="download" size={18} className="panel-icon blue" />
                Deliver
              </h3>
            </div>
            <div className="deliver-list">
              <button type="button" className="button primary block" onClick={onExportPdf} disabled={busy.pdf}>
                <Icon name="download" size={14} />
                {busy.pdf ? "Exporting…" : proposal.pdf_file ? "Re-export PDF" : "Export PDF"}
              </button>
              {proposal.pdf_file && domain ? (
                <a className="button block" href={fileUrl(proposal.pdf_file)} target="_blank" rel="noopener noreferrer">
                  <Icon name="external" size={14} /> Open PDF
                </a>
              ) : null}
              {proposal.markdown_file && domain ? (
                <a className="button block" href={fileUrl(proposal.markdown_file)} target="_blank" rel="noopener noreferrer">
                  <Icon name="file" size={14} /> Open Markdown
                </a>
              ) : null}
              <button type="button" className="button block" onClick={onGenerate} disabled={busy.proposal}>
                <Icon name="refresh" size={14} /> Regenerate
              </button>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
