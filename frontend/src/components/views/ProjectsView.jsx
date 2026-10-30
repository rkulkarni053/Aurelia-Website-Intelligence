import { crawlBadgeClass } from "../../lib/crawl";
import Icon from "../Icon";

export default function ProjectsView({
  portfolio,
  activeProjectId,
  onNavigate,
  onRename,
  onDelete,
  onOpenAdd,
}) {
  const companies = [
    ...(portfolio?.companies || []),
    ...((portfolio?.unassigned_projects || []).length
      ? [{ id: "", name: "Unassigned", projects: portfolio.unassigned_projects, virtual: true }]
      : []),
  ];

  return (
    <div className="mode-body">
      <div className="view-head">
        <div>
          <h2>Projects</h2>
          <p>Every company and project in your workspace.</p>
        </div>
        <button type="button" className="action-btn primary solo" onClick={onOpenAdd}>
          <Icon name="plus" size={15} />
          <span>New</span>
        </button>
      </div>

      {!companies.length ? (
        <div className="panel empty-panel">Nothing here yet. Use New to add a company.</div>
      ) : (
        companies.map((company) => (
          <section className="panel company-panel" key={company.id || "unassigned"}>
            <div className="company-head">
              <span className="company-avatar">{(company.name || "?").slice(0, 1).toUpperCase()}</span>
              <div className="company-text">
                <h3>{company.name}</h3>
                <span>{(company.projects || []).length} project(s)</span>
              </div>
              {!company.virtual ? (
                <div className="row-actions">
                  <button type="button" className="icon-btn" title="Rename company" onClick={() => onRename("company", company.id, company.name)}>
                    <Icon name="edit" size={14} />
                  </button>
                  <button type="button" className="icon-btn danger" title="Delete company" onClick={() => onDelete("company", company.id, company.name)}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              ) : null}
            </div>

            <div className="project-grid">
              {!(company.projects || []).length ? (
                <div className="muted-note">No projects yet</div>
              ) : (
                company.projects.map((project) => (
                  <div
                    className={`project-card${String(project.id) === String(activeProjectId) ? " active" : ""}`}
                    key={project.id}
                  >
                    <div className="project-card-head">
                      <button
                        type="button"
                        className="project-open"
                        onClick={() => onNavigate({ companyId: company.id, projectId: project.id })}
                      >
                        <span className="project-icon">
                          <Icon name="folder" size={16} />
                        </span>
                        <span>
                          <strong>{project.name}</strong>
                          <span className="muted-note">{project.website_count || 0} site(s)</span>
                        </span>
                      </button>
                      <div className="row-actions">
                        <button type="button" className="icon-btn" title="Rename project" onClick={() => onRename("project", project.id, project.name)}>
                          <Icon name="edit" size={14} />
                        </button>
                        <button type="button" className="icon-btn danger" title="Delete project" onClick={() => onDelete("project", project.id, project.name)}>
                          <Icon name="trash" size={14} />
                        </button>
                      </div>
                    </div>
                    <div className="project-sites">
                      {!(project.websites || []).length ? (
                        <span className="muted-note">No websites yet</span>
                      ) : (
                        project.websites.map((site) => {
                          const latest = site.crawls?.[0];
                          const status = latest?.status || site.latest_crawl_status || "";
                          return (
                            <button
                              type="button"
                              key={site.id}
                              className="site-chip"
                              onClick={() =>
                                onNavigate({
                                  companyId: company.id,
                                  projectId: project.id,
                                  websiteId: site.id,
                                  crawlId: latest?.id || "",
                                })
                              }
                            >
                              <Icon name="globe" size={13} />
                              <span>{site.domain || site.url}</span>
                              {status ? <span className={`badge ${crawlBadgeClass(status)}`}>{status}</span> : null}
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
