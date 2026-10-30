import { formatDate } from "../../api";
import { crawlBadgeClass } from "../../lib/crawl";
import Icon from "../Icon";

export default function SitesView({ portfolio, activeWebsiteId, onNavigate, onOpenAdd }) {
  const rows = [];
  const groups = [
    ...(portfolio?.companies || []),
    { id: "", name: "Unassigned", projects: portfolio?.unassigned_projects || [] },
  ];
  for (const company of groups) {
    for (const project of company.projects || []) {
      for (const site of project.websites || []) {
        rows.push({ company, project, site, latest: site.crawls?.[0] || null });
      }
    }
  }

  return (
    <div className="mode-body">
      <div className="view-head">
        <div>
          <h2>Sites</h2>
          <p>{rows.length} website(s) across all projects.</p>
        </div>
        <button type="button" className="action-btn primary solo" onClick={onOpenAdd}>
          <Icon name="plus" size={15} />
          <span>Add website</span>
        </button>
      </div>

      <section className="panel">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Website</th>
                <th>Company</th>
                <th>Project</th>
                <th>Crawls</th>
                <th>Last crawl</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {!rows.length ? (
                <tr>
                  <td colSpan={6} className="table-empty">
                    No websites yet.
                  </td>
                </tr>
              ) : (
                rows.map(({ company, project, site, latest }) => {
                  const status = latest?.status || site.latest_crawl_status || "";
                  return (
                    <tr
                      key={site.id}
                      className={String(site.id) === String(activeWebsiteId) ? "current" : ""}
                      onClick={() =>
                        onNavigate({
                          companyId: company.id,
                          projectId: project.id,
                          websiteId: site.id,
                          crawlId: latest?.id || "",
                        })
                      }
                    >
                      <td>
                        <span className="cell-site">
                          <span className="site-dot">
                            <Icon name="globe" size={14} />
                          </span>
                          <span>
                            <strong>
                              {site.domain || site.url}
                              {site.role === "competitor" ? (
                                <span className="role-pill">competitor</span>
                              ) : null}
                            </strong>
                            <span className="muted-note">{site.url}</span>
                          </span>
                        </span>
                      </td>
                      <td>{company.name}</td>
                      <td>{project.name}</td>
                      <td>{site.crawl_count || 0}</td>
                      <td>{latest ? formatDate(latest.completed_at || latest.created_at) : "—"}</td>
                      <td>{status ? <span className={`badge ${crawlBadgeClass(status)}`}>{status}</span> : "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
