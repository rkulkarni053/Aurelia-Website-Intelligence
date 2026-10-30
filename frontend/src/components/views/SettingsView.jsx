import { useEffect, useState } from "react";
import { api } from "../../api";
import Icon from "../Icon";

function Row({ label, value, ok }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <strong className={ok == null ? "" : ok ? "text-good" : "text-high"}>{value}</strong>
    </div>
  );
}

export default function SettingsView({ brainStatus, onRecheck }) {
  const image = brainStatus?.image_generation || {};
  const [agency, setAgency] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState("");

  useEffect(() => {
    api("/api/agency/settings")
      .then(setAgency)
      .catch((err) => setError(err.message));
  }, []);

  const branding = agency?.branding || {};
  const packages = agency?.packages || {};
  const proposal = agency?.proposal || {};

  async function save() {
    if (!agency) return;
    setSaving(true);
    setError("");
    try {
      const data = await api("/api/agency/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(agency),
      });
      setAgency(data);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function patchBranding(key, value) {
    setAgency((prev) => ({
      ...prev,
      branding: { ...(prev?.branding || {}), [key]: value },
    }));
  }

  function patchProposal(key, value) {
    setAgency((prev) => ({
      ...prev,
      proposal: { ...(prev?.proposal || {}), [key]: value },
    }));
  }

  function patchPackage(key, field, value) {
    setAgency((prev) => {
      const pkgs = { ...(prev?.packages || {}) };
      const current = { ...(pkgs[key] || {}) };
      current[field] = field === "price" || field === "duration_days" ? Number(value) || 0 : value;
      pkgs[key] = current;
      return { ...prev, packages: pkgs };
    });
  }

  return (
    <div className="mode-body">
      <div className="view-head">
        <div>
          <h2>Settings</h2>
          <p>Agency branding, packages, and local AI services.</p>
        </div>
        <div className="panel-actions">
          <button type="button" className="action-btn solo" onClick={onRecheck}>
            <Icon name="refresh" size={15} />
            <span>Re-check AI</span>
          </button>
          <button type="button" className="action-btn primary solo" onClick={save} disabled={saving || !agency}>
            <Icon name="check" size={15} />
            <span>{saving ? "Saving…" : "Save agency"}</span>
          </button>
        </div>
      </div>
      {error ? <div className="muted-note text-high">{error}</div> : null}
      {savedAt ? <div className="muted-note">Saved at {savedAt}</div> : null}

      <div className="settings-grid agency-settings">
        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="brush" size={20} className="panel-icon blue" />
              Branding
            </h3>
          </div>
          <label className="field-label">
            Agency name
            <input value={branding.agency_name || ""} onChange={(e) => patchBranding("agency_name", e.target.value)} />
          </label>
          <label className="field-label">
            Tagline
            <input value={branding.tagline || ""} onChange={(e) => patchBranding("tagline", e.target.value)} />
          </label>
          <label className="field-label">
            Contact email
            <input value={branding.contact_email || ""} onChange={(e) => patchBranding("contact_email", e.target.value)} />
          </label>
          <label className="field-label">
            Website
            <input value={branding.website || ""} onChange={(e) => patchBranding("website", e.target.value)} />
          </label>
          <label className="field-label">
            Primary color
            <input value={branding.primary_color || ""} onChange={(e) => patchBranding("primary_color", e.target.value)} />
          </label>
          <label className="field-label">
            Secondary color
            <input value={branding.secondary_color || ""} onChange={(e) => patchBranding("secondary_color", e.target.value)} />
          </label>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="brain" size={20} className="panel-icon blue" />
              Agent methodology
            </h3>
            <span className="panel-meta">Trains Brain + chat voice</span>
          </div>
          <label className="field-label">
            How your agency works (injected into AI prompts)
            <textarea
              rows={6}
              value={agency?.methodology || ""}
              onChange={(e) => setAgency((prev) => ({ ...prev, methodology: e.target.value }))}
              placeholder="Turn website problems into priced projects…"
            />
          </label>
          <label className="field-label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={agency?.agent?.use_ollama_for_advisory !== false}
              onChange={(e) =>
                setAgency((prev) => ({
                  ...prev,
                  agent: { ...(prev?.agent || {}), use_ollama_for_advisory: e.target.checked },
                }))
              }
            />
            Use local Ollama for Site chat Q&amp;A (generative agent)
          </label>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="signature" size={20} className="panel-icon blue" />
              Proposal defaults
            </h3>
          </div>
          <label className="field-label">
            Payment terms
            <textarea rows={2} value={proposal.payment_terms || ""} onChange={(e) => patchProposal("payment_terms", e.target.value)} />
          </label>
          <label className="field-label">
            Terms
            <textarea rows={3} value={proposal.terms || ""} onChange={(e) => patchProposal("terms", e.target.value)} />
          </label>
          <label className="field-label">
            Disclaimer
            <textarea rows={2} value={proposal.disclaimer || ""} onChange={(e) => patchProposal("disclaimer", e.target.value)} />
          </label>
          <label className="field-label">
            Footer
            <input value={proposal.footer || ""} onChange={(e) => patchProposal("footer", e.target.value)} />
          </label>
        </section>

        <section className="panel span-2">
          <div className="panel-head">
            <h3>
              <Icon name="box" size={20} className="panel-icon blue" />
              Packages
            </h3>
            <span className="panel-meta">Prices shown in Proposal and Sell This</span>
          </div>
          <div className="package-edit-grid">
            {Object.entries(packages).map(([key, pkg]) => (
              <div key={key} className="package-edit">
                <strong>{key}</strong>
                <label className="field-label">
                  Name
                  <input value={pkg.name || ""} onChange={(e) => patchPackage(key, "name", e.target.value)} />
                </label>
                <label className="field-label">
                  Price
                  <input type="number" value={pkg.price ?? ""} onChange={(e) => patchPackage(key, "price", e.target.value)} />
                </label>
                <label className="field-label">
                  Duration (days)
                  <input type="number" value={pkg.duration_days ?? ""} onChange={(e) => patchPackage(key, "duration_days", e.target.value)} />
                </label>
                <label className="field-label">
                  Summary
                  <textarea rows={2} value={pkg.summary || ""} onChange={(e) => patchPackage(key, "summary", e.target.value)} />
                </label>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="brain" size={20} className="panel-icon blue" />
              Brain
            </h3>
            <span className={`chip-status ${brainStatus?.ok ? "completed" : "failed"}`}>
              <span className="status-dot" />
              {brainStatus == null ? "Checking…" : brainStatus.ok ? "Online" : "Offline"}
            </span>
          </div>
          <Row label="Provider" value={brainStatus?.provider || "ollama"} />
          <Row label="Configured model" value={brainStatus?.configured_model || "—"} />
          <Row label="Model ready" value={brainStatus?.model_ready ? "Yes" : "No"} ok={brainStatus ? Boolean(brainStatus.model_ready) : null} />
          <Row label="Local Ollama models" value={(brainStatus?.models || []).join(", ") || "—"} />
          <Row
            label="Anthropic"
            value={
              brainStatus?.anthropic?.billing === "no_credits"
                ? "Key set · no credits"
                : brainStatus?.anthropic?.configured
                  ? "Configured"
                  : "Not configured"
            }
            ok={
              brainStatus?.anthropic?.billing === "no_credits"
                ? false
                : brainStatus?.anthropic?.configured
                  ? true
                  : null
            }
          />
          {brainStatus?.error ? <div className="muted-note">{brainStatus.error}</div> : null}
          <p className="muted-note" style={{ marginTop: 10 }}>
            Company understanding comes from the crawl profile (instant, local). Optional LLM polish
            uses Ollama when a GPU is available, or Claude/GPT if you add credits and set{" "}
            <code>BRAIN_PROVIDER</code> in <code>.env</code>.
          </p>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>
              <Icon name="image" size={20} className="panel-icon gold" />
              Image generation
            </h3>
            <span className={`chip-status ${image.ok ? "completed" : "failed"}`}>
              <span className="status-dot" />
              {brainStatus == null ? "Checking…" : image.ok ? "Available" : "Unavailable"}
            </span>
          </div>
          <Row label="Engine" value={image.engine || "—"} />
          <Row label="Model" value={image.model_id || image.default_model || "—"} />
          <Row label="Backend setting" value={image.backend_setting || "—"} />
          {image.error ? <div className="muted-note">{image.error}</div> : null}
        </section>
      </div>
    </div>
  );
}
