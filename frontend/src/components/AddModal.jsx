import { useEffect, useState } from "react";
import Icon from "./Icon";

export default function AddModal({
  open,
  onClose,
  companies = [],
  companyId = "",
  projectId = "",
  onSelectCompany,
  onAddCompany,
  onAddProject,
  onAddWebsite,
  onError,
}) {
  const [companyName, setCompanyName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [websiteRole, setWebsiteRole] = useState("primary");
  const [busy, setBusy] = useState("");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    if (!open) {
      setLocalError("");
      setBusy("");
    }
  }, [open]);

  if (!open) return null;

  const selectedCompany = companies.find((c) => String(c.id) === String(companyId));

  async function handle(kind, fn, reset) {
    setBusy(kind);
    setLocalError("");
    try {
      await fn();
      reset();
    } catch (err) {
      const message = err?.message || "Something went wrong.";
      setLocalError(message);
      onError?.(message);
    } finally {
      setBusy("");
    }
  }

  const steps = [
    {
      kind: "company",
      label: "Company",
      hint: selectedCompany
        ? `Selected: ${selectedCompany.name}`
        : "Create a client, or pick one below",
      id: "newCompanyName",
      value: companyName,
      setValue: setCompanyName,
      placeholder: "Acme Corp",
      button: "Add company",
      submit: () => onAddCompany(companyName.trim()),
      reset: () => setCompanyName(""),
    },
    {
      kind: "project",
      label: "Project",
      hint: selectedCompany
        ? `Adds under ${selectedCompany.name}`
        : "Adds as Unassigned (or pick/create a company first)",
      id: "newProjectName",
      value: projectName,
      setValue: setProjectName,
      placeholder: "Website redesign",
      button: "Add project",
      submit: () => onAddProject(projectName.trim()),
      reset: () => setProjectName(""),
    },
    {
      kind: "website",
      label: "Website URL",
      hint: projectId
        ? websiteRole === "competitor"
          ? "Added as a competitor on this project"
          : "Added as the primary client site"
        : "Create a project first",
      id: "newWebsiteUrl",
      type: "url",
      value: websiteUrl,
      setValue: setWebsiteUrl,
      placeholder: "https://client-site.com",
      button: "Add website",
      primary: true,
      submit: () => onAddWebsite(websiteUrl, websiteRole),
      reset: () => {
        setWebsiteUrl("");
        setWebsiteRole("primary");
      },
      role: true,
    },
  ];

  return (
    <div
      className="modal-backdrop open"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal">
        <div className="modal-head">
          <div>
            <h3>Add client work</h3>
            <p className="card-subtitle">Company → project → website URL</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="close" size={14} />
          </button>
        </div>

        {companies.length ? (
          <div className="onboard-company-pick">
            <label htmlFor="addModalCompany">
              Active company
              <span>Projects are attached to this company</span>
            </label>
            <select
              id="addModalCompany"
              value={companyId || ""}
              onChange={(e) => onSelectCompany?.(e.target.value)}
            >
              <option value="">Unassigned</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {localError ? (
          <div className="error" role="alert" style={{ margin: "0 0 12px" }}>
            <span>{localError}</span>
          </div>
        ) : null}

        <div className="onboard-grid">
          {steps.map((step, idx) => (
            <form
              key={step.kind}
              className="onboard-form"
              onSubmit={(e) => {
                e.preventDefault();
                handle(step.kind, step.submit, step.reset);
              }}
            >
              <span className="step-num">{idx + 1}</span>
              <div className="onboard-fields">
                <label htmlFor={step.id}>
                  {step.label}
                  <span>{step.hint}</span>
                </label>
                {step.role ? (
                  <div className="role-toggle">
                    <label>
                      <input
                        type="radio"
                        name="websiteRole"
                        checked={websiteRole === "primary"}
                        onChange={() => setWebsiteRole("primary")}
                      />
                      Primary client
                    </label>
                    <label>
                      <input
                        type="radio"
                        name="websiteRole"
                        checked={websiteRole === "competitor"}
                        onChange={() => setWebsiteRole("competitor")}
                      />
                      Competitor
                    </label>
                  </div>
                ) : null}
                <div className="inline-form">
                  <input
                    id={step.id}
                    type={step.type || "text"}
                    value={step.value}
                    onChange={(e) => step.setValue(e.target.value)}
                    placeholder={step.placeholder}
                    required
                  />
                  <button
                    type="submit"
                    className={`button${step.primary ? " primary" : ""}`}
                    disabled={busy === step.kind}
                  >
                    {busy === step.kind ? "Adding…" : step.button}
                  </button>
                </div>
              </div>
            </form>
          ))}
        </div>

        <div className="modal-actions">
          <button type="button" className="button" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
